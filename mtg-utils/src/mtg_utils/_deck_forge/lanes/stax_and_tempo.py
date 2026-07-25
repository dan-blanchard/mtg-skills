"""Crosswalk signal lanes — enters-punish, tap lanes, tempo (dig/bounce/blink),
stax, land denial/protection, superfriends, and vehicles (split from
crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptTree,
    change_zone_dirs,
    counter_kind,
    counter_kind_any,
    counter_pred_kinds,
    detriment_directed_scope,
    double_target_kind,
    effect_filter,
    effect_owner_duration,
    effect_owner_player_scope,
    effect_owner_raw,
    effect_owner_targets_per_opponent,
    effect_reaches_player,
    explicit_recipient_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_non_types,
    filter_owned_controller,
    filter_subtypes,
    has_filter_property,
    iter_mod_sites,
    iter_nested_spellcast_static_modes,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    mod_keyword_name,
    modify_cost_mode,
    modify_cost_spell_filter,
    player_filter_tag,
    settap_state,
    static_mode_tag,
    tag_of,
    trigger_caster_scope,
    trigger_counter_filter,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import MirrorVariant
from mtg_utils._card_ir.tree_synthesis import (
    SynthesizedNode,
    _stax_structural_walk,
    has_structural_big_hand_makers,
    has_structural_big_hand_matters,
    has_structural_counter_distribute,
    has_structural_exert_matters,
    has_structural_keyword_counter,
    has_structural_kill_engine,
    has_structural_manland,
    has_structural_superfriends,
    has_structural_type_change,
    has_structural_vehicles_matter,
)
from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.lanes._shared import (
    _LAND_SUBTYPE_WORDS,
    _SELF_BLINK_RETURN_TAGS,
    _TAP_EVENTS,
    _kept,
    _site_raw,
)
from mtg_utils._deck_forge.signal_base import (
    Signal,
    _resolve_subject,
)


def _counter_place_trigger(tree: ConceptTree) -> list[Signal]:
    """counter_place_trigger — the counters-placed payoff (CR 122.1 + 603.2):
    a ``CounterAdded`` trigger whose typed ``counter_filter`` is NOT the lore
    kind. The typed Saga gate (CR 714.2b: a chapter IS a lore-CounterAdded
    trigger — 723 of 798 corpus) IMPROVES on live's type_line sniff; the
    card-subtype belt (``Saga`` in the card's own subtypes) rides over it.
    The opponent-side population punisher (Kros, Defense Contractor /
    Generous Patron — ``valid_card`` controller Opponent) is vetoed
    (checklist #6). Cards that PLACE counters via effect (Cathars' Crusade —
    a ChangesZone trigger + PutCounterAll, no CounterAdded mode) never fire.
    Scope "you" (live).
    """
    if "Saga" in tree.card_subtypes:
        return []
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "counter_added":
            continue
        ct, _threshold = trigger_counter_filter(unit.node)
        if ct == "lore":
            continue
        if filter_controller(getattr(unit.node, "valid_card", None)) == "Opponent":
            continue
        return [Signal("counter_place_trigger", "you", "", "", tree.name, "high")]
    return []


def _tribal_etb_multi(tree: ConceptTree) -> list[Signal]:
    """tribal_etb_multi — the tribal ETB-chain payoff (CR 603.6a): an
    ``enters`` trigger whose watched-object filter carries a vocab-validated
    CREATURE subtype, including Or-branch walks (Noxious Ghoul's
    ``Or[SelfRef, Typed[Zombie, Another]]``). The ``_subtypes`` vocab IS the
    precision gate: a generic Creature watcher (Soul Warden → the ported
    ``creature_etb``) and a non-creature-subtype watcher (an Aura/Equipment
    ETB) never fire. Scope "you" (live).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "enters":
            continue
        subs = filter_subtypes(getattr(unit.node, "valid_card", None))
        if any(_resolve_subject(s, CREATURE_SUBTYPES) for s in subs):
            return [Signal("tribal_etb_multi", "you", "", "", tree.name, "high")]
    return []


def _typed_enters_punish(tree: ConceptTree) -> list[Signal]:
    """typed_enters_punish — the "your things enter → burn the opponents"
    co-occurrence (CR 603.6a + 102.2/102.3, granularity a): an ``enters``
    trigger on a YOUR-controlled population whose SAME unit deals damage
    reaching opponents — the typed ``DamageEachPlayer {player_filter:
    Opponent}`` read (Witty Roastmaster — the shape live could only recover
    from raw "each opponent") or an opponent/each-scoped ``DealDamage``
    player recipient. Checklist #1/#5: the enterer's controller reads off
    the trigger's own ``valid_card``; the damage recipient off the effect's
    OWN player_filter/recipient node. The opponent-enterer punisher (Suture
    Priest's second trigger) and non-damage payoffs (Soul Warden) never
    fire. Scope "you" (live).
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "enters":
            continue
        if filter_controller(getattr(unit.node, "valid_card", None)) != "You":
            continue
        for c in unit.effect_concepts("deal_damage"):
            if not effect_reaches_player(c.node, unit.node):
                continue
            t = tag_of(c.node)
            if t in ("DamageEachPlayer", "DamageAll"):
                hit = player_filter_tag(c.node) in ("Opponent", "All")
            else:
                hit = explicit_recipient_scope(c.node) in ("opponents", "each")
            if hit:
                return [
                    Signal("typed_enters_punish", "you", "", c.raw, tree.name, "high")
                ]
    return []


def _noncreature_cast_punish(tree: ConceptTree) -> list[Signal]:
    """noncreature_cast_punish — the noncreature-spell punisher (CR 603.2 +
    102.2 — deliberately scope "any": "a player" includes you): a
    ``SpellCast`` trigger whose watched-spell filter carries a
    ``{Non: Creature}`` entry (Ruric Thar — the entry IS the discriminator,
    read via the negation-aware :func:`filter_non_types`). A Creature-typed
    cast watcher (Beast Whisperer) and an instant/sorcery-only watcher
    (Talrand → the ported ``spellcast_matters``) never fire. Caster gate
    (checklist #5, corpus-measured: 126 prowess-family over-fires without
    it): a YOU-cast noncreature REWARD ("whenever you cast a noncreature
    spell, ~ gets +1/+0" — Burning Prophet, ``valid_target {Controller}``)
    is prowess, not a punisher — live fires only the symmetric
    (recipient-less "a player casts" — Ruric Thar) and opponent-scoped
    halves.
    """
    for unit in tree.units:
        if unit.origin != "trigger" or unit.trigger_event != "cast_spell":
            continue
        if trigger_caster_scope(unit.node) == "you":
            continue  # the prowess/you-cast reward family — not a punisher
        if "Creature" in filter_non_types(getattr(unit.node, "valid_card", None)):
            return [Signal("noncreature_cast_punish", "any", "", "", tree.name, "high")]
    return []


# ADR-0037/0038 W3: the tap_down ParentTarget/TrackedSet clause-level
# fallback — "that player controls" (an anaphoric back-reference to an
# opponent named earlier in the SAME isolated clause) or an explicit
# "opponent(s) control(s)" phrase. Read via :func:`effect_owner_raw` (the
# DIRECT owning wrapper's own clause, never the unit's whole multi-clause
# description — see the call site), and only ever consulted AFTER a genuine
# Tap effect is already structurally confirmed, so this never broadens which
# cards carry a tap — only which DIRECTION an already-confirmed tap
# resolves to.
_OPPONENT_CONTROLS_TAP_RE = re.compile(
    r"\bthat player controls\b|\b(?:that |an |your )?opponents? controls?\b",
    re.IGNORECASE,
)
# ADR-0037/0038 W3: the tap_down trigger-phase mis-stamp idiom — "on each
# opponent's turn" — deliberately narrower than ``_OPPONENT_CONTROLS_TAP_RE``
# (see the call site for why "each player's" must NOT match).
_OPPONENTS_TURN_RE = re.compile(r"\bopponent'?s turn\b", re.IGNORECASE)
# ADR-0037/0038 W3 no-residue class: "for each opponent, tap ... THAT
# OPPONENT controls" (Omega, Heartless Evolution) — phase drops the
# per-opponent loop structure entirely, so only a whole-card, tightly-scoped
# idiom match recovers it (see the call site).
_FOR_EACH_OPPONENT_TAP_RE = re.compile(
    r"\bfor each opponent\b[^.]*\btap\b[^.]*\bopponent controls\b", re.IGNORECASE
)
_TAP_WORD_RE = re.compile(r"\btaps?\b", re.IGNORECASE)
# ADR-0038 W3 batch 2 unit 8 (tap_down follow-up): Unhinged Beast Hunt's
# Stickers-mechanic ability ("Whenever ~ attacks, tap each creature an
# opponent controls with the same power and/or same toughness as ~")
# defeats phase's parser entirely (an Unimplemented "unknown"-name residue
# — the {TK} placeholder-pip Stickers syntax, not a normal clause phase's
# grammar ever tokenizes), so no SetTapState node exists anywhere in the
# tree to read structurally. Last-resort whole-card text idiom,
# corpus-verified singleton (the only commander-legal card with this exact
# phrase).
_TAP_EACH_OPPONENT_CREATURE_RE = re.compile(
    r"tap each creature an opponent controls", re.IGNORECASE
)


def _tap_sentence(text: str) -> str:
    """The sentence(s) naming "tap" from a multi-sentence clause — isolates
    a compound description's OWN tap clause from an unrelated SIBLING
    clause naming a different creature's controller (Coordinated
    Clobbering: "Tap ... you control. They deal damage ... an opponent
    controls." — only the FIRST sentence is the tap's own; a period-joined
    compound is common when the tap is the OUTERMOST effect in its ability,
    so its "owner" per :func:`effect_owner_raw` is the whole multi-sentence
    text, not an isolated nested clause). Returns ``text`` unchanged when no
    sentence names "tap" (nothing to narrow)."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    hits = [s for s in sentences if _TAP_WORD_RE.search(s)]
    return " ".join(hits) if hits else text


def _tap_owner_text(tree: ConceptTree, unit: AbilityUnit, node: object) -> str:
    """The text source for the tap_down clause-level fallback: the DIRECT
    owning wrapper's own raw (:func:`effect_owner_raw`); when THAT is empty
    AND the unit's own top-level description is ALSO empty (Delirium: a
    single-ability spell whose "Cast this spell only during an opponent's
    turn" restriction is a card-level ``casting_restrictions`` field with
    no ability/wrapper description anywhere to carry it), falls all the way
    to the whole-card oracle text. Deliberately NOT a fallback when the
    unit's OWN description is merely non-empty but unrelated (Dread
    Cacodemon, Nihiloor: a real but DIFFERENT compound-sentence description
    exists — falling through past it to the card level would risk pulling
    in an unrelated sibling ability's text on a MULTI-ability card; a
    single-ability spell has no such sibling to confuse it with)."""
    raw = effect_owner_raw(unit.node, node)
    if raw:
        return raw
    if getattr(unit.node, "description", None):
        return ""
    return tree.oracle or ""


def _tap_lanes(tree: ConceptTree) -> list[Signal]:
    """tap_down + tapper_engine — the CR 701.26a tap-doer pair, one shared
    effect walk (a tap-as-COST emits no ``SetTapState`` effect — Prodigal
    Sorcerer — so pure-cost taps self-exclude, reproducing live's
    subject-is-not-None gate):

    * ``tap_down`` — (arm a) a ``SetTapState {state: Tap}`` whose target's
      controller is Opponent (Dungeon Geists; checklist #5 — the effect's
      own target node); (arm b) a ``Detain`` effect (Azorius Arrester —
      CR 701.35, all opponent-targeted corpus-wide). A controller-null tap
      (Master Decoy, Frost Titan) is arm-less here (live's strict opp gate).
      Scope "opponents".
    * ``tapper_engine`` — a ``SetTapState {state: Tap}`` with a REAL
      Typed/Or target, any controller (Master Decoy / Frost Titan), plus
      the typed ``CantUntap`` static-rider arm (live's raw-"untap"
      restriction arm — the mirror types it: Frost Titan / Dungeon Geists
      nested static ``mode: CantUntap``). Self-taps (SelfRef) and untap
      engines (state Untap) never fire. Scope "any".

    ADR-0037/0038 W3: ``TargetOpponent`` joins the always-opponent controller
    set; a no-residue text fallback (:data:`_OPPONENT_CONTROLS_TAP_RE`, run
    only AFTER a Tap effect is already structurally confirmed) recovers three
    shapes the effect's own ``target`` field never carries the digger on — a
    ``controller: You``/``TriggeringPlayer`` mis-stamp bound to an opponent
    named earlier in the clause, a ``controller: null`` "for each opponent"
    loop phase drops entirely, and a ``ParentTarget`` sub-effect whose real
    target filter lives on an earlier SequentialSibling. ``SkipNextStep{step:
    Untap}`` (a phase v0.20 addition superseding the old "no SkipStep node in
    v0.9.0" note) recovers the "skips their next untap step" tempo-skip
    structurally.

    Logged SUPPLEMENT tail (live-documented, phase-confirmed): the
    aura/morph untap-lock statics.

    ADR-0038 W3 batch 2 unit 8 (the tap_down measured-residual follow-up
    the SkipNextStep-only Yosei fix deliberately did not touch): a
    corpus-verified singleton text idiom
    (:data:`_TAP_EACH_OPPONENT_CREATURE_RE`) recovers Unhinged Beast
    Hunt's Stickers-mechanic "tap each creature an opponent controls with
    the same power and/or same toughness" — a genuine ``Unimplemented``
    parse failure (the {TK} placeholder-pip Stickers syntax defeats
    phase's grammar entirely, no SetTapState node anywhere in the tree).
    Two adjudicated SHEDS deliberately left non-firing (legacy over-fires,
    verified NOT structural gaps): Invasion of New Phyrexia // Teferi
    Akosa of Zhalfir's loyalty -3 ("Tap any number of untapped creatures
    YOU CONTROL...") taps YOUR OWN creatures as a cost for an unrelated
    removal effect — legacy's category-based read credits ANY "tap"
    effect to tap_down regardless of direction, a miscredit this typed
    ``controller: You`` gate already correctly excludes. Two cards were
    ALREADY firing correctly before this follow-up (kept, no fix needed,
    pinned for the first time): Icingdeath, Frost Tyrant's death-trigger
    Equipment-token grant (the GrantTrigger-in-a-created-Token arm
    above) and Kang Dynasty's Saga chapters (the "for each opponent" arm
    above).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        for c in unit.iter_concepts():
            if c.role != "effect":
                continue
            if c.concept == "tap_untap":
                if settap_state(c.node) != "Tap":
                    continue
                tgt = getattr(c.node, "target", None)
                ttag = tag_of(tgt)
                if ttag == "SelfRef":
                    continue  # self-tap, no real target
                if ttag in ("Typed", "Or", "And"):
                    fire("tapper_engine", "any", c.raw)
                ctrl = filter_controller(tgt)
                # b11 follow-up (b), adjudicated: DefendingPlayer is
                # opponent-directed BY RULE (CR 506.2 — the defending player
                # is an opponent of the attacker; 20/21 live-verified), so it
                # joins Opponent unconditionally. A TargetPlayer tap joins
                # ONLY under an attack/damage-trigger unit (Hammers of
                # Moradin's Myriad rider — ~25 of 44 live_only recovered);
                # the one-shot/activated TargetPlayer sweeps (Sleep,
                # Dawnglare Invoker) are the genuine supplement tail.
                # ADR-0037/0038 W3: ``TargetOpponent`` (a "target opponent"
                # PLAYER already chosen, "tap all creatures TARGET OPPONENT
                # controls" — Assassin Gauntlet, Tempest Caller, Dovin's -9,
                # Kiora Bests the Sea God's Dragons chapter) is unambiguously
                # opponent-directed by its own tag, joining Opponent
                # unconditionally like DefendingPlayer.
                # ADR-0037/0038 W3 follow-up: ``TriggeringPlayer``/``You``
                # join when the trigger's OWN watched-object filter is
                # itself opponent-scoped (War's Toll: "whenever AN OPPONENT
                # taps a land for mana, tap all lands THAT PLAYER
                # controls"; Mana Web: "whenever a land AN OPPONENT
                # controls is tapped for mana, tap all lands THAT PLAYER
                # controls" — a ``controller: You`` mis-stamp on the SAME
                # idiom) — ``valid_card.controller == "Opponent"`` on the
                # SAME trigger unit means the bound "that player"/"you" IS
                # that opponent by definition, never a bare "any player"
                # watcher.
                if (
                    ctrl in ("Opponent", "DefendingPlayer", "TargetOpponent")
                    or (
                        ctrl == "TargetPlayer"
                        and unit.origin == "trigger"
                        and unit.trigger_event in ("attacks", "deals_damage")
                    )
                    or (
                        ctrl in ("TriggeringPlayer", "You")
                        and unit.origin == "trigger"
                        and filter_controller(getattr(unit.node, "valid_card", None))
                        == "Opponent"
                    )
                ):
                    fire("tap_down", "opponents", c.raw)
                elif _OPPONENT_CONTROLS_TAP_RE.search(
                    _tap_sentence(_tap_owner_text(tree, unit, c.node))
                ):
                    # ADR-0037/0038 W3: a ``ParentTarget``/``TrackedSet``
                    # sub-effect whose REAL target filter lives on an
                    # earlier SIBLING in the SequentialSibling chain, never
                    # on this node (Mind Spiral, Snaremaster Sprite,
                    # Stunning Shot, Crashing Wave's stun-counter tail —
                    # "tap target creature an opponent controls and put a
                    # stun counter on it"). Read via the DIRECT owning
                    # wrapper's OWN isolated clause text
                    # (:func:`effect_owner_raw`), narrowed to the sentence
                    # actually naming "tap" (:func:`_tap_sentence`) —
                    # Coordinated Clobbering / Spirit Flare's OUTERMOST tap
                    # effect has NO nested wrapper of its own, so its
                    # "owner" is the whole multi-sentence ability
                    # ("Tap ... you control. They deal damage ... an
                    # opponent controls.") — the sentence split is what
                    # keeps that SIBLING clause's opponent reference from
                    # over-firing tap_down on a self-targeted tap
                    # (corpus-verified: an unsplit owner-raw match
                    # over-fired on both).
                    fire("tap_down", "opponents", c.raw)
                elif ctrl == "TargetPlayer" and effect_owner_targets_per_opponent(
                    unit.node, c.node
                ):
                    # ADR-0037/0038 W3: a "for each opponent, tap up to one
                    # target creature THAT PLAYER controls" loop (Juvenile
                    # Mist Dragon) — the ``TargetPlayer`` bound variable is
                    # ambiguous alone (b11's own docstring above), but the
                    # WRAPPER's ``multi_target.max`` scaling by opponent
                    # COUNT (``PlayerCount`` qty filtered to ``Opponent``)
                    # is unambiguous: CR 506.4's "each opponent" default.
                    fire("tap_down", "opponents", c.raw)
                elif ctrl is None and _FOR_EACH_OPPONENT_TAP_RE.search(
                    tree.oracle or ""
                ):
                    # ADR-0037/0038 W3 no-residue class: "for each
                    # opponent, tap up to one target permanent THAT
                    # OPPONENT controls" (Omega, Heartless Evolution's Wave
                    # Cannon) — phase drops the per-opponent loop structure
                    # ENTIRELY (``controller: null``, ``multi_target: Fixed
                    # (1)``, no ``repeat_for`` — the SAME SwallowedClause-
                    # class parser gap dig_until's own no-residue fallback
                    # recovers), so no per-unit field survives to read.
                    # Whole-card, gated on the rare, specific "for each
                    # opponent … tap … opponent controls" idiom (never a
                    # bare "opponent controls" — no cross-clause
                    # misattribution risk).
                    fire("tap_down", "opponents", c.raw)
                elif ctrl in ("You", "ScopedPlayer") and _OPPONENTS_TURN_RE.search(
                    getattr(unit.node, "description", None) or ""
                ):
                    # ADR-0037/0038 W3: "at the beginning of combat on each
                    # OPPONENT'S TURN, tap target creature that player
                    # controls" (Citadel Siege's Dragons mode, Sentinel of
                    # the Eternal Watch). Through phase v0.23.0 this was a
                    # ``controller: You`` mis-stamp (the same
                    # per-iteration-variable class as RevealUntil's [P28]
                    # "their library" bug); v0.35.2 stamps the honest
                    # ``ScopedPlayer`` turn-player back-reference instead —
                    # but the trigger still carries NO typed opponents-turn
                    # constraint, so the "opponent's turn" text gate stays
                    # the scope proof either way. Deliberately NARROWER
                    # than the ``_OPPONENT_CONTROLS_TAP_RE`` clause-level
                    # check above (requires the literal "opponent's turn",
                    # never "each PLAYER's turn/step") — Angel's Trumpet /
                    # Monsoon's genuinely SYMMETRIC "each player's end
                    # step, tap ... that player controls" must NOT fire
                    # (corpus-verified: an unscoped "that player controls"
                    # match alone over-fired on both).
                    fire("tap_down", "opponents", c.raw)
            elif c.concept == "detain":
                fire("tap_down", "opponents", c.raw)
            elif c.concept == "skip_next_step":
                # ADR-0037/0038 W3: ``SkipNextStep{step: Untap}`` (a phase
                # v0.20 addition — CR 502.3's "kept from untapping" family)
                # is a DISTINCT effect from SetTapState — "each opponent
                # skips their next untap step" (Brine Elemental, Shisato,
                # Whispering Hunter). Opponent-directed via EITHER the
                # effect's own ``target`` tag or the owning wrapper's
                # ``player_scope`` actor (Brine Elemental's TurnFaceUp
                # trigger carries the "each opponent" edict on the WRAPPER,
                # target itself reads Controller — the per-opponent
                # iteration variable, mirroring
                # effect_owner_player_scope's own Nihiloor precedent). A
                # bare TriggeringPlayer target joins ONLY under an
                # attack/damage-trigger unit, the same b11 discipline as
                # SetTapState's TargetPlayer arm above (Shisato's "deals
                # combat damage to a player, THAT PLAYER skips ...").
                #
                # ADR-0038 deferral sweep unit 5 (Dan's detriment-directed-
                # targeting principle): a bare targeted-player recipient
                # (Yosei, the Morning Star: "target player skips their next
                # untap step") is opponent-directed for SIGNAL purposes even
                # though CR 603.3d lets the controller legally target
                # themself — :func:`detriment_directed_scope` reads the
                # node's own recipient fields the same way this arm already
                # reads ``ttag`` (a targeted Player/Target tag -> "opponents",
                # a Controller/SelfRef/You tag -> "you"). The genuinely
                # beneficial self-target shape (Avizoa: "You skip your next
                # untap step" as an activation COST for a pump — no-fire
                # control) reads ``target=Controller()`` -> "you", correctly
                # excluded; ``detriment_directed_scope`` is additive here
                # (it never returns "opponents" for that shape).
                step = getattr(c.node, "step", None)
                if tag_of(step) != "Step" or getattr(step, "data", None) != "Untap":
                    continue
                tgt = getattr(c.node, "target", None)
                ttag = tag_of(tgt)
                owner_scope = effect_owner_player_scope(unit.node, c.node)
                if (
                    ttag in ("Opponent", "Opponents", "EachOpponent", "DefendingPlayer")
                    or owner_scope in ("Opponent", "Opponents", "EachOpponent")
                    or (
                        ttag == "TriggeringPlayer"
                        and unit.origin == "trigger"
                        and unit.trigger_event in ("attacks", "deals_damage")
                    )
                    or detriment_directed_scope(c.node) == "opponents"
                ):
                    fire("tap_down", "opponents", c.raw)
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) == "CantUntap":
                fire("tapper_engine", "any", _site_raw(sdef))
        # b11 follow-up (b) continued: a GRANTED attack-tap trigger — an
        # Aura/Equipment conferring "Whenever this creature attacks, tap
        # target creature defending player controls" (Grasp of the
        # Hieromancer, Conformer Shuriken: a ``GrantTrigger`` modification
        # whose inner trigger's effect chain carries the SetTapState).
        for _sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "GrantTrigger":
                continue
            trig = getattr(mod, "trigger", None)
            tmode = getattr(trig, "mode", None)
            tmode = tmode if isinstance(tmode, str) else tag_of(tmode)
            if tmode not in ("Attacks", "YouAttack", "DamageDone"):
                continue
            for tnode in iter_typed_nodes(getattr(trig, "execute", None)):
                if tag_of(tnode) != "SetTapState":
                    continue
                if settap_state(tnode) != "Tap":
                    continue
                tctrl = filter_controller(getattr(tnode, "target", None))
                if tctrl in ("Opponent", "DefendingPlayer", "TargetPlayer"):
                    fire("tap_down", "opponents", "")
    if "tap_down" not in seen and _TAP_EACH_OPPONENT_CREATURE_RE.search(_kept(tree)):
        fire("tap_down", "opponents", "")
    return out


def _tap_untap_matters(tree: ConceptTree) -> list[Signal]:
    """tap_untap_matters — the becomes-tapped/untapped payoff (CR 603.2e +
    701.26a): a trigger whose mode is ``Taps`` / ``TapsForMana`` (both the
    becomes-tapped family — Attentive Sunscribe) or ``Untaps`` (the Inspired
    payoff — Pain Seer; a SelfRef subject is live-INCLUDED, a genuine untap
    payoff). Tap DOERS (Master Decoy — a SetTapState effect, no Taps
    trigger) never fire. Scope "you".

    Bucket-B tail (ADR-0039 task #82, the step-7 open tombstone):
    Darksteel Garrison's "fortified land becomes tapped" and its 3 corpus
    siblings (Grand Marshal Macie, Roots of Life, Royal Decree) are an
    Unknown-mode trigger phase never tags ``Taps``/``Untaps`` at all;
    ``tree_synthesis._arm_tap_untap_becomes`` recovers the dropped event from
    the trigger's OWN ``mode.inner`` residue and emits the REAL "taps"/
    "untaps" concept, so this second loop reads it through the ordinary typed
    ``effect_concepts`` walk — keyed off the :class:`SynthesizedNode`
    identity so a live phase-classified trigger (the loop above) never
    doubles through this branch.
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in _TAP_EVENTS:
            return [Signal("tap_untap_matters", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        for concept in ("taps", "untaps"):
            for c in unit.effect_concepts(concept):
                if isinstance(c.node, SynthesizedNode):
                    return [
                        Signal("tap_untap_matters", "you", "", "", tree.name, "high")
                    ]
    return []


def _dig_until(tree: ConceptTree) -> list[Signal]:
    """dig_until — the reveal-until-a-condition deep dig (CR 701.20a): a
    ``RevealUntil`` effect whose ``player`` is the Controller (Hermit Druid —
    90 of 115 corpus). The opponent-library digs (``player``
    ParentTargetController / TriggeringPlayer / Typed — Telemin
    Performance-family mill/theft, the [P16]-adjacent direction gate) and
    the FIXED-count reveals (Fact or Fiction — a ``RevealTop`` node →
    topdeck_selection) never fire. The draw-replacement / Saga / grandeur
    residue phase emits no dig structure for is SUPPLEMENT — logged, live's
    narrowed residue mirror stays. Scope "you".
    """
    # [P28]: phase stamps player=Controller on "each opponent reveals cards
    # from the top of THEIR library" (Mind Grind family — the [P17]
    # mis-stamp on RevealUntil), so the digger gate alone passes on
    # opponent mills. All 69 both-members are "your library" digs
    # (parity-verified). Tier-1 (ADR-0036/0037 T10-finalize2 GLOBAL
    # FINALIZE-2 fold): the deleted lane-time "their library" veto (the
    # [P8]/[P21]-precedent screen) is relocated verbatim to the bucket-B
    # ``synth_dig_until`` node (:func:`_arm_dig_until`), read below.
    for c in tree.iter_concepts():
        if c.concept == "synth_dig_until":
            return [Signal("dig_until", "you", "", "", tree.name, "high")]
    return []


def _exile_until_leaves(tree: ConceptTree) -> list[Signal]:
    """exile_until_leaves — the O-Ring exile (CR 611.2b durations + 603.6c):
    a ``ChangeZone {destination: Exile}`` whose OWNING wrapper carries the
    ``UntilHostLeavesPlay`` duration (Banisher Priest; Oblivion Ring's ETB
    trigger — the duration on the FIRST trigger alone suffices, no
    cross-ability join). Checklist #5 zone/dest ([P2]/[P4] family): the
    destination must be Exile with the duration on the same node chain — a
    permanent exile (no duration → the ported ``exile_removal``) and the LTB
    return trigger alone (TrackedSet → Battlefield; CR 603.6c's
    from-anywhere caveat) never fire. Case law (Banisher Priest): "If a
    token is exiled this way, it will cease to exist." Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("change_zone"):
            if tag_of(c.node) != "ChangeZone":
                continue
            if change_zone_dirs(c.node)[1] != "Exile":
                continue
            if effect_owner_duration(unit.node, c.node) == "UntilHostLeavesPlay":
                return [
                    Signal("exile_until_leaves", "you", "", c.raw, tree.name, "high")
                ]
    return []


# ADR-0038 W3 batch 2 unit 2 — the typed_spellcast replicate-grant residue.
# "Each <Subtype> spell you cast has replicate" (Hatchery Sliver, Ian
# Chesterton's "Each Saga spell you cast has replicate") phase's static
# parser cannot express (an Unimplemented ``static_structure`` residue whose
# OWN description carries the parse-failure diagnostic wrapper, verbatim
# oracle text included) — a last-resort text idiom over that description,
# scoped to the exact "spell(s) you cast has/have replicate" tail so it
# never fires on an unrelated Unimplemented residue. Corpus-verified: the
# whole commander-legal bulk corpus has exactly 3 hits (Hatchery Sliver ->
# Sliver, Ian Chesterton -> Saga, Djinn Illuminatus -> "sorcery" — the third
# is not a creature-subtype vocab word so it silently drops via
# ``_resolve_subject``, never a false subject). CR 601.2f / 702.
_REPLICATE_GRANT_RX = re.compile(
    r"\b([A-Za-z]+?)s? spells? you cast has? replicate", re.IGNORECASE
)

# ADR-0038 W3 batch 2 unit 2 — the typed_spellcast alt-cost residue. Kentaro,
# the Smiling Cat's "You may pay {X} rather than pay the mana cost for
# Samurai spells you cast, where X is that spell's mana value" is an
# alternative-cost ``PayCost`` effect whose node carries NO subject field at
# all — phase drops the "for <Subtype> spells you cast" qualifier entirely
# (the effect is indistinguishable from an unrestricted X-cost grant). No
# structural node exists to recover; last-resort whole-card text idiom, read
# ONCE over the reminder-stripped kept oracle (not per-node). Corpus-
# verified: the whole commander-legal bulk corpus has exactly one card whose
# "for <word> spells you cast" resolves to a real creature-subtype vocab
# word (Kentaro -> Samurai); the other hits ("a", "permanent", "Rune") are
# not creature subtypes and silently drop via ``_resolve_subject``. CR 601.2f.
_ALT_COST_SPELLCAST_RX = re.compile(
    r"\bfor ([A-Za-z]+?)s? spells? you cast\b", re.IGNORECASE
)


def _typed_spellcast_lane(tree: ConceptTree) -> list[Signal]:
    """typed_spellcast (§F, SUBJECT-BEARING) — the tribal cast payoff
    (CR 603.2 + 102.2): a ``SpellCast`` trigger whose watched-spell filter
    carries a vocab creature subtype AND whose ``valid_target`` is the
    Controller — the TYPED you-cast discriminator (Lys Alana Huntmaster
    carries ``valid_target {Controller}``; the symmetric "a player casts a
    Giant spell" hoser — Elvish Handservant — carries none, and an
    opponent-punisher carries Opponent). REPLACES live's
    ``_self_cast_oracle`` "you cast" regex gate with a typed read (a
    documented improvement).

    b11 follow-up (a), adjudicated: the STATIC cost-reduction form is a cast
    payoff too — "<Subtype> spells you cast cost {N} less" (the Warchief /
    Banneret family; CR 601.2f couples the discount to the cast event, so the
    tribal reducer rewards CASTING the tribe). Read the already-ported
    cost-modification static's typed ``spell_filter`` subtypes
    (vocab-validated), gated to a ``Reduce`` direction and YOUR cards
    (``affected`` controller You; a SelfRef self-discount never fires).

    ADR-0038 W3 batch 2 unit 2: the SAME static read also covers a
    ``CastWithKeyword`` mode ("<Subtype> spells you cast have <keyword>" —
    Ezio Auditore da Firenze's Freerunning grant, Hunting Velociraptor's
    Prowl grant, The First Sliver's Cascade grant; CR 601.3e's cast-keyword
    grant is a cast payoff same as a cost discount), and both modes are now
    read via :func:`iter_nested_spellcast_static_modes`'s deep walk so a
    nested grant — a ``GrantStaticAbility`` modification's ``.definition``
    (Acolyte of Bahamut's "Commander creatures you own have '... Dragon
    spell ... costs {2} less ...'") or a created token's own
    ``static_abilities`` (The Eleventh Hour's Human token granting "Doctor
    spells you cast cost {1} less") — fires exactly like the top-level form.

    ADR-0038 W3 batch 2 unit 2 also adds a ``ReduceNextSpellCost`` effect
    arm — a ONE-SHOT "the next <Subtype> spell you cast this turn costs {N}
    less" (Invasion of the Giants' Saga chapter III), a distinct typed
    effect from the persistent ``ModifyCost`` static (no ongoing "affected"
    filter — a Saga chapter is inherently its controller's own effect, CR
    714, so no direction gate is needed). Same cast-cost-discount payoff,
    CR 601.2f.

    Scope "you", subject = the subtype.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def emit(subtype: str) -> None:
        sub = _resolve_subject(subtype, CREATURE_SUBTYPES)
        if sub and sub not in seen:
            seen.add(sub)
            out.append(
                Signal(signal_keys.TYPED_SPELLCAST, "you", sub, "", tree.name, "high")
            )

    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event == "cast_spell"
            and trigger_caster_scope(unit.node) == "you"
        ):
            for s in filter_subtypes(getattr(unit.node, "valid_card", None)):
                emit(s)
        for n in iter_nested_spellcast_static_modes(unit.node):
            affected = getattr(n, "affected", None)
            if tag_of(affected) == "SelfRef":
                continue  # a self-discount (A-Demilich) is not a cast payoff
            if filter_controller(affected) != "You":
                continue  # the "you cast" coupling (checklist #6)
            mode = getattr(n, "mode", None)
            if isinstance(mode, MirrorVariant) and mode.key == "CastWithKeyword":
                for s in filter_subtypes(affected):
                    emit(s)
            elif modify_cost_mode(n) == "Reduce":
                for s in filter_subtypes(modify_cost_spell_filter(n)):
                    emit(s)
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "ReduceNextSpellCost":
                for s in filter_subtypes(getattr(n, "spell_filter", None)):
                    emit(s)
            elif tag_of(n) == "Unimplemented":
                desc = getattr(n, "description", None)
                if isinstance(desc, str):
                    m = _REPLICATE_GRANT_RX.search(desc)
                    if m:
                        emit(m.group(1))
    m = _ALT_COST_SPELLCAST_RX.search(_kept(tree))
    if m:
        emit(m.group(1))
    return out


def _legends_historic_matters(tree: ConceptTree) -> list[Signal]:
    """legends_matter + historic_matters (§F) — the supertype/historic
    build-arounds, whole-card granularity (c) mirroring live's
    ``ir_predicates`` collection:

    * ``legends_matter`` — any typed filter carrying ``HasSupertype:
      Legendary`` (Reki — CR 205.4d). Being legendary ITSELF (Ruric Thar) is
      not legends-matter — no Legendary-referencing filter, no fire.
    * ``historic_matters`` — any filter carrying the ``Historic`` property
      (Jhoira — CR 700.6: "legendary supertype, the artifact card type, or
      the Saga subtype"). A Legendary-only filter (Reki) does not cross-fire.
      A card whose Historic qualifier phase drops entirely (Curator's Ward,
      Sanctum Spirit, Jhoira's Familiar, Banish to Another Universe, The
      Eighth Doctor, Havi, the All-Father — CR 700.10) is covered by
      ``tree_synthesis._arm_historic_matters``'s bare-word bridge, ALSO read
      here via its "historic_ref" concept — no lane special-case.

    Both scope "you" (live).
    """
    out: list[Signal] = []
    if any(
        has_filter_property(u.node, "HasSupertype", "Legendary") for u in tree.units
    ):
        out.append(Signal("legends_matter", "you", "", "", tree.name, "high"))
    if any(has_filter_property(u.node, "Historic") for u in tree.units) or (
        tree.effect_concepts("historic_ref")
    ):
        out.append(Signal("historic_matters", "you", "", "", tree.name, "high"))
    return out


def _self_blink_lane(tree: ConceptTree) -> list[Signal]:
    """self_blink (§F) — the self-exile-and-return engine (CR 611.2b
    durations; contrast 603.6c): an effect-role ``ChangeZone {target:
    SelfRef, destination: Exile}`` whose SAME unit chains a return —
    another ``ChangeZone`` to the Battlefield naming the exiled object
    (ParentTarget / TrackedSet through a ``CreateDelayedTrigger`` —
    Aetherling's probed shape; the effect-chain walk flattens the delayed
    trigger's inner return into the unit). Live is kept-mirror-ONLY ("no
    clean structural IR form" — STALE for the v0.9.0 mirror). Cost-exiles
    live in cost leaves and self-exclude; exiling ANOTHER target (Banisher
    Priest, Oblivion Ring) fails the SelfRef gate. The "~-substituted raw"
    residue tail live's fulltext detector catches is SUPPLEMENT — logged.
    Two corpus-measured gates (97 over-fires without them; SCOPED by
    per-shape live measurement, not blanket — the parity-before-veto
    lesson): a Saga LORE-CHAPTER unit never fires (the transforming-Saga
    chapter-III "Exile this Saga, then return it … transformed" — The
    Restoration of Eiganjo family, 29 corpus, live uniformly no-fire;
    CR 714.2b + 712 — a one-shot flip vehicle, not a blink engine), and a
    GRAVEYARD-origin return never counts as the return half (unearth's
    Graveyard→Battlefield self-return — Anathemancer; CR 702.84a —
    graveyard recursion whose exile is the delayed unearth cleanup). The
    NON-Saga transform flips stay IN: live fires the ability/dies forms
    (Clive / Elesh Norn / Liliana, Heretical Healer — measured), so a
    transform veto there would regress live members. Scope "you"
    (granularity a chain-join).
    """
    for unit in tree.units:
        if unit.origin not in ("ability", "trigger"):
            continue
        if trigger_counter_filter(unit.node)[0] == "lore":
            continue  # a Saga chapter (CR 714.2b) — a flip, not a blink
        czs = [
            c
            for c in unit.effect_concepts("change_zone")
            if tag_of(c.node) == "ChangeZone"
        ]
        if not any(
            change_zone_dirs(c.node)[1] == "Exile"
            and tag_of(getattr(c.node, "target", None)) == "SelfRef"
            for c in czs
        ):
            continue
        for c in czs:
            origin, dest = change_zone_dirs(c.node)
            if dest != "Battlefield" or origin == "Graveyard":
                continue  # the unearth-style graveyard self-return
            if tag_of(getattr(c.node, "target", None)) in _SELF_BLINK_RETURN_TAGS:
                return [Signal("self_blink", "you", "", c.raw, tree.name, "high")]
    return []


# ── Batch 12 lanes (ADR-0035 Stage 2) ────────────────────────────────────────


def _scry_surveil_matters(tree: ConceptTree) -> list[Signal]:
    """scry_surveil_matters (§A) — CR 701.22a / 701.25a: a Scry / Surveil
    TRIGGER mode is the payoff watcher (Arwen Undómiel, Whispering Snitch,
    Mirko). Gate #4 membership: a bare Scry/Surveil EFFECT node (Opt — a
    doer) never fires; doers ride the ported topdeck_selection. The
    conferral/reference residue live reaches via the ADR-0027 marker is
    SUPPLEMENT-FIXABLE (the oracle carries "you scry"), logged. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in ("scry", "surveil"):
            return [Signal("scry_surveil_matters", "you", "", "", tree.name, "high")]
        # b14 §R(c) arm 1 — the PlayerPerformedAction composite (Matoya,
        # Planetarium of Wan Shi Tong — probed verbatim): ``player_actions``
        # a NON-EMPTY subset of {scry, surveil} (NO "searchedlibrary" — that
        # routes to opponent_search_matters; the Proliferate composites fail
        # the subset), watched player Controller (River Song fails twice:
        # names SearchedLibrary AND valid_target Opponent). CR 701.22a /
        # 701.25a.
        if unit.origin == "trigger":
            mode = getattr(unit.node, "mode", None)
            mode_s = mode if isinstance(mode, str) else tag_of(mode)
            if mode_s == "PlayerPerformedAction":
                actions = getattr(unit.node, "player_actions", None)
                norm = {a.lower() for a in actions or () if isinstance(a, str)}
                if (
                    norm
                    and norm <= {"scry", "surveil"}
                    and trigger_scope(unit.node) == "you"
                ):
                    return [
                        Signal("scry_surveil_matters", "you", "", "", tree.name, "high")
                    ]
        # b14 §R(c) arm 2 — the Scry-event REPLACEMENTS (CR 614.1a "instead"):
        # ``event == "Scry"`` (Eligeth's scry-becomes-draw, Kenessos's
        # scry-plus-one — the ENTIRE corpus census, probed).
        if unit.origin == "replacement" and getattr(unit.node, "event", None) == "Scry":
            return [Signal("scry_surveil_matters", "you", "", "", tree.name, "high")]
    return []


def _cycling_matters(tree: ConceptTree) -> list[Signal]:
    """cycling_matters (§A) — CR 702.29a: a Cycled / CycledOrDiscarded
    trigger whose watched card is NOT SelfRef (Astral Slide — null watcher;
    Archfiend of Ifnir — Typed/Another). The "when you cycle THIS card"
    bonus (Agonasaur Rex — SelfRef, 58 corpus) is membership. Reads the RAW
    mode (not the derived event — CycledOrDiscarded shares the "discarded"
    event with plain Discarded watchers). The ReduceAbilityCost{Cycling}
    static family (Fluctuator, 26 corpus) is live-verified no-fire — logged,
    not ported. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        mode = getattr(unit.node, "mode", None)
        mode_s = mode if isinstance(mode, str) else tag_of(mode)
        if mode_s not in ("Cycled", "CycledOrDiscarded"):
            continue
        if tag_of(getattr(unit.node, "valid_card", None)) == "SelfRef":
            continue
        return [Signal("cycling_matters", "you", "", "", tree.name, "high")]
    return []


def _exert_matters(tree: ConceptTree) -> list[Signal]:
    """exert_matters (§A) — CR 701.43a + 702.20b (vigilance neutralizes
    exert's won't-untap).

    Tier-1 (ADR-0036/0037 fold — the lane-time ``_JOHAN_MIRROR`` kept-oracle
    read is RETIRED):

    (a) STRUCTURAL — :func:`has_structural_exert_matters` — a mass-vigilance
    grant onto your GENERIC creature board (Always Watching —
    AddKeyword{Vigilance}, affected Typed[Creature] controller You, no
    subtype scoping; Another/NonToken allowed). SELF-GRANT veto via the
    affected-tag check.
    (b) the ``tree_synthesis`` stage's ``synth_exert_matters`` bucket-B node
    — Johan's unique "attacking doesn't cause creatures you control to tap"
    replacement, gated against (a). Gate #4: the Exerted trigger (28 corpus,
    all SelfRef riders — Combat Celebrant) is MEMBERSHIP and never fires.
    Scope "you".
    """
    if has_structural_exert_matters(tree):
        for unit in tree.units:
            for sdef, mod in iter_mod_sites(unit.node):
                if tag_of(mod) != "AddKeyword" or mod_keyword_name(mod) != "Vigilance":
                    continue
                affected = getattr(sdef, "affected", None)
                if tag_of(affected) != "Typed":
                    continue
                if "Creature" not in filter_core_types(affected):
                    continue
                if filter_controller(affected) != "You" or filter_subtypes(affected):
                    continue
                return [
                    Signal(
                        "exert_matters", "you", "", _site_raw(sdef), tree.name, "high"
                    )
                ]
    for c in tree.iter_concepts():
        if c.concept == "synth_exert_matters":
            return [Signal("exert_matters", "you", "", "", tree.name, "high")]
    return []


# Trigger events an attack/combat-damage context is derived from — the
# entered_attacker structural gate (CR 302.6 / 603.10a).
_ENTERED_ATTACKER_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {"attacks", "deals_damage"}
)


def _entered_attacker(tree: ConceptTree) -> list[Signal]:
    """entered_attacker (§A) — CR 302.6 / 603.10a: a newly-entered creature
    that attacks or deals combat damage this turn (Samut, Pick Up the Pace).

    Tier-1 (ADR-0036/0037 fold — the lane-time ``ENTERED_ATTACKER_REGEX``
    per-clause kept-oracle read is RETIRED): FULLY STRUCTURAL — a trigger
    unit whose derived event is an attack/combat-damage event
    (:data:`_ENTERED_ATTACKER_TRIGGER_EVENTS`) carrying an
    ``EnteredThisTurn`` filter property (a watched OTHER creature, Pick Up
    the Pace) or a ``SourceEnteredThisTurn`` condition (a self-referential
    "if ~ entered this turn", Hixus, Prison Warden) anywhere in the trigger.
    Measured over the commander-legal corpus: a NET RECALL IMPROVEMENT over
    the old per-clause mirror (10 vs 4, 0 drops) — the mirror's exact
    phrasing anchor missed "entered the battlefield UNDER YOUR CONTROL this
    turn" (Iron Man, Ash Party Crasher, Waterspout Warden), verb-number
    variants ("creatures ... attack"/"deal combat damage" vs "attacks"/
    "deals combat damage" — Whirlwind, Goro-Goro and Satoru), and a
    cross-clause split (Moon-Circuit Hacker's "... draw a card. If you do,
    discard a card unless this creature entered this turn." spans two
    sentences). Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if unit.trigger_event not in _ENTERED_ATTACKER_TRIGGER_EVENTS:
            continue
        for n in iter_typed_nodes(unit.node):
            # BattlefieldEntriesThisTurn: the v0.32.0 entry-ledger rename
            # of the EnteredThisTurn QTY (Iron Man's intervening-if counts
            # this-turn artifact entries through it).
            if tag_of(n) in (
                "EnteredThisTurn",
                "SourceEnteredThisTurn",
                "BattlefieldEntriesThisTurn",
            ):
                return [Signal("entered_attacker", "you", "", "", tree.name, "high")]
    return []


def _saga_matters(tree: ConceptTree) -> list[Signal]:
    """saga_matters (§A) — CR 714.2 / 714.4 (case law Satsuki: a lore
    counter usually triggers the next chapter): on a NON-Saga card, (a) a
    lore-kind place/remove/move counter effect (Keldon Warcaller, Satsuki,
    Myth Realized's SelfRef build-up), or (b) a Saga-subtype AFFECTED filter
    on a top-level static (Barbara Wright's read-ahead grant — a documented
    crosswalk add; live's projection dropped it). Gate #4: a Saga's OWN
    chapter triggers / ETB lore replacement are membership — the whole-card
    Saga-subtype gate excludes them (An Unearthly Child, History of
    Benalia). [P16]: a multi-choice tutor that merely CAN fetch a Saga
    (Search for Glory — live-verified no-fire) never fires — search/reveal
    selector filters are not read. Scope "you".

    Arm (c) runs BEFORE the membership gate: a ``CountersOn{lore}`` COUNT
    operand (Genesis of the Daleks' "a Dalek for each lore counter") is a
    lore PAYOFF even on a Saga itself — scaling on the pile is caring,
    while chapters merely HAVING lore thresholds (``counter_filter``) is
    membership and is never read.
    """
    for unit in tree.units:
        for c in unit.iter_concepts():
            for q in iter_typed_nodes(c.node):
                ct = getattr(q, "counter_type", None)
                if (
                    tag_of(q) == "CountersOn"
                    and isinstance(ct, str)
                    and ct.lower() == "lore"
                ):
                    return [Signal("saga_matters", "you", "", c.raw, tree.name, "high")]
    if "Saga" in tree.card_subtypes:
        return []
    for unit in tree.units:
        for c in unit.iter_concepts():
            if c.role != "effect":
                continue
            if c.concept not in ("place_counter", "remove_counter", "move_counters"):
                continue
            kind = counter_kind(c.node) or counter_kind_any(c.node)
            if kind.lower() == "lore":
                return [Signal("saga_matters", "you", "", c.raw, tree.name, "high")]
        if unit.origin == "static":
            subs = {
                s.lower() for s in filter_subtypes(getattr(unit.node, "affected", None))
            }
            if "saga" in subs:
                return [
                    Signal(
                        "saga_matters",
                        "you",
                        "",
                        _site_raw(unit.node),
                        tree.name,
                        "high",
                    )
                ]
    return []


def _life_total_set(tree: ConceptTree) -> list[Signal]:
    """life_total_set (§B) — CR 119.5 + 701.12c (case law Magister Sphinx:
    becoming 10 IS gaining/losing the difference): a ``SetLifeTotal`` with a
    PLAYER-shaped target, an ``ExchangeLifeTotals`` / ``ExchangeLifeWithStat``,
    or a one-shot ``Double{LifeTotal}`` (Celestial Mantle). Gate: phase
    misparses perpetual P/T sets as SetLifeTotal onto CREATURE filters
    (Baffling Defenses / Teyo / Mortal Flesh Is Weak — live over-fires them
    from the same misparse; the spec's rules-lawyer gate vetoes any target
    with core card types). Scope "any" (a scope-agnostic build-around).
    """
    for c in tree.effect_concepts("set_life"):
        if tag_of(c.node) == "SetLifeTotal":
            if filter_core_types(getattr(c.node, "target", None)):
                continue  # a P/T-set misparse onto a permanent filter
            return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
        return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("double_quantity"):
        if double_target_kind(c.node) == "LifeTotal":
            return [Signal("life_total_set", "any", "", c.raw, tree.name, "high")]
    return []


def _unspent_mana(tree: ConceptTree) -> list[Signal]:
    """unspent_mana (§B) — CR 106.4 / 500.5 (case law Kruphix: unspent mana
    becomes colorless as steps end). Tier-1 (ADR-0036/0037 fold — the
    lane-time ``_UNSPENT_MANA_RX`` kept-oracle read is RETIRED):

    * **Structural:** :func:`has_structural_unspent_mana` — the
      ``StepEndUnspentMana`` static mode (action Retain — Upwelling;
      Transform — Horizon Stone, Kruphix; live's "v0.1.19 drops it" note was
      STALE).
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_unspent_mana`` node — the mana-burst-rider tail (Savage
      Ventmaw, Brazen Collector) and the "loses all unspent mana" tax forms
      (Mana Short, Power Sink) phase never structures, gated against the
      same structural mode census.

    Scope "you" (live's forced scope — parity).
    """
    for unit in tree.units:
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "StepEndUnspentMana"
        ):
            return [
                Signal(
                    "unspent_mana", "you", "", _site_raw(unit.node), tree.name, "high"
                )
            ]
    for c in tree.iter_concepts():
        if c.concept == "synth_unspent_mana":
            return [Signal("unspent_mana", "you", "", "", tree.name, "high")]
    return []


def _opp_top_exile(tree: ConceptTree) -> list[Signal]:
    """opp_top_exile (§B) — CR 406.1: an ``ExileTop`` whose exiled-library
    PLAYER is an opponent — the Typed{controller: Opponent} filter (Ashiok,
    Nightmare Weaver) or a directed ``Player`` target (Circu; the caster
    aims it at an opponent's library). Gates ([P5]/[P17]): a
    Controller-resolving player is self-mill / impulse territory (Ashiok,
    Wicked Manipulator's pay-life exile rides ChangeZone, not ExileTop —
    doubly out). Scope "you" (the engine controller, matching live).
    """
    for c in tree.effect_concepts("exile_top"):
        player = getattr(c.node, "player", None)
        ptag = tag_of(player)
        if ptag == "Typed" and filter_controller(player) == "Opponent":
            return [Signal("opp_top_exile", "you", "", c.raw, tree.name, "high")]
        if ptag in ("Player", "TriggeringPlayer"):
            return [Signal("opp_top_exile", "you", "", c.raw, tree.name, "high")]
    # b14 §R(a) — the ChangeZone/ChooseFromZone steal-chain family (CR 406.1).
    for unit in tree.units:
        # (1) Exile-from-opponent-library head: ``ChangeZone → Exile`` whose
        # target is an opponent-controlled Library-zone filter (Brainstealer
        # Dragon, Arvinox, Stolen Strategy — probed verbatim; corpus census is
        # exactly the 7-card steal family, so no cast-permission sibling gate:
        # Arvinox's permission is textual-only in a GenericEffect description
        # and a GrantCastingPermission gate would LOSE it). Nassari, Dean of
        # Expression was banked as the ONE logged add (hook = exile-each-
        # opponent-top + "you may cast spells from among those exiled cards"
        # — the same steal-and-cast contract); the shadow diff's DFC
        # same-oid union shows live firing the joined "Uvilda // Nassari"
        # record, so the arm lands it as BOTH (live_only shrank by exactly
        # the 7-card census + that DFC row; cw_only grew by ZERO).
        for c in unit.effect_concepts("change_zone"):
            if tag_of(c.node) != "ChangeZone":
                continue
            if change_zone_dirs(c.node)[1] != "Exile":
                continue
            target = getattr(c.node, "target", None)
            if (
                tag_of(target) == "Typed"
                and filter_controller(target) == "Opponent"
                and "Library" in filter_inzone_zones(target)
            ):
                return [Signal("opp_top_exile", "you", "", c.raw, tree.name, "high")]
        # (2) Choose-from-their-zones chain (Covetous Urge, Psychic Intrusion
        # — probed verbatim): a ``ChooseFromZone`` with an opponent/targeted
        # zone owner + a same-unit sibling ChangeZone→Exile + a
        # ``cast_from_zone`` concept (the SequentialSibling chain,
        # granularity a). ``ChooseFromZone`` is a tag_of read only — no
        # EFFECT_CONCEPTS row (§0.2).
        chooses_theirs = any(
            tag_of(c.node) == "ChooseFromZone"
            and getattr(c.node, "zone_owner", None) in ("TargetedPlayer", "Opponent")
            for c in unit.effects
        )
        exiles = any(
            tag_of(c.node) == "ChangeZone" and change_zone_dirs(c.node)[1] == "Exile"
            for c in unit.effect_concepts("change_zone")
        )
        if chooses_theirs and exiles and unit.has_effect("cast_from_zone"):
            return [Signal("opp_top_exile", "you", "", "", tree.name, "high")]
    # Deliberate NON-extension: ``ExileFromTopUntil{player: Opponent}``
    # (Umbris, Chaos Wand, Nicol Bolas God-Pharaoh) lives in theft_makers'
    # mirror pop, NOT here — reading it would move both/live_only.
    return []


def _kill_engine(tree: ConceptTree) -> list[Signal]:
    """kill_engine (§B) — CR 305.6 / 701.8: a REPEATABLE-frame single-target
    creature ``Destroy`` on a card that is itself a Creature — an activated
    unit (Visara, Avatar of Woe, Royal Assassin's qualified "tapped
    creature") or a recurring trigger (event outside the one-shot set;
    Nekrataal's ETB destroy is out). ``DestroyAll`` wipes never fire (the
    tag IS the mass discriminator). Tier-1 (ADR-0036/0037 fold — the
    lane-time ``_REPEATABLE_KILL_RE`` kept-oracle read is RETIRED): the
    Evil Twin quoted-grant tail (its destroy lives inside a QUOTED granted
    ability folded into a ``clone`` Effect, no destroy ability of its own —
    the ONE card phase can't structure) now rides the ``tree_synthesis``
    stage's ``synth_kill_engine`` node, gated against
    :func:`has_structural_kill_engine`. LOW confidence, scope "you" (the
    live producer's identity — never feeds has_other_plan). Read via the
    SHARED :func:`has_structural_kill_engine` predicate itself for the
    structural arm too (GAP-GATE-ALIGNMENT — ADR-0036/0037 Stage 5 #58
    hardening; this used to re-derive the same repeatable-Destroy walk
    inline, a drift risk).
    """
    if has_structural_kill_engine(tree):
        return [Signal("kill_engine", "you", "", "", tree.name, "low")]
    for c in tree.iter_concepts():
        if c.concept == "synth_kill_engine":
            return [Signal("kill_engine", "you", "", "", tree.name, "low")]
    return []


def _control_exchange(tree: ConceptTree) -> list[Signal]:
    """control_exchange (§C) — CR 701.12b / 108.3: the exile-your-OWNED +
    sibling return-to-battlefield chain join (granularity a — Meneldor's
    "exile up to one target creature you own, then return it"). The
    mandatory parity check ran FIRST: live fires the 18 ``ExchangeControl``
    swaps (Gilded Drake, Daring Thief, Perplexing Chimera) under the PORTED
    gain_control lane, so ONLY the exile-Owned-return shape ports here.
    Oblivion Sower (Owned:TargetPlayer — theft-ramp) and a plain blink
    (controller-You filter, no Owned predicate — Cloudshift) never fire.
    An exile filter carrying Owned:You AND controller:You is a pure value
    blink (own+control leaves no steal to recover — CR 108.3 vs 701.12b;
    Yorion, rules-lawyer-adjudicated b12): the CONJUNCTION is vetoed while
    Meneldor's controller-null Owned:You keeps firing. Scope "you".
    """
    for unit in tree.units:
        czs = [
            c
            for c in unit.effect_concepts("change_zone")
            if tag_of(c.node) == "ChangeZone"
        ]

        def _steal_recovery(target: object) -> bool:
            return (
                filter_owned_controller(target) == "You"
                and filter_controller(target) != "You"
            )

        exile_owned = any(
            change_zone_dirs(c.node)[1] == "Exile"
            and _steal_recovery(getattr(c.node, "target", None))
            for c in czs
        )
        returns = any(change_zone_dirs(c.node)[1] == "Battlefield" for c in czs)
        if exile_owned and returns:
            return [Signal("control_exchange", "you", "", "", tree.name, "high")]
    return []


def _land_exchange(tree: ConceptTree) -> list[Signal]:
    """land_exchange (§C) — CR 701.12b: an ``ExchangeControl`` either of
    whose sides is a Land-cored filter (Political Trickery, Vedalken
    Plotter), or a ``gain_control`` effect over a Land filter (live's
    "Land in ftypes" rider). Gilded Drake's creature-for-creature swap
    never fires. Scope "you".
    """
    for c in tree.effect_concepts("exchange_control"):
        for side in ("target_a", "target_b"):
            if "Land" in filter_core_types(getattr(c.node, side, None)):
                return [Signal("land_exchange", "you", "", c.raw, tree.name, "high")]
    for concept in ("gain_control", "give_control"):
        for c in tree.effect_concepts(concept):
            if "Land" in filter_core_types(effect_filter(c.node)):
                return [Signal("land_exchange", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "ChangeController":
                continue
            if "Land" in filter_core_types(getattr(sdef, "affected", None)):
                return [
                    Signal(
                        "land_exchange", "you", "", _site_raw(sdef), tree.name, "high"
                    )
                ]
    return []


def _land_denial(tree: ConceptTree) -> list[Signal]:
    """land_denial (§C) — CR 702.26: a ``PhaseOut`` whose target is the pure
    Typed[Land] controller-You board (Taniwha's upkeep mass phase-out — the
    Taniwha probe verbatim). Reality Ripple's Or-filter one-shot and Clever
    Concealment's Non-Land permanent sweep never fire (checklist #5 — the
    effect's own target node). Scope "you".
    """
    for c in tree.effect_concepts("phasing"):
        if tag_of(c.node) != "PhaseOut":
            continue
        target = getattr(c.node, "target", None)
        if tag_of(target) != "Typed":
            continue
        if set(filter_core_types(target)) != {"Land"} or filter_non_types(target):
            continue
        if filter_controller(target) == "You":
            return [Signal("land_denial", "you", "", c.raw, tree.name, "high")]
    return []


def _is_protection_animator(unit: AbilityUnit) -> bool:
    """The land_protection-only WIDER animator read (the shared b1 helper is
    untouched so the settled land_creatures_matter lane cannot move): any
    static whose subject is land-ish — the ``Land`` core OR a land SUBTYPE
    word ("Enchanted Forest" — Genju of the Cedars) — carrying an ``AddType
    Creature`` OR the ``SetCardTypes [Creature]`` rewrite (the Zendikon
    family). All controllers (live passes ("you","any"))."""
    statics = getattr(unit, "statics", ())
    if not statics:
        return False
    subject = statics[0].subject
    landish = "Land" in subject or ({w.lower() for w in subject} & _LAND_SUBTYPE_WORDS)
    if not landish or "Creature" in subject:
        return False
    for concept in statics:
        node = concept.node
        if (
            concept.concept == "add_type"
            and getattr(node, "core_type", None) == "Creature"
        ):
            return True
        if tag_of(node) == "SetCardTypes":
            cores = getattr(node, "core_types", None) or ()
            if "Creature" in cores:
                return True
    return False


def _land_protection(tree: ConceptTree) -> list[Signal]:
    """land_protection (§C) — CR 613.1d / 305: a commander animating MANY
    lands wants them kept alive. Shares the b1 animator predicate widened
    past the you-gate (Living Plane — live passes ("you","any"); the
    crosswalk's controller-less scope maps to "each", so the widened tuple
    here is ("you","any","each")), plus the Tier-1 manland self-animate /
    landish-affected structural read (ADR-0036/0037 fold — a SelfRef nested
    static on a Land card, Restless Anchorage/Crawling Barrens; or a
    landish-AFFECTED nested static, the Genju cycle / mass "lands become
    creatures" anthems — a GenericEffect-nested modification a plain
    top-level walk misses), with a bucket-B ``synth_manland`` tail (the
    deleted ``_MANLAND_MIRROR`` relocated with an adjudicated land-
    type-change veto) for the residual genuine members phase structures
    too loosely to read directly (a SearchLibrary-then-animate tracked
    chain, a mass land-to-copy effect, a fully ``Unimplemented`` ability).
    Scope "you".
    """
    for unit in tree.units:
        if _is_protection_animator(unit):
            return [Signal("land_protection", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            # The first-class Animate node (the TLA earthbend family — Bumi,
            # Badgermole: "Animate {types: [Creature], target: Land you
            # control}"): a mass/targeted land-animate the statics walk never
            # sees (no static def — the node carries the types directly).
            if c.role == "effect" and tag_of(c.node) == "Animate":
                tgt = getattr(c.node, "target", None)
                if "Land" in filter_core_types(tgt) or (
                    {t.lower() for t in filter_subtypes(tgt)} & _LAND_SUBTYPE_WORDS
                ):
                    return [
                        Signal("land_protection", "you", "", c.raw, tree.name, "high")
                    ]
        # The threaded one-shot animate ("target Forest becomes a 4/5 …
        # creature" — Awakener Druid: a GenericEffect whose resolved target is
        # the land, mods AddType Creature).
        for resolved, sdef in iter_threaded_target_statics(unit.node):
            landish = "Land" in filter_core_types(resolved) or (
                {t.lower() for t in filter_subtypes(resolved)} & _LAND_SUBTYPE_WORDS
            )
            if not landish:
                continue
            for _sd, mod in iter_mod_sites(sdef):
                if (
                    tag_of(mod) == "AddType"
                    and getattr(mod, "core_type", None) == "Creature"
                ):
                    return [Signal("land_protection", "you", "", "", tree.name, "high")]
        # The reverse animator (Ashaya: "creatures you control are Forest
        # lands in addition …" — an AddType Land over your board; both type
        # sets live on one permanent, the same keep-my-lands-alive care).
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddType" or getattr(mod, "core_type", None) != "Land":
                continue
            affected = getattr(sdef, "affected", None)
            if filter_controller(affected) == "You":
                return [
                    Signal(
                        "land_protection", "you", "", _site_raw(sdef), tree.name, "high"
                    )
                ]
    # The manland self-animate / landish-affected structural read (ADR-0036
    # fold): a SelfRef nested static on a card that IS itself a Land (the
    # "Restless" cycle, Crawling Barrens), OR a landish-AFFECTED nested
    # static (Land core type / land-subtype word, e.g. the Genju cycle's
    # EnchantedBy-Island filter, or a mass "lands become creatures" anthem)
    # — a GenericEffect-nested modification :func:`_is_protection_animator`
    # (top-level statics only) never sees. Read via the SHARED
    # :func:`has_structural_manland` predicate (GAP-GATE-ALIGNMENT — the
    # same source the ``synth_manland`` gap gate reads; ADR-0036/0037 Stage
    # 5 #58 hardening — this used to re-derive the check inline against a
    # separately-defined ``_LAND_SUBTYPE_WORDS`` copy, a drift risk).
    if has_structural_manland(tree):
        return [Signal("land_protection", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_manland":
            return [Signal("land_protection", "you", "", "", tree.name, "high")]
    return []


def _evasion_denial(tree: ConceptTree) -> list[Signal]:
    """evasion_denial (§C) — CR 702.14: the ``IgnoreLandwalkForBlocking``
    static mode (Great Wall's plainswalk, Crevasse's mountainwalk — 9 corpus
    statics on 8 cards). Staff of the Ages's conferral is ADR-0038
    recovery-promoted: its own static parser fails, leaving an Unimplemented
    parse-failure residue (still role=effect) the ``clause_grammar.
    static_token`` STATIC_TOKENS row re-decorates to concept="evasion_denial"
    via ``recovery.ALLOWLIST``, so this single typed read covers both the
    clean static and the recovered one. Scope "opponents" (live).
    """
    for unit in tree.units:
        if (
            unit.origin == "static"
            and static_mode_tag(unit.node) == "IgnoreLandwalkForBlocking"
        ):
            return [
                Signal(
                    "evasion_denial",
                    "opponents",
                    "",
                    _site_raw(unit.node),
                    tree.name,
                    "high",
                )
            ]
    for c in tree.effect_concepts("evasion_denial"):
        return [Signal("evasion_denial", "opponents", "", c.raw, tree.name, "high")]
    return []


def _animate_artifact(tree: ConceptTree) -> list[Signal]:
    """animate_artifact (§D) — CR 613.1d + 702.122b: "artifacts become
    creatures" (Karn Silver Golem, Titania's Song). Tier-1 (ADR-0036/0037
    fold): reads the ``tree_synthesis`` bucket-B ``synth_animate_artifact``
    node (the deleted ``_ANIMATE_ARTIFACT_RX`` relocated verbatim — no
    competing Tier-1 predicate: the Animate effect tag is TLA earthbend, not
    artifact animation, and every structural AddType/base_pt_set arm either
    90%-over-fires or loses core animators, per the batch-12 adjudication).
    A bare becomes-an-ARTIFACT type conferral (Liquimetal Coating, Mycosynth
    Lattice) is a non-match. Scope "you".
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_animate_artifact":
            return [Signal("animate_artifact", "you", "", "", tree.name, "high")]
    return []


def _color_change(tree: ConceptTree) -> list[Signal]:
    """color_change (§D) — CR 105.3: a color-changing effect ("becomes the
    color of your choice"/"becomes all colors" — Alchor's Tomb, Distorting
    Lens). Tier-1 (ADR-0036/0037 fold): reads the ``tree_synthesis``
    bucket-B ``synth_color_change`` node (the deleted ``_COLOR_CHANGE_RX``
    relocated verbatim — no competing Tier-1 predicate: the only structural
    anchor, cat=='animate', fires on 391 corpus cards, ~94% over-fire from
    devoid CDAs / eternalize token colors / animate riders, per the batch-12
    adjudication). "Becomes colorless" (Ancient Kavu) is a deliberate
    non-match. Scope "you".
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_color_change":
            return [Signal("color_change", "you", "", "", tree.name, "high")]
    return []


def _type_change(tree: ConceptTree) -> list[Signal]:
    """type_change (§D) — CR 702.16 + 613.1d: the type-HOSER read, Tier-1
    (ADR-0036/0037 Stage 5 T9-finalize fold — the byte-identical mirror is
    RETIRED to a bucket-B synth arm). Structural: an ``AddKeyword`` whose
    keyword is ``Protection{CardType: <arg>}`` with the argument
    vocab-validated against the creature-subtype list (Gor Muldrak's
    Salamanders — the "phase drops the argument" note was STALE);
    protection from a COLOR (White Knight) fails the vocab gate.
    bucket-B synth: the ``synth_type_change`` node
    (:func:`_arm_type_change`) for the per-clause
    ``protection from (\\w+)`` vocab-gated residue. Scope "you". Read via
    the SHARED :func:`has_structural_type_change` predicate (GAP-GATE-
    ALIGNMENT — the same source the ``synth_type_change`` gap gate reads;
    ADR-0036/0037 Stage 5 #58 hardening — this used to re-derive the same
    ``AddKeyword``/vocab walk inline, a drift risk).
    """
    if has_structural_type_change(tree):
        return [Signal("type_change", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_type_change":
            return [Signal("type_change", "you", "", "", tree.name, "high")]
    return []


def _stax_lanes(tree: ConceptTree) -> list[Signal]:
    """stax_taxes (scope "opponents") + symmetric_stax (scope "each") — CR
    101.2 + 604.1. A pure Tier-1 UNION (ADR-0036/0037 fold — the residue
    text mirror is RETIRED):

    * **Structural (bucket-A):** :func:`has_structural_stax_taxes` /
      :func:`has_structural_symmetric_stax` — the full static census
      (plain restrictions / cost taxes / cast-activation locks / attack
      ceilings / step-skips / trigger-suppression / hand-size / enters-
      tapped), scope from each static's OWN who/affected node. Gate: the
      single-creature pacify veto (EnchantedBy/EquippedBy — Pacifism,
      Arrest) opens NEITHER lane; an untap BLESSING (Seedborn Muse's
      UntapsDuringEachOtherPlayersUntapStep) is not in any census set.
    * **bucket-B synth (ADR-0037):** the ``tree_synthesis`` stage's
      ``synth_stax_taxes`` / ``synth_symmetric_stax`` nodes — the
      unstructurable residue tail phase drops WHOLLY (Winter Orb's
      "players can't untap", Failure // Comply's dropped-face cast-lock,
      Archfiend of Despair / Platinum Angel / Stranglehold's opponent
      locks), gated against the SAME structural read (SYNTH-EXCLUSION-
      PARITY: the pacify veto + single-target + defer-to-structural
      cast-lock guards ride along unchanged).
    """
    out: list[Signal] = []
    seen: set[str] = set()
    stax_fired, sym_fired, stax_raw, sym_raw = _stax_structural_walk(tree)
    if stax_fired:
        seen.add("stax_taxes")
        out.append(Signal("stax_taxes", "opponents", "", stax_raw, tree.name, "high"))
    if sym_fired:
        seen.add("symmetric_stax")
        out.append(Signal("symmetric_stax", "each", "", sym_raw, tree.name, "high"))
    for c in tree.iter_concepts():
        # "stax_taxes" (not just the synth_ marker) is the ADR-0038
        # clause-grammar recovery's real-concept token (Lavinia's
        # dynamic-threshold cast lock -- recovery.ALLOWLIST's
        # "stax_cast_lock" rule re-decorates straight to this concept).
        if c.concept in ("synth_stax_taxes", "stax_taxes") and "stax_taxes" not in seen:
            seen.add("stax_taxes")
            out.append(Signal("stax_taxes", "opponents", "", c.raw, tree.name, "high"))
        elif c.concept == "synth_symmetric_stax" and "symmetric_stax" not in seen:
            seen.add("symmetric_stax")
            out.append(Signal("symmetric_stax", "each", "", "", tree.name, "high"))
    return out


def _keyword_counter(tree: ConceptTree) -> list[Signal]:
    """keyword_counter (§E) — CR 122.1b: a place/remove of a counter whose
    kind is in the closed ``_KEYWORD_COUNTER_KINDS`` set: Arwen, Mortal
    Queen's indestructible enters-with. A pure Tier-1 UNION (ADR-0036/0037
    fold — the ``KEYWORD_COUNTER_REGEX`` text mirror is RETIRED):

    * **Structural:** :func:`has_structural_keyword_counter` — the closed-set
      kind check phase types directly.
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_keyword_counter`` node — the counter-kind-dropped choice/grant
      tail phase nests outside the effect chain (Boot Nipper's ChooseOneOf
      branches, Luminous Broodmoth's return-with-counter rider), gated
      against the same structural read.

    Gates: P1P1/loyalty/oil/shield/rad/lore route to their own ported lanes
    via the kind set; stun is NOT a 122.1b keyword counter (CR 122.1d — a
    replacement-maker, the b11 tap cluster's country). Scope "any".
    """
    if has_structural_keyword_counter(tree):
        return [Signal("keyword_counter", "any", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_keyword_counter":
            return [Signal("keyword_counter", "any", "", "", tree.name, "high")]
    return []


def _counter_grants_kw(tree: ConceptTree) -> list[Signal]:
    """counter_grants_kw (§E) — a keyword granted to YOUR creatures that
    HAVE a counter (Bramblewood Paragon's P1P1-predicated trample; Cathedral
    Acolyte's kind-agnostic Any ward). Gates: an off-kind SPECIFIC grant
    (oil/stun) is keyword_counter's domain (the P1P1/Any kind gate);
    an opponent-side subject is the wrong direction (checklist #6 — the
    controller-You gate). Scope "you".
    """
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("AddKeyword", "GrantAbility"):
                continue
            affected = getattr(sdef, "affected", None)
            kinds = counter_pred_kinds(affected)
            if not ("P1P1" in kinds or "Any" in kinds):
                continue
            if filter_controller(affected) != "You":
                continue
            return [
                Signal(
                    "counter_grants_kw", "you", "", _site_raw(sdef), tree.name, "high"
                )
            ]
    return []


def _counter_distribute(tree: ConceptTree) -> list[Signal]:
    """counter_distribute (§E) — CR 115.7f + 601.2d, the board-wide +1/+1
    spread. A pure Tier-1 UNION (ADR-0036/0037 fold — the
    ``_COUNTER_DISTRIBUTE_MIRROR`` text mirror is RETIRED):

    * **Structural:** :func:`has_structural_counter_distribute` — a mass
      ``PutCounterAll`` of kind P1P1 onto your creatures (Cathars' Crusade),
      or the typed ``distribute`` marker on a controller-You P1P1 PutCounter
      (Verdurous Gearhulk).
    * **bucket-B synth:** the ``tree_synthesis`` stage's
      ``synth_counter_distribute`` node — the distribute-among / "each of" /
      support-N / enters-with-additional residue (Bramblewood Paragon) phase
      types identically to an unrelated single-target pump, gated against
      the same structural read.

    The plain self-enters arm stays deliberately EXCLUDED (Endless One /
    Triskelion → self_counter_grow); a lore/loyalty PutCounterAll (Satsuki)
    fails the kind gate. Scope "you".
    """
    if has_structural_counter_distribute(tree):
        return [Signal("counter_distribute", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_counter_distribute":
            return [Signal("counter_distribute", "you", "", "", tree.name, "high")]
    return []


def _superfriends_matters(tree: ConceptTree) -> list[Signal]:
    """superfriends_matters (§F) — CR 306.5: caring about the planeswalker
    TYPE/GROUP. A pure Tier-1 UNION (ADR-0036/0037 fold — the
    ``SUPERFRIENDS_MATTERS_REGEX`` word mirror is RETIRED):

    * **Structural (bucket-A):** :func:`has_structural_superfriends` — a
      CONDITION-site Planeswalker group-reference (Historian of Zhalfir,
      Arisen Gorgon, Companion of the Trials), an attack-recipient trigger
      or static defending "you or planeswalkers you control" (Blood
      Reckoning, Archangel of Tithes, the Vow cycle), a Planeswalker-group
      anthem/grant static (Ichormoon Gauntlet, Sorin), a battlefield dies-
      trigger subject including Planeswalker (Carth the Lion), an
      activate-loyalty engine (Chandra's Regulator, The Chain Veil), a
      dynamic count/cost-reduction operand naming Planeswalker (Ajani,
      Strength of the Pride; Tomik), or a non-Opponent loyalty-counter
      EFFECT (Chandra, Acolyte of Flame) — minus the removal-target /
      ``TargetMatchesFilter`` / opponent-controlled / event-plumbing
      over-fires (Hero's Downfall, Chandra's Defeat, Eidolon of Obstruction,
      Hunter's Insight never fire).
    * **bucket-B synth (ADR-0037):** the ``tree_synthesis`` stage's
      ``synth_superfriends_matters`` node — an Unimplemented anthem/engine
      static (Shalai, Kasmina Enigma Sage), a CantAttack/CantBlock static
      with no typed recipient payload (Onakke Oathkeeper, Assault Suit), or
      an activate-loyalty permission ability with no typed carrier (Oath of
      Teferi) — gated against the SAME structural read + the SAME opponent/
      self-only/incidental vetoes (SYNTH-EXCLUSION-PARITY).

    Scope "you", HIGH.
    """
    if has_structural_superfriends(tree):
        return [Signal("superfriends_matters", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_superfriends_matters":
            return [Signal("superfriends_matters", "you", "", "", tree.name, "high")]
    return []


def _commander_matters(tree: ConceptTree) -> list[Signal]:
    """commander_matters (§F) — CR 903.3: an ``IsCommander`` FILTER property
    anywhere on the card (Bastion Protector, Anara, Forge of Heroes).
    CRITICAL gate: the card-level is_commander / brawl_commander metadata
    flags are NEVER read — eligibility is not caring. The
    CommanderManaValue / commander-cast trigger tail stays LOGGED, unported.
    Scope "you".
    """
    if any(has_filter_property(u.node, "IsCommander") for u in tree.units):
        return [Signal("commander_matters", "you", "", "", tree.name, "high")]
    return []


def _big_hand_lanes(tree: ConceptTree) -> list[Signal]:
    """big_hand_makers + big_hand_matters (§F) — CR 402.2, one shared walk.
    Tier-1 (ADR-0036/0037 fold — the lane-time ``_BIG_HAND_MAKERS_MIRROR`` /
    ``_BIG_HAND_MATTERS_MIRROR`` kept-oracle reads are RETIRED):

    * **makers** — :func:`has_structural_big_hand_makers`'s walk inline
      (the ``NoMaximumHandSize`` static mode — Reliquary Tower, Kruphix —
      or effect node, the ``MaximumHandSize{SetTo/AdjustedBy}`` family —
      Cursed Rack, Gnat Miser, Jin-Gitaxias — live's mirror keeps the
      REDUCERS in the lane; the parity quirk is kept and logged for a
      future lane split) plus the ``tree_synthesis`` stage's
      ``synth_big_hand_makers`` node for the bucket-B "maximum hand size"
      residual, gated against the same structural predicate.
    * **matters** — :func:`has_structural_big_hand_matters`'s walk inline
      (a ``HandSize``-family qty operand reading YOUR hand — [P5] gate,
      Maro's dynamic-P/T pair, Akki Underling's threshold condition; an
      opponent-hand count is vetoed) plus the ``tree_synthesis`` stage's
      ``synth_big_hand_matters`` node for the bucket-B full-grip-reference
      residual (Body of Knowledge fires BOTH halves).

    Both scope "you" (the live pair's identity).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    # makers SITE gate (:func:`has_structural_big_hand_makers` — a shared
    # source with the ``tree_synthesis`` gap gate, ADR-0036/0037 Stage 5
    # #58 hardening; this used to re-derive the same NoMaximumHandSize/
    # MaximumHandSize static-mode + no_max_handsize walk inline, a drift
    # risk).
    if has_structural_big_hand_makers(tree):
        fire("big_hand_makers", "")
    # matters SITE gate (:func:`has_structural_big_hand_matters` — a shared
    # source with the ``tree_synthesis`` gap gate, ADR-0036 fold): only a
    # CONDITION threshold (Akki Underling) or a dynamic-P/T modification
    # value (Maro's ``SetDynamicPower``/``SetDynamicToughness`` CDA pair) is
    # a grip PAYOFF — a raw count ref ("discard your hand" =
    # Discard{count: HandSize}) is not, and the hellbent family (HandSize EQ
    # 0 — Bloodhall Priest) is the OPPOSITE payoff, so the condition arm
    # requires a GE/GT comparison against a full-grip bar (>= 4 — the live
    # mirror's "five or more" family, Akki's GE 7).
    if has_structural_big_hand_matters(tree):
        fire("big_hand_matters", "")
    for c in tree.iter_concepts():
        if c.concept == "synth_big_hand_makers":
            fire("big_hand_makers", "")
        elif c.concept == "synth_big_hand_matters":
            fire("big_hand_matters", "")
    return out


def _vehicles_matter(tree: ConceptTree) -> list[Signal]:
    """vehicles_matter (§F) — CR 301.7 + 702.122, the four-arm union:
    (a) a Crews / SaddlesOrCrews trigger (Gearshift Ace, Speedway Fanatic,
    Tiana — the crewING pilot's payoff, SelfRef watcher included);
    (b) a top-level static whose AFFECTED filter subtypes contain Vehicle,
    controller You (Aeronaut Admiral; Depala's "Each Vehicle you control" —
    a structural add over live's plural-literal miss, logged);
    (c) a graveyard→battlefield recursion over a Vehicle filter
    (Greasefang); (d) Tier-1 (ADR-0036/0037 fold): the ``tree_synthesis``
    bucket-B ``synth_vehicles_matter`` node (the deleted
    ``_VEHICLES_MATTER_RX`` relocated, gap-gated against the SAME arms
    a-c — :func:`~mtg_utils._card_ir.tree_synthesis.has_structural_vehicles_matter`).
    Gate #4 membership: a card that IS a Vehicle never fires from its own
    nodes (arms a-c gated; Smuggler's Copter/Peacewalker); ``BecomesCrewed``
    with a SelfRef watcher (Ghost Ark) is not a ``crews?`` payoff — its
    mode is outside arm (a)'s set. Scope "you". Read via the SHARED
    :func:`has_structural_vehicles_matter` predicate for arms a-c
    (GAP-GATE-ALIGNMENT — ADR-0036/0037 Stage 5 #58 hardening; this used
    to re-derive the same three-arm walk inline, a drift risk).
    """
    if has_structural_vehicles_matter(tree):
        return [Signal("vehicles_matter", "you", "", "", tree.name, "high")]
    for c in tree.iter_concepts():
        if c.concept == "synth_vehicles_matter":
            return [Signal("vehicles_matter", "you", "", "", tree.name, "high")]
    return []


LANES = (
    _counter_place_trigger,
    _tribal_etb_multi,
    _typed_enters_punish,
    _noncreature_cast_punish,
    _tap_lanes,
    _tap_untap_matters,
    _dig_until,
    _exile_until_leaves,
    _typed_spellcast_lane,
    _legends_historic_matters,
    _self_blink_lane,
    _scry_surveil_matters,
    _cycling_matters,
    _exert_matters,
    _entered_attacker,
    _saga_matters,
    _life_total_set,
    _unspent_mana,
    _opp_top_exile,
    _kill_engine,
    _control_exchange,
    _land_exchange,
    _land_denial,
    _land_protection,
    _evasion_denial,
    _animate_artifact,
    _color_change,
    _type_change,
    _stax_lanes,
    _keyword_counter,
    _counter_grants_kw,
    _counter_distribute,
    _superfriends_matters,
    _commander_matters,
    _big_hand_lanes,
    _vehicles_matter,
)
