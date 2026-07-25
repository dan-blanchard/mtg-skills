"""Crosswalk signal lanes — card advantage: impulse, draw engines, cantrips,
topdeck selection/stack, exile matters, and facedown matters (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    additional_phase_kind,
    amount_factor,
    amount_is_scaling,
    change_zone_dirs,
    count_operand_filter,
    counter_kind_any,
    effect_filter,
    effect_owner_player_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_subtypes,
    has_fixed_count,
    is_dies_return_trigger,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_typed_nodes,
    mod_keyword_name,
    modal_mode_description,
    permission_tag,
    recipient_tag,
    reveal_until_player,
    static_mode_tag,
    tag_of,
    trigger_scope,
    trigger_subject,
    trigger_subject_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _TOPDECK_OTHER_ZONE,
    _TOPDECK_YOUR_LIBRARY,
    _topdeck_stack_self,
)
from mtg_utils._card_ir.tree_synthesis import (
    _EACH_DRAW_RECIPIENTS,
    SynthesizedNode,
    _is_self_return_effect,
    _is_shuffle_back_effect,
)
from mtg_utils._deck_forge._sweep_detectors import TOPDECK_STACK_SWEEP_REGEX
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _GRANT_ABILITY_MOD_TAGS,
    _OPP_TOP_OWNERS,
    _PT_COUNTER_KINDS,
    _REMINDER_RX,
    _condition_leaves,
    _discard_watch_is_opponent,
    _target_owner_beneficiary_scope,
)
from mtg_utils._deck_forge.signal_base import (
    Signal,
    _clauses,
)


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

    task #95 adds the ``synth_impulse_top_play`` bucket-B marker check
    (see :func:`~mtg_utils._card_ir.tree_synthesis.
    _arm_known_token_impulse_top_play`'s own docstring) — the Junk
    predefined-token cycle's "Exile the top card of your library. You may
    play that card this turn" ability rides a zero-unit text-only tree
    with no exile_top/cast_from_zone pair to walk structurally.
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
    for c in tree.iter_concepts():
        if c.concept == "synth_impulse_top_play":
            return [Signal("impulse_top_play", "you", "", "", tree.name, "high")]
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


# ``_EACH_DRAW_RECIPIENTS`` (the group_hug_draw direction — ``ScopedPlayer``
# deliberately ABSENT, Howling Mine's each-player Phase trigger routes to
# card_draw_engine / target_player_draws instead) moved to tree_synthesis.py
# so :func:`has_structural_group_hug_draw` and this lane share ONE source
# (imported above).
# Draw recipients naming a DIRECTED single player (CR 121.1) — the
# target_player_draws forced-draw direction (Bloodgift Demon's ``Player``).
# ADR-0038 W3 batch 6 (draw-etb-tokens cluster) widened three tags, all
# corpus-verified DIRECTED-at-one-player shapes (never a group/"each
# player" distribution, which stays routed to group_hug_draw per the
# ScopedPlayer exclusion below): ``Typed`` — a player FILTER recipient
# whose controller names ``Opponent`` (Lord of Tresserhorn, Communal
# Brewing, Sphinx of Enlightenment's "target opponent draws" — phase
# models "target/each opponent" as a Typed player filter, not a bare
# ``Target``/``Player`` tag); ``ParentTargetController`` — the controller
# of a PREVIOUSLY TARGETED object draws (Call to Heel's "Its controller
# draws a card" off a bounced creature, Gwafa Hazid's stolen-creature
# controller, Acolyte Hybrid's destroyed-artifact controller — CR
# 121.1/608.2h, the object-chain analog of a direct player target);
# ``TriggeringPlayer`` — the SPECIFIC player who performed the watched
# action draws (Curse of Chaos's attacking player), a single determined
# player exactly like a direct target, not a distributed group. Corpus-
# verified: ``OriginalController`` is DELIBERATELY absent — every corpus
# instance is the "you AND target opponent EACH draw" idiom's OWN-caster
# half (Secret Rendezvous's SECOND Draw node — "you" back-referenced as
# the spell's original controller, not a directed target at all; the
# SIBLING ``Typed(Opponent)`` Draw is what actually fires). ADR-0038 W5
# tails: ``Any`` admitted unconditionally too — the "you and X each draw"
# multi-recipient idiom's COLLAPSED single-node form (Karazikar, the Eye
# Tyrant's "you and the attacking player each draw", Zurzoth's "you and
# those players", Nelly Borca's "you and the controller of those
# creatures", Cait's "you and defending player", Splinter's "you and
# another target player") — phase folds the whole multi-player set into
# ONE ``Draw`` node tagged ``Any`` rather than the paired OriginalController
# / ScopedPlayer shape below. Corpus-verified exhaustively (the ONLY tag
# used for a ``Draw`` node's recipient, whole commander-legal corpus): 6
# hits, all this same directed multi-recipient idiom, 0 exceptions — no
# phrase gate needed (several of the 6 don't even contain the phrase
# gate's word list — "the attacking player"/"those players"/"defending
# player" — so gating would UNDER-fire the very class it exists to admit).
# CR 121.1. ``ParentTargetOwner`` (the OWNER, not controller, of a
# previously targeted object — CR 108.3) joined this UNCONDITIONAL set in
# task #93: a full commander-legal corpus census of every
# ``ParentTargetOwner``-tagged Draw node (32,521 cards scanned) turns up
# EXACTLY 4 hits, whole population, 0 exceptions — Oft-Nabbed Goat ("its
# owner draws that many cards"), Apple of Eden // Isu Relic ("its owner
# draws a card"), Oblation and Deadly Cover-Up ("The owner of target
# nonland permanent shuffles it into their library, then draws two
# cards." / "That player shuffles, then draws a card for each card
# exiled..."). All 4 are the SAME genuine same-unit "target X's owner
# gets the draw" idiom (no bled-from-elsewhere false positive anywhere in
# the tag's population), so unlike the phrase-gated tags below there is
# no bleed risk to guard against — moving it here also fixes the
# previously-deferred comma-gap miss on Oblation/Deadly Cover-Up (task
# #91 finding): their draw sits in a "..., then draws ..." clause with a
# comma between the owner reference and the verb that
# :data:`_TARGET_PLAYER_DRAW_PHRASE_RE`'s ``[^.,;]*?`` can't cross, so the
# phrase gate previously always missed them regardless of wording.
_TARGETED_DRAW_TAGS: frozenset[str] = frozenset(
    {"Player", "ParentTarget", "Target", "Any", "ParentTargetOwner"}
)
# ADR-0038 W3 batch 6 — the THREE widened tags above (``Typed``,
# ``ParentTargetController``, ``TriggeringPlayer``) are NOT unconditional
# like the original ones: a phase templating quirk bleeds a PRECEDING
# clause's "target X. Its controller may Y." recipient onto a FOLLOWING,
# textually-unattributed "Draw a card." sentence that per CR 608.2h
# actually defaults to the caster (Price of Freedom, Cleansing Wildfire,
# Geomancer's Gambit all structurally tag their trailing "Draw a card."
# ``ParentTargetController`` even though the SENTENCE never says
# "controller"). These three need the draw's OWN clause to explicitly
# name a player reference, gated by :data:`_TARGET_PLAYER_DRAW_PHRASE_RE`
# below (Call to Heel's "Its controller draws a card." — SAME clause —
# still fires correctly; the bled cards' bare "Draw a card." clause has no
# such wording and correctly stays out).
# ADR-0038 W5 tails: one more widened tag, SAME phrase-gate treatment —
# ``TriggeringSourceController`` (the controller of the trigger's SOURCE
# permanent — Norn's Decree's "the attacking player draws a card", the
# object-chain analog of ``TriggeringPlayer``'s direct-player read).
_TARGETED_DRAW_WIDENED_TAGS: frozenset[str] = frozenset(
    {
        "Typed",
        "ParentTargetController",
        "TriggeringPlayer",
        "TriggeringSourceController",
    }
)
# ADR-0038 W5 tails: two more alternatives. A ``\w+'s (?:controller|owner)``
# alternative admits the OBJECT-possessive phrasing the original
# ``(?:its|their|that|the) controller`` word list missed — "That creature's
# controller draws X cards" (Nin, the Pain Artist; Nessian Boar's "that
# creature's controller draws a card"), "That spell's controller may draw a
# card" (Vex) — the SAME same-clause-attribution semantic (CR 121.1/608.2h),
# just with the possessed noun spelled out instead of elided to a bare
# pronoun. A bare ``(?:an|each) opponent`` alternative (no "target" prefix
# required) admits Baleful Mastery's "an opponent draws a card" (a
# ``ChosenPlayer``-controller ``Typed`` node — a genuine player filter, unlike
# Herigast, Erupting Nullkite's card-property ``Typed`` node reusing the same
# tag for an unrelated hand-size reference, which the phrase gate correctly
# keeps excluded since its clause names no opponent at all). A
# ``that (?:\w+ )?player``/``the (?:\w+ )?player`` alternative admits a
# PARTICIPLE-modified back-reference — Breena, the Demagogue's "that
# attacking player draws a card", Norn's Decree's "the attacking player
# draws a card" (``TriggeringSourceController``) — the bare "that
# player"/"the player" word list missed the adjective in between. A
# standalone ``choose ... player ... draws`` alternative admits a
# SEQUENTIAL-choice recipient (Gluntch, the Bestower's "Choose a second
# player to draw a card." — a ``ChosenPlayer``-controller ``Typed`` node,
# the SAME structural shape as Baleful Mastery's "an opponent draws" but
# phrased as an explicit choice instead of an opponent filter); corpus-
# verified as the ONLY ``Typed``-tag draw whose clause contains this
# "choose ... player ... draws" shape.
_TARGET_PLAYER_DRAW_PHRASE_RE = re.compile(
    r"\b(?:target (?:player|opponent)s?|(?:an|each) opponents?"
    r"|(?:its|their|that|the) (?:controller|owner)s?"
    r"|\w+'s (?:controller|owner)s?|(?:that|the) (?:\w+ )?player|they)\b"
    r"[^.,;]*?\bdraws?\b"
    r"|\bdraws?\b[^.,;]*?\b(?:target (?:player|opponent)s?|(?:an|each) opponents?"
    r"|(?:its|their|that|the) (?:controller|owner)s?|\w+'s (?:controller|owner)s?"
    r"|(?:that|the) (?:\w+ )?player|they)\b"
    r"|\bchoose\b[^.,;]*?\bplayer\b[^.,;]*?\bdraws?\b",
    re.IGNORECASE,
)
# Combat-frame trigger events (CR 508 / 509.3a) — the combat_buff_engine
# anchor. ``deals_damage`` is DELIBERATELY absent so Renown / the separate
# self_counter_grow shapes don't over-fire (mirrors the live exclusion).
_COMBAT_BUFF_EVENTS: frozenset[str] = frozenset(
    {"attacks", "blocks", "becomes_blocked"}
)
# Land-to-graveyard payoff trigger events (CR 701.21a / 603.6c).
_LAND_SAC_EVENTS: frozenset[str] = frozenset({"dies", "leaves", "sacrificed"})


def _discard_matters(tree: ConceptTree) -> list[Signal]:
    """discard_matters — the SELF/any-scope discard PAYOFF (CR 702.29a:
    cycling IS "[Cost], Discard this card: Draw a card", so a cycle is a
    discard — phase's ``CycledOrDiscarded`` joins ``Discarded`` /
    ``DiscardedAll`` under the derived ``discarded`` event): "whenever you
    cycle or discard a card, …" (Archfiend of Ifnir). DISJOINT from the
    opponent-watching punisher (Megrim → the ``opponent_discard`` trigger
    arm) by the same watcher read. A loot OUTLET (Careful Study) has no
    discarded trigger — it stays discard_makers. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event != "discarded":
            continue
        if not _discard_watch_is_opponent(unit):
            return [Signal("discard_matters", "you", "", "", tree.name, "high")]
    return []


def _opponent_draw_matters(tree: ConceptTree) -> list[Signal]:
    """opponent_draw_matters — the wheel-punisher payoff (CR 121.1):
    "whenever an opponent draws a card, …" (Nekusar, Underworld Dreams). The
    complementary scope gate to the ported ``draw_matters`` (you/any-scope
    drawn watcher — Niv-Mizzet) — the two stay set-disjoint. Scope
    "opponents".
    """
    for unit in tree.units:
        if unit.trigger_event == "drawn" and trigger_scope(unit.node) == "opponents":
            return [
                Signal("opponent_draw_matters", "opponents", "", "", tree.name, "high")
            ]
    return []


def _self_death_payoff(tree: ConceptTree) -> list[Signal]:
    """self_death_payoff — own-death VALUE (CR 700.4 dies / 603.6c): "when
    this creature dies, <payoff>" (Solemn Simulacrum's draw, Kokusho's
    drain). Four gates mirror the live split: the ``SelfRef`` watcher
    excludes the aristocrats lane (``death_matters`` — a subject-bearing
    watcher, Blood Artist); the recognized-effect gate drops unparsed
    bodies; the SELF-RETURN exclusion keeps the undying/persist return
    (Kitchen Finks — ``ChangeZone`` back to the battlefield) in
    ``dies_recursion``, not here; and the SHUFFLE-BACK exclusion drops the
    "shuffle … into its owner's library" protection rider (Kozilek — a
    dies-to-Library move is self-preservation, not value). Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "dies":
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) != "SelfRef":
            continue
        for c in unit.effects:
            if (
                c.concept == OTHER
                or _is_self_return_effect(c)
                or _is_shuffle_back_effect(c)
            ):
                continue
            return [Signal("self_death_payoff", "you", "", c.raw, tree.name, "high")]
    return []


_DIES_RECURSION_GRANT_KEYWORDS: frozenset[str] = frozenset({"Persist", "Undying"})


def _dies_recursion(tree: ConceptTree) -> list[Signal]:
    """dies_recursion — SELF-recursion on death (CR 702.93a undying /
    702.79a persist: "when this permanent is put into a graveyard from the
    battlefield, … return it to the battlefield"). Fully structural, three
    arms sharing :func:`iter_mod_sites`' tree-preserving mod-site walk:

    * the card's OWN dies-return trigger — phase expands undying (Young
      Wolf) and persist (Kitchen Finks) to exactly this shape, so the
      keyword bearers read structurally (memory: mirror=backup — prefer the
      structural shape over a keyword field-lookup);
    * the GRANT form — a ``GrantTrigger`` modification whose granted trigger
      is that same dies-return shape (Feign Death);
    * (ADR-0038 W3 batch 2 unit 3) an ``AddKeyword`` modification granting
      ``Persist``/``Undying`` to ANY target, at ANY nesting depth
      (:func:`iter_typed_nodes`'s generic deep walk — not
      :func:`iter_mod_sites`'s curated one-hop walk, since a doubly-nested
      grant needs to reach INSIDE a granted trigger's own execute chain:
      Haunted One's "Commander creatures … have '… gain undying …'" nests
      the ``AddKeyword`` inside a ``GrantStaticAbility``'s granted
      ``GrantTrigger``'s pump sub-ability): self (Rattleblaze Scarecrow's
      conditional static, Endling's activated self-grant), another
      creature (Cauldron Haze, Antler Skulkin, Rhys the Evermore's ETB
      grant), or a typed filter (Mikaeus the Unhallowed's "other
      creatures … have undying", Haunted One) — the keyword ITSELF is CR
      702.93a/702.79a's dies-return ability, so granting it (to anyone) is
      dies-recursion tech regardless of the grant's own trigger/static/
      activated-ability shape. Mirrors the sibling ``has_undying_persist``
      membership lane's ``_B13_MOD_GRANT_LANES`` walk — proven safe over
      the corpus for these two keyword names.

    The destination gate (Battlefield) keeps a dies→hand return out; a
    GY→battlefield reanimate of OTHERS (Reanimate) has no SelfRef dies
    watcher and stays creature_recursion/reanimator. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and is_dies_return_trigger(unit.node):
            return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) == "GrantTrigger" and is_dies_return_trigger(
                getattr(mod, "trigger", None)
            ):
                return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) == "AddKeyword"
                and mod_keyword_name(n) in _DIES_RECURSION_GRANT_KEYWORDS
            ):
                return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
    if _has_exile_then_return_replacement(tree):
        return [Signal("dies_recursion", "you", "", "", tree.name, "high")]
    return []


def _has_exile_then_return_replacement(tree: ConceptTree) -> bool:
    """Darigaaz Reincarnated's phoenix-analog (CR 614.1/700.4): "If ~ would
    die, instead exile it with three egg counters on it" (a REPLACEMENT
    redirect, not a dies TRIGGER — so :func:`is_dies_return_trigger` never
    reaches it) + a SEPARATE later counter-driven upkeep trigger that
    eventually returns it to the battlefield once the counters are gone.
    Corpus-narrow (grepped 2026-07: exactly 2 commander-legal cards carry
    "egg counter" — Xira, the Golden Sting does not pair a self-exile
    replacement with a self-return, so this predicate is a clean singleton
    match, not a broad idiom)."""
    has_exile_redirect = False
    has_delayed_return = False
    for unit in tree.units:
        if unit.origin == "replacement" and (
            tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef"
        ):
            for c in unit.effects:
                if tag_of(c.node) == "ChangeZone" and (
                    getattr(c.node, "destination", None) == "Exile"
                    and getattr(c.node, "enter_with_counters", None)
                ):
                    has_exile_redirect = True
        for c in unit.effects:
            # ParentTarget accepted HERE (unlike the dies-trigger predicate's
            # producer-tracked read): Darigaaz's counter-driven upkeep return
            # ("return it to the battlefield") binds ParentTarget to its own
            # trigger's source, and this arm is already gated on the
            # co-occurring self-exile replacement — corpus-singleton, so the
            # wider target set cannot over-fire.
            if tag_of(c.node) == "ChangeZone" and (
                getattr(c.node, "destination", None) == "Battlefield"
                and tag_of(getattr(c.node, "target", None))
                in ("SelfRef", "TriggeringSource", "ParentTarget")
            ):
                has_delayed_return = True
    return has_exile_redirect and has_delayed_return


def _creature_recursion(tree: ConceptTree) -> list[Signal]:
    """creature_recursion — loop-a-creature (CR 700.4 / 401.4 / 404). Two
    typed arms mirroring the live structural pair:

    * **reanimation** — a ``ChangeZone`` / ``ChangeZoneAll`` Graveyard→
      Battlefield over a Creature-cored filter (Alesha's attack trigger;
      Reanimate — scope stays "you" even over an opponent's graveyard: you
      control the returned creature);
    * **recall** — a ``ChangeZone`` / ``ChangeZoneAll`` Graveyard→Hand or
      Graveyard→Library (Soul Salvage, Aether Helix's recall half — phase
      v0.23.0 migrated the GY-recall family from a zone-predicated
      ``Bounce`` to a full ``ChangeZone`` carrying its origin directly:
      698 GY→Hand + 22 GY→Library carriers at the task #84 census), OR the
      LEGACY shape — a ``Bounce`` (→hand) / ``PutAtLibraryPosition``
      (→library) whose subject carries the ``InZone: Graveyard`` predicate
      (retained: the 5-card Advocate cycle still parses that way at
      v0.23.0); the graveyard origin/predicate is required either way (a
      battlefield bounce is tempo, not recursion).

    Gate #6: subject controller ≠ Opponent (an opponents'-graveyard-ONLY
    pull is graveyard hate, not your loop). A type-less "target card"
    (Regrowth) has no Creature core — no fire. Scope "you".

    KNOWN upstream residue (task #84 census, 1 of 228 recall carriers):
    Aether Burst — "Return up to X target creatures to their owners'
    hands, where X is ... cards named Aether Burst in all graveyards" is a
    BATTLEFIELD bounce whose graveyards-COUNT clause phase mis-stamps as
    ``origin: Graveyard`` on the ChangeZone, so this lane over-fires it.
    Left as-is deliberately: the structure is upstream-wrong (a phase-rs
    report candidate — Dan posts), and a text veto here would re-grep the
    oracle against the substrate contract for one card.

    task #86/#87 Aura cross-reference: a reanimation-Aura's OWN reattach
    trigger (Animate Dead — "Return enchanted creature card to the
    battlefield under your control and attach ~ to it") carries NO type
    filter of its own once the ``ChangeZone``'s target is ``AttachedTo()``
    — CR 303.4f: the enchanted permanent, whatever it is. The Creature
    constraint lives entirely on the card's OWN printed ``Enchant``
    keyword ("enchant creature card in a graveyard"), a SEPARATE root-level
    fact this filter read never crossed until now. When ``filter_core_
    types`` comes back empty AND the target is specifically ``AttachedTo``
    (never for an ordinary explicit-target reanimation — Reanimate's own
    filter already carries "Creature" directly), fall back to the card's
    own :attr:`ConceptTree.card_enchant_core_types`. Necromancy's
    equivalent clause stays Unimplemented upstream (its whole "become an
    Aura... put target creature card... onto the battlefield" body is one
    ``GrantAbility.definition`` with an ``Unimplemented("enchant")``
    payload — no ``ChangeZone`` node survives at all), so it correctly
    gains nothing here; corpus-swept 2026-07 for every OTHER ``AttachedTo``
    reanimation carrier (Dance of the Dead is the only sibling).
    """
    for unit in tree.units:
        for c in unit.effects:
            t = tag_of(c.node)
            sub = effect_filter(c.node)
            if filter_controller(sub) == "Opponent":
                continue
            types = filter_core_types(sub)
            if (
                not types
                and t in ("ChangeZone", "ChangeZoneAll")
                and tag_of(sub) == "AttachedTo"
            ):
                types = tree.card_enchant_core_types
            if "Creature" not in types:
                continue
            if t in ("ChangeZone", "ChangeZoneAll"):
                origin, dest = change_zone_dirs(c.node)
                if origin == "Graveyard" and dest in ("Battlefield", "Hand", "Library"):
                    return [
                        Signal(
                            "creature_recursion", "you", "", c.raw, tree.name, "high"
                        )
                    ]
            if t in ("Bounce", "PutAtLibraryPosition") and (
                "Graveyard" in filter_inzone_zones(sub)
            ):
                return [
                    Signal("creature_recursion", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _draw_engine_scope(unit: AbilityUnit, c: ConceptNode) -> str:
    """The card_draw_engine scope: "each" when the draw reaches every player
    (an each-player Phase trigger's ``ScopedPlayer`` — Howling Mine; an
    explicit each-player recipient; a ``player_scope: All`` wrapper — Temple
    Bell); task #91 — "any"/"opponents" when the recipient is the OWNER of
    an earlier-targeted permanent (:func:`_target_owner_beneficiary_scope` —
    Oblation's "The owner of target nonland permanent...then draws two
    cards": the target is unconstrained, so the drawer could be YOU or an
    opponent, 'any'; Deadly Cover-Up's search-and-exile chain constrains the
    root target to ``Owned: Opponent``, so the drawer is ALWAYS an opponent,
    'opponents' — CR 108.3); else "you"."""
    if recipient_tag(c.node) == "ScopedPlayer":
        return "each"
    if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS:
        return "each"
    if effect_owner_player_scope(unit.node, c.node) == "All":
        return "each"
    if recipient_tag(c.node) == "ParentTargetOwner":
        override = _target_owner_beneficiary_scope(unit)
        if override is not None:
            return override
    return "you"


def _card_draw_engine(tree: ConceptTree) -> list[Signal]:
    """card_draw_engine — recurring / BULK card advantage, NOT a cantrip (CR
    121.1 / 121.2). The live path is a byte-identical kept mirror whose "no
    clean structural shape" justification is STALE for the lossless
    substrate: the tree preserves the Phase-mode trigger unit CONTAINING the
    Draw (granularity a — the anchor and the Draw share a unit). Three
    typed arms:

    * a ``Draw`` whose typed ``count`` is ≥2 or dynamic ("draw three cards"
      — Divination; "draw cards equal to …"), excluding a one-shot ETB unit
      (Elvish Visionary's enters-draw never fires, mirroring the live
      mirror's ETB skip) — a bare cantrip (Opt, count 1) never fires;
    * ANY ``Draw`` inside a ``Phase``-mode trigger unit ("at the beginning
      of …, draw" — Phyrexian Arena; Howling Mine's each-player draw step →
      scope "each" via the ``ScopedPlayer`` recipient);
    * a Draw-REPLACEMENT unit ("if you would draw a card, … draw two cards
      instead" — Alhammarret's Archive; the replacement's ``event`` field is
      the typed anchor).

    Expected shadow posture: recall gains over the mirror are the desired
    structural improvement — adjudicated via the harness, not drift.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for unit in tree.units:
        is_phase = unit.trigger_event == "phase"
        is_draw_repl = (
            unit.origin == "replacement" and getattr(unit.node, "event", None) == "Draw"
        )
        for c in unit.effect_concepts("draw"):
            bulk = amount_factor(c.node, "count") >= 2 or amount_is_scaling(
                c.node, "count"
            )
            if not (
                is_phase or is_draw_repl or (bulk and unit.trigger_event != "enters")
            ):
                continue
            scope = _draw_engine_scope(unit, c)
            if scope not in seen:
                seen.add(scope)
                out.append(
                    Signal("card_draw_engine", scope, "", c.raw, tree.name, "high")
                )
    return out


def etb_bulk_draw(tree: ConceptTree) -> bool:
    """True when TREE draws 2+ cards (fixed or scaling) off its OWN
    enters-the-battlefield trigger (CR 121.1 / 603.6e) — Mulldrifter,
    Elvish Visionary's bigger siblings. This is the ETB-bulk counterpart
    the task #83 'card-draw' preset view needs to reach Mulldrifter:
    :func:`_card_draw_engine`'s own bulk-Draw arm deliberately EXCLUDES an
    ``enters`` unit (a one-shot ETB draw is a value creature, not a
    repeatable engine — see that function's own docstring), so
    ``card_draw_engine`` alone never fires for it. Reuses the SAME
    ``amount_factor`` / ``amount_is_scaling`` reads that lane's bulk gate
    runs, just requiring the trigger shape that lane requires ABSENT.
    """
    for unit in tree.units:
        if unit.trigger_event != "enters":
            continue
        for c in unit.effect_concepts("draw"):
            if amount_factor(c.node, "count") >= 2 or amount_is_scaling(
                c.node, "count"
            ):
                return True
    return False


def _group_hug_draw(tree: ConceptTree) -> list[Signal]:
    """group_hug_draw — a draw GIVEN to everyone (CR 121.1): "each player
    draws a card" (Temple Bell — the ``player_scope: All`` wrapper on the
    ability that owns the Draw; an explicit each-player recipient). A
    controller-only draw (Divination) never fires. Scope "each".

    Stage-A recovery (ADR-0037/0038): Grothama, All-Devouring's
    leaves-the-battlefield damage-scaled draw drops its "each player" subject
    when phase leaves the clause Unimplemented — the subject survives ONLY in
    the whole-card oracle, so ``tree_synthesis._arm_group_hug_draw`` fills the
    gap from there, gated on the SAME typed read this lane runs
    (``has_structural_group_hug_draw``). It emits the REAL "draw" concept
    with ``scope="each"`` directly (no ``synth_*`` marker), so the second
    loop below reads it through the ordinary typed
    ``effect_concepts("draw")`` walk — keyed off the :class:`SynthesizedNode`
    identity so a live ``ScopedPlayer`` ("that player draws" — Howling Mine)
    never widens into group-hug territory via this branch either.
    """
    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if recipient_tag(c.node) in _EACH_DRAW_RECIPIENTS or (
                effect_owner_player_scope(unit.node, c.node) == "All"
            ):
                return [Signal("group_hug_draw", "each", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.effect_concepts("draw"):
            if c.scope == "each" and isinstance(c.node, SynthesizedNode):
                return [Signal("group_hug_draw", "each", "", c.raw, tree.name, "high")]
    return []


_SELF_DRAW_RECIPIENT_TAGS: frozenset[str] = frozenset(
    {"OriginalController", "Controller"}
)


def _unit_has_originalcontroller_draw(unit: AbilityUnit) -> bool:
    """True when ``unit`` owns a ``Draw`` effect recipient-tagged
    ``OriginalController`` OR ``Controller`` — the "you" half of a paired
    "you and [target opponent/that player] each draw" idiom sharing ONE
    unit with a ``ScopedPlayer``/widened-tag sibling Draw (see
    :func:`_target_player_draws`). ``OriginalController`` is the SPELL's
    own controller (survives a copy); ``Controller`` is the ordinary
    current-ability-controller tag most self-cantrips carry (Legend of
    Yangchen's "target opponent draws three cards. If you do, draw three
    cards." pairs ``Typed``/``Controller`` rather than
    ``OriginalController``/``Typed``). ADR-0038 W6 endgame corpus-verified
    the ``Controller`` addition separately from the original
    ``OriginalController`` citation on the ``ScopedPlayer`` branch's own
    docstring: 7 total commander-legal ``Controller``-paired Draw hits
    (Arcane Denial, Dream Fracture — a ``ParentTargetController`` Draw and
    a SEPARATE textually-grounded "Draw a card." sentence, both already
    admitted independently via their own real clause text; Ms.
    Bumbleflower, Sphinx of Enlightenment — a ``Typed`` Draw with its own
    real clause text, already admitted independently; Pendant of
    Prosperity — an unconditionally-admitted ``Any`` Draw; Willie Lumpkin,
    Postman — a ``TriggeringPlayer`` Draw with its own real clause text,
    already admitted independently; The Legend of Yangchen — the ONE
    genuinely NEW admission, a Saga chapter's synthetic-description gap
    identical to the ``OriginalController`` cases), 0 exceptions — every
    hit is a genuine directed-draw pairing, most already reachable via
    their own text and this addition changes nothing for them; only
    Legend of Yangchen newly closes."""
    return any(
        recipient_tag(c.node) in _SELF_DRAW_RECIPIENT_TAGS
        for c in unit.effect_concepts("draw")
    )


def _pce_has_paired_draw(pce: object) -> bool:
    """True when a ``Vote`` ``per_choice_effect`` branch (CR 701.38) owns
    BOTH a self-tagged Draw (:data:`_SELF_DRAW_RECIPIENT_TAGS`) and a
    ``ScopedPlayer``/widened/basic-tagged Draw among its own typed nodes —
    the SAME "you and X each draw" idiom nested one level deeper behind a
    vote outcome (Master of Ceremonies's "secrets" branch), scoped strictly
    to ``pce``'s own subtree so a SIBLING branch's unrelated Draw (the
    "money"/"friends" Token branches, or another vote's own self-payoff)
    never bleeds in. ADR-0038 W6 endgame corpus-verified: 8 total
    commander-legal ``Vote``-branch Draw hits, 7 are a bare
    ``Controller``-tagged self-payoff for winning a "Will of the council"
    vote (correctly unpaired — no sibling directed Draw in the same
    branch), only Master of Ceremonies pairs, 0 false positives."""
    tags = [recipient_tag(n) for n in iter_typed_nodes(pce) if tag_of(n) == "Draw"]
    if not any(t in _SELF_DRAW_RECIPIENT_TAGS for t in tags):
        return False
    others = {"ScopedPlayer"} | _TARGETED_DRAW_TAGS | _TARGETED_DRAW_WIDENED_TAGS
    return any(t in others for t in tags)


# ADR-0038 W5 tails: a RECOVERED "draw" residue (recovery.py's ALLOWLIST
# token row) keeps the Unimplemented wrapper as ``.node`` — no typed
# recipient, so the clause's own words are the only direction carrier, same
# precedent as ``discard_outlet``'s ``_RECOVERED_OPP_DISCARD_RE`` (inverted
# polarity: THIS lane wants the directed-AWAY-from-you class). Reuses
# :data:`_TARGET_PLAYER_DRAW_PHRASE_RE`'s direction-word list but additionally
# refuses to cross an "if"/"unless" boundary between the verb and the
# direction word — Faramir, Prince of Ithilien's "you draw a card if they
# didn't attack you" names "they" as the subject of a CONDITION clause, not
# the drawer (the drawer is plainly "you", stated earlier in the SAME
# clause); Forget's "draws as many cards as they discarded this way" and
# Soldevi Sentry's "that player may draw a card" carry no such conditional
# boundary and correctly match. CR 121.1.
_RECOVERED_DRAW_DIRECTED_RE = re.compile(
    r"\b(?:target (?:player|opponent)s?|(?:its|their|that|the) (?:controller|owner)s?"
    r"|\w+'s (?:controller|owner)s?|that player|they)\b"
    r"(?:(?!\bif\b|\bunless\b)[^.,;])*?\bdraws?\b"
    r"|\bdraws?\b(?:(?!\bif\b|\bunless\b)[^.,;])*?\b(?:target (?:player|opponent)s?"
    r"|(?:its|their|that|the) (?:controller|owner)s?|\w+'s (?:controller|owner)s?"
    r"|that player|they)\b",
    re.IGNORECASE,
)
# A recovered "draw" residue whose diagnostic wrapper names phase's OWN
# replacement parser ("Replacement pattern matched but line failed
# replacement parser: ..." — Alms Collector's "instead you and that player
# each draw a card" symmetric draw-cap) is a rules REWRITE phase merely
# failed to structure, not a forced gift — the SAME exclusion the typed
# ``unit.origin == "replacement"`` check applies below, extended to a
# residue whose own origin field reads "ability" (the failed-parse fallback)
# because the diagnostic prefix itself says what it is.
_RECOVERED_DRAW_REPLACEMENT_RE = re.compile(
    r"^\s*replacement pattern matched", re.IGNORECASE
)


def _widened_tag_phrase_match(
    unit: AbilityUnit, node: TypedMirrorNode, tree: ConceptTree
) -> bool:
    """Whether a widened-tag Draw's OWN clause names a player recipient
    (:data:`_TARGET_PLAYER_DRAW_PHRASE_RE`) — read off the unit's own
    ``description`` first, falling back to the REAL per-mode English
    (:func:`~mtg_utils._card_ir.crosswalk.modal_mode_description`) when the
    unit-level field carries nothing usable: ``None`` for a modal SPELL's
    per-mode ability entry, or a synthetic trigger-condition label ("When ~
    enters"/"Whenever ~ attacks") for a modal TRIGGER. ADR-0039 grammar
    sprint (task #82) — retires the ``tpd_widened_tag_synthetic_desc``
    bridge: Fatal Lore's/Season of the Burrow's per-mode text lives ONLY on
    the card-root ``modal.mode_descriptions`` (their own mode ability's
    ``description`` is ``None``); Ertai Resurrected's/Balor's lives on
    ``execute.modal.mode_descriptions`` (their unit's own ``description``
    is a synthetic "When ~ enters"/"Whenever ~ attacks" label). Vault 11:
    Voter's Dilemma stays excluded (a Saga's chapters are independent
    triggers, never a "choose one" modal branch — neither shape applies,
    so :func:`modal_mode_description` returns ``""`` and this predicate
    falls through unchanged).
    """
    desc = getattr(unit.node, "description", None) or ""
    if any(_TARGET_PLAYER_DRAW_PHRASE_RE.search(cl.lower()) for cl in _clauses(desc)):
        return True
    modal_desc = modal_mode_description(unit, node, tree)
    return bool(modal_desc) and any(
        _TARGET_PLAYER_DRAW_PHRASE_RE.search(cl.lower()) for cl in _clauses(modal_desc)
    )


def _target_player_draws(tree: ConceptTree) -> list[Signal]:
    """target_player_draws — a DIRECTED / forced draw (CR 121.1): "target
    player draws a card" (Bloodgift Demon — the typed ``Player`` recipient).
    With the typed recipient present the live path's self-loot phantom
    exclusion is unnecessary in v0.9.0 (Careful Study's draw carries
    ``Controller``); the negative fixture pins it regardless. A REPLACEMENT
    unit's rewritten draw ("if a player would draw …, that player … instead"
    — Chains of Mephistopheles' draw-tax) is a rules rewrite, not a forced
    gift — replacement units are skipped (mirrors the live non-directed
    exclusion). The ``ScopedPlayer`` each-player draw ("at the beginning of
    each player's draw step, that player may draw" — Academy Loremaster) is
    a GROUP draw distributed by an each-player trigger, not a directed gift
    — batch-9 adjudicated OUT (group-draw territory; the live routing of it
    here is the documented divergence). Scope "any".

    ADR-0038 W3 batch 6 (draw-etb-tokens cluster): three more recipient
    tags admitted (:data:`_TARGETED_DRAW_WIDENED_TAGS`) — ``Typed`` (a
    player FILTER recipient naming ``Opponent`` — "target/each opponent
    draws", Lord of Tresserhorn), ``ParentTargetController`` (the
    controller of a previously targeted OBJECT — "its controller draws a
    card", Call to Heel), ``TriggeringPlayer`` (the specific player who
    performed the watched action — Curse of Chaos's attacking player).
    Unlike the original three, these are gated behind
    :data:`_TARGET_PLAYER_DRAW_PHRASE_RE` (the draw's OWN clause, off the
    owning unit's description) — a phase templating quirk bleeds a
    PRECEDING "target X. Its controller may Y." clause's recipient onto a
    FOLLOWING, textually-unattributed "Draw a card." sentence that per CR
    608.2h actually defaults to the caster (Price of Freedom, Cleansing
    Wildfire, Geomancer's Gambit); the phrase gate keeps the genuine
    same-clause "Its controller draws"/"target player draws"/"they draw"
    hits and excludes the bled ones. CR 121.1.

    ADR-0038 W5 tails, two more admissions:

    * a ``ScopedPlayer`` recipient IS admitted when the SAME unit also owns
      an ``OriginalController``-tagged Draw (:func:`_unit_has_originalcontroller_
      draw`) — the "you and target opponent/that player each draw" idiom
      (Intellectual Offering, Tenuous Truce, Diviner Spirit, Xyris, the
      Writhing Storm, Black Widow, Intel Expert, Sergeant John Benton): phase
      splits this into TWO sibling Draw nodes sharing one unit, one
      ``OriginalController`` (the you-side, never counted — CR
      121.1/608.2h's directed-AT-ANOTHER-player sense excludes it) and one
      ``ScopedPlayer`` (the SAME-unit paired player — a genuine directed
      gift). An UNPAIRED ``ScopedPlayer`` (no ``OriginalController`` sibling
      — Howling Mine's lone each-player-draw-step node) stays group_hug_draw
      territory; corpus-verified across the full commander-legal
      ``ScopedPlayer``-draw population: 17 unpaired (all "each player"/"each
      opponent" phase triggers) vs. 6 paired (all this idiom), 0 exceptions
      either way;
    * a RECOVERED "draw" residue (:data:`_RECOVERED_DRAW_DIRECTED_RE` — Forget,
      Soldevi Sentry) — guarded against the replacement-diagnostic residue
      (:data:`_RECOVERED_DRAW_REPLACEMENT_RE`) and the symmetric each-player
      residue (``effect_owner_player_scope(...) == "All"`` — Grothama,
      All-Devouring's damage-scaled leaves-trigger, group_hug_draw's own
      synthesis-arm territory per its docstring).

    ADR-0038 W6 endgame, two more admissions (corpus re-measure at fresh
    HEAD: 178 both / 75 live_only, down from there):

    * the self-paired admission (:func:`_unit_has_originalcontroller_draw`)
      widens on TWO axes at once: (1) from ``ScopedPlayer``-only to EVERY
      :data:`_TARGETED_DRAW_WIDENED_TAGS` member too — a ``Typed``
      (opponent-filter) sibling paired with a self-tagged Draw in the SAME
      unit is the identical "you and target opponent each draw" idiom,
      just phase-tagged with the opponent-FILTER shape instead of the
      bare-player shape; (2) the self half now also accepts the ordinary
      ``Controller`` tag, not just ``OriginalController``
      (:data:`_SELF_DRAW_RECIPIENT_TAGS` — Legend of Yangchen's "You may
      have target opponent draw three cards. If you do, draw three cards."
      pairs ``Typed``/``Controller``, not ``OriginalController``/``Typed``).
      Fall of the First Civilization's Saga chapter I, Love Song of Night
      and Day's Saga chapter I, Your Temple Is Under Attack's "Strike a
      Deal" mode, and Legend of Yangchen's Saga chapter II all carry NO
      reachable clause text anywhere in the typed tree for the widened-tag
      phrase gate to read (a Saga chapter's ``unit.node.description`` is a
      synthetic structural label — "Chapter 1" — never the chapter's real
      English; :func:`~mtg_utils._card_ir.crosswalk.effect_owner_raw`
      confirms empty too), so the phrase gate can never fire for them —
      but the PAIRING itself is independent of any text. Corpus
      re-verified for BOTH widenings together: 23 total commander-legal
      self-paired Draw hits (6 ``ScopedPlayer``/``OriginalController`` —
      the original citation — + 10 widened-tag/``OriginalController`` + 7
      */``Controller``), ALL twenty-three are the same "you and X each
      draw" (or, for Legend of Yangchen, "have X draw, then you draw")
      idiom, 0 exceptions — safe to bypass the phrase gate whenever the
      pairing itself is present, same discipline as the original
      ``ScopedPlayer`` admission. The other six ``Controller``-paired hits
      (Arcane Denial, Dream Fracture, Ms. Bumbleflower, Sphinx of
      Enlightenment, Pendant of Prosperity, Willie Lumpkin) were already
      admitted independently via their own real clause text or an
      unconditional tag, so this widening changes nothing for them — only
      Legend of Yangchen newly closes;
    * a ``Vote`` ``per_choice_effect`` branch (CR 701.38) carrying BOTH a
      self-tagged Draw and a ``ScopedPlayer``/widened/basic-tagged Draw
      side by side (:func:`_pce_has_paired_draw`) — the SAME paired idiom
      nested one level deeper behind a vote outcome (Master of Ceremonies:
      "For each player who chose secrets, you and that player each draw a
      card." — a ``per_choice_effect[i]`` branch phase never surfaces
      through ``effect_concepts`` at all, the identical unreached-branch
      shape draw_for_each's own ``Vote`` descent closes for a different
      lane). Corpus-verified: 8 total commander-legal ``Vote``-branch Draw
      hits; 7 are a bare ``Controller``-tagged self-draw payoff for
      winning a "Will of the council" vote (Plea for Power, Coercive
      Portal, Galadriel Elven-Queen, Sail into the West, Khorvath's Fury,
      Seize the Spotlight, Truth or Consequences — correctly NOT paired,
      so this admission never touches them); only Master of Ceremonies
      pairs ``OriginalController`` with ``ScopedPlayer``, 0 false
      positives. CR 121.1 / 701.38.

    ADR-0039 W7 BRIDGES wave (2026-07-12) — PROMOTED. The final 6
    live_only closed. One real structural gain, a buried-grant ``Draw``
    descent (mirrors ``opponent_discard``'s own ``iter_typed_nodes``
    precedent for Mindlash Sliver/Dementia Sliver): Thief of Existence's
    granted "target opponent draws a card" trigger lives inside a
    ``GrantAbility`` nested in the CASTING trigger's own effect chain (CR
    603.6c), invisible to ``effect_concepts("draw")``'s direct-chain-only
    read; the buried node's tag branching reuses the EXISTING
    ``_TARGETED_DRAW_TAGS``/``_TARGETED_DRAW_WIDENED_TAGS`` + phrase-gate
    logic verbatim (Thief of Existence's own unit-level description
    already carries the full quoted grant text, so the phrase gate passes
    unmodified) — corpus-verified narrow (31,622 commander-legal): exactly
    1 new hit, with Zur's Weirding's superficially similar buried Draw
    correctly excluded by the pre-existing ``unit.origin == "replacement"``
    skip. Two ADR-0039 ledgered bridges opened for the residual 5 pins;
    BOTH graduated off the ledger in the grammar sprint (task #82,
    2026-07-12):

    * ``tpd_widened_tag_synthetic_desc`` (Fatal Lore, Season of the
      Burrow, Ertai Resurrected, Balor: each already carries a typed
      ``Draw`` node with a correctly-widened recipient tag, but the
      owning unit's ``description`` is ``None`` or a synthetic trigger-
      condition label — "When ~ enters"/"Whenever ~ attacks" — never the
      modal bullet's own English) is now served structurally:
      :func:`_widened_tag_phrase_match` falls back to
      :func:`~mtg_utils._card_ir.crosswalk.modal_mode_description` — the
      REAL per-mode text phase carries positionally on the card-ROOT
      ``modal.mode_descriptions`` (a modal SPELL, paired with
      ``root.abilities`` by ``unit.index``) or the TRIGGER's own
      ``execute.modal.mode_descriptions`` (paired with
      ``execute.mode_abilities`` by an object-identity walk) — whenever
      the unit-level field can't confirm the direction. Vault 11:
      Voter's Dilemma stays correctly excluded (a Saga's chapters carry
      NEITHER modal shape, so the fallback returns "" and the predicate
      falls through unchanged).
    * ``tpd_wedding_ellipsis_repeat`` (The Wedding of River Song's "Then
      target opponent does the same" names its own clause-grammar token,
      ``Unimplemented(name='target_opponent_does_the_same')``) is now
      served via a new ``clause_grammar`` verb (``ellipsis_repeat`` — the
      EXISTING "target opponent " subject-prefix peel lands dispatch on
      the bare "does the same" tail) + a ``recovery.ALLOWLIST`` mapping
      to the real "draw" concept, read here through the ordinary
      ``effect_concepts("draw")`` walk via a dedicated
      ``recovered_by == "ellipsis_repeat"`` arm gated on the SAME-unit
      self-tagged Draw sibling (:func:`_unit_has_originalcontroller_draw`
      — the "you and X each draw" pairing precedent, since the recovered
      node's raw carries no verb of its own to re-check). Full-corpus
      scan (32,521 commander-legal, 2026-07-12): "does the same" is a
      residue exactly once in the WHOLE corpus (this card) — no blast
      radius beyond the single pin.

    CR 121.1 / 603.6c / 608.2h verified this session.
    """
    for unit in tree.units:
        if unit.origin == "replacement":
            continue
        for c in unit.effect_concepts("draw"):
            if c.recovered_by == "ellipsis_repeat":
                # ADR-0039 grammar sprint (task #82) — retires the
                # ``tpd_wedding_ellipsis_repeat`` bridge. "<player> does
                # the same" (The Wedding of River Song) carries no verb of
                # its own in the raw (the subject peel eats it), so
                # direction comes from the SAME-unit self-tagged Draw
                # SIBLING — the identical "you and X each draw" pairing
                # :func:`_unit_has_originalcontroller_draw` already reads
                # for the widened-tag idiom above.
                if _unit_has_originalcontroller_draw(unit):
                    return [
                        Signal(
                            "target_player_draws", "any", "", c.raw, tree.name, "high"
                        )
                    ]
                continue
            if c.recovered_by == "draw":
                if _RECOVERED_DRAW_REPLACEMENT_RE.search(c.raw or ""):
                    continue
                if effect_owner_player_scope(unit.node, c.node) == "All":
                    continue  # each-player group draw, group_hug territory
                if _RECOVERED_DRAW_DIRECTED_RE.search((c.raw or "").lower()):
                    return [
                        Signal(
                            "target_player_draws", "any", "", c.raw, tree.name, "high"
                        )
                    ]
                continue
            rt = recipient_tag(c.node)
            if rt == "ScopedPlayer":
                if _unit_has_originalcontroller_draw(unit):
                    return [
                        Signal(
                            "target_player_draws", "any", "", c.raw, tree.name, "high"
                        )
                    ]
                continue  # each-player group draw — never a directed gift
            if rt in _TARGETED_DRAW_TAGS:
                return [
                    Signal("target_player_draws", "any", "", c.raw, tree.name, "high")
                ]
            if rt in _TARGETED_DRAW_WIDENED_TAGS:
                # ADR-0038 W6 endgame: the paired idiom bypasses the phrase
                # gate entirely (Fall of the First Civilization, Love Song
                # of Night and Day, Your Temple Is Under Attack — a Saga
                # chapter/modal-mode unit whose OWN description is a
                # synthetic structural label, never the real English the
                # phrase gate needs; the pairing itself is text-independent
                # and already corpus-verified safe).
                if _unit_has_originalcontroller_draw(unit):
                    return [
                        Signal(
                            "target_player_draws", "any", "", c.raw, tree.name, "high"
                        )
                    ]
                if _widened_tag_phrase_match(unit, c.node, tree):
                    return [
                        Signal(
                            "target_player_draws", "any", "", c.raw, tree.name, "high"
                        )
                    ]
        # ADR-0038 W6 endgame: a ``Vote`` ``per_choice_effect`` branch (CR
        # 701.38) is a separate typed subtree ``effect_concepts`` never
        # walks into (the SAME unreached-branch shape draw_for_each's own
        # Vote descent closes) — Master of Ceremonies's "For each player
        # who chose secrets, you and that player each draw a card."
        # Scoped to the branch's OWN subtree (:func:`_pce_has_paired_draw`)
        # so a sibling branch's unrelated Draw/Token effect never bleeds
        # in.
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Vote":
                continue
            for pce in getattr(n, "per_choice_effect", None) or ():
                if _pce_has_paired_draw(pce):
                    return [
                        Signal("target_player_draws", "any", "", "", tree.name, "high")
                    ]
        # ADR-0039 W7 BRIDGES wave: a Draw node BURIED inside a granted
        # ability's own definition (Thief of Existence: "If you do,
        # Thief of Existence gains 'When this creature leaves the
        # battlefield, target opponent draws a card.'" — a GrantAbility
        # nested inside the CASTING trigger's own effect chain, CR
        # 603.6c) is not on the unit's DIRECT effect chain, so
        # ``effect_concepts("draw")`` never reaches it — the SAME buried-
        # grant shape ``opponent_discard``'s own ``iter_typed_nodes`` deep
        # walk already closes for Mindlash Sliver/Dementia Sliver. The
        # buried node's OWN tag branching is IDENTICAL to the surface
        # loop above (no new logic): a ``_TARGETED_DRAW_TAGS`` recipient
        # admits unconditionally, a ``_TARGETED_DRAW_WIDENED_TAGS``
        # recipient still needs the unit's own clause text to name a
        # player (Thief of Existence's unit-level description carries the
        # full quoted grant, "target opponent draws a card" included, so
        # the EXISTING phrase gate passes with no widening of its own).
        # Corpus-verified narrow (2026-07-12, 31,622 commander-legal, the
        # SAME replacement-unit skip above already applies): exactly 1 new
        # hit, Thief of Existence itself (Zur's Weirding's superficially
        # similar buried ``ParentTargetController`` Draw lives in a
        # REPLACEMENT unit and is already excluded by this loop's own
        # ``unit.origin == "replacement"`` skip).
        surface_ids = {id(c.node) for c in unit.effect_concepts("draw")}
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Draw" or id(n) in surface_ids:
                continue
            rt = recipient_tag(n)
            if rt in _TARGETED_DRAW_TAGS:
                return [Signal("target_player_draws", "any", "", "", tree.name, "high")]
            if rt in _TARGETED_DRAW_WIDENED_TAGS and _widened_tag_phrase_match(
                unit, n, tree
            ):
                return [Signal("target_player_draws", "any", "", "", tree.name, "high")]
    # ADR-0039 W7 BRIDGES wave opened two ledgered bridges here
    # (``tpd_widened_tag_synthetic_desc`` — Fatal Lore, Season of the
    # Burrow, Ertai Resurrected, Balor; ``tpd_wedding_ellipsis_repeat`` —
    # The Wedding of River Song); BOTH GRADUATED this sprint (task #82,
    # 2026-07-12), no bridge lookup left in this lane. The synthetic-desc
    # class is served by :func:`_widened_tag_phrase_match`'s fallback to
    # :func:`~mtg_utils._card_ir.crosswalk.modal_mode_description`'s real
    # per-mode English (the widened-tag branches above); the ellipsis-
    # repeat class is served by the ``recovered_by == "ellipsis_repeat"``
    # arm in the surface loop above (``clause_grammar``'s new
    # ``ellipsis_repeat`` verb + ``recovery.ALLOWLIST``).
    return []


def _cantrip(tree: ConceptTree) -> list[Signal]:
    """cantrip — a low-opportunity-cost spell that draws exactly ONE card as a
    RIDER on another primary effect (CR 121.1): Preordain ("Scry 2, then draw
    a card"), Opt, Consider, Chandra's Defeat's kicker-draw. Distinct from
    ``card_draw_engine`` (2+ / recurring draw) — a bare single-draw spell with
    NO sibling effect (Divination-shaped) is not a cantrip, it IS the spell's
    whole point, so it is deliberately excluded here too.

    Gated to Instant/Sorcery — the traditional MTG-community "cantrip" usage.
    A permanent's repeatable ETB/attack-trigger single draw (Mulldrifter,
    Bloodsoaked Champion) is a VALUE creature, a different archetype, not
    this lane (and IS the ``blink_flicker`` membership-floor "worth
    blinking" shape documented at :func:`_blink_flicker` — the same
    "own-ETB-value" tell, a different key). Four structural requirements on
    the owning ability unit:

    * a ``Draw`` whose ``count`` is an EXPLICIT, present ``Fixed`` node
      whose value is 1 (:func:`has_fixed_count` — task #87: NOT the bare
      ``amount_factor(...) == 1 and not amount_is_scaling(...)`` pair this
      arm used before, which folds an ABSENT count field into the SAME
      "1, non-scaling" numbers a genuine ``Fixed(1)`` produces. A
      ``recovery.py``-recovered ``Unimplemented`` "draw" residue carries
      NO count field at all — Arcane Endeavor's "Draw cards equal to
      [a d8 roll]" satisfied the old bare-pair gate by omission, a
      genuine over-fire: CR 121.1's "draw" isn't bounded to one card just
      because phase's grammar couldn't structure the die-roll amount.
      "draw a card for each ..." (real card_draw_engine's scaling arm) is
      excluded the SAME way — its scaling qty, when phase DOES structure
      it, is a non-``Fixed`` tag ``has_fixed_count`` also rejects);
    * at least one OTHER effect concept in the SAME unit (the rider — a bare
      Divination has none);
    * the draw's own recipient is not ``Opponent`` (Bargain's "target
      opponent draws a card. You gain 7 life." is a gift, not your cantrip);
    * the unit is neither a ``Phase`` trigger (Phyrexian Arena) nor a Draw
      REPLACEMENT (Alhammarret's Archive) — card_draw_engine's territory,
      never a one-shot rider.

    Corpus-scanned (433 commander-legal hits off a 3279-card "draws a card"
    superset — Preordain / Opt / Serum Visions / Portent / Consider / Blink
    of an Eye / Arcane Denial all recovered, Lightning Bolt / Sign in Blood
    correctly excluded): a BOUNDED read, not the deleted ``cantrip``
    preset's raw ``draws? (?:a|an additional) card`` substring (3174 hits,
    which counts every payoff mention, reflexive trigger, and creature ETB).

    Task #87 corpus re-diff after the ``has_fixed_count`` tightening: TWO
    commander-legal losses, both adjudicated genuine over-fire removals,
    not regressions — Arcane Endeavor ("Roll two d8 and choose one
    result. Draw cards equal to that result...", the row's own flagship
    example) and Mob Verdict ("For each vote you received, draw a card" —
    CR 701.38d: a vote effect gives each player exactly one vote, but
    MULTIPLE players can vote for the SAME target, so "votes received" is
    a genuine 0..N-1 board-count in an N-player game, not a bounded 1;
    ``recovery.py``'s own "draw" ALLOWLIST comment already group-names
    Mob Verdict alongside Arcane Endeavor as the identical "amount-
    computed or per-thing draws" residue class). Both carry the SAME
    Unimplemented-recovered "draw" concept node with no count field at
    all — genuinely indistinguishable from each other structurally, and
    correctly excluded together.
    Scope "you"."""
    if not (tree.is_type("Instant") or tree.is_type("Sorcery")):
        return []
    for unit in tree.units:
        if unit.trigger_event == "phase" or unit.origin == "replacement":
            continue
        others = [
            c
            for c in unit.iter_concepts()
            if c.role == "effect" and c.concept != "draw"
        ]
        if not others:
            continue
        for c in unit.effect_concepts("draw"):
            if not has_fixed_count(c.node, "count"):
                continue
            if amount_factor(c.node, "count") != 1:
                continue
            if filter_controller(effect_filter(c.node)) == "Opponent":
                continue
            return [Signal("cantrip", "you", "", c.raw, tree.name, "high")]
    return []


def _activated_draw(tree: ConceptTree) -> list[Signal]:
    """activated_draw — a tap-to-draw engine (CR 121.1 / 601.2b): an
    ``Activated`` unit with ``Tap`` among its cost leaves and a ``Draw``
    effect (Sensei's Divining Top's ``{T}: Draw``). A cycling activation
    (Archfiend of Ifnir — ``Composite[Mana, Discard]``, no Tap) and a
    tap-for-mana ability (no Draw) stay out. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "ability" or unit.kind != "Activated":
            continue
        if not unit.has_effect("draw"):
            continue
        if any(
            tag_of(leaf) == "Tap"
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
        ):
            return [Signal("activated_draw", "you", "", "", tree.name, "high")]
    return []


_TOPDECK_SELECTION_TARGET_TAGS: frozenset[str] = frozenset(
    {"Dig", "RevealTop", "ExileTop"}
)

# ADR-0038 W4 giant batch — the residual bucket-B text idiom, TWO independent
# per-UNIT conditions (never a single adjacency-bound regex — legacy's own
# C8 owner-tag mechanism works the SAME way: it tags an "exile"/"reveal"
# category effect with ``top:you`` whenever the WHOLE ability's raw contains
# a top-of-library phrase ANYWHERE, not necessarily next to the triggering
# verb — Doomsday's "exile the rest" gets ``top:you`` from a LATER, separate
# sentence "Put the chosen cards on top of your library"):
#
# (1) a SELECTION-shaped verb (exile / reveal / look at / manifest — CR
#     701.13a/701.20a/401.5/701.40) appears anywhere in the unit's own text;
# (2) a top-of-library phrase (:data:`_TOPDECK_SELECTION_TOP_RX`) appears
#     anywhere in the SAME unit's text, self-referential ("your"/"THIS
#     card's" library, never "their"/"target opponent's").
#
# Both required, gating out a bare "put ... on top of your library" alone
# with NO selection verb anywhere in the ability (Aminatou, the
# Fateshifter's "+1: Draw a card, then put a card from your hand on top of
# your library" — a pure topdeck_STACK tuck, CR 401.4, never a look/reveal/
# exile). "put" itself is deliberately NOT a selection verb — Winter,
# Cynical Opportunist's plain "mill three cards" trigger has neither "top"
# nor "library" in its OWN unit text at all (its Delirium ability's "exile
# ... graveyard ... put a permanent card from among them onto the
# battlefield" carries the verb but no top-of-library phrase), so it stays
# correctly excluded under this same two-condition gate — closing the
# deleted SWEEP mirror's context-blind false-positive class without any
# extra bookkeeping.
_TOPDECK_SELECTION_VERB_RX = re.compile(
    r"\b(?:exile|exiles|reveal|reveals|look at|looks at|manifest|manifests)\b",
    re.IGNORECASE,
)
_TOPDECK_SELECTION_TOP_RX = re.compile(
    r"\btop\b[^.]{0,20}\bof your library\b|\bfrom the top of your library\b",
    re.IGNORECASE,
)


# ``_TOPDECK_OTHER_ZONE`` (reused verbatim from supplement.py) has no "each
# player's library" alternative — a corpus-only gap this session found (its
# consumers all pre-date the symmetric-reveal cross-open cluster): Etali,
# Primal Storm / Pako, Arcane Retriever / Share the Spoils all read "exile
# the top card of EACH PLAYER's library", a symmetric multi-library effect,
# not the controller's own curation. LOCAL supplement (not a mutation of the
# shared constant — other reusers of ``_TOPDECK_OTHER_ZONE`` stay untouched).
_TOPDECK_EACH_PLAYER_ZONE = re.compile(
    r"\beach player'?s? (?:library|hand)\b", re.IGNORECASE
)


def _topdeck_owner_ok(text: str) -> bool:
    """True unless the unit's own text names a DIFFERENT player's library
    (``_TOPDECK_OTHER_ZONE``, plus the local ``_TOPDECK_EACH_PLAYER_ZONE``
    supplement) without also naming the controller's own
    (``_TOPDECK_YOUR_LIBRARY`` takes precedence — mirrors
    ``supplement._top_library_owner``'s ordering, CR 401.1). Reused verbatim
    single-source: phase's ``Dig``/``RevealTop``/``ExileTop`` ``player``
    field names who PERFORMS the look, never whose library it is (Gonti's
    ``Dig(player=Controller)`` digs a TARGETED OPPONENT's library — the
    node alone can't tell; the raw still can)."""
    if _TOPDECK_YOUR_LIBRARY.search(text):
        return True
    return not (
        _TOPDECK_OTHER_ZONE.search(text) or _TOPDECK_EACH_PLAYER_ZONE.search(text)
    )


def _topdeck_selection(tree: ConceptTree) -> list[Signal]:
    """topdeck_selection — OWN-library top curation (CR 701.22a scry /
    701.25a surveil / 701.20a reveal / 701.13a exile / 701.17 mill / 701.40
    manifest / 401.1 library-zone ownership / 401.5 "look at the top card
    of your library" statics). Deep-walked (:func:`iter_typed_nodes`
    recurses into a GRANTED ability's own ``.definition`` sub-tree for free
    — Oracle's Insight's enchant-granted Scry, Tocasia's granted Surveil,
    Candlestick's granted attack-trigger Surveil):

    * ``Scry`` / ``Surveil`` — always self (CR 701.22a/701.25a name no
      other-player variant, zero owner ambiguity).
    * ``Dig`` whose ``player`` is Controller and whose destination is NOT
      the battlefield (Sensei's Divining Top — a dig-to-battlefield is the
      cheat/ramp put, a different lane), ``RevealTop`` whose ``player`` is
      Controller (vetoing a SAME-unit ``SearchLibrary`` sibling — phase
      mislabels a tutor's found-card reveal as ``RevealTop(Controller)``,
      CR 701.23a search vs 701.20a reveal), and ``ExileTop`` whose
      ``player`` is Controller (Abbot of Keral Keep's impulse-draw exile,
      CR 701.13a). All three additionally gate on :func:`_topdeck_owner_ok`
      — the node's ``player`` field names who PERFORMS the dig/reveal/
      exile, never whose LIBRARY it targets (CR 401.1), so a raw-text
      owner check is load-bearing (Gonti, Lord of Luxury digs a TARGET
      OPPONENT's library with ``player=Controller``; Selvala's "each
      player reveals the top card of THEIR library" is symmetric, not a
      your-library curation build; Etali, Primal Storm / Pako, Arcane
      Retriever's "top card of EACH PLAYER's library" is the same
      symmetric shape under different wording, closed by the local
      :data:`_TOPDECK_EACH_PLAYER_ZONE` supplement).
    * ``RevealUntil`` / ``ExileFromTopUntil`` (CR 701.20a reveal / 701.13a
      exile, the "until" dig idiom) whose digger
      (:func:`reveal_until_player`) resolves "you" (Hermit Druid's
      own-library dig; Demonlord Belzenlok's exile-side sibling).
    * a static ability whose ``mode`` is ``MayLookAtTopOfLibrary`` ("You may
      look at the top card of your library any time" — Vizier of the
      Menagerie, One with the Multiverse, Korlessa, The Fourth Doctor,
      Bolas's Citadel, Elsha of the Infinite), controller-gated (CR 401.5,
      "some effects ... say that a player may look at the top card of
      their library").
    * **mill-then-cheat-to-battlefield** (CR 701.17 mill + 401.1 library
      zone) — a ``Mill`` effect co-occurring (same unit) with a
      ``ChangeZone`` to Battlefield whose target is a
      ``TrackedSet``/``TrackedSetFiltered`` back-reference re-consuming the
      milled group (Eivor, Wolf-Kissed; Rampant Frogantua; Mole Module;
      Bind to Life — "mill N, put a card from among them onto the
      battlefield"). The Battlefield-destination gate is load-bearing, not
      cosmetic — mirrors the deleted SWEEP regex's own literal "...onto the
      battlefield" tail: the ~50-card "mill N, put a card from among them
      INTO YOUR HAND" cantrip family (Ravenous Gigamole, Ainok Wayfarer,
      Cache Grab, …) is corpus-verified to NOT fire in legacy at all (a
      genuine mill-to-hand card-advantage engine is not topdeck curation
      per legacy's own boundary) — gating on Battlefield keeps that whole
      family correctly excluded. A bare mill with no re-consumption
      (Stitcher's Supplier) does NOT fire either way — the back-reference
      is the anchor, mirroring the ``topdeck_stack`` precedent's own
      TrackedSet disambiguation one level up.
    * bucket-B text idiom (last resort, arms above found nothing) — TWO
      independent conditions over the UNIT's joined text (every reachable
      node's own ``description`` plus every modal's ``mode_descriptions``,
      so a straddling Ao-the-Dawn-Sky-style modal branch or a
      Doomsday-style multi-sentence ability still joins): a SELECTION verb
      (:data:`_TOPDECK_SELECTION_VERB_RX` — exile/reveal/look at/manifest,
      CR 701.13a/701.20a/401.5/701.40) present ANYWHERE, and a
      top-of-library phrase (:data:`_TOPDECK_SELECTION_TOP_RX`) present
      ANYWHERE, in the SAME unit — mirroring legacy's own C8 owner-tag
      mechanism, which tags an exile/reveal-category effect with
      ``top:you`` off the WHOLE ability's raw text, not just the clause
      touching that specific effect (Doomsday's "exile the rest" effect
      gets ``top:you`` from a LATER, separate sentence "Put the chosen
      cards on top of your library"). Closes the residual tail phase's
      static/effect parser drops into an ``Unimplemented`` (Ao, the Dawn
      Sky's modal branch, read off the PARENT ``S_modal.mode_descriptions``
      when the per-mode-ability ``description`` is bare ``None`` —
      Silverback Elder; Aladdin's Lamp's replace-a-draw dig; Scion of
      Halaster's granted replacement-effect clause), a whole "manifest the
      top card of your library" family phase's static parser never
      structures at all (CR 701.40 — Primordial Mist, Omarthis, Ugin's
      Mastery, Temur War Shaman, Whisperwood Elemental, Mastery of the
      Unseen, Soul Summons, Qarsi High Priest, Sultai Emissary, Fierce
      Invocation, Arashin War Beast, Formless Nurturing, Wildcall, Ethereal
      Ambush, Soul-Strike Technique, Guardian of the Forgotten, Cryptic
      Pursuit), an "exile the top card(s) of your library: <effect>"
      activated-cost family phase folds into a bare ``Unimplemented`` cost
      (Royal Herbalist, Seasoned Tactician, Storm Elemental, Thought Lash,
      Phyrexian Devourer, Whirling Catapult, Arc-Slogger), AND the raw-bleed
      class (Doomsday, Mirror of Fate, Once and Future, Stillness in
      Motion, Paramecia Coloniex, Flitting Guerrilla — a graveyard-sourced
      "put ... on top of your library" clause co-occurring with an "exile"
      clause in the SAME multi-effect ability; CR 401.4 makes this
      topdeck_STACK's own territory when read narrowly, but legacy's real
      corpus behavior treats the whole ability as one curation unit, and a
      Doomsday pile is exactly the kind of top-of-library build-around
      this key exists to catch). The two-condition (never single-regex)
      design is what keeps Aminatou, the Fateshifter's "+1: Draw a card,
      then put a card from your hand on top of your library" OUT — no
      selection verb anywhere in that ability at all, a pure tuck, CR
      401.4.

    ADR-0038 W4 giant batch: corpus re-measure live_only 440 -> 4, all four
    ADJUDICATED SHEDS (genuine legacy ``old_ir_for`` false positives, never
    chased): Arjun, the Shifting Flame / Mindmoil's "put the cards in your
    hand on the BOTTOM of your library ... then draw" wheel effect
    mis-classifies as the retired ``project.py`` pipeline's
    ``topdeck_select`` category — bottom-of-library, not top ("bottom"
    never matches :data:`_TOPDECK_SELECTION_TOP_RX`'s literal "top"), a
    genuine scope/category bug (the same class ``lifegain_makers`` found
    and excluded); Winter, Cynical Opportunist's plain "mill three cards"
    trigger has neither "top" nor "library" anywhere in its OWN unit text
    (its separate Delirium ability's "exile ... graveyard ... put a
    permanent card from among them onto the battlefield" carries the verb
    but no top-of-library phrase at all — "graveyard", never "library") —
    it fires in legacy only because the deleted ``TOPDECK_SELECTION_REGEX``
    SWEEP mirror's context-blind fourth alternative (``put [^.]*from among
    them onto the battlefield``) matches that wholly UNRELATED clause,
    where "them" is graveyard-exiled cards, never milled library cards;
    Ecological Appreciation's tutor-and-reveal effect ("Search your library
    and graveyard for ... reveal them ...") gets a stray
    ``from:top``/``top:you`` zone tag from the SAME retired pipeline's
    ``reveal``-category default, even though nothing in its text says "top"
    at all — a genuine legacy zone-derivation bug, not a real
    top-of-library curation instance.
    Scope "you".
    """
    for unit in tree.units:
        has_search = any(tag_of(c.node) == "SearchLibrary" for c in unit.effects)
        nodes = list(iter_typed_nodes(unit.node))
        tags_here = {tag_of(n) for n in nodes}
        unit_text = _REMINDER_RX.sub(" ", getattr(unit.node, "description", None) or "")
        for n in nodes:
            t = tag_of(n)
            if t in ("Scry", "Surveil"):
                return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
            if t in _TOPDECK_SELECTION_TARGET_TAGS:
                player = tag_of(getattr(n, "player", None))
                if player != "Controller":
                    continue
                if t == "Dig" and getattr(n, "destination", None) == "Battlefield":
                    continue
                if t == "RevealTop" and has_search:
                    continue
                if not _topdeck_owner_ok(unit_text):
                    continue
                return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
        for c in unit.effect_concepts("reveal_until"):
            if reveal_until_player(c.node) == "you":
                return [
                    Signal("topdeck_selection", "you", "", c.raw, tree.name, "high")
                ]
        if unit.origin == "static" and (
            getattr(unit.node, "mode", None) == "MayLookAtTopOfLibrary"
        ):
            aff = getattr(unit.node, "affected", None)
            if getattr(aff, "controller", None) in ("You", None):
                return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
        if "Mill" in tags_here and any(
            tag_of(n) == "ChangeZone"
            and getattr(n, "destination", None) == "Battlefield"
            and tag_of(getattr(n, "target", None))
            in ("TrackedSet", "TrackedSetFiltered")
            for n in nodes
        ):
            return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
        # Bucket-B: the joined text of every node's own ``description`` PLUS
        # every modal's ``mode_descriptions`` (a per-mode text sometimes
        # lives on the PARENT ``S_modal`` rather than each
        # ``mode_abilities[i].description`` — Silverback Elder's "Look at
        # the top five cards of your library..." mode carries a bare
        # ``None`` per-mode description; the modal's own list is the only
        # place the text survives). Joined, not scanned per-node, so the
        # two conditions can straddle sibling clauses within one ability
        # (Doomsday's "exile the rest" + a LATER "Put the chosen cards on
        # top of your library" sentence — the exact cross-clause reach
        # legacy's own whole-ability-raw C8 tag has).
        parts = [unit_text]
        for n in nodes:
            d = getattr(n, "description", None)
            if d:
                parts.append(_REMINDER_RX.sub(" ", d))
            for mdesc in getattr(n, "mode_descriptions", None) or ():
                parts.append(_REMINDER_RX.sub(" ", mdesc))
        corpus = " ".join(parts)
        if _TOPDECK_SELECTION_VERB_RX.search(
            corpus
        ) and _TOPDECK_SELECTION_TOP_RX.search(corpus):
            return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
    # task #np_roles — the ``synth_topdeck_selection`` bucket-B marker
    # (see :func:`~mtg_utils._card_ir.tree_synthesis.
    # _arm_known_token_topdeck_scry`): a known-token zero-unit text-only
    # tree whose fixed text performs a Scry (the Sorcerer Role's granted
    # attack-scry, CR 111.10n; the Shard's sac-for-scry-and-draw) has no
    # ``Scry`` typed node to walk — CR 701.22a scry is always own-library
    # curation, so the marker is owner-unambiguous.
    for c in tree.iter_concepts():
        if c.concept == "synth_topdeck_selection":
            return [Signal("topdeck_selection", "you", "", "", tree.name, "high")]
    return []


_TOPDECK_STACK_SWEEP_RE = re.compile(TOPDECK_STACK_SWEEP_REGEX, re.IGNORECASE)


def _topdeck_stack(tree: ConceptTree) -> list[Signal]:
    """topdeck_stack — stack the top of YOUR library (CR 401.4): a
    ``PutAtLibraryPosition`` whose ``position`` is ``Top`` (Brainstorm's
    hand-to-top; Sensei's Divining Top's SelfRef top) or the
    ``PutOnTopOrBottom`` choice form, over YOUR object (filter controller
    You / ``SelfRef``). The position gate keeps the ``NthFromTop``
    precise-insertion removal (Chronostutter) and the ``Bottom`` cleanup
    (Aethermage's Touch) out.

    ADR-0038 W3 batch 4 (draw-etb-tokens cluster), two widening arms,
    corpus-verified card-by-card against ``old_ir_for`` (never assumed):

    * **Nested-grant descent** (mechanism b — the ``_GRANT_ABILITY_MOD_TAGS``
      ``.definition`` precedent :func:`_self_pump`'s sibling scan already
      establishes): a ``GrantAbility``/``GrantTrigger``/``GrantStaticAbility``
      modification's OWN ``.definition`` sub-tree is scanned for a nested
      ``PutAtLibraryPosition``/``PutOnTopOrBottom`` (Scion of Halaster's
      Background grants Commander creatures a "look at the top two, one to
      graveyard, other back on top" replacement — the put node lives under
      ``GrantAbility.definition.sub_ability``). Deliberately NOT a blanket
      ``iter_typed_nodes(unit.node)`` descent: that ALSO reaches a modal
      ``RollDie`` result's own put-on-top branch (Loathsome Troll's
      graveyard-recursion die-roll outcome), which legacy's project.py never
      walks for this concept — corpus-verified as a genuine crosswalk-only
      over-fire when tried, reverted.
    * **Back-reference widening + self-anchor confirmation**: a
      ``ParentTarget``/``TrackedSet``/``ExiledBySource``/controller-less
      ``Or`` target is accepted when the OWNING ability's own clause text
      (falling back to the whole-card oracle on a single-ability card) names
      the self anchor via :func:`_topdeck_stack_self` — the legacy
      ``supplement._recover_topdeck_stack_self`` idiom, reused verbatim. This
      is the SAME disambiguation legacy itself needs: phase's Dig /
      PutAtLibraryPosition carry NO library-OWNER field at all, so a self
      top-stack (Scroll Rack's ``ExiledBySource``; Doomsday's tutor-fed
      ``TrackedSet``; Mirror of Fate's exile-fed ``TrackedSet``; Nael, Avizoa
      Aeronaut / Thassa's Oracle / Slimefoot's Survey's dug ``ParentTarget``;
      Mortuary's dies-trigger ``ParentTarget``; Triumph of Saint Katherine's
      ``ExileTop``-fed ``ParentTarget``) and an opponent-library tuck (Cruel
      Fate, Sealed Fate — "put ... on top of THAT PLAYER's library",
      structurally byte-identical Dig/TrackedSet nodes) are indistinguishable
      without it. A REPLACEMENT-origin unit is excluded from this arm —
      legacy's project.py never walks ``card.replacements`` for this concept
      at all (Library of Leng's discard-to-top replacement carries no
      topdeck_stack Effect in ``old_ir_for``, verified), so admitting it here
      would be a beyond-legacy claim this batch does not adjudicate. CR
      401.4 vests the effect in whoever the ability names as the library's
      owner, never the digger.

    An idiom with NO topdeck_stack node at all — a "put a card from your
    hand on top of your library" ACTIVATION COST (Leashling, Penance, Hidden
    Retreat) or a modal reveal-then-place ``Dig`` phase doesn't fully
    structure (Munda, Ambush Leader's Rally; Diabolic Vision) — needs the
    legacy kept-mirror itself: ``_sweep_detectors.TOPDECK_STACK_SWEEP_REGEX``
    run FLAT over the reminder-stripped whole-card oracle (card-level, not
    unit/node-gated — the SAME scope legacy's own mirror runs at), reused
    single-source. Deliberately the NARROW sweep, not the broad self-anchor:
    the self-anchor scan would ALSO over-admit a "look at N, may put one
    back on top" selection idiom with no put node at all (Telling Time,
    Silhana Wayfinder, Sage of Days, Gurmag Nightwatch, Devourer of Destiny,
    Fertile Thicket, Planar Atlas, Gutless Plunderer — all corpus-verified
    to carry NO topdeck_stack Effect in ``old_ir_for``; that idiom is
    topdeck_selection's territory, not topdeck_stack's). Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "replacement":
            continue
        put_nodes = [c.node for c in unit.effect_concepts("put_library_position")]
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) not in _GRANT_ABILITY_MOD_TAGS:
                continue
            d = getattr(n, "definition", None)
            if d is None:
                continue
            put_nodes += [
                m
                for m in iter_typed_nodes(d)
                if tag_of(m) in ("PutAtLibraryPosition", "PutOnTopOrBottom")
            ]

        def self_anchor(unit: AbilityUnit = unit) -> bool:
            text = getattr(unit.node, "description", None) or tree.oracle or ""
            return _topdeck_stack_self(text)

        for node in put_nodes:
            if tag_of(node) == "PutAtLibraryPosition" and (
                tag_of(getattr(node, "position", None)) != "Top"
            ):
                continue
            tgt = getattr(node, "target", None)
            ttag = tag_of(tgt)
            if ttag == "SelfRef" or filter_controller(tgt) == "You":
                return [Signal("topdeck_stack", "you", "", "", tree.name, "high")]
            if (
                ttag
                in (
                    "ParentTarget",
                    "TrackedSet",
                    "ExiledBySource",
                    "Or",
                )
                and self_anchor()
            ):
                return [Signal("topdeck_stack", "you", "", "", tree.name, "high")]

    # Legacy kept-mirror, reused verbatim (CARD-level, not unit/node-gated —
    # mirrors the deleted ``_signals_ir``'s own ``TOPDECK_STACK_SWEEP_REGEX`` producer
    # exactly, run flat over the reminder-stripped whole-card oracle):
    # recovers the two idioms phase drops structurally with no residue at
    # all — a "put a card from your hand on top of your library" ACTIVATION
    # COST (Leashling, Penance, Hidden Retreat: no Dig/put node whatsoever)
    # and a modal reveal-then-place ``Dig`` with no separate put node
    # (Munda, Ambush Leader's Rally).
    stripped = re.sub(r"\([^)]*\)", " ", tree.oracle or "")
    if _TOPDECK_STACK_SWEEP_RE.search(stripped):
        return [Signal("topdeck_stack", "you", "", "", tree.name, "high")]
    return []


def _combat_buff_engine(tree: ConceptTree) -> list[Signal]:
    """combat_buff_engine — combat-keyed pump (CR 508 / 509.3a): a trigger in
    the combat frame (attacks / blocks / becomes-blocked / begin-combat) with
    a ``pump`` / ``place_counter`` effect in the SAME unit (granularity a) —
    Anafenza's attack counter, Accorder Paladin's Battle-cry ``PumpAll``
    (the keyword expansion the deleted regex missed — checklist #3: the
    keyword tags payoffs, so the structural read wins). The batch-9
    adjudicated fix also reads the fully-typed ``AddPower``/``AddToughness``
    mod sites a ``GenericEffect`` confers ("target artifact creature you
    control gets +2/+2 and gains indestructible" — Aethershield Artificer:
    the pump is a nested static modification, not a ``Pump`` effect; the
    overlay surfaces it as a static-role ``pump`` concept in the SAME unit).
    ``deals_damage`` is DELIBERATELY excluded so Renown / self_counter_grow
    shapes (Skirk Commando) never over-fire. Scope "you".
    """
    for unit in tree.units:
        ev = unit.trigger_event
        combat = ev in _COMBAT_BUFF_EVENTS or (
            ev == "phase" and getattr(unit.node, "phase", None) == "BeginCombat"
        )
        if not combat:
            continue
        if any(c.concept in ("pump", "place_counter") for c in unit.effects) or any(
            c.concept == "pump" for c in unit.statics
        ):
            return [Signal("combat_buff_engine", "you", "", "", tree.name, "high")]
    return []


def _land_sacrifice_matters(tree: ConceptTree) -> list[Signal]:
    """land_sacrifice_matters — the lands-to-graveyard PAYOFF (CR 701.21a /
    603.6c): a dies / leaves / sacrificed trigger whose watched OBJECT is a
    Land you control (The Gitrog Monster's ``ChangesZoneAll`` → Graveyard
    land watcher — the mass mode joins via the §0.2 derivation). Gate #6:
    subject controller you (an opponent-land watcher is not your payoff); a
    land-ETB watcher is the landfall lane. The you-sacrifice-a-land OUTLET
    (Gitrog's upkeep unit) is the already-ported ``land_sacrifice_makers`` —
    keys disjoint. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event not in _LAND_SAC_EVENTS:
            continue
        if "Land" not in trigger_subject(unit.node):
            continue
        if trigger_subject_scope(unit.node) != "you":
            continue
        return [Signal("land_sacrifice_matters", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W5 tails — the gap-marker text-fallback anchor for the
# "you/an opponent own(s) a card in exile" self-condition (Howling Galefang
# / Warden of the Beyond / Dreadlight Monstrosity — see the arm below).
_EXILE_OWNS_COND_TEXT_RX = re.compile(r"owns? a card in exile")


def _exile_matters_time_counter_reuse(filt: object) -> bool:
    """Whether a ``Typed`` filter's OWN ``Counters`` property names the
    "time" counter kind — the Suspend-mechanic-reuse tell (CR 702.62a) the
    exile_matters lane excludes corpus-wide (Timecrafting / Shivan
    Sand-Mage / Fury Charm / Timebender / Clockspinning / Rose Tyler / Amy
    Pond all structure a suspended card as "InZone: Exile" + "Counters:
    time" the SAME way a genuine exiled-with-counter pile does)."""
    if tag_of(filt) != "Typed":
        return False
    for prop in getattr(filt, "properties", None) or []:
        if tag_of(prop) != "Counters":
            continue
        kind_node = getattr(prop, "counters", None)
        if getattr(kind_node, "data", None) == "time":
            return True
    return False


def _has_suspend_keyword_property(node: object) -> bool:
    """Whether NODE's own subtree carries a ``HasKeywordKind(value='Suspend')``
    property — the STRUCTURAL Suspend tell (CR 702.62a), distinct from the
    "time" counter KIND proxy :func:`_exile_matters_time_counter_reuse` reads.
    ADR-0039 W7 (2026-07-12): Shivan Sand-Mage / Fury Charm / Timebender /
    Timecrafting's ``RemoveCounter`` targets are an ``Or[Typed(Battlefield),
    Typed(Exile + HasKeywordKind='Suspend' + Counters='time')]`` — the Suspend
    keyword property is what actually marks the reused mechanic, not the
    counter's name. Alaundo the Seer's own "remove a time counter from each
    other card you own in exile" RemoveCounter target is a bare
    ``Typed(Another, Owned, InZone=Exile)`` with NO ``HasKeywordKind`` branch
    at all (a home-brewed counter mechanic that merely reuses the "time"
    counter's flavor name, not CR 702.62a Suspend) — corpus-verified this
    session: of every commander-legal ``RemoveCounter{counter_type=time}``
    node whose target reaches the exile zone, Alaundo is the ONLY one
    without this property (2026-07 census, 5 hits total)."""
    for n in iter_typed_nodes(node):
        if tag_of(n) == "HasKeywordKind" and getattr(n, "value", None) == "Suspend":
            return True
    return False


def _exile_ability_chain_effects(unit_node: object) -> list[object]:
    """Every step's OWN ``effect`` in a ``S_abilities``/``S_triggers``
    ability's ``sub_ability`` linked list, in EXECUTION order (trigger units
    wrap their first step under ``execute``)."""
    out: list[object] = []
    cur = getattr(unit_node, "execute", None) or unit_node
    while cur is not None:
        eff = getattr(cur, "effect", None)
        if eff is not None:
            out.append(eff)
        cur = getattr(cur, "sub_ability", None)
    return out


def _exile_then_tracked_set_size(unit_node: object) -> bool:
    """True once a LATER chain step (after an earlier step exiled cards —
    ``ChangeZone{destination: Exile}``) carries a bare ``TrackedSetSize`` qty
    — Rysorian Badger's "exile up to two target creature cards ... you gain
    1 life for each card exiled this way" (``GainLife`` amount=
    ``TrackedSetSize()`` as the VERY NEXT chain step, no ``caused_by`` filter
    the way :func:`FilteredTrackedSetSize` cards carry it). ORDER-SENSITIVE:
    Revival Experiment's superficially similar shape ("return ... you lose 3
    life for each card returned this way. Exile ~.") reverses the order — the
    ``TrackedSetSize`` counts an EARLIER return-from-graveyard step, and the
    self-exile ``ChangeZone(SelfRef)`` is a LATER, unrelated one-shot
    housekeeping step (consuming the spell itself, not building an exile
    pile) — so walking in execution order and gating the TrackedSetSize scan
    on "exile already seen" correctly excludes it. 2026-07 corpus census:
    of every commander-legal unit carrying a bare ``TrackedSetSize`` node,
    exactly 2 also carry an exile ``ChangeZone`` anywhere in the same unit
    (Rysorian Badger, Revival Experiment) — this order check is what
    separates them. CR 406.1/601.2c ("this way" scaling)."""
    seen_exile = False
    for eff in _exile_ability_chain_effects(unit_node):
        if seen_exile and any(
            tag_of(n) == "TrackedSetSize" for n in iter_typed_nodes(eff)
        ):
            return True
        if tag_of(eff) == "ChangeZone" and getattr(eff, "destination", None) == "Exile":
            seen_exile = True
    return False


def _exile_matters(tree: ConceptTree) -> list[Signal]:
    """exile_matters — exile-as-resource payoff (CR 406.1): a trigger
    watching cards LAND in exile (``ChangesZone`` destination Exile) whose
    watched object is NOT the card itself (Ketramose's "whenever one or more
    cards leave the battlefield and/or graveyards … [to] exile"). The
    ``SelfRef`` gate keeps the suspend/foretell/blink SELF-state watcher
    (God-Eternal Bontu's "when this is exiled" shuffle-in) out — the live
    #24b boundary (CR 702.62a analog); the ``AttachedTo`` gate keeps the
    enchanted-object recursion Aura (Kaya's Ghostform — insurance on ONE
    object, not exile-as-resource) out. A dig-and-cast engine with no
    exile-watcher trigger (Aetherworks Marvel) never fires. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if change_zone_dirs(unit.node)[1] != "Exile":
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) in ("SelfRef", "AttachedTo"):
            continue
        return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # recall-completion b2 (ADR-0034): the STRUCTURAL in:exile count-operand / P/T
    # scaler — an effect whose VALUE counts cards STANDING in exile as a resource: a
    # count-operand filter carrying ``InZone Exile`` (Kaya, Orzhov Usurper) or a
    # ``ZoneCardCount`` over the exile zone in the amount/count/value subtree (Beacon
    # Bolt, Ral, Izzet Viceroy — a P/T / X scaler). Distinct from ``to:exile`` removal
    # / ``from:exile`` cast / opponent GY-hate (those read the effect's ChangeZone /
    # target, never a count operand — so no re-conflation of the sibling exile lanes).
    # The old IR reads ``"in:exile" in e.zones``; this reads the count STRUCTURALLY
    # (ADR-0035 prefer-structural). CR 406.1.
    for unit in tree.units:
        for c in unit.effects:
            if c.role == "cost":
                continue
            cof = count_operand_filter(c.node)
            if cof is not None and "Exile" in filter_inzone_zones(cof):
                return [Signal("exile_matters", "you", "", c.raw, tree.name, "high")]
            for fld in ("amount", "count", "value"):
                sub = getattr(c.node, fld, None)
                if sub is not None and any(
                    tag_of(n) == "ZoneCardCount" and getattr(n, "zone", None) == "Exile"
                    for n in iter_typed_nodes(sub)
                ):
                    return [
                        Signal("exile_matters", "you", "", c.raw, tree.name, "high")
                    ]
    # recall-completion b2 (ADR-0034): the CONDITION count-in-exile arm — an ability
    # gated on the NUMBER of cards standing in exile (Ketramose, the New Dawn — "can't
    # attack or block unless there are seven or more cards in exile"): a
    # ``ZoneCardCount`` over the exile zone inside a condition site. Distinct from a
    # suspend / foretell source-in-exile SELF gate (that references the SOURCE's own
    # exile state, never carries a ZoneCardCount). CR 406.1. Ketramose also carries an
    # exile-landing trigger (the arm above), so this is currently subsumed on the
    # corpus; kept for structural completeness matching the IR condition arm (a future
    # count-in-exile card with no trigger stays covered).
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            if any(
                tag_of(n) == "ZoneCardCount" and getattr(n, "zone", None) == "Exile"
                for n in iter_typed_nodes(site)
            ):
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W3 batch 5 — the STATIC P/T-scaler arm: a characteristic-defining
    # ``SetDynamicPower``/``SetDynamicToughness`` (or any static modification)
    # carries its exile-zone count operand inside ``modifications``, not on an
    # ``amount``/``count``/``value`` field the effect-role loop above reads —
    # static units never populate ``unit.effects`` at all. Two count-operand
    # shapes both count the exile zone: ``ZoneCardCount{zone: Exile}``
    # (Crackling Drake's "total number of instant and sorcery cards you own
    # in exile and in your graveyard") and ``ObjectCount`` over a filter
    # carrying ``InZone{zone: Exile}`` (Cosmogoyf's "number of cards you own
    # in exile" — a plain card-count, not type-restricted). A direct deep
    # scan of the static node's own subtree reaches both. CR 406.1 / 613.4c.
    #
    # ADR-0038 W3 batch 6 widens a THIRD shape: ``ObjectCount`` over a filter
    # carrying ``ExiledBySource`` instead of ``InZone{Exile}`` — Lumbering
    # Battlement's "gets +2/+2 for each card exiled WITH IT" counts its OWN
    # maker-populated pile the same way Gorex's ChooseFromZone arm does, but
    # as a static P/T-scaler rather than a triggered choice.
    for unit in tree.units:
        if unit.origin != "static":
            continue
        if any(
            (tag_of(n) == "ZoneCardCount" and getattr(n, "zone", None) == "Exile")
            or (
                tag_of(n) == "ObjectCount"
                and (
                    "Exile" in filter_inzone_zones(getattr(n, "filter", None))
                    or any(
                        tag_of(x) == "ExiledBySource"
                        for x in iter_typed_nodes(getattr(n, "filter", None))
                    )
                )
            )
            for n in iter_typed_nodes(unit.node)
        ):
            return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W3 batch 5 — the "exiled with ~" persistent-pile arm: a
    # ``ChooseFromZone{zone: Exile, filter: ExiledBySource}`` (Gorex's
    # "choose a card at random exiled with Gorex") reads directly from the
    # standing exile pile a MAKER put there earlier as a resource. The
    # ``filter`` gate is load-bearing: phase ALSO emits a bare
    # ``ChooseFromZone{zone: Exile, filter: MISSING}`` as an internal staging
    # detail for "look at the top N, separate into piles, choose one" effects
    # (Steam Augury, Gifts Ungiven, Intuition) — the piles sit in exile as an
    # implementation artifact, never named "exile" in the oracle text at all,
    # so a bare zone match massively over-fires (71-card corpus check). CR
    # 406.1.
    for unit in tree.units:
        for c in unit.effects:
            if (
                getattr(c.node, "zone", None) == "Exile"
                and tag_of(c.node) == "ChooseFromZone"
                and tag_of(getattr(c.node, "filter", None)) == "ExiledBySource"
            ):
                return [Signal("exile_matters", "you", "", c.raw, tree.name, "high")]
    # ADR-0038 W3 batch 6 — the "exiled with a [named] counter" persistent-
    # pile arm: a per-card-unique counter kind (Altaïr Ibn-La'Ahad's
    # "memory" counter, Karn Scion of Urza's "silver" counter, Lara Croft's
    # "discovery" counter) tracks a maker-populated exile pile the SAME way
    # Gorex's ``ExiledBySource`` does, but structured as a plain ``Typed``
    # filter carrying BOTH an ``InZone{zone: Exile}`` property AND a
    # ``Counters`` property (of ANY kind) — reached anywhere in the unit's
    # subtree (``CopyTokenOf.source_filter``, a ``ChangeZoneAll.target``
    # filter, etc.), not just a ``ChooseFromZone``. Gated OFF the "time"
    # counter kind specifically: phase structures Suspend's "target
    # permanent or suspended card [with a time counter]" the SAME way
    # (a suspended card IS structurally in exile with a time counter, CR
    # 702.62a) even though the card's OWN oracle text never says "exile" at
    # all (Shivan Sand-Mage, Fury Charm, Timebender, Timecrafting,
    # Clockspinning, Rose Tyler, Amy Pond — every commander-legal "time
    # counter on a suspended card" hit in the 2026-07 corpus census) — that
    # population is the suspend-mechanic's own generic counter manipulation,
    # not an exile-as-resource build-around; excluding it is zero-guess
    # (every non-"time" counter kind in the census names a card-specific
    # exile-pile mechanic). CR 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "Typed":
                continue
            props = getattr(n, "properties", None) or []
            has_exile = any(
                tag_of(p) == "InZone" and getattr(p, "zone", None) == "Exile"
                for p in props
            )
            if not has_exile:
                continue
            for p in props:
                if tag_of(p) != "Counters":
                    continue
                kind_node = getattr(p, "counters", None)
                kind = getattr(kind_node, "data", None)
                if kind == "time":
                    continue  # the Suspend-mechanic reuse — never guess
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W3 batch 6 — the RemoveCounter-from-an-exiled-card arm: Mari,
    # the Killing Quill's granted ability ("remove a hit counter from a card
    # that player owns in exile") is a ``RemoveCounter`` whose OWN ``target``
    # filter carries ``InZone{zone: Exile}`` — the counter kind lives on the
    # effect's ``counter_type`` field here, not a filter ``Counters``
    # property, so the persistent-pile arm above (which reads filter
    # properties) misses it; a direct field read closes the gap.
    # ADR-0039 W7 (2026-07-12): the exclusion gate is now the STRUCTURAL
    # Suspend tell (:func:`_has_suspend_keyword_property` — an
    # ``Or``-branch carrying ``HasKeywordKind='Suspend'``), not the
    # ``counter_type == 'time'`` NAME proxy the W3 arm used — the name
    # proxy over-excluded Alaundo the Seer, whose own "remove a time
    # counter from each other card you own in exile" is a home-brewed
    # counter mechanic with NO Suspend keyword property anywhere in its
    # target, not CR 702.62a reuse (see the helper's own docstring for the
    # corpus census that verified this correctly still excludes Shivan
    # Sand-Mage / Fury Charm / Timebender / Timecrafting). CR 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) != "RemoveCounter":
                continue
            target = getattr(n, "target", None)
            if _has_suspend_keyword_property(target):
                continue  # the Suspend-mechanic reuse — never guess
            if "Exile" in filter_inzone_zones(target):
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0039 W7 (2026-07-12) — the order-sensitive "for each card exiled
    # this way" TrackedSetSize arm (:func:`_exile_then_tracked_set_size`):
    # Rysorian Badger's own life-gain scales off a bare ``TrackedSetSize``
    # (no ``caused_by`` filter — distinct from the ``FilteredTrackedSetSize``
    # arm above) chained directly after its own exile step. CR 406.1/601.2c.
    for unit in tree.units:
        if _exile_then_tracked_set_size(unit.node):
            return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — the "for each card exiled this way" count arm: a
    # ``FilteredTrackedSetSize`` qty whose ``caused_by`` field is
    # ``'Exiled'`` counts the cards an EARLIER effect in the SAME
    # resolution chain just exiled — the scaling payoff
    # supplement.py's deleted regex intentionally kept as a real
    # exile_matters member (Crypt Incursion's "gain 3 life for each card
    # exiled this way", the March cycle's "costs {2} less to cast for each
    # card exiled this way", Titania's Command / Kaya, Geist Hunter's -6 /
    # Haunting Echoes / Honor the Fallen / Necromancer's Covenant / Grime
    # Gorger / Hour of Eternity / Quintorius Kand / Suffer the Past /
    # Mizzix's Mastery / Heartless Conscription / Reap Intellect).
    # ``caused_by`` also carries Destroyed/Sacrificed/Discarded/Milled for
    # OTHER zone-change payoffs (2026-07 corpus census: 57 Exiled / 30
    # Destroyed / 19 Sacrificed / 13 Discarded / 5 Milled) — gated narrowly
    # to ``'Exiled'``. CR 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) == "FilteredTrackedSetSize"
                and getattr(n, "caused_by", None) == "Exiled"
            ):
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — the "draw a card for each card exiled from your
    # hand this way" arm: the "hate a card name" cycle (The Stone Brain /
    # Unmoored Ego / Lost Legacy / Necromentia / Deadly Cover-Up / The End
    # / Test of Talents) pays its victim off with a bare
    # ``ExiledFromHandThisResolution`` qty — a dedicated node with no
    # fields at all. 2026-07 corpus census: exactly these 7 commander-legal
    # cards, zero false positives. CR 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "ExiledFromHandThisResolution":
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — the companion-adjacent "face-up exile" search arm:
    # Karn, the Great Creator's -2 / Coax from the Blind Eternities read a
    # ``SearchOutsideGame`` whose ``source_pool`` is
    # ``SideboardAndFaceUpExile`` — the ONLY ``source_pool`` variant the
    # substrate carries (2026-07 census), so tagging it is zero-guess. CR
    # 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if (
                tag_of(n) == "SearchOutsideGame"
                and tag_of(getattr(n, "source_pool", None)) == "SideboardAndFaceUpExile"
            ):
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — the "spells you cast from exile gain keyword X"
    # arm: a STATIC ability whose OWN ``affected`` scope is a Typed filter
    # carrying InZone{Exile} (Wild-Magic Sorcerer's cascade grant, Party
    # Thrasher / Hoarding Broodlord's convoke grant, Rassilon, the War
    # President's conspire grant) restricts a keyword grant to spells CAST
    # FROM the exile zone — a build-around that wants an ongoing exile pile
    # to cast from, not a one-shot cast enabler. 2026-07 census: exactly
    # these 4 commander-legal cards carry this shape. CR 406.1 / 613.4c.
    for unit in tree.units:
        if unit.origin != "static":
            continue
        aff = getattr(unit.node, "affected", None)
        if aff is not None and "Exile" in filter_inzone_zones(aff):
            return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — gap-marker text fallback, narrowly scoped (the
    # SAME precedent ``plus_one_matters`` established for Pipsqueak /
    # Skarrgan Hellkite, CR 602.5): three cards' "you/an opponent own(s) a
    # card in exile" self-condition never reaches phase's typed grammar at
    # all. Howling Galefang / Warden of the Beyond decorate as
    # ``Unrecognized(text=…)`` (a raw parse residue); Dreadlight
    # Monstrosity's activation restriction decorates as an EMPTY
    # ``RequiresCondition`` (``data.inner is None``) with no text of its
    # own, so the fallback reads the SAME unit's own ``description`` field
    # instead. A 2026-07 corpus census of "owns? a card in exile" across
    # every commander-legal card found exactly these 3, zero false
    # positives. CR 406.1.
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for cond in _condition_leaves(site):
                ctag = tag_of(cond)
                if ctag == "Unrecognized":
                    text = str(getattr(cond, "text", "") or "")
                    if _EXILE_OWNS_COND_TEXT_RX.search(text):
                        return [
                            Signal("exile_matters", "you", "", "", tree.name, "high")
                        ]
                elif ctag == "RequiresCondition":
                    data = getattr(cond, "data", None)
                    inner = data.inner if isinstance(data, MirrorVariant) else data
                    if inner is None:
                        desc = str(getattr(unit.node, "description", "") or "")
                        if _EXILE_OWNS_COND_TEXT_RX.search(desc):
                            return [
                                Signal(
                                    "exile_matters", "you", "", "", tree.name, "high"
                                )
                            ]
        # phase v0.35.2 residue drift for the SAME census: Dreadlight
        # Monstrosity's activation restriction no longer emits the empty
        # RequiresCondition — the clause parks as an
        # ``Unimplemented(name='activate')`` sub-effect carrying the
        # restriction sentence in its own description. Same three-card
        # census, same narrowly-scoped text anchor.
        for cn in unit.iter_concepts():
            node = cn.node
            if (
                tag_of(node) == "Unimplemented"
                and getattr(node, "name", None) == "activate"
                and _EXILE_OWNS_COND_TEXT_RX.search(
                    str(getattr(node, "description", "") or "")
                )
            ):
                return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0038 W5 tails — a Token/PutCounter-style effect's OWN scaling
    # count nests a ZoneCardCount/ObjectCount UNDER a wrapper field
    # (``enter_with_counters`` — Serpentine Curve / Slime Against
    # Humanity's "put X +1/+1 counters on it, where X is … cards you own in
    # exile") the amount/count/value-scoped scan above never reaches, and
    # an ``ObjectCount`` can also be WRAPPED inside a scaling operator
    # (Niko Defies Destiny's "gain 2 life for each foretold card you own in
    # exile" nests it under ``Multiply``) instead of sitting bare on
    # ``amount``. A full per-effect subtree scan (mirroring the STATIC
    # arm's own deep scan above) reaches both shapes regardless of nesting
    # depth or field name. The SAME "time" counter Suspend-mechanic-reuse
    # gate applies (Rose Tyler's "put a time counter on it for each
    # suspended card you own" sums an ``ObjectCount`` whose filter carries
    # BOTH ``InZone{Exile}`` and ``Counters: time`` — the identical
    # Suspend-reuse shape the other arms exclude; without the SAME gate
    # here this deep scan would silently re-admit her). CR 406.1.
    for unit in tree.units:
        for c in unit.effects:
            if c.role == "cost":
                continue
            for n in iter_typed_nodes(c.node):
                if tag_of(n) == "ZoneCardCount" and getattr(n, "zone", None) == "Exile":
                    return [
                        Signal("exile_matters", "you", "", c.raw, tree.name, "high")
                    ]
                if tag_of(n) == "ObjectCount":
                    filt = getattr(n, "filter", None)
                    if filt is None or _exile_matters_time_counter_reuse(filt):
                        continue
                    if "Exile" in filter_inzone_zones(filt) or any(
                        tag_of(x) == "ExiledBySource" for x in iter_typed_nodes(filt)
                    ):
                        return [
                            Signal("exile_matters", "you", "", c.raw, tree.name, "high")
                        ]
    # ADR-0038 W5 tails — the GENERAL exile-standing-target arm: ANY effect
    # (any origin) whose OWN ``target``/``filter`` field is a FRESH
    # ``Typed`` selection filter carrying ``InZone{zone: Exile}``
    # references a card STANDING in exile as a resource, regardless of
    # what the effect then DOES with it — send it to a graveyard (the
    # Eldrazi Processor cycle: Ruin Processor / Murk Strider / Ulamog's
    # Reclaimer / Mind Raker / Wasteland Strangler; Oblivion Sower puts it
    # onto the battlefield instead), cast it (Tasha, the Witch Queen's -3 /
    # Goliath Daydreamer / Draugr Necromancer / Boiling Rock Rioter /
    # Knowledge Pool / The Dragon-Kami Reborn — a ``CastFromZone`` whose
    # target is the SAME Typed+InZone shape), return it to hand (Rootcoil
    # Creeper's flashback-only recall; Sentinel of Lost Lore's first mode),
    # bury it (Sentinel's second mode, ``PutAtLibraryPosition``), or
    # aggregate a property across the whole pile (Ashiok, Wicked
    # Manipulator's -7 / Ulamog, the Defiler's ETB replacement — an
    # ``Aggregate`` qty whose OWN ``filter`` carries the same InZone
    # shape). The ``ParentTarget``/``TrackedSet``/``SelfRef`` blink tell
    # (Flickerwisp / Ephemerate / Banisher Priest all track ONE
    # already-known object through their OWN return step via those tags,
    # never re-select via a fresh Typed filter) stays excluded because
    # those tags are never ``"Typed"`` — 2026-07 census of every
    # commander-legal Typed target/filter carrying InZone{Exile}: 38 hits,
    # every one a genuine standing-exile-pile reference. The SAME "time"
    # counter Suspend-mechanic-reuse gate the arms above use is re-applied
    # here so this broader, later-checked arm can never re-admit Alaundo
    # the Seer / Rose Tyler / Amy Pond. CR 406.1.
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "RemoveCounter" and getattr(n, "counter_type", None) == (
                "time"
            ):
                continue
            for fname in ("target", "filter"):
                filt = getattr(n, fname, None)
                if tag_of(filt) != "Typed":
                    continue
                if _exile_matters_time_counter_reuse(filt):
                    continue
                if "Exile" in filter_inzone_zones(filt):
                    return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    # ADR-0039 W7 ledgered bridges — the residual upstream-parse-failure /
    # dropped-clause bucket (bridge_ledger.py rows, docstring there for the
    # full corpus accounting):
    for bridge_id in (
        "exile_grant_all_activated_abilities",
        "grolnok_cast_from_exile_counter_pile",
        "candlekeep_inspiration_exile_gy_pt_setter",
        "close_encounter_warped_exile_additional_cost",
        "kaya_emblem_cast_from_exile_drop",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("exile_matters", "you", "", "", tree.name, "high")]
    return []


def _energy_matters(tree: ConceptTree) -> list[Signal]:
    """energy_matters — an energy SINK payoff (CR 107.14: "to pay {E}, a
    player removes one energy counter"): a ``PayEnergy`` cost leaf
    (Whirler Virtuoso's ``Pay {E}{E}{E}: token``; Aetherworks Marvel's
    ``Composite[Tap, PayEnergy 6]``) buying a NON-mana effect. The non-ramp
    gate mirrors the live pay-life painland exclusion: a fixing land whose
    only pay-energy effect is mana (Aether Hub) is the mana base +
    energy_makers, not a sink engine. The "whenever you get {E}" doubler
    trigger has NO mode in v0.9.0 — SUPPLEMENT-FIXABLE (the oracle carries
    "you get {E}"; a Stage-3 re-categorizer arm can stamp the marker). Scope
    "you".
    """
    for unit in tree.units:
        if not any(
            tag_of(leaf) == "PayEnergy"
            for leaf in iter_cost_leaves(getattr(unit.node, "cost", None))
        ):
            continue
        if any(c.concept != "ramp" for c in unit.effects):
            return [Signal("energy_matters", "you", "", "", tree.name, "high")]
    return []


def _counter_move(tree: ConceptTree) -> list[Signal]:
    """counter_move — a counter RELOCATION engine (CR 122.1): a
    ``MoveCounters`` effect (Nesting Grounds). The kind-gated
    ``counter_manipulation`` and the kind-agnostic ``any_counter_makers``
    co-fire where already ported (additive); this adds only the dedicated
    key. A ``PutCounter`` placer (Renata) never fires. Scope "you".

    np_counters item 3: the ``synth_counter_move`` marker
    (``tree_synthesis._arm_dropped_counter_move``) covers the two corpus
    cards whose possessed-counters relocation clause phase drops WHOLE
    (Ambitious Augmenter, Heroic Sacrifice) — same key, same scope as their
    19 typed ``MoveCounters`` classmates. CR 122.1.
    """
    hits = tree.effect_concepts("move_counters")
    if hits:
        return [Signal("counter_move", "you", "", hits[0].raw, tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_counter_move":
            return [Signal("counter_move", "you", "", "", tree.name, "high")]
    return []


def _explore_matters(tree: ConceptTree) -> list[Signal]:
    """explore_matters — the explore PAYOFF (CR 701.44): a first-class
    ``Explored`` trigger mode ("whenever a creature you control explores" —
    Wildgrowth Walker; the live path reaches this via a raw discriminator on
    an event='other' marker, so the mode read is a structural fidelity
    gain). An explore DOER (Merfolk Branchwalker — ``Explore`` effect →
    explore_makers) never co-fires. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "explored":
            return [Signal("explore_matters", "you", "", "", tree.name, "high")]
    return []


def _dice_matters(tree: ConceptTree) -> list[Signal]:
    """dice_matters — the roll PAYOFF (CR 706.1): a ``RolledDie`` /
    ``RolledDieOnce`` trigger mode ("whenever you roll one or more dice" —
    Brazen Dwarf). A roller DOER (Adorable Kitten — ``RollDie`` effect →
    dice_makers) never co-fires. Scope "you".
    """
    for unit in tree.units:
        if unit.trigger_event == "rolled_die":
            return [Signal("dice_matters", "you", "", "", tree.name, "high")]
    return []


def _extra_upkeep_end(tree: ConceptTree) -> list[Signal]:
    """extra_upkeep / extra_end_step / extra_draw_step — extra non-combat
    phases (CR 500.8): an ``AdditionalPhase`` whose ``phase`` is Upkeep
    (Paradox Haze, Obeka), Draw, or End (Y'shtola Rhul). Paradox Haze's
    recipient is ``TriggeringPlayer`` under an Enchant-Player trigger — the
    lane fires scope "you" regardless, mirroring the live scope (an extra
    upkeep you distribute is the build-around). A combat phase is the
    disjoint ``extra_combats`` lane. Tiny lanes are deliberate (niche ≠
    skip).

    ADR-0039 W8 (KEPT-key promotion, extra_draw_step): an additional
    BEGINNING phase (phase v0.20 emits its first step, "untap") CONTAINS
    all three beginning-phase steps — untap, upkeep, AND draw, in that
    order (CR 501.1) — so it re-triggers upkeep AND draw-step payoffs
    (Sphinx of the Second Sun / Shadow of the Second Sun / Cyclonus, the
    Saboteur, all "additional beginning phase" — the legacy regex's
    "beginning phase" substring correctly recognized this too, CR 501.1).
    Decompose "untap" -> BOTH extra_upkeep and extra_draw_step. A bare
    "draw"/"drawstep" kind (an additional DRAW STEP alone, no full
    beginning phase) also maps straight to extra_draw_step — 0 commander-
    legal holders today, kept for shape-completeness with the sibling
    "upkeep"/"end" rows. Re-measured (ADR-0039 W8): both == 3 == the
    deleted regex producer's live set (Cyclonus/Sphinx/Shadow of the
    Second Sun), 0 lost, 0 over-fire.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for c in tree.effect_concepts("extra_phase"):
        kind = additional_phase_kind(c.node)
        keys: tuple[str, ...] = {
            "upkeep": ("extra_upkeep",),
            "untap": ("extra_upkeep", "extra_draw_step"),
            "draw": ("extra_draw_step",),
            "drawstep": ("extra_draw_step",),
            "end": ("extra_end_step",),
        }.get(kind, ())
        for key in keys:
            if key not in seen:
                seen.add(key)
                out.append(Signal(key, "you", "", c.raw, tree.name, "high"))
    return out


def _facedown_has_marker(node: object) -> bool:
    """Whether ANY typed node under ``node`` carries the ``FaceDown``
    predicate tag (a target/affected filter's ``properties``) or a
    ``Subtype: Face-down`` type-filter word — the structural read of
    legacy's ``_is_facedown_subject`` (Nosy Goblin's ``Destroy`` target,
    Etrata's granted-ability ``affected``, Kadena's ETB ``valid_card``).
    """
    for n in iter_typed_nodes(node):
        if tag_of(n) == "FaceDown":
            return True
        if "Face-down" in filter_subtypes(n):
            return True
    return False


# ADR-0038 W3 batch 6: the maker-vs-payoff boundary regexes. A morph/
# manifest/cloak/disguise MAKER's own reminder text and ETB-parity rider
# ("Turn it face up any time for its mana cost" / "As ~ enters or is
# turned face up, ...") ALWAYS names "face down"/"face up" too — batch 5
# proved the legacy population's naive text-idiom port conflates the two,
# exploding cw_only 3→126. ``_FACEDOWN_MAKER_IDIOM_RX`` excludes every
# maker-only idiom this corpus surfaced (reminder-completion, the
# "exile ... face-down pile" gambit mechanic and its "turn ... face up"
# follow-through, the self-referential turn-up rider, the ETB-parity
# "enters or is turned face up" template, and a bare "is turned face up"
# fragment phase sometimes double-decomposes into its own tiny ability
# unit alongside the full sentence). CR 702.37a/c (morph), 702.152/153
# (disguise), 701.62 (manifest dread).
_FACEDOWN_MAKER_IDIOM_RX = re.compile(
    r"face up any time for its"
    r"|\bpile\b"
    r"|exiled with (?:this|~|itself)"
    r"|as (?:this .{0,20}|~) ?(?:is|becomes) turned face up"
    r"|(?:as|when) (?:this .{0,30}|~) enters,? or is turned face up"
    r"|^(?:or |and )?is turned face up\.?$",
    re.IGNORECASE,
)
# A genuine cares-about reference: "face-down creature(s)"/"face-down
# permanent(s)" (either word order) or a "turn(ed) ... face up" clause —
# legacy's own ``_FACEDOWN_WORD`` + ``_FACEDOWN_NOUN`` shape, narrowed to
# require the noun so a hidden-info "exile ... face down" idiom (Scroll
# Rack, Bottled Cloister, hideaway lands — a CR 701 mechanic, NOT CR 708)
# never qualifies (CR 701 vs 708 boundary, corpus-verified).
_FACEDOWN_REF_HOOK_RX = re.compile(
    r"face[- ]down .{0,3}(?:creature|permanent)s?"
    r"|(?:creature|permanent)s? .{0,3}(?:is |are |that.s )?face[- ]down"
    r"|turn(?:ed)? .{0,20}face up",
    re.IGNORECASE,
)


def _facedown_node_descriptions(node: object) -> list[str]:
    return [
        d
        for n in iter_typed_nodes(node)
        if isinstance((d := getattr(n, "description", None)), str) and d
    ]


def _facedown_matters(tree: ConceptTree) -> list[Signal]:
    """facedown_matters — the face-down PAYOFF (CR 708.1). Structural hooks,
    widest to narrowest:

    * a ``TurnFaceUp`` EFFECT (the turner references existing face-down
      permanents — Break Open) or TRIGGER mode ("when this is turned face
      up" — CR 708.3), or the first-class ``ManifestDread`` node (CR
      701.62 — Abhorrent Oculus both MAKES the face-down 2/2 and selects
      for the theme, so maker + matters fire together);
    * a ``manifestdread`` TRIGGER EVENT — "whenever you manifest dread"
      (Paranormal Analyst) is reactive to the ACTION, not the making of it;
    * a ``FaceDown``-typed target/affected/trigger-subject filter anywhere
      in the unit (:func:`_facedown_has_marker` — Nosy Goblin's ``Destroy``
      target, Etrata's face-down-creatures grant, Kadena's face-down-ETB
      draw, Veiled Ascension, Tunnel Tipster, Cryptic Pursuit, Dream
      Chisel, Obscuring Aether, Ixidron, Primordial Mist);
    * an ``EnchantedIsFaceDown`` typed CONDITION (Unable to Scream's "as
      long as enchanted creature is face down, it can't be turned face
      up" lock) or a static ``mode == "CantBeTurnedFaceUp"`` (Karlov
      Watchdog);
    * an ``Unimplemented`` residue whose own ``name`` is phase's ``look``
      or ``turn`` discriminator AND whose description names "face" —
      narrower than a bare text scan (Smoke Teller/Aven Soulgazer's
      "look at target face-down creature", Showstopping Surprise/
      Backslide/Cyber Conversion/Illithid Harvester's "turn ... face
      down/up"), or an Unimplemented ``static_structure`` residue naming
      a morph-cost tax (Exiled Doomsayer);
    * LAST RESORT: any node's own description matching
      :data:`_FACEDOWN_REF_HOOK_RX` (a genuine "face-down creature(s)"/
      "face-down permanent(s)" reference or a "turn(ed) ... face up"
      clause — Qarsi Deceiver, Revealing Wind, Lens of Clarity, Spy
      Network, Illusionary Mask's bespoke "it's turned face up"), gated
      UNIT-WIDE (not per-node) by :data:`_FACEDOWN_MAKER_IDIOM_RX` — if
      any description in the SAME unit is a maker-only idiom, the whole
      unit is maker territory, so a sibling node's truncated echo of the
      same clause can't slip past the exclusion in isolation.

    Deliberately NOT a bare "face down"/keyword match (a plain morph/
    manifest/cloak/disguise MAKER's own reminder text and ETB-parity
    rider always names the mechanic too — batch 5's naive port exploded
    cw_only 3→126 on exactly this conflation; see
    :data:`_FACEDOWN_MAKER_IDIOM_RX`). Scope "you"/"any" per hook.
    """
    for unit in tree.units:
        if unit.trigger_event in ("turnfaceup", "manifestdread"):
            return [Signal("facedown_matters", "you", "", "", tree.name, "high")]
        if _facedown_has_marker(unit.node):
            return [Signal("facedown_matters", "you", "", "", tree.name, "high")]
        descs = _facedown_node_descriptions(unit.node)
        unit_is_maker_idiom = any(_FACEDOWN_MAKER_IDIOM_RX.search(d) for d in descs)
        for n in iter_typed_nodes(unit.node):
            t = tag_of(n)
            if t == "EnchantedIsFaceDown":
                return [Signal("facedown_matters", "you", "", "", tree.name, "high")]
            if t == "Unimplemented":
                name = getattr(n, "name", None)
                desc = getattr(n, "description", "") or ""
                if (
                    name in ("look", "turn")
                    and "face" in desc.lower()
                    and not unit_is_maker_idiom
                ):
                    return [
                        Signal("facedown_matters", "you", "", desc, tree.name, "high")
                    ]
                if name == "static_structure" and re.search(
                    r"morph costs? cost", desc, re.IGNORECASE
                ):
                    return [
                        Signal("facedown_matters", "you", "", desc, tree.name, "high")
                    ]
        if getattr(unit.node, "mode", None) == "CantBeTurnedFaceUp":
            return [Signal("facedown_matters", "you", "", "", tree.name, "high")]
    hits = tree.effect_concepts("turn_face_up")
    if hits:
        return [Signal("facedown_matters", "you", "", hits[0].raw, tree.name, "high")]
    for c in tree.effect_concepts("facedown"):
        if tag_of(c.node) == "ManifestDread":
            return [Signal("facedown_matters", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        descs = _facedown_node_descriptions(unit.node)
        if any(_FACEDOWN_MAKER_IDIOM_RX.search(d) for d in descs):
            continue
        for desc in descs:
            if _FACEDOWN_REF_HOOK_RX.search(desc):
                return [Signal("facedown_matters", "you", "", desc, tree.name, "high")]
    return []


LANES = (
    _impulse_top_play,
    _play_from_top,
    _counter_manipulation,
    _discard_matters,
    _opponent_draw_matters,
    _self_death_payoff,
    _dies_recursion,
    _creature_recursion,
    _card_draw_engine,
    _group_hug_draw,
    _target_player_draws,
    _activated_draw,
    _cantrip,
    _topdeck_selection,
    _topdeck_stack,
    _combat_buff_engine,
    _land_sacrifice_matters,
    _exile_matters,
    _energy_matters,
    _counter_move,
    _explore_matters,
    _dice_matters,
    _extra_upkeep_end,
    _facedown_matters,
)
