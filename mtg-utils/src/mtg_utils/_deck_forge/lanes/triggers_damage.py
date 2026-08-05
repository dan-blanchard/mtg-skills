"""Crosswalk signal lanes — ETB/LTB/cast triggers, hand disruption, keyword
grants, base-P/T, doublers, and the damage-trigger / mass-damage cluster
(split from crosswalk_signals.py)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from mtg_utils._card_ir.crosswalk import (
    OTHER,
    AbilityUnit,
    ConceptTree,
    cast_with_keyword_name,
    change_zone_dirs,
    damage_filter_scope,
    damage_recipient_is_player,
    damage_to_player_trigger_kind,
    detriment_directed_scope,
    double_target_kind,
    double_triggers_cause_core_types,
    effect_filter,
    effect_owner_player_scope,
    entered_this_turn_filters,
    filter_controller,
    filter_core_types,
    filter_predicates,
    filter_subtypes,
    granted_next_spell_keyword,
    is_creature_cast_trigger_def,
    is_creature_etb_trigger_def,
    is_damage_reflect_trigger_def,
    is_opponent_cast_trigger_def,
    iter_cost_leaves,
    iter_deep_target_grants,
    iter_delayed_trigger_condition_defs,
    iter_mod_sites,
    iter_nested_trigger_defs,
    iter_single_target_grants,
    iter_static_defs,
    iter_threaded_target_statics,
    iter_typed_nodes,
    mana_restrictions,
    mod_keyword_name,
    player_filter_tag,
    recipient_tag,
    ref_count_qty,
    ref_qty_tag,
    replacement_damage_mod,
    replacement_event_tag,
    replacement_qty_mod,
    replacement_token_owner_scope,
    spell_count_at_least,
    spell_velocity_static_two,
    static_mode_tag,
    static_reveal_who,
    tag_of,
    trigger_constraint_n,
    trigger_constraint_tag,
    trigger_damage_kind,
    trigger_subject_scope,
    zone_change_count_reads,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import (
    _FORCE_ATTACK,
    _FORCE_ATTACK_REF,
    combat_damage_recipients_from_text,
)
from mtg_utils._card_ir.tree_synthesis import SynthesizedNode
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _REVEAL_WHO_OPP,
    _SPELL_GRANT_KEYWORDS,
    _attack_compulsion_hit,
    _kept,
    _site_raw,
    _unknown_mode_combat_damage_to_player,
)
from mtg_utils._deck_forge.signal_base import Signal
from mtg_utils._deck_forge.text_reads import (
    _BASE_PT_ANIMATE_HOOK,
    _BASE_PT_RAW_HOOK,
    _DAMAGE_REDIRECT_MIRROR,
    _ETB_HAD_RE,
    _creature_etb_clause,
    _detect_self_damage_prevention,
)


def _norm_kw(kw: str) -> str:
    """Normalize a phase keyword spelling for set membership (lower,
    spaceless, hyphenless — ``JumpStart`` → ``jumpstart``)."""
    return kw.lower().replace(" ", "").replace("-", "")


def _spell_keyword_grant(tree: ConceptTree) -> list[Signal]:
    """spell_keyword_grant (+ flash_grant / flash_makers / convoke_makers)
    — grants a keyword to spells / castable cards (CR 702.8 flash, 702.34
    flashback, 702.51 convoke, 601.3e). Three typed arms:

    * a ``CastWithKeyword`` STATIC ("you may cast spells as though they had
      flash" — Leyline of Anticipation; "<class> spells you cast have
      <keyword>" — Chief Engineer's convoke grant), read via
      :func:`cast_with_keyword_name`;
    * an ``AddKeyword`` modification whose keyword is a SPELL-CAST keyword
      (:data:`_SPELL_GRANT_KEYWORDS` — Snapcaster Mage's targeted Flashback
      grant); the curated set is the spell-vs-battlefield discriminator (an
      evergreen grant is team_buff territory, checklist #3);
    * a ``GrantNextSpellAbility`` effect ("the next spell you cast this
      turn has convoke" — Wand of the Worldsoul), a ONE-SHOT ability grant
      distinct from the always-on static form, read via
      :func:`granted_next_spell_keyword`.

    Gate #2: beneficiary you — the affected filter/player must not name an
    opponent. A Flash grant additionally opens flash_grant + flash_makers
    (the live structural ``cast_with_keyword{flash}`` pair); a Convoke
    grant additionally opens convoke_makers (CR 702.51 — the GRANTER form;
    a card's OWN printed convoke keyword is the separate ``_keyword_field_
    signals_b7`` field-lookup). A PRINTED keyword bearer (Faithless
    Looting's own Flashback) carries no grant node and never fires. A
    conditional printed SELF-flash ("~ has flash as long as you control a
    Merfolk" — Crashing Tide) parses as ``AddKeyword`` with
    ``affected=SelfRef``: the card grants only ITSELF castability (CR
    702.8a), not your spells — the SelfRef veto keeps all three keys out.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    def grant(kw: str, raw: str) -> None:
        fire("spell_keyword_grant", raw)
        if _norm_kw(kw) == "flash":
            fire("flash_grant", raw)
            fire("flash_makers", raw)
        elif _norm_kw(kw) == "convoke":
            fire("convoke_makers", raw)

    for unit in tree.units:
        if unit.origin == "static":
            kw = cast_with_keyword_name(unit.node)
            affected = getattr(unit.node, "affected", None)
            if (
                kw is not None
                and tag_of(affected) != "SelfRef"
                and filter_controller(affected) != "Opponent"
            ):
                grant(kw, "")
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = mod_keyword_name(mod)
            if kw is None or _norm_kw(kw) not in _SPELL_GRANT_KEYWORDS:
                continue
            affected = getattr(sdef, "affected", None)
            if tag_of(affected) == "SelfRef":
                continue  # a self-grant is castability of this card, not an engine
            if filter_controller(affected) == "Opponent":
                continue  # a grant to the opponent's spells is not your engine
            grant(kw, _site_raw(sdef))
        for n in iter_typed_nodes(unit.node):
            kw = granted_next_spell_keyword(n)
            if kw is None:
                continue
            if tag_of(getattr(n, "player", None)) == "Opponent":
                continue  # a grant to an opponent's next spell is not your engine
            grant(kw, "")
    return out


# ADR-0038 deferral sweep unit 4: the specific missing fact a detriment-
# directed LoseLife/RevealTop node's own fields never carry — "reveals
# {their/his or her/its} hand" (third-person only, matching the grammar's
# own "reveal_hand_action" gate — "your hand" is a self-reveal, never this
# lane). Matched against :func:`_kept` (reminder-stripped), gated to a
# NARROW compound-effect confirmation (Thoughtcutter Agent, Psychotic
# Episode), never a bare reveal-adjacent scan.
_REVEALS_HAND_TEXT_RE = re.compile(
    r"reveals?\s+(?:their|his or her|its)\s+hands?\b", re.IGNORECASE
)


def _hand_disruption(tree: ConceptTree) -> list[Signal]:
    """hand_disruption — opponent hand reveal/peek (CR 402.3: "a player
    can't look at the cards in another player's hand"). Two typed arms:

    * a ``RevealHand`` EFFECT whose recipient EXPLICITLY names another
      player (Duress — ``Typed controller=Opponent``; Addle — a targeted
      ``Player``; checklist #5). A self-reveal (Goblin Secret Agent —
      ``Controller``) never fires; nor does a bare ``Any`` target UNLESS
      the OWNING wrapper's ``player_scope`` is symmetric-or-wider
      (Kamahl's Summons / Noxious Vapors — "each player reveals their
      hand": ``Any`` there is the CARD selection, not the player, same as
      the self-reveal case, but a genuine "each player" wrapper scope
      still counts — ADR-0037/0038 W3, mirroring phasing_makers'
      blanket-not-split precedent: the key's scope is hardcoded
      "opponents" regardless of symmetry);
    * the ``RevealHand`` STATIC mode ("your opponents play with their hands
      revealed" — Telepathy; the symmetric Zur's Weirding reaches their
      hands too), via :func:`static_reveal_who`.

    ADR-0037/0038 W3: a ``RevealHand`` buried inside a GRANTED activated
    ability (Dementia Sliver's tribal static: "All Slivers have '{T}:
    Choose a card name. Target opponent reveals a card at random from
    their hand...'") is never its own top-level unit — reached via
    :func:`iter_typed_nodes`'s generic deep walk (unlike
    ``iter_nested_trigger_defs``, which only covers ``GrantTrigger``/
    ``CreateEmblem``, a ``GrantAbility``'s ``definition`` field needs the
    fully generic walk).

    ADR-0038 deferral sweep unit 4 (Dan's detriment-directed-targeting
    principle — see :func:`~mtg_utils._card_ir.crosswalk.
    detriment_directed_scope`): two more no-residue/unbound shapes closed:

    * Friendly Fire's "target creature's controller reveals a card at
      random from their hand" — the possessive binding between a
      TARGETED creature and "that player" lives only in prose; phase
      structures a bare ``RevealHand{target: Any}`` with no player field
      connecting it to the creature target at all. Structural precondition
      (never text-matched, corpus-verified unique shape): a
      ``RevealHand{target: Any}`` in a unit whose FIRST effect is a
      ``TargetOnly`` naming a Creature — the possessive CR 109.5
      back-reference the shape itself establishes.
    * Thoughtcutter Agent ("Target player loses 1 life and reveals their
      hand") / Psychotic Episode ("Target player reveals their hand and
      the top card of their library...") — phase structures only the
      OTHER half of the compound ("loses 1 life" / "the top card"); the
      hand-reveal half leaves no node of its own at all. A detriment-
      directed ``LoseLife``/``RevealTop`` recipient (opponent-directed by
      :func:`detriment_directed_scope`) COMBINED with the ability's own
      text confirming the specific missing fact ("reveals {their/his or
      her/its} hand") — the same text-confirms-after-structural-
      confirmation discipline as ``_tap_lanes``'s
      ``_OPPONENT_CONTROLS_TAP_RE`` — recovers both without opening the
      lane to any bare reveal-adjacent text (corpus-verified: every OTHER
      commander-legal match is an already-firing Thoughtseize-style
      discard spell, so this arm is never the deciding vote for them).

    Scope "opponents" (the live lane's).
    """
    for unit in tree.units:
        for c in unit.effects:
            if c.concept == "reveal_hand" and c.recovered_by:
                # ADR-0037/0038 W3 + ADR-0038 deferral sweep unit 4: a
                # grammar-recovered "plays with {their/its} hand revealed"
                # STATIC clause (Sen Triplets, Stromgald Spy) or the
                # IMPERATIVE "reveal(s) {their/his or her/its} hand" ACTION
                # idiom (Alhammarret, High Arbiter) — the recovered node's
                # ``.node`` is still the phase Unimplemented wrapper (no
                # ``target`` field of its own), so trust the recovery
                # unconditionally (the grammar's third-person-only gate
                # already excludes a self-reveal).
                return [
                    Signal("hand_disruption", "opponents", "", c.raw, tree.name, "high")
                ]
            if tag_of(c.node) == "RevealHand" and _reveal_names_other_player(
                c.node, unit.node
            ):
                return [
                    Signal("hand_disruption", "opponents", "", c.raw, tree.name, "high")
                ]
        if unit.origin == "static" and static_reveal_who(unit.node) in _REVEAL_WHO_OPP:
            return [Signal("hand_disruption", "opponents", "", "", tree.name, "high")]
        if unit.origin == "static":
            for n in iter_typed_nodes(unit.node):
                if tag_of(n) == "RevealHand" and _reveal_names_other_player(
                    n, unit.node
                ):
                    return [
                        Signal(
                            "hand_disruption", "opponents", "", "", tree.name, "high"
                        )
                    ]
        # Friendly Fire's "target creature's controller reveals ..." shape.
        if unit.effects and tag_of(unit.effects[0].node) == "TargetOnly":
            first_filt = effect_filter(unit.effects[0].node)
            if first_filt is not None and "Creature" in filter_core_types(first_filt):
                for c in unit.effects:
                    if (
                        tag_of(c.node) == "RevealHand"
                        and tag_of(getattr(c.node, "target", None)) == "Any"
                    ):
                        return [
                            Signal(
                                "hand_disruption",
                                "opponents",
                                "",
                                c.raw,
                                tree.name,
                                "high",
                            )
                        ]
        # Thoughtcutter Agent / Psychotic Episode's dropped hand-reveal half.
        if _REVEALS_HAND_TEXT_RE.search(_kept(tree)):
            for c in unit.effects:
                if tag_of(c.node) in ("LoseLife", "RevealTop") and (
                    detriment_directed_scope(c.node) == "opponents"
                ):
                    return [
                        Signal(
                            "hand_disruption", "opponents", "", c.raw, tree.name, "high"
                        )
                    ]
    return []


# RevealHand recipient tags that EXPLICITLY name another player (CR 402.3).
# ``Any`` / ``ScopedPlayer`` are deliberately absent — phase's self-reveal
# ("reveal any number of cards from your hand") carries a bare ``Any`` CARDS
# target, not a player, and ``ScopedPlayer`` defers to the wrapper's OWN
# player_scope (read separately — see ``_reveal_names_other_player``'s
# ``unit_node`` arm). ``DefendingPlayer`` (Port Inspector, Zara) is
# opponent-directed BY RULE (CR 506.2 — the b11 tap_down precedent), same as
# ``EachOpponent``.
_REVEAL_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "Player",
        "ParentTarget",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ParentTargetController",
        "Each",
        "AllPlayers",
        "EachPlayer",
        "DefendingPlayer",
    }
)
# player_scope tags on the OWNING wrapper that make an ambiguous ``Any``/
# ``ScopedPlayer`` RevealHand recipient count as opponent-directed — a
# symmetric "each player reveals" wrapper scope (Kamahl's Summons, Noxious
# Vapors) still discloses opponents' hands, matching the key's hardcoded
# "opponents" scope regardless of symmetry; an explicit "Opponent"/
# "Opponents" wrapper scope (Valki, God of Lies: "each opponent reveals
# their hand" — player_scope carries the "for each opponent" edict, the
# RevealHand's OWN target reads bare ``Any``) is unambiguous.
_REVEAL_SCOPE_WRAPPER_TAGS: frozenset[str] = frozenset(
    {"All", "AllPlayers", "Each", "Opponent", "Opponents", "EachOpponent"}
)


def _reveal_names_other_player(node: TypedMirrorNode, unit_node: object = None) -> bool:
    """Whether a ``RevealHand`` effect's recipient names ANOTHER player —
    an explicit player tag, an opponent-controlled ``Typed`` filter, a
    ``ChosenPlayer`` backreference to a SIBLING ``Choose{choice_type:
    Opponent}`` in the same unit (Anointed Peacekeeper, Arachne, Sorcerous
    Spyglass: "look at an opponent's hand, then choose …"), or an
    ambiguous ``Any``/``ScopedPlayer`` recipient whose OWNING wrapper's
    ``player_scope`` is symmetric-or-wider (:data:`_REVEAL_SCOPE_WRAPPER_
    TAGS`). ``unit_node`` is optional — omitting it skips the ChosenPlayer/
    player_scope arms (the STATIC-mode nested-descent call site has no
    single owning unit to scope a wrapper lookup to)."""
    t = recipient_tag(node)
    if t in _REVEAL_PLAYER_TAGS:
        return True
    if t == "Typed":
        filt = effect_filter(node)
        if filter_controller(filt) == "Opponent":
            return True
        raw_ctrl = getattr(filt, "controller", None)
        is_chosen_player = (
            isinstance(raw_ctrl, MirrorVariant) and raw_ctrl.key == "ChosenPlayer"
        )
        if unit_node is not None and is_chosen_player:
            return any(
                tag_of(n) == "Choose" and getattr(n, "choice_type", None) == "Opponent"
                for n in iter_typed_nodes(unit_node)
            )
    if unit_node is not None and t in ("Any", "ScopedPlayer"):
        return effect_owner_player_scope(unit_node, node) in _REVEAL_SCOPE_WRAPPER_TAGS
    return False


# ── Batch 10 lanes (ADR-0035 Stage 2) ────────────────────────────────────────

# Evasion subset for the generic-team grant (live ``_EVASION_GRANT_KW``).
_TEAM_EVASION_KW: frozenset[str] = frozenset(
    {"flying", "intimidate", "shadow", "horsemanship", "fear", "menace", "skulk"}
)
# ADR-0038 W3 batch-3 — the BROADER team_evasion_grant forms (live's own
# SANCTIONED kept-oracle mirror, byte-identical port, ``_IR_KEPT_DETECTORS``):
# a tribal- (Galerider Sliver), color- (Deepchannel Mentor), core-type- (
# Anikthea's "Other enchantment creatures"; Cyberdrive Awakener's "Other
# artifact creatures"), power- (Delney), or Equipped-qualified (Dalakos)
# team grant, plus any ONE-SHOT ("gain … until end of turn" — Dread Charge,
# Driven // Despair, Agility Bobblehead, Glaring Spotlight) grant of an
# evasion keyword OR the "can't be blocked" static mode (CR 509.1b defines
# this as an evasion ability; phase structures it as an ``AddStaticMode``
# {CantBeBlockedExceptBy}, a DIFFERENT modification tag from ``AddKeyword``
# with no concept mapping of its own — Dread Charge, Delney, Agility
# Bobblehead, Glaring Spotlight all reach team_evasion_grant ONLY through
# this word idiom). The live structural gate above (``team and kw in
# _TEAM_EVASION_KW``) deliberately excludes ALL of these (the subtype/
# predicate/one-shot exclusions are what keep the flood out of the OTHER
# lanes reading the SAME mod-site loop); this is a SEPARATE whole-card scan,
# not a narrowing of that gate. CR 702.9/702.13/702.28/702.31/702.36/
# 702.111/702.118/509.1b.
_TEAM_EVASION_GRANT_RX = re.compile(
    r"(?:other |attacking )?creatures you control (?:gain|have)\b"
    r"[^.]{0,40}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk"
    r"|flying|can't be blocked)\b"
    r"|(?:other |attacking )?creatures you control[^.]*can't be blocked",
    re.IGNORECASE,
)
# The deleted SWEEP detector's exact single-target keyword-grant regex
# (``_sweep_detectors.KEYWORD_GRANT_TARGET_REGEX``), reused verbatim
# (ADR-0038 W3 batch 4) as the split/aftermath back-half text-only-tree
# residue read below — single source, zero drift.
_KEYWORD_GRANT_TARGET_KEPT_RX = re.compile(
    r"target creature (?:you control )?(?:gains?|gets [+\-][0-9x]/[+\-][0-9x] "
    r"and gains?) (?:deathtouch|trample|flying|menace|vigilance|double strike"
    r"|first strike|lifelink|haste|hexproof|indestructible|protection|reach"
    r"|ward|shroud)",
    re.IGNORECASE,
)
# Protective keywords (live ``_PROTECTION_GRANT_KW`` — CR 702.11 hexproof /
# 702.12 indestructible / 702.16 protection / 702.18 shroud / 702.21 ward).
_PROTECTIVE_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "shroud", "indestructible", "ward", "protection"}
)
# Evergreen allowlist for the Aura/Equipment-subgroup grant (live
# ``_AURA_EQUIP_GRANT_KW`` — excludes equip{0}/crew cost grants).
_AURA_EQUIP_KW: frozenset[str] = frozenset(
    {
        "exalted",
        "flying",
        "trample",
        "deathtouch",
        "lifelink",
        "vigilance",
        "haste",
        "firststrike",
        "doublestrike",
        "hexproof",
        "ward",
        "menace",
        "reach",
        "indestructible",
    }
)
# Suit-up predicates: the grant lands on the creature the Aura/Equipment is
# attached to (live ``_is_aura_equip_protection_subject`` — CR 303 / 301).
_SUIT_UP_PREDS: frozenset[str] = frozenset({"EnchantedBy", "EquippedBy"})
# ``DoublePT`` modes that double POWER (CR 613.4c; a toughness-only doubler is
# not the beater build-around).
_POWER_DOUBLE_MODES: frozenset[str] = frozenset({"Power", "PowerAndToughness"})
# Direct-player recipient tags for the damage_equal_power read (CR 120.3).
# ``Any`` is "any target" (a player is reachable); ``ParentTarget``/``Target``
# are DELIBERATELY absent — they re-reference an earlier (creature) target.
_DEP_PLAYER_TAGS: frozenset[str] = frozenset(
    {
        "Any",
        "Player",
        "TriggeringPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "Each",
        "AllPlayers",
        "EachPlayer",
    }
)


def _unknown_mode_creature_etb(trig: object) -> str | None:
    """Whether trigger DEFINITION ``trig`` is an Unknown-mode node whose OWN
    ``description`` field confirms CR 603.6a's creature-ETB payoff shape
    phase couldn't classify structurally at all — a filter phase's typed
    ``valid_card`` parse doesn't cover (Symmetry Matrix's power-equals-
    toughness filter, Gladewalker Ritualist's named-self filter, Bess, Soul
    Nourisher's base-power-and-toughness-1/1 filter all fall back to an
    ``Unknown`` mode carrying only the raw description). Read ONLY when the
    structural predicate (:func:`is_creature_etb_trigger_def`) already
    missed this exact node — never overrides a structural hit, matching
    ``_unknown_mode_combat_damage_to_player``'s fallback-only contract.
    Reuses the legacy ``_creature_etb_clause`` two-scope regex VERBATIM but
    scoped to this ONE trigger's own description — never blended with a
    sibling ability's text the way the whole-card kept-mirror is, so the
    cross-clause bleed the whole-card mirror is prone to (Kitnap,
    Scrapshooter, Callidus Assassin — an unrelated "a card"/"a copy of any
    creature" elsewhere on the card coincidentally completing the regex)
    can't happen here.
    """
    mode = getattr(trig, "mode", None)
    if not (isinstance(mode, MirrorVariant) and mode.key == "Unknown"):
        return None
    desc = getattr(trig, "description", "") or ""
    return _creature_etb_clause(desc.lower())


def _unimplemented_ability_creature_etb(node: object) -> str | None:
    """Whether an ``origin == "ability"`` unit's node is a WHOLE-ability
    ``Unimplemented`` effect (phase parsed none of it — not even a trigger
    mode) whose OWN ``description`` confirms CR 603.6a's creature-ETB shape:
    the Stickers-card family (Familiar Beeble Mascot, Cool Fluffy Loxodon,
    Geek Lotus Warrior — each ``{TK}``-templated sticker line is its own
    isolated ability unit, so the per-unit description is never blended
    with a sibling line the way a whole-card mirror would be). Corpus
    re-measured across all 31622 commander-legal joined cards: exactly
    these 3 fire and nothing else — the ``{TK}`` template marker plus the
    Unimplemented-whole-ability gate makes this safe without a Stickers-
    specific allowlist.
    """
    eff = getattr(node, "effect", None)
    if eff is None or tag_of(eff) != "Unimplemented":
        return None
    desc = getattr(node, "description", "") or ""
    return _creature_etb_clause(desc.lower())


def _delayed_had_enter_creature_etb(trig: object) -> bool:
    """Whether a trigger DEFINITION's own ``description`` matches the
    legacy ``_ETB_HAD_RE`` delayed-payoff idiom: "at the beginning of
    upkeep, if you HAD a creature enter the battlefield ... last turn, …"
    (Ephara, God of the Polis). Unlike :func:`_unknown_mode_creature_etb`
    this is NOT gated on an Unknown mode — phase correctly classifies
    Ephara's trigger as a ``phase``-event (upkeep) trigger, not a
    ``ChangesZone``/enters event at all, so there's no ``etb`` event for a
    structural arm to ever reach (ADR-0027 β's original rationale for
    riding the whole-card kept-mirror here). Scoped per-unit like the other
    fallback arms — full-corpus re-measure confirms only Ephara's own
    description matches this specific idiom, so it's safe unconditional on
    ``mode`` (commander-legal corpus: 1 hit, 0 collateral).
    """
    desc = getattr(trig, "description", "") or ""
    return _ETB_HAD_RE.search(desc.lower()) is not None


def _etb_trigger_lanes(tree: ConceptTree) -> list[Signal]:
    """creature_etb + permanent_etb — the ETB-payoff pair (CR 603.6a: "Whenever
    a [type] enters, …"). One shared trigger walk:

    * ``creature_etb`` — an ``enters``/``entersorattacks`` trigger whose
      watched-object filter has the Creature core type (Soul Warden), via
      :func:`is_creature_etb_trigger_def`. Scope from the filter's
      controller (checklist #5 — the trigger's OWN ``valid_card`` node):
      null/You → "you", Opponent → "opponents" (the punisher row). A SelfRef
      watcher (Elvish Visionary's enters-draw) is ETB *value on itself*, not
      a payoff ENGINE — never fires. **Arm 2** (the known-lossy-case
      improvement over live, which NEUTRALIZED its structural arm and rides
      a byte mirror): a ``DoubleTriggers`` static whose cause is an
      ``EntersBattlefield`` whose core types include Creature — or are
      EMPTY, the any-permanent form that subsumes creatures (Panharmonicon /
      Yarok / Elesh Norn, per Panharmonicon's 2021-03-19 ruling). **Arm 3**
      (b10 follow-up b): the "if a creature entered the battlefield under
      your control this turn" CONDITION family carries a typed
      ``EnteredThisTurn`` qty whose filter names the population (Bellowing
      Elk — Creature core, controller You; the batch-10 "no phase condition
      node" comment was STALE for this slice). The Celebration nonland-
      permanent forms (Ash, Party Crasher) and the filterless self-check
      (Cactuar) fail the Creature/You gates (measured live parity); Ephara
      HERSELF still parses condition-less as an ``EnteredThisTurn`` qty (no
      such node at all) — recovered a different way this batch, **Arm 8**
      below.

      ADR-0038 W3 batch 6 (draw-etb-tokens cluster): five more arms, all
      reusing :func:`iter_nested_trigger_defs` /
      :func:`iter_delayed_trigger_condition_defs`'s shared granted-trigger
      descent (the SAME two iterators ``creature_cast_trigger`` /
      ``opponent_cast_matters`` already ride) rather than growing a new
      walk: **Arm 4** a ``GrantTrigger``/``CreateEmblem`` nested creature-ETB
      def (Nurturing Presence's Aura grant; Kiora/Huatli/Mila's -7/-8
      emblems), **Arm 5** a ``CreateDelayedTrigger``'s ``WheneverEvent``
      watcher (First Day of Class / Rite of Harmony / Theoretical
      Duplication's "this turn" delayed trigger — an Instant/Sorcery
      installing a temporary ETB watcher, not itself a top-level trigger
      unit), **Arm 6** :func:`_unknown_mode_creature_etb`'s per-node
      description fallback for the three filters phase's ``valid_card``
      parse can't structurally represent at all (Symmetry Matrix,
      Gladewalker Ritualist, Bess Soul Nourisher), and **Arm 7**
      :func:`_unimplemented_ability_creature_etb`'s per-unit description
      fallback for a WHOLE-ability ``Unimplemented`` node (the Stickers
      family's ``{TK}``-templated lines — Familiar Beeble Mascot, Cool
      Fluffy Loxodon, Geek Lotus Warrior; full-corpus re-measure: exactly
      these 3 fire, nothing else), and **Arm 8**
      :func:`_delayed_had_enter_creature_etb`'s per-trigger description
      fallback for the legacy ``_ETB_HAD_RE`` delayed-payoff idiom (Ephara,
      God of the Polis's condition-less upkeep check — phase models it as
      a ``phase``-event trigger with no ``etb`` event at all, so no
      structural arm can ever reach it; unconditional on ``mode`` since
      full-corpus re-measure shows only Ephara's own description matches).
      Also widened: the
      compound ``entersorattacks`` event (Kindred Discovery) folds into
      :func:`is_creature_etb_trigger_def` directly (CR 603.2 — one trigger
      condition naming two alternative events; the predicate only asserts
      the entering half). The Soulbond/Graft granted-ability bodies
      (CR 702.95a/702.58a) parse as TWO top-level trigger units each — the
      SelfRef "when this creature enters, pair/graft" half (excluded, ETB
      value on itself) and a second "whenever ANOTHER creature you control
      enters" half with a Creature-typed ``valid_card`` — so they already
      fire via the EXISTING top-level Arm 1 (:func:`is_creature_etb_trigger_def`
      applied to ``unit.node`` directly), no new code; verified as
      CR-grounded cw_only gains this batch (not previously adjudicated).

      NOT recovered (adjudicated SHEDS — legacy over-fires this lane never
      reproduces): (1) a "when you cast a creature spell, that creature
      enters with N additional counters" idiom (Boreal Outrider, Communal
      Brewing, Jade Orb of Dragonkind, Chocobo Camp, Yuna, Grand Summoner,
      Runadi, Behemoth Caller, Torgal, A Fine Hound, Wildgrowth Archaic,
      Long List of the Ents, Summon: Fenrir, Kumano Faces Kakkazan) is a
      CAST-triggered replacement of how the permanent enters (CR 614.12),
      not an ENTERS-event trigger — ``creature_cast_trigger``'s own
      docstring already names these as ITS gap, confirming the lane
      boundary; (2) a combat-damage/attacks trigger merely CONDITIONED on
      "that creature entered this turn" (Samut, Vizier of Naktamun,
      Goro-Goro and Satoru, Pick Up the Pace, Whirlwind, Killer Cyclone,
      Hixus, Prison Warden, Park Heights Pegasus, Redoubled Stormsinger) —
      the watched EVENT is combat damage/attacking (CR 510.1b/508.1), not
      entering; legacy's whole-clause regex can't tell a trigger's OWN
      event from a same-clause CONDITION and fires on the "creature ...
      entered" substring regardless; (3) legacy's ``[^.]*``-spanning regex
      bleeding an unrelated "a"/"creature"/"enter[s]" across a
      newline-joined but period-less span of UNRELATED ability lines
      (Kitnap, Scrapshooter, Callidus Assassin, Cherished Hatchling,
      Crafty Cutpurse, Lictor, Call the Mountain Chocobo, Choco-Comet,
      Chocobo Racetrack, Gysahl Greens, Sidequest: Raise a Chocobo,
      Summon: Fat Chocobo, Ka-Zar of the Savage Land, The Prydwen, Steel
      Flagship, Paleontologist's Pick-Axe) — verified per-card via the match
      SPAN, never a real creature-ETB trigger; (4) the ``DOUBLER`` regex
      firing on a LAND/ARTIFACT/legendary-permanent trigger-doubler with no
      Creature filter at all (Traveling Chocobo, Ancient Greenwarden,
      Gandalf the White) — CR 603.6a requires the watched event's filter
      include the Creature core type, which these lack; (5) Sweet-Gum
      Recluse's SelfRef "when this creature enters" whose ONLY "a/another/
      each creature ... enter" match is its OWN targeting filter ("any
      number of target creatures that entered this turn") — a targeting
      restriction, not a payoff engine, consistent with the SelfRef
      exclusion. All corpus re-measured 0 genuine members lost — live_only
      after this batch is exactly this adjudicated shed set. CR 603.6a.
    * ``permanent_etb`` — the GENERIC permanent-ETB engine: a Permanent-cored
      watcher with controller You (Amareth; checklist #6 — an opp-scoped
      permanent-ETB punisher is excluded, mirroring live).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str) -> None:
        if key + scope not in seen:
            seen.add(key + scope)
            out.append(Signal(key, scope, "", "", tree.name, "high"))

    def fire_etb_from(trig: object) -> None:
        ctrl = filter_controller(getattr(trig, "valid_card", None))
        fire("creature_etb", "opponents" if ctrl == "Opponent" else "you")

    for unit in tree.units:
        if unit.origin == "trigger":
            if is_creature_etb_trigger_def(unit.node):
                fire_etb_from(unit.node)
            elif unit.trigger_event == "enters":
                vc = getattr(unit.node, "valid_card", None)
                if "Permanent" in filter_core_types(vc) and (
                    filter_controller(vc) == "You"
                ):
                    fire("permanent_etb", "you")
            else:
                scope = _unknown_mode_creature_etb(unit.node)
                if scope is not None:
                    fire("creature_etb", scope)
                elif _delayed_had_enter_creature_etb(unit.node):
                    fire("creature_etb", "you")
        elif unit.origin == "ability":
            scope = _unimplemented_ability_creature_etb(unit.node)
            if scope is not None:
                fire("creature_etb", scope)
        if unit.origin == "static":
            dt_cores = double_triggers_cause_core_types(unit.node)
            if dt_cores is not None and (not dt_cores or "Creature" in dt_cores):
                fire("creature_etb", "you")
        for filt in entered_this_turn_filters(unit.node):
            # None controller: the v0.32.0 entry-ledger shape scopes the
            # controller on the qty's own player field (the helper already
            # gates on it), leaving the filter's controller null.
            if "Creature" in filter_core_types(filt) and (
                filter_controller(filt) in ("You", None)
            ):
                fire("creature_etb", "you")
        for trig in iter_nested_trigger_defs(unit.node):
            if is_creature_etb_trigger_def(trig):
                fire_etb_from(trig)
        for trig in iter_delayed_trigger_condition_defs(unit.node):
            if is_creature_etb_trigger_def(trig):
                fire_etb_from(trig)
    return out


def _ltb_matters(tree: ConceptTree) -> list[Signal]:
    """ltb_matters — the leaves-the-battlefield payoff (CR 603.6c). Two typed
    arms: the bare ``LeavesBattlefield`` mode (Luminous Phantom) and a
    ``ChangesZone`` FROM the battlefield to a non-graveyard zone. Gates:
    recall-completion b1 (ADR-0034) NOW fires a SelfRef self-LTB value trigger
    ("when THIS leaves the battlefield, [value]" — Skyclave Apparition, Sengir
    Autocrat, Walker of the Grove, Thalakos Seer): unlike death→self_death_payoff
    there is NO separate self_ltb lane, so live keys BOTH self and other leaves on
    ``ltb_matters`` (verified: every SelfRef leaves-trigger fires it, the O-Ring
    cards Fiend Hunter / Oblivion Ring co-fire ``exile_until_leaves`` + ltb_matters,
    Banishing Light carries an exile-DURATION not a leaves-trigger so stays out).
    An ``AttachedTo`` watcher (Curator's Ward /
    Traveling Plague — insurance on the ONE enchanted object, the same
    boundary the exile_matters lane draws) still never fires; a graveyard-ARRIVAL "from
    anywhere" watcher (Compost — dest Graveyard, no battlefield origin) is
    graveyard territory, and CR 603.6c explicitly de-classifies it as an LTB
    ability. Third arm (b10 follow-up a — the batch-10 "no phase node"
    comment was STALE): the "a permanent left the battlefield under your
    control this turn" CONDITION family carries a typed
    ``ZoneChangeCountThisTurn {from: Battlefield}`` qty (the Revolt shape —
    Airdrop Aeronauts / Aid from the Cowl; 33 corpus with controller You).
    Zone-precise: Morbid's ``to: Graveyard`` variant (Tragic Slip — a death
    check) and the bounce-precise ``to: Hand`` (Barrin, Tolarian Archmage)
    carry a ``to`` and never fire; the controller-less symmetric forms
    (Alpharael, Stonechosen) fail the You gate (measured live parity). Scope
    from the watched object's controller (trigger arms) / "you" (condition
    arm, matching live).
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) == "AttachedTo":
            continue
        origin, dest = change_zone_dirs(unit.node)
        is_ltb = unit.trigger_event == "leaves" or (
            origin == "Battlefield" and dest not in ("Graveyard", "Battlefield")
        )
        if is_ltb:
            # A self-LTB (SelfRef) value trigger keys "you" (the self form); an
            # other-permanent watcher keys its watched object's controller.
            scope = (
                "you" if tag_of(vc) == "SelfRef" else trigger_subject_scope(unit.node)
            )
            return [Signal("ltb_matters", scope, "", "", tree.name, "high")]
    for unit in tree.units:
        for frm, to, filt in zone_change_count_reads(unit.node):
            if frm == "Battlefield" and to is None and filter_controller(filt) == "You":
                return [Signal("ltb_matters", "you", "", "", tree.name, "high")]
    return []


def _creature_cast_trigger(tree: ConceptTree) -> list[Signal]:
    """creature_cast_trigger — the creature-spell cast payoff (CR 701.5a /
    603.2): a ``SpellCast`` trigger whose watched-spell filter carries the
    Creature core type (Beast Whisperer). An instant/sorcery watcher (Talrand
    → spellcast_matters) and a NONcreature watcher (Kambal — the ``{Non:
    Creature}`` entry is dropped by the negation-aware type read) never fire.

    :func:`is_creature_cast_trigger_def` is this SAME predicate, applied at
    TWO tree positions (ADR-0037/0038 W1 batch-3, reusing the shared
    granted-trigger descent): a top-level trigger unit's own node, and a
    NESTED trigger definition :func:`iter_nested_trigger_defs` reaches
    inside a GRANTED-ability construct — Garruk, Caller of Beasts's -7
    emblem (``CreateEmblem.triggers``), Blink's Alien Angel token grant (a
    ``GrantTrigger`` nested inside the Chapter II/IV Token effect). The
    remaining gap cards (Boreal Outrider, Communal Brewing, Kozilek's
    Return, Runadi, Behemoth Caller, Volo, Itinerant Scholar, Wildgrowth
    Archaic, Glimpse of Nature) all carry the "whenever you cast a[n] ...
    creature spell" idiom as a REPLACEMENT unit's ``valid_card`` (an
    approximated "the cast creature enters with counters" rewrite, several
    with a phase ``SwallowedClause`` parse warning) or a
    ``CreateDelayedTrigger`` condition — no shape the flat trigger-unit
    walk (or the granted-trigger descent) reaches — so
    ``tree_synthesis._arm_creature_cast_trigger`` fills those from
    ``tree.oracle`` directly via a synthetic ``creature_cast`` marker (this
    key's underlying read is trigger-unit-based, not
    ``effect_concepts``-based, matching opponent_cast_matters's mechanism).
    Scope "any" (the live hard-emit).
    """
    for unit in tree.units:
        if unit.origin == "trigger" and is_creature_cast_trigger_def(unit.node):
            return [Signal("creature_cast_trigger", "any", "", "", tree.name, "high")]
    for unit in tree.units:
        for trig in iter_nested_trigger_defs(unit.node):
            if is_creature_cast_trigger_def(trig):
                return [
                    Signal("creature_cast_trigger", "any", "", "", tree.name, "high")
                ]
    for c in tree.effect_concepts("creature_cast"):
        if isinstance(c.node, SynthesizedNode):
            return [
                Signal("creature_cast_trigger", "any", "", c.raw, tree.name, "high")
            ]
    return []


def _opponent_cast_matters(tree: ConceptTree) -> list[Signal]:
    """opponent_cast_matters — the opponent-cast punisher (CR 102.2/102.3 +
    603.2): a ``SpellCast`` trigger whose cast-PLAYER recipient node names an
    opponent (Kambal — ``valid_target {Typed, controller: Opponent}``;
    checklist #5, the recipient node, never a summary scope). The SYMMETRIC "a
    player casts" punisher (Eidolon of the Great Revel — no recipient node) is
    CORRECTLY excluded: "a player" includes you (CR 102.1). A self-cast
    watcher (Beast Whisperer — ``Controller``) never fires. The batched
    ``SpellCastOrCopy`` mode ("whenever [a player] casts or copies …", 33
    corpus — b10 follow-up e) joins the same read: its opponent-scoped
    ``valid_target`` fires, its Controller-scoped form (Archmage Emeritus)
    stays out on the same gate.

    :func:`is_opponent_cast_trigger_def` is this SAME predicate, applied at
    TWO tree positions (ADR-0037/0038 W1 batch-3): a top-level trigger
    unit's own node, and a NESTED trigger definition
    :func:`iter_nested_trigger_defs` reaches inside a GRANTED-ability
    construct the flat per-unit walk never surfaces as its own unit —
    Hunting Grounds's Threshold-gated static grant, Jace, Unraveler of
    Secrets's -8 emblem (``CreateEmblem.triggers``), Blink's Alien Angel
    token grant. Thundering Mightmare's soulbond-paired grant carries NO
    node at all (``modifications: []``, a no-residue class-2 gap) — a
    synthetic ``opponent_cast`` marker from
    ``tree_synthesis._arm_opponent_cast_matters`` fills that one (this key's
    underlying read is trigger-unit-based, not ``effect_concepts``-based,
    so the marker needs its own explicit check, unlike a lane that already
    reads via ``effect_concepts``). Scope "opponents".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and is_opponent_cast_trigger_def(unit.node):
            return [
                Signal("opponent_cast_matters", "opponents", "", "", tree.name, "high")
            ]
    for unit in tree.units:
        for trig in iter_nested_trigger_defs(unit.node):
            if is_opponent_cast_trigger_def(trig):
                return [
                    Signal(
                        "opponent_cast_matters", "opponents", "", "", tree.name, "high"
                    )
                ]
    for c in tree.effect_concepts("opponent_cast"):
        if isinstance(c.node, SynthesizedNode):
            return [
                Signal(
                    "opponent_cast_matters", "opponents", "", c.raw, tree.name, "high"
                )
            ]
    return []


# ADR-0038 W3 batch 2 unit 4 — a SANCTIONED byte-identical mirror of the
# deleted ``DAMAGE_TO_OPP_MATTERS_REGEX`` (``_sweep_detectors.py``): "when
# (ever) … deals (noncombat) damage to a player/opponent". Non-greedy across
# the WHOLE sentence, so it also matches a LATER "~ deals damage to that
# player" clause inside a combat-damage trigger's own effect (Sword of War
# and Peace) — a genuine textual signal (an ADDITIONAL damage effect the
# trigger causes), not a mis-fire. CR 119.3 / 510.1c.
_DAMAGE_TO_OPP_MATTERS_MIRROR = re.compile(
    r"\bwhen(?:ever)?\b[^.]*?\bdeals (?:noncombat )?damage to "
    r"(?:a player|an opponent|one of your opponents|each opponent"
    r"|target opponent|that player|a player or planeswalker)\b",
    re.IGNORECASE,
)


def _combat_damage_lanes(tree: ConceptTree) -> list[Signal]:
    """combat_damage_matters + damage_to_opp_matters — the damage-connect
    payoffs, split by the trigger's typed ``damage_kind`` (checklist #5 — the
    recipient node decides reach, the kind decides the lane):

    * ``combat_damage_matters`` — ``DamageDone`` with ``CombatOnly`` kind
      reaching a player/planeswalker (Coastal Piracy; CR 510.1b). A creature
      recipient (Serpentine Basilisk) is the to-creature lane, not this one.
    * ``damage_to_opp_matters`` — the ANY-damage connect ("deals damage to an
      opponent" — Hypnotic Specter; CR 120.3), same player-reach read.

    ADR-0038 W3 batch 2 unit 4: :func:`damage_to_player_trigger_kind` is one
    predicate over BOTH a top-level trigger unit's own node AND a nested
    granted-trigger def (:func:`iter_nested_trigger_defs` — the
    opponent_cast_matters/connive precedent), so a damage-connect payoff
    granted through a static (Snake Umbra's Aura, Talon of Pain's own
    static, Sword of War and Peace's Equipment, Stormbreath Dragon's
    monstrosity-granted static) fires exactly like the top-level form
    (Hypnotic Specter).

    ADR-0038 W3 batch 4 (combat-damage cluster): a third descent position —
    :func:`iter_delayed_trigger_condition_defs` — reaches a
    ``CreateDelayedTrigger`` watcher def (Subira, Tulzidi Caravanner's
    "Until end of turn, whenever a creature you control ... deals combat
    damage to a player, draw a card"; Fire Giant's Fury, Hunter's Insight's
    "whenever that creature deals combat damage to a player [or
    planeswalker] this turn" one-shot pumps), the SAME watcher shape 4 other
    already-promoted lanes already read.

    ADR-0038 W3 batch 2 unit 4: a SANCTIONED byte-identical mirror
    (:data:`_DAMAGE_TO_OPP_MATTERS_MIRROR`, ported unchanged from the
    deleted ``DAMAGE_TO_OPP_MATTERS_REGEX``) covers the tail phase can't
    structure as a ``deals_damage`` trigger at all: an ETB/attack/other-
    event trigger whose OWN effect ALSO deals damage to a player within the
    SAME sentence (Sword of War and Peace's combat-damage trigger causes a
    SEPARATE "~ deals damage to that player" effect the regex's non-greedy
    span reaches past the non-matching "combat damage" clause; Talon of
    Pain's Unknown-mode trigger phase never types as ``deals_damage``), and
    a direct ETB/ability damage BURST with no reactive trigger shape at all
    (Fanatic of Mogis, Gruesome Scourger, Meria's Outrider). Fallback-only
    (checked when the structural arm found nothing) — never overrides a
    structural miss into a wrong key.

    Both hard-scope "opponents" (live). Co-fires with the ported
    ``combat_damage_to_opp`` where live does — distinct keys, the diff slices
    per key.

    ADR-0038 W3 batch 6: ``combat_damage_matters`` gains the SAME bare-
    quoted-grant fallback ``combat_damage_to_opp`` needed (Sokrates,
    Predators' Hour, the Unfinity Sticker Sheet TK-templates, Kassandra's
    Equipment-gated granted quote, Spawning Kraken's tribal Unknown-mode
    top-level trigger whose own ``description`` names the connect but whose
    ``Unimplemented`` execute chain defeats the typed kind read) —
    :func:`combat_damage_recipients_from_text` over the FACE's own oracle,
    fallback-only, fired only when NO structural arm reached
    ``combat_damage_matters`` on this tree (never overrides a genuine
    structural miss — e.g. a creature-only or damage_to_opp_matters-only
    read stays that way).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def emit(kind: str | None) -> None:
        if kind is None:
            return
        key = (
            "combat_damage_matters" if kind == "CombatOnly" else "damage_to_opp_matters"
        )
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "opponents", "", "", tree.name, "high"))

    for unit in tree.units:
        if unit.origin == "trigger":
            emit(damage_to_player_trigger_kind(unit.node))
        for trig in iter_nested_trigger_defs(unit.node):
            kind = damage_to_player_trigger_kind(trig)
            if kind is None and _unknown_mode_combat_damage_to_player(trig):
                kind = "CombatOnly"
            emit(kind)
        for trig in iter_delayed_trigger_condition_defs(unit.node):
            kind = damage_to_player_trigger_kind(trig)
            if kind is None and _unknown_mode_combat_damage_to_player(trig):
                kind = "CombatOnly"
            emit(kind)
    if "damage_to_opp_matters" not in seen and _DAMAGE_TO_OPP_MATTERS_MIRROR.search(
        _kept(tree)
    ):
        out.append(
            Signal("damage_to_opp_matters", "opponents", "", "", tree.name, "high")
        )
    if "combat_damage_matters" not in seen and "player" in (
        combat_damage_recipients_from_text(tree.oracle)
    ):
        out.append(
            Signal("combat_damage_matters", "opponents", "", "", tree.name, "high")
        )
    return out


# ADR-0038 W3 batch 3 — a real phase-parser gap the other three typed arms can't
# reach: a ``ModifyCost`` static ability's ordinal-count qualifier carries NO
# structured field at all (Highspire Bell-Ringer, Uthros Psionicist, Monk Class,
# Alisaie Leveilleur, Raging Battle Mouse — "The second spell you cast each turn
# costs {N} less to cast" projects to a bare cost-reduction static with
# ``condition=None``), and an ETB trigger's ordinal condition is dropped entirely
# too (Codespell Cleric — "if it was the second spell you cast this turn" leaves
# the trigger's own ``condition``/``execute.condition`` both ``None``). The
# qualifier survives ONLY in that ONE node's own generated ``description`` — never
# the whole-card oracle — so this scan can never cross-contaminate with an
# UNRELATED ability's "cast two or more spells LAST turn" elsewhere on the same
# card (the Innistrad werewolf day/night transform condition — Afflicted
# Deserter, Call of the Full Moon — and the opponent-scoped "if an opponent cast
# two or more spells this turn" cost-discount, Ertai's Scorn, CR 712 excluded by
# :func:`spell_velocity_static_two`'s own Controller-scope gate): both use
# DIFFERENT wording ("cast two or more spells" bare, third-person "casts their",
# or "last turn") that this narrower "<ordinal> spell YOU CAST (each|this) turn"
# phrasing never matches. CR 601.
#
# ADR-0038 W3 batch 4 — a THIRD phrasing this same per-node text bridge also
# covers: a kind-agnostic, ANY-PLAYER ordinal count of the turn's spells
# ("Whenever the fourth spell of a turn is cast" — Erayo, Soratami Ascendant)
# projects to a bare ``cast_spell`` trigger with no count qualifier at all —
# identical in shape to a plain magecraft trigger, so no structural arm can
# discriminate it (test_signals_effect_axes.py::test_spell_count_storm_widen
# pins the legacy IR's OWN byte-mirror firing this exact same way, CR 601).
# "of (a|each|that) turn IS CAST" (passive, no "you") is distinct enough from
# the werewolf day/night transform condition ("cast two or more spells LAST
# turn", CR 712) and Ertai's Scorn's opponent-scoped discount ("if an
# opponent cast two or more spells THIS turn") that neither can cross-match —
# both lack an ordinal word entirely.
_SECOND_SPELL_NODE_TEXT = re.compile(
    r"(?:second|third|fourth|fifth) spell you cast (?:each|this) turn"
    r"|was the (?:second|third|fourth|fifth) spell you cast this turn"
    r"|(?:second|third|fourth|fifth) spell of (?:a|each|that) turn is cast",
    re.IGNORECASE,
)


def _second_spell_node_text(unit: AbilityUnit) -> bool:
    """Whether THIS unit's own node ``description`` names the second-spell
    ordinal qualifier (:data:`_SECOND_SPELL_NODE_TEXT`), gated to a
    ``ModifyCost`` mode for a static-origin unit (never an unrelated static)."""
    if unit.origin == "static" and static_mode_tag(unit.node) != "ModifyCost":
        return False
    desc = getattr(unit.node, "description", "") or ""
    return bool(_SECOND_SPELL_NODE_TEXT.search(desc))


def _second_spell_matters(tree: ConceptTree) -> list[Signal]:
    """second_spell_matters — the spell-velocity payoff (CR 603.2), the
    reclassified-UP probe win: the "second spell each turn" qualifier the OLD
    projection dropped (forcing live onto a byte mirror) is a first-class
    ``constraint {NthSpellThisTurn, n}`` on the SpellCast trigger in v0.9.0
    (Cori-Steel Cutter, n=2). Four arms: the trigger constraint with n ≥ 2;
    the activation-restriction CONDITION form ``YouCastSpellCountAtLeast
    count ≥ 2`` ("Activate only if you've cast two or more spells this turn" —
    Xerex Strobe-Knight); the static/replacement-CONDITION form — a
    ``QuantityComparison``/``OnlyIfQuantity`` over ``SpellsCastThisTurn`` gating a
    payoff on "two or more spells this turn" (Brightspear Zealot, b3 recall;
    Effortless Master's ETB counters, ADR-0038 W3 batch 3 — both share the
    identical comparator/lhs/rhs shape, :func:`spell_velocity_static_two`); and the
    per-node text bridge (:func:`_second_spell_node_text`) for the two real
    phase-parser gaps a ``ModifyCost`` static's dropped qualifier and an ETB
    trigger's dropped ordinal condition leave with no typed field to read. A bare
    SpellCast trigger (Talrand), the n=1 first-spell form (Alela, Cunning
    Conqueror), and a "three or more spells" static (Arclight Phoenix — a
    broader velocity lane) never fire. Scope "you".
    """
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        if (
            trigger_constraint_tag(unit.node) == "NthSpellThisTurn"
            and (trigger_constraint_n(unit.node) or 0) >= 2
        ):
            return [Signal("second_spell_matters", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if spell_count_at_least(unit.node) >= 2 or spell_velocity_static_two(unit.node):
            return [Signal("second_spell_matters", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        if _second_spell_node_text(unit):
            return [Signal("second_spell_matters", "you", "", "", tree.name, "high")]
    return []


def _xspell_matters(tree: ConceptTree) -> list[Signal]:
    """xspell_matters — the {X}-spell payoff/enabler pair (CR 107.3 + 601.2b;
    checklist #4 — this IS the payoff lane, membership stays live): a
    ``SpellCast`` trigger whose watched-spell filter carries the
    ``HasXInManaCost`` predicate (Zaxara — the same predicate live reads), or
    a ``Mana`` effect restricted ``XCostOnly`` (Rosheen Meanderer's "Spend
    this mana only on costs that contain {X}"). A spell that merely HAS {X}
    in its own cost (Hydroid Krasis — a SelfRef cast watcher, no predicate)
    never fires. Scope "you".
    """
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event == "cast_spell":
            vc = getattr(unit.node, "valid_card", None)
            if "HasXInManaCost" in filter_predicates(vc):
                return [Signal("xspell_matters", "you", "", "", tree.name, "high")]
        for c in unit.effect_concepts("ramp"):
            if "XCostOnly" in mana_restrictions(c.node):
                return [Signal("xspell_matters", "you", "", c.raw, tree.name, "high")]
    return []


def _counter_control(tree: ConceptTree) -> list[Signal]:
    """counter_control — the stack counterspell (CR 701.6a): a ``Counter`` /
    ``CounterAll`` effect (Counterspell — ``target {StackSpell}``).
    Structurally DISJOINT from the other meaning of "counter"
    (``PutCounter``/``RemoveCounter`` — distinct tags) and from the "can't be
    countered" permission STATICS (Vexing Shusher — a ``CantBeCountered``
    mode, no Counter effect). Scope "you" (live).
    """
    hits = tree.effect_concepts("counter_spell")
    if hits:
        return [Signal("counter_control", "you", "", hits[0].raw, tree.name, "high")]
    return []


def _bounce_tempo(tree: ConceptTree) -> list[Signal]:
    """bounce_tempo — battlefield→hand bounce as tempo (CR 402.1: Boomerang,
    Unsummon). Two live gates (checklist #2 — the bounced subject's controller
    is the direction): a graveyard-zone subject (``InZone: Graveyard`` — a
    GY→hand recall, the creature_recursion arm) and a your-own-permanent
    subject (Aviary Mechanic — self-bounce value, controller You) never fire.
    Phase ALSO emits a ZONE-LESS ``Bounce`` for graveyard-to-hand returns
    ([P21] — the InZone marker is dropped), so the [P8]-precedent node-local
    description screen restores the recursion/tempo boundary (CR 402.1 vs
    404.1), scoped two ways against the multi-sentence description blob:
    a SelfRef subject with a "from ... graveyard" description is a
    self-return (Abzan Devotee) — WITHOUT it, battlefield self-bounce
    (Blinking Spirit) keeps firing, matching live; a targeted bounce with
    that description is vetoed only when it is the unit's ONLY bounce
    (Aphetto Dredging, Greasefang's reanimate-loop return) — a unit that
    also carries a genuine tempo bounce (Aether Helix's two-sentence pair)
    still fires, matching live. A mass bounce co-fires with the ported
    ``mass_bounce`` (live keeps both). Tier-1 (ADR-0036/0037 T10-finalize2
    GLOBAL FINALIZE-2 fold): the deleted lane-time GY-return veto (node-own
    description, whole-card fallback) is relocated verbatim to the bucket-B
    ``synth_bounce_tempo`` node (:func:`_arm_bounce_tempo`), read below.
    Scope "you".
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_bounce_tempo":
            return [Signal("bounce_tempo", "you", "", "", tree.name, "high")]
    return []


def _power_double(tree: ConceptTree) -> list[Signal]:
    """power_double — the P/T-doubling payoff (CR 613.4c + Unleash Fury's
    ruling): a ``DoublePT`` / ``DoublePTAll`` effect whose ``mode`` doubles
    POWER (``Power`` / ``PowerAndToughness``). The typed tag is the fix for
    the Scryfall ``Double`` keyword's over-fire onto damage/token/counter
    doublers (checklist #3 — distinct tags, split lanes); a flat pump (Giant
    Growth — a ``Pump`` node) and a toughness-only doubler never fire. Scope
    "you".
    """
    for c in tree.effect_concepts("double_pt"):
        if getattr(c.node, "mode", None) in _POWER_DOUBLE_MODES:
            return [Signal("power_double", "you", "", c.raw, tree.name, "high")]
    return []


def _keyword_grant_lanes(tree: ConceptTree) -> list[Signal]:
    """The AddKeyword mod-site cluster (CR 613.1f layer 6) — one shared walk,
    per-ability aggregation (granularity b), direction gates per checklist #6
    (the AFFECTED filter's controller, read off the mod-site's own node):

    * ``keyword_grant_target`` — the single-target grant: an ``AddKeyword``
      whose affected is ``ParentTarget`` under a ``GenericEffect`` whose
      resolved target carries the Creature CORE type — live's two v14
      markers mirrored exactly: the DEEP local-target leaf on ANY unit
      (trigger / modal / Saga / quoted — Aethershield Artificer) via
      :func:`iter_deep_target_grants`, plus the flat threaded walk on
      abilities for the "It gains X" idiom via
      :func:`iter_single_target_grants` (Snakeskin Veil, Jump). A PERMANENT
      target (Aegis Angel) and a subtype-only target (a tribal grant) stay
      out on the creature-core gate, exactly as live. Scope "you".
    * ``protection_grant`` — a PROTECTIVE keyword (hexproof / shroud /
      indestructible / ward / protection, incl. the parameterized
      ``{Protection: …}`` variant whose KEY is the name — Gods Willing) to a
      single target (same v14 shape), your generic creature team, your
      permanents, or the suit-up equipped/enchanted recipient
      (CR 702.11/12/16/18/21).
    * ``all_creatures_kw_grant`` — the SYMMETRIC "all creatures [have/gain]
      X" (Concordant Crossroads; the one-shot Dirge of Dread): generic
      Creature filter, controller NULL / TargetPlayer (never You/Opponent),
      no subtypes/predicates. ANY granted keyword fires (the live arm is
      keyword-ungated). Scope "any" (it buffs opponents too, checklist #5).
    * ``team_evasion_grant`` — the evasion subset on your generic creature
      team (Levitation). Co-fires with the ported ``team_buff`` (a documented
      subset). A subtype/chosen-type-scoped grant (Cover of Darkness) fails
      the generic-team gate — the live mirror tail, SUPPLEMENT, logged.
    * ``aura_equip_kw_grant`` — an evergreen keyword to YOUR Aura/Equipment
      subgroup (Rashel, Fist of Torm). A name-scoped controller-null cycle
      (Shield of Kaldra) and the equipped-CREATURE recipient (Cori-Steel
      Cutter's haste — no Aura/Equipment subtype on the affected filter)
      never fire.

    A SelfRef affected (a card granting ITSELF a keyword) is vetoed
    throughout (the batch-9 self-grant lesson).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for unit in tree.units:
        grants = list(iter_deep_target_grants(unit.node))
        if unit.origin in ("ability", "trigger"):
            # ADR-0038 W3 batch 4: the threaded-target walk ALSO covers a
            # TRIGGER's own "gain control of target creature ... Untap that
            # creature. It gains haste" idiom (Conquering Manticore, every
            # Equipment's "attach it to target creature. That creature gains
            # X" ETB idiom, Hidden Footblade/Squire's Lightblade) — the SAME
            # tracked-target thread as the ability form (Snakeskin Veil,
            # Jump), just riding a GainControl/Attach producer effect first
            # instead of a plain instant. iter_threaded_target_statics
            # already resolves it (a GenericEffect's OWN target is
            # ParentTarget, threaded back to the GainControl/Attach's Typed
            # target) — this was a caller-side origin gate, not a missing
            # accessor. CR 613.1f (layer 6, ability-adding effects).
            grants.extend(iter_single_target_grants(unit.node))
        for resolved, mod in grants:
            if "Creature" not in filter_core_types(resolved):
                continue  # the live creature-core gate (no tribal/permanent)
            fire("keyword_grant_target", "you", "")
            if _norm_kw(mod_keyword_name(mod) or "") in _PROTECTIVE_GRANT_KW:
                fire("protection_grant", "you", "")
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) != "AddKeyword":
                continue
            kw = _norm_kw(mod_keyword_name(mod) or "")
            affected = getattr(sdef, "affected", None)
            atag = tag_of(affected)
            if atag in ("SelfRef", "ParentTarget"):
                continue  # self-grant / the single-target arm above
            raw = _site_raw(sdef)
            cores = set(filter_core_types(affected))
            ctrl = filter_controller(affected)
            subs = {s.lower() for s in filter_subtypes(affected)}
            preds = filter_predicates(affected)
            generic = not subs and not preds
            team = "Creature" in cores and ctrl == "You" and generic
            if team and kw in _TEAM_EVASION_KW:
                fire("team_evasion_grant", "you", raw)
            if "Creature" in cores and ctrl not in ("You", "Opponent") and generic:
                fire("all_creatures_kw_grant", "any", raw)
            if ctrl == "You" and subs & {"aura", "equipment"} and kw in _AURA_EQUIP_KW:
                fire("aura_equip_kw_grant", "you", raw)
            your_perms = "Permanent" in cores and ctrl == "You" and generic
            suit_up = set(preds) & _SUIT_UP_PREDS and cores & {"Creature", "Permanent"}
            if kw in _PROTECTIVE_GRANT_KW and (team or your_perms or suit_up):
                fire("protection_grant", "you", raw)
    if _TEAM_EVASION_GRANT_RX.search(_kept(tree)):
        fire("team_evasion_grant", "you", "")
    # ADR-0038 W3 batch 4 — the split/aftermath BACK-HALF grant residue: phase
    # emits no record for a split/aftermath back face at all (Onward //
    # Victory's "Victory" — "Target creature gains double strike until end
    # of turn" — Claim // Fame's "Fame"), so this card's ONLY tree for that
    # face is the ADR-0038 W2c text-only tree (originally ``units=()`` — no
    # node to structurally walk — every arm above sees nothing; NOTE:
    # ``extract_crosswalk_signals`` runs ``apply_tree_synthesis`` on every
    # tree BEFORE any lane sees it, which appends a synthetic bucket-B unit
    # even to a text-only tree, so gating on ``not tree.units`` is WRONG by
    # the time this lane runs — gate on "not fired yet" via ``seen`` instead,
    # keyed to THIS key specifically (a sibling grant like team_evasion_grant
    # firing first must never suppress it)). Read it off the tree's own
    # ``oracle`` (verbatim bulk face text) via the deleted SWEEP detector's
    # exact regex, the legacy's own residue path for this identical gap
    # (``_KGT_SPLIT_RESIDUE_RE`` in the deleted ``_signals_ir``). CR 613.1f (layer 6,
    # ability-adding effects).
    if "keyword_grant_target" not in seen and _KEYWORD_GRANT_TARGET_KEPT_RX.search(
        _kept(tree)
    ):
        fire("keyword_grant_target", "you", "")
    # task #np_roles — the ``synth_protection_grant_suit_up`` bucket-B
    # marker (see :func:`~mtg_utils._card_ir.tree_synthesis.
    # _arm_known_token_ward_grant`): the Royal Role known-token tree's
    # "Enchanted creature gets +1/+1 and has ward {1}" (CR 111.10m /
    # 702.21a) is the suit-up protective grant this lane's structural
    # branch fires ``protection_grant`` for on a real Aura (Shield of the
    # Oversoul), but a zero-unit text-only tree has no AddKeyword mod site
    # to walk — read the marker instead (the split/aftermath residue-read
    # precedent directly above; same "not fired yet" gate).
    if "protection_grant" not in seen:
        for c in tree.iter_concepts():
            if c.concept == "synth_protection_grant_suit_up":
                fire("protection_grant", "you", "")
    return out


def _iter_base_pt_modal_threaded_statics(
    root: object,
) -> Iterator[tuple[object, object]]:
    """``(resolved_target, static_def)`` pairs for a base-P/T-set static
    nested inside a MODAL mode's OWN sub-ability chain (Sauron, Dino
    Devotee's "Turn People into Dinosaurs" mode: ``PutCounter``'s own
    ``target`` — "another target creature", CR 700.2's per-mode target
    declaration — threads through that SAME mode's ``sub_ability`` chain to
    the nested ``GenericEffect``'s ``ParentTarget``-affected static, "It's a
    green Dinosaur with base power and toughness 5/5 for as long as it has
    a saurian counter"). :func:`iter_threaded_target_statics` doesn't reach
    this: it walks ``effect``/``sub_ability``/``execute`` but has no
    ``mode_abilities`` hop, so a doubly-nested ``ParentTarget`` (the mode's
    inner ``GenericEffect.target`` is ITSELF an unresolved ``ParentTarget``,
    referring to the mode's OWN top-level target one level further up, not
    a sibling of the ``GenericEffect``) never resolves via the main sites
    loop's single-level ``own_target`` read.

    Mirrors ``_iter_untap_targets``' established effect/sub_ability/
    execute/mode_abilities walk (:mod:`_card_ir.tree_synthesis`, the
    precedent for a per-key modal hop) rather than widening the SHARED
    ``iter_threaded_target_statics`` utility itself — no other lane needs
    the modal hop yet, and a shared-helper widening needs the full-corpus
    sibling check this session's time budget keeps scoped to base_pt_set's
    own call site.
    """
    tracked: object | None = None
    seen: set[int] = set()
    queue: list[object] = [root]
    while queue:
        node = queue.pop(0)
        if not isinstance(node, TypedMirrorNode) or id(node) in seen:
            continue
        seen.add(id(node))
        tgt = getattr(node, "target", None)
        if isinstance(tgt, TypedMirrorNode) and tag_of(tgt) in ("Typed", "Or", "And"):
            tracked = tgt
        if tag_of(node) == "GenericEffect" and tracked is not None:
            for st in getattr(node, "static_abilities", None) or []:
                if tag_of(getattr(st, "affected", None)) == "ParentTarget":
                    yield tracked, st
        for fname in ("execute", "effect", "sub_ability"):
            child = getattr(node, fname, None)
            if isinstance(child, TypedMirrorNode):
                queue.append(child)
        modes = getattr(node, "mode_abilities", None)
        if isinstance(modes, list):
            queue.extend(modes)


def _base_pt_set(tree: ConceptTree) -> list[Signal]:
    """base_pt_set — the fixed base-P/T-SET toolbox (CR 613.4b's "and/or" —
    613.4d for the switch form): a mod site carrying ``SetPower`` and/or
    ``SetToughness`` (Polymorphist's Jest's PAIR — the "becomes a 1/1"
    neutralize; Singing Tree/Withercrown's SINGLE "has base power 0"), or a
    ``SwitchPT`` effect (Merfolk Thaumaturgist). Per-site subject RESOLUTION
    (granularity b): a nested site whose affected is ``ParentTarget`` resolves
    through the
    owning ``GenericEffect``'s target.

    ADR-0038 W3 batch 4 (corpus re-measure): membership is TEXT-HOOK driven,
    not subject-core-type driven — legacy's arm is the SetPower+SetToughness
    pair OR'd with exactly two text hooks over the site's OWN description,
    with NO separate core-type/subtype exclusion at all: ``_BASE_PT_RAW_HOOK``
    (a literal "base power"/"base toughness" — Figure of Destiny's level-up
    cycle, Circle of the Moon Druid's Bear Form, Evolved Sleeper, ALSO the
    fixed-toolbox removal spells — Lignify, Ovinize) or
    ``_BASE_PT_ANIMATE_HOOK`` ("N/N ... in addition to its other types" —
    Riddleform, Tezzeret's Touch, Ensoul Artifact, Zoetic Glyph). A prior cut
    tried a core-type carve-out (Land/Artifact excluded unconditionally) —
    corpus-verified WRONG in BOTH directions: it dropped genuine ARTIFACT-
    target members that DO name a hook (Tezzeret's Touch/Ensoul Artifact/
    Zoetic Glyph's "creature with base power and toughness N/N in addition
    to its other types" enchant-artifact reducers), and (when applied
    unconditionally to a bare SelfRef with no text screen at all) added +169
    cw_only man-lands/Angel's Tomb self-animates ("This land/artifact
    becomes a 2/1 ... creature ... It's still a land/artifact" — names
    NEITHER hook). The land/artifact MASS-animators (Living Plane, Animate
    Land) are excluded ENTIRELY BY the hooks' absence in their own text ("are
    1/1 creatures" matches neither phrase) — no additional gate needed. An
    unresolvable ParentTarget with no other tag (Cyclone Sire's sibling-land
    target) has no positive subject evidence and never fires regardless of
    text.

    Two further node-scoped screens the hook alone can't discriminate: a
    DYNAMIC pair (``SetPowerDynamic``/``SetToughnessDynamic``) whose value
    Refs ANOTHER object's OWN Power/Toughness (Eldrazi Mimic/Shape Stealer's
    "become equal to that creature's power and toughness", Amplifire's
    "twice that card's power") is a COPY-STATS idiom, not the toolbox's
    SCALAR dynamic form (Trench Gorger's exiled-card count, Aettir and
    Priwen's life total) — :func:`refs_other_object_stats` excludes it even
    though the raw text still names "base power"/"base toughness" literally.
    A site gated "as long as ~ ISN'T on the battlefield" (Grist, the Hunger
    Tide's off-battlefield creature flavor, a Commander-eligibility marker)
    is excluded too — CR 613's layers apply to a permanent ON the
    battlefield, so an off-battlefield-only P/T set is never a genuine
    on-battlefield build-around.

    The SwitchPT arm keeps its own SelfRef veto (Aquamoeba's self-switch is
    a P/T trick, not the toolbox — ``switch_pt`` has no legacy counterpart
    at all, a pre-existing beyond-legacy CR-613.4d gain, unaffected by this
    fix). Additive pumps (Giant Growth — layer 7c) are distinct tags. The
    dynamic set-equal-to-a-SCALAR form is also read by :func:`_variable_pt`
    for the CDA (``characteristic_defining``) shape (Tarmogoyf); this lane
    only reads the non-CDA continuous-effect shape.

    ADR-0038 W3 batch 6: a fourth site shape — the ``Animate`` top-level
    EFFECT (Belligerent Yearling's "you may have ~'s base power become
    equal to that creature's power" trigger) carries its base ``power``/
    ``toughness`` as DIRECT fields, never decomposed into a SetPower/
    SetToughness modification pair at all, so the sites-loop above never
    sees it. :func:`_animate_refs_other_object_stats` mirrors
    ``refs_other_object_stats`` but requires BOTH stats to Ref another
    object before excluding (a power-ONLY set-equal-to-another-object's-
    power, like Belligerent Yearling, is corpus-verified a genuine legacy
    member — CR 613.4b's "and/or"). Corpus-verified 0 new cw_only. Still
    residual — the corpus re-measure surfaced further shapes this batch's
    time budget didn't reach (modal ``mode_abilities`` — Storvald, Sita
    Varma; nested ``CreateEmblem.statics``/``.triggers`` — Capitoline
    Triad, Tezzeret the Schemer; a quoted granted ability inside
    ``BecomeCopy`` — Gigantoplasm, Mindlink Mech; an ``Unimplemented``
    residue whose OWN text names the hook — Tanazir Quandrix, Unruly
    Krasis, Circle of the Moon Druid, Candlekeep Inspiration; the sticker-
    sheet TK-placeholder shape — Cool Fluffy Loxodon, Ambassador
    Blorpityblorpboop; an ``AddPower``/``AddToughness`` PAIR phase chose
    over a literal Set for a type-changing override — Goddric, Cloaked
    Reveler; a CDA-like mana-value scalar under a non-``static``
    ``TargetOnly`` — Captain Rex Nebula; REPLACEMENT-origin type-overrides
    — Displaced Dinosaurs, Shadow Puppeteers, Sauron Dino Devotee, Ultron)
    — see the ADR-0038 W3 batch 6 session notes for the per-card triage.

    ADR-0038 W5 tails: the sites-loop now does a DEEP ``iter_typed_nodes``
    scan for every ``GenericEffect``/``CreateEmblem`` reachable from a
    unit's node, not just the unit's own top-level effect chain — a
    ``GenericEffect`` can be nested arbitrarily deep: a MODAL mode's own
    effect (Storvald's "choose one or both — Target creature has base
    power and toughness 7/7 .../1/1..." — each mode's ``S_mode_abilities.
    effect`` carries its OWN ``target`` field, self-contained per mode), an
    emblem's granted TRIGGERED ability's effect (Tezzeret the Schemer's -7:
    ``CreateEmblem.triggers[i].execute.effect``), or a granted ACTIVATED
    ability's effect (Gigantoplasm's BecomeCopy-quoted "{X}: ~ has base
    power and toughness X/X" — ``BecomeCopy.additional_modifications``'
    ``GrantAbility.definition.effect``). Each found ``GenericEffect``
    resolves its OWN nested static's ``ParentTarget`` through THAT SAME
    ``GenericEffect``'s ``target`` field (self-contained — a modal mode /
    emblem ability / granted ability owns its target independently of the
    enclosing unit, distinct from :func:`iter_threaded_target_statics`'s
    cross-clause "It becomes ..." back-reference, which threads a target
    from an EARLIER sibling effect in the SAME ability chain). A
    ``CreateEmblem``'s own ``.statics`` (Capitoline Triad's "Creatures you
    control have base power and toughness 9/9" — a continuous ability
    living directly on the emblem, no target involved at all) is read the
    same way as a top-level unit static. The resolved-tag accept-list also
    admits ``TriggeringSource`` (Creepy Puppeteer's "you may have THAT
    creature's [the just-attacked-with creature's] base power and
    toughness become 4/3" — a definite, resolvable subject, CR 603.2's
    "that permanent" back-reference to the trigger event).

    :func:`refs_other_object_stats` is narrowed to a MATCHED-quantity
    check: a genuine full-identity "become a copy of that creature's power
    AND toughness" idiom (Eldrazi Mimic, Shape Stealer, Amplifire) sets
    ``SetPowerDynamic`` to a ``Ref(qty=Power)`` of the other object AND
    ``SetToughnessDynamic`` to a ``Ref(qty=Toughness)`` of the SAME kind —
    verified corpus-wide, all three name-checked cards carry this exact
    matched pair. A MISMATCHED reuse — BOTH stats set to the SAME single
    Ref (Sita Varma's "have the base power and toughness of each other
    creature you control become equal to Sita Varma's power": both
    ``SetPowerDynamic`` AND ``SetToughnessDynamic`` Ref ``qty=Power``, never
    ``Toughness``) — is a genuine SCALAR set (CR 613.4b), not a full-
    identity copy; the prior ANY-Ref-to-Power/Toughness check over-excluded
    it. Legacy's own regex-based ``_recover_dynamic_base_pt_set`` (arm 6,
    "base power [and toughness] ... become") confirms Sita Varma is a
    named example — a pure text-hook synthesis with no copy-stats
    discrimination at all, so the crosswalk's narrower matched-qty gate is
    the more precise structural read of the SAME membership rule.

    STILL not promoted — a genuinely diverse tail remains after this
    batch's recovery: two more mass "have X become Y" idioms park as a
    whole-clause ``Unimplemented`` residue phase's own grammar can't
    structure at all (Unruly Krasis, Tanazir Quandrix — needs a NEW
    ``clause_grammar.py`` static token, out of scope this session, same
    class as Circle of the Moon Druid's "is a Bear with base power and
    toughness 4/2" whole-ability residue); a ``BecomeCopy`` with no
    ``additional_modifications`` field AT ALL (Mindlink Mech's "it's 4/3"
    override — phase drops the P/T-override clause with no residue node
    anywhere, confirmed via direct tree dump — needs phase parser work);
    the sticker-sheet TK-placeholder shape (Cool Fluffy Loxodon, Ambassador
    Blorpityblorpboop); an ``AddPower``/``AddToughness`` pair (Goddric); a
    CDA-like mana-value scalar (Captain Rex Nebula); REPLACEMENT-origin
    type-overrides (Displaced Dinosaurs, Shadow Puppeteers, Sauron Dino
    Devotee, Ultron); Candlekeep Inspiration's exile/graveyard-count
    scalar. Landfall rule not met (live_only != the shed set) — key stays
    residual.
    Scope "any" (live).
    """

    def mod_tags(st: object) -> set[str]:
        stm = getattr(st, "modifications", None)
        if not isinstance(stm, list):
            return set()
        return {tag_of(m) or "" for m in stm}

    def site_text(st: object) -> str:
        desc = getattr(st, "description", None)
        return desc if isinstance(desc, str) else ""

    def _refs_qty(value: object, qty: str) -> bool:
        for node in iter_typed_nodes(value):
            if tag_of(node) == "Ref" and tag_of(getattr(node, "qty", None)) == qty:
                return True
        return False

    def refs_other_object_stats(st: object) -> bool:
        """Whether a ``SetPowerDynamic``/``SetToughnessDynamic`` PAIR is a
        full-identity "become a copy of that creature's power AND
        toughness" idiom (Eldrazi Mimic, Shape Stealer, Amplifire's "twice
        that card's power [and toughness]") — corpus-verified NOT a legacy
        base_pt_set member, distinct from a SCALAR dynamic value (a card
        count/life total/devotion — Trench Gorger, Aettir and Priwen; or a
        single scalar REUSED for both stats — Sita Varma's "base power and
        toughness ... become equal to Sita Varma's power", both fields Ref
        the SAME ``qty=Power``, never ``Toughness``), which IS the
        toolbox's dynamic form.

        ADR-0038 W5 tails: narrowed to a MATCHED-quantity check —
        ``SetPowerDynamic`` Refs the OTHER object's OWN ``Power`` AND
        ``SetToughnessDynamic`` Refs its OWN ``Toughness`` (the genuine
        full-identity copy). A mismatch (both stats Ref the SAME single
        quantity, as Sita Varma's does) is a scalar set, not excluded — the
        prior ANY-Ref-to-Power/Toughness check over-excluded it (corpus-
        verified via all three name-checked exclusion cases, which DO carry
        the matched pair, and Sita Varma, which does not).
        """
        stm = getattr(st, "modifications", None)
        if not isinstance(stm, list):
            return False
        p_refs_power = t_refs_toughness = False
        has_p = has_t = False
        for m in stm:
            tag = tag_of(m)
            if tag == "SetPowerDynamic":
                has_p = True
                p_refs_power = _refs_qty(getattr(m, "value", None), "Power")
            elif tag == "SetToughnessDynamic":
                has_t = True
                t_refs_toughness = _refs_qty(getattr(m, "value", None), "Toughness")
        return has_p and has_t and p_refs_power and t_refs_toughness

    def off_battlefield_gated(st: object) -> bool:
        """Whether a site's OWN ``condition`` is "as long as ~ ISN'T on the
        battlefield" (Grist, the Hunger Tide's off-battlefield creature
        flavor, a Commander-eligibility marker, not a genuine on-battlefield
        base-P/T build-around — CR 613's layers apply to a permanent ON the
        battlefield; pop-verified False against legacy)."""
        cond = getattr(st, "condition", None)
        if tag_of(cond) != "Not":
            return False
        inner = getattr(cond, "condition", None)
        return (
            tag_of(inner) == "SourceInZone"
            and getattr(inner, "zone", None) == "Battlefield"
        )

    sites: list[tuple[object, set[str], str, bool, bool]] = []
    for unit in tree.units:
        if unit.origin == "static":
            # raw modification tags (not the set_pt concept slice) so the
            # dynamic pair on a top-level static (Aettir and Priwen)
            # surfaces alongside SetPower/SetToughness.
            sites.append(
                (
                    getattr(unit.node, "affected", None),
                    mod_tags(unit.node),
                    site_text(unit.node),
                    refs_other_object_stats(unit.node),
                    off_battlefield_gated(unit.node),
                )
            )
        # DEEP GenericEffect/CreateEmblem descent (ADR-0038 W5 tails): a
        # GenericEffect can nest arbitrarily deep — a modal mode's own
        # effect (Storvald), an emblem's granted TRIGGERED ability's effect
        # (Tezzeret the Schemer's -7, ``CreateEmblem.triggers[i].execute.
        # effect``), a granted ACTIVATED ability's effect (Gigantoplasm's
        # BecomeCopy-quoted "{X}: ~ has base power and toughness X/X",
        # ``BecomeCopy.additional_modifications``' ``GrantAbility.
        # definition.effect``) — never just the unit's own top-level effect
        # chain (Polymorphist's Jest — the affected IS the population, a
        # direct filter, not ParentTarget). Each found GenericEffect
        # resolves its OWN nested static's ParentTarget through THAT SAME
        # GenericEffect's ``target`` (self-contained — distinct from the
        # cross-sibling THREADED walk below, which resolves an EARLIER
        # effect's target for a same-ability "It becomes ..." back-
        # reference — Ovinize's local target, Cyclone Sire's sibling land
        # target; a GenericEffect with no target of its own here correctly
        # yields no site, leaving those cases to the threaded walk).
        #
        # ADR-0039 W7 endgame: a nested static's OWN ``description`` is
        # sometimes empty (Displaced Dinosaurs' REPLACEMENT-origin static —
        # the hook text "becomes a 7/7 Dinosaur creature in addition to its
        # other types" lives only on the ENCLOSING unit's top-level
        # description, CR 614.12/701.21a; the nested static def itself
        # carries the typed SetPower/SetToughness pair with no text of its
        # own). ``site_text(st) or site_text(unit.node)`` falls back to the
        # unit's own description ONLY when the site's own text is empty —
        # never overrides a site that already carries its own text, so a
        # multi-static unit with one hook-naming site and one unrelated site
        # can't cross-clause-bleed the hook onto the unrelated site.
        for ge in iter_typed_nodes(unit.node):
            if tag_of(ge) != "GenericEffect":
                continue
            own_target = getattr(ge, "target", None)
            nested = getattr(ge, "static_abilities", None)
            for st in nested if isinstance(nested, list) else []:
                affected = getattr(st, "affected", None)
                resolved = (
                    own_target if tag_of(affected) == "ParentTarget" else affected
                )
                sites.append(
                    (
                        resolved,
                        mod_tags(st),
                        site_text(st) or site_text(unit.node),
                        refs_other_object_stats(st),
                        off_battlefield_gated(st),
                    )
                )
        # ADR-0039 W7 endgame: a MODAL mode's own sub-ability chain (Sauron,
        # Dino Devotee — see :func:`_iter_base_pt_modal_threaded_statics`),
        # where the GenericEffect descent above finds the SAME nested
        # static but can't resolve its DOUBLY-nested ParentTarget (the
        # mode's own inner target is itself unresolved) — this walker
        # threads the mode's OWN declared target down instead.
        for resolved, st in _iter_base_pt_modal_threaded_statics(unit.node):
            sites.append(
                (
                    resolved,
                    mod_tags(st),
                    site_text(st) or site_text(unit.node),
                    refs_other_object_stats(st),
                    off_battlefield_gated(st),
                )
            )
        # ``CreateEmblem``'s own ``.statics`` (Capitoline Triad's "Creatures
        # you control have base power and toughness 9/9") — a continuous
        # ability living directly on the emblem, no target/ParentTarget
        # involved at all; read the same as a top-level unit static.
        for ce in iter_typed_nodes(unit.node):
            if tag_of(ce) != "CreateEmblem":
                continue
            for st in getattr(ce, "statics", None) or []:
                sites.append(
                    (
                        getattr(st, "affected", None),
                        mod_tags(st),
                        site_text(st),
                        refs_other_object_stats(st),
                        off_battlefield_gated(st),
                    )
                )
        for resolved, st in iter_threaded_target_statics(unit.node):
            sites.append(
                (
                    resolved,
                    mod_tags(st),
                    site_text(st),
                    refs_other_object_stats(st),
                    off_battlefield_gated(st),
                )
            )
    for resolved, mods, text, other_stats, off_bf in sites:
        # Fixed pair (Polymorphist's Jest) OR the DYNAMIC base-P/T-set pair
        # (b10 follow-up f): ``SetPowerDynamic`` + ``SetToughnessDynamic``
        # ("base power and toughness X/X" — Biomass Mutation; "…each equal
        # to your life total" — Aettir and Priwen). Distinct from the
        # ``SetDynamicPower`` CDA tags (:func:`_variable_pt` — Tarmogoyf).
        # ADR-0038 W3 batch 4: a SINGLE fixed stat (``SetPower`` XOR
        # ``SetToughness`` alone — Singing Tree/Island of Wak-Wak's "has base
        # power 0", Withercrown's "has base power 0") ALSO fires — CR
        # 613.4b's "and/or" explicitly covers a power-only or toughness-only
        # set, and corpus-verified these ARE legacy members (a prior cut
        # required BOTH stats, dropping every power-only/toughness-only
        # setter).
        if off_bf:
            continue
        if not (
            mods & {"SetPower", "SetToughness"}
            or ({"SetPowerDynamic", "SetToughnessDynamic"} <= mods and not other_stats)
        ):
            continue
        rtag = tag_of(resolved)
        # ADR-0038 W5 tails: ``TriggeringSource`` (Creepy Puppeteer's "you
        # may have THAT creature's base power and toughness become 4/3" —
        # "that creature" back-references the OTHER attacker from the SAME
        # trigger event, CR 603.2) is a definite, resolvable subject, same
        # footing as a SelfRef/Typed target.
        # ADR-0039 W7 endgame: ``LastCreated`` (Ultron, Artificial
        # Malevolence's "create a token that's a copy of it. If the token
        # isn't a creature, IT becomes a 2/2 Robot Villain creature ..." —
        # "the token"/"it" back-references the object the SAME ability just
        # created via ``CopyTokenOf``, CR 701.7a's create action combined
        # with CR 608.2h's "the object as it exists" resolution rule) is
        # equally definite and resolvable — the same footing as
        # ``TriggeringSource``, just anchored to a create-token step instead
        # of a trigger event.
        if rtag not in (
            "SelfRef",
            "Typed",
            "Or",
            "And",
            "TriggeringSource",
            "LastCreated",
        ):
            continue  # an unresolvable ParentTarget ("It becomes a 0/0
            # Elemental" over a SIBLING land target — Cyclone Sire): no
            # positive subject evidence, never fire
        if _BASE_PT_RAW_HOOK.search(text) or _BASE_PT_ANIMATE_HOOK.search(text):
            return [Signal("base_pt_set", "any", "", "", tree.name, "high")]
        # neither hook fires — a land/artifact MASS/SELF-animator (Living
        # Plane, Animate Land, Angel's Tomb, man-lands) says neither phrase,
        # correctly excluded by TEXT alone (matching legacy exactly)
    for c in tree.effect_concepts("switch_pt"):
        tgt = getattr(c.node, "target", None)
        if tgt is None or tag_of(tgt) == "SelfRef":
            continue  # self-switch — a P/T trick on itself
        return [Signal("base_pt_set", "any", "", c.raw, tree.name, "high")]
    # ADR-0038 W3 batch 6: the ``Animate`` top-level EFFECT (a "becomes a
    # Type with base power and toughness N/N" idiom phase does NOT
    # decompose into a SetPower/SetToughness modification pair — the base
    # stats are direct ``power``/``toughness`` fields on the Animate node
    # itself). Distinct node shape, same CR 613.4b membership rule.
    for unit in tree.units:
        for c in unit.effects:
            if tag_of(c.node) != "Animate":
                continue
            anim = c.node
            power = getattr(anim, "power", None)
            toughness = getattr(anim, "toughness", None)
            if power is None and toughness is None:
                continue  # a type-only animate (no base-stat set at all)
            if _animate_refs_other_object_stats(anim):
                continue
            tgt = getattr(anim, "target", None)
            ttag = tag_of(tgt)
            if ttag not in (None, "None", "SelfRef", "Typed", "Or", "And"):
                continue
            text = getattr(unit.node, "description", "") or ""
            if _BASE_PT_RAW_HOOK.search(text) or _BASE_PT_ANIMATE_HOOK.search(text):
                return [Signal("base_pt_set", "any", "", "", tree.name, "high")]
    # ADR-0039 W7 endgame ledgered bridges — the final residual stragglers
    # (a dropped dynamic-scalar site, a BecomeCopy P/T override with zero
    # trace, a Stickers TK-cost parse failure; bridge_ledger.py rows,
    # docstring there for the full corpus accounting). Goddric's
    # mis-decomposed AddPower/AddToughness row retired at the v0.35.2 bump
    # (phase now emits the real base-P/T type-change).
    for bridge_id in (
        "base_pt_tk_sticker_parse_failure",
        "base_pt_each_equal_to_dropped",
        "base_pt_becomecopy_no_pt_override",
        # v0.45.0 pin bump — Sauron's previously-STRUCTURAL modal "It's a
        # green Dinosaur with base power and toughness 5/5" mode regressed
        # upstream to an Unimplemented residue; membership preserved via
        # the ledgered bridge until the upstream report lands.
        "base_pt_modal_its_clause_regressed",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("base_pt_set", "any", "", "", tree.name, "high")]
    # ADR-0039 task #82 grammar sprint: the three whole-clause "have ...
    # become" / conditional "is a(n) ... with base power and toughness
    # N/N" / mass "have base power and toughness X/X, where X is ..."
    # residues graduated off their bridge_ledger.py rows into
    # tree_synthesis.py arms (regex read ONCE at tree-build time — this
    # lane now reads pure structure via the synthesized concept node).
    for c in tree.effect_concepts("base_pt_set"):
        if isinstance(c.node, SynthesizedNode):
            return [Signal("base_pt_set", "any", "", "", tree.name, "high")]
    return []


def _animate_refs_other_object_stats(anim: object) -> bool:
    """Whether an ``Animate`` effect's ``power`` AND ``toughness`` are BOTH
    set via a value that Refs an external object's OWN Power/Toughness (an
    Eldrazi Mimic/Shape Stealer-style full-identity copy — excluded, same
    as :func:`_base_pt_set`'s modification-form ``refs_other_object_stats``
    check). A SINGLE-stat set that Refs another object (Belligerent
    Yearling's "this creature's base power become equal to THAT
    creature's power" — power only, toughness untouched) is NOT excluded;
    CR 613.4b's "and/or" covers a power-only or toughness-only set.
    """
    power = getattr(anim, "power", None)
    toughness = getattr(anim, "toughness", None)
    if power is None or toughness is None:
        return False

    def _refs(val_wrap: object) -> bool:
        val = getattr(val_wrap, "value", None)
        for node in iter_typed_nodes(val):
            if tag_of(node) == "Ref" and tag_of(getattr(node, "qty", None)) in (
                "Power",
                "Toughness",
            ):
                return True
        return False

    return _refs(power) and _refs(toughness)


def _variable_pt(tree: ConceptTree) -> list[Signal]:
    """variable_pt — the */* characteristic-defining P/T (CR 604.3 + 613.4a
    layer 7a): a static def with ``characteristic_defining == true`` carrying
    a ``SetDynamicPower`` / ``SetDynamicToughness`` modification (Tarmogoyf —
    value = a ``Ref``/``DistinctCardTypes`` count). A fixed-number set
    (Polymorphist's Jest — ``characteristic_defining`` false, plain
    ``SetPower``) is :func:`_base_pt_set`. The TOKEN-borne */* and triggered
    self-set tail phase can't structure — SUPPLEMENT, logged. Scope "any".
    """
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in ("SetDynamicPower", "SetDynamicToughness"):
                continue
            if getattr(sdef, "characteristic_defining", None) is True:
                raw = _site_raw(sdef)
                return [Signal("variable_pt", "any", "", raw, tree.name, "high")]
    return []


# trigger-doubling GRANT idiom (CR 603.2): "<abilities> trigger(s) an
# additional time" — Dungeon Delver's "Room abilities of dungeons you own
# trigger an additional time", The Masamune's "that ability triggers an
# additional time". Requires "trigger(s)" itself in the clause (not just "an
# additional time" alone) so a REPLACEMENT effect using the same "an
# additional time" phrase for an unrelated repeated ACTION — CR 701.55c's
# villainous-choice replacement / CR 701.38d's multi-vote replacement (The
# Valeyard: "they face that choice an additional time" / "you may vote an
# additional time", neither containing the word "trigger") — never matches.
_TRIGGER_DOUBLING_GRANT_RE = re.compile(
    r"\btriggers?\b.*\ban additional time\b", re.IGNORECASE | re.DOTALL
)


def _trigger_doubling(tree: ConceptTree) -> list[Signal]:
    """trigger_doubling — the trigger-doubling engine (grounded by
    Panharmonicon's 2021-03-19 ruling; ``rules-lookup --grep`` finds no
    dedicated CR term): a static whose mode variant is ``DoubleTriggers``
    (Panharmonicon, Yarok, Strionic-style ``Any`` causes). The REPLACEMENT
    doublers of tokens/counters (Doubling Season — ``quantity_modification``
    replacement nodes, NOT DoubleTriggers) are split lanes and never fire.
    The creature-ETB cause co-fires ``creature_etb`` via
    :func:`_etb_trigger_lanes` arm 2. Scope "you".

    Stage-A recovery (ADR-0038): a GRANTED doubler whose own quoted
    definition text carries the doubling clause (Dungeon Delver's Commander-
    creature grant, The Masamune's Equip grant) lands as a
    ``GrantStaticAbility`` / ``GrantTrigger`` node phase doesn't decompose
    further (no ``DoubleTriggers`` mode node exists to read) — a genuine
    STRUCTURAL gap, read directly off the grant node's own raw via
    :data:`_TRIGGER_DOUBLING_GRANT_RE` (CR 603.2).
    """
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) == "DoubleTriggers":
                return [Signal("trigger_doubling", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            if (
                c.concept == OTHER
                and tag_of(c.node) in ("GrantStaticAbility", "GrantTrigger")
                and c.raw
                and _TRIGGER_DOUBLING_GRANT_RE.search(c.raw)
            ):
                return [Signal("trigger_doubling", "you", "", c.raw, tree.name, "high")]
    return []


# W3 batch-3 (ADR-0038): the "didn't attack this turn" PUNISHER idiom (Erg
# Raiders, Kratos, Angel's Trumpet, Season of the Witch) — CR 508.1d's
# requirement family covers the compulsion-to-attack theme legacy folds this
# punisher into (forced_attack), but phase carries NO node for a punishment
# triggered off a creature's PAST inaction (only the `AttackedThisTurn`
# state-check property, never a dedicated effect/static tag) — a genuine
# bucket-B gap. Byte-identical to the ``_IR_KEPT_DETECTORS`` inline pattern
# in the deleted ``_signals_ir`` (no separate importable constant there to
# reuse single-source), so this is a local last-resort ``_kept(tree)`` idiom, not a new
# grammar arm. Scope "you" (self/team punishment, matching legacy).
_FORCED_ATTACK_PUNISH_RX = re.compile(r"didn't attack this turn", re.IGNORECASE)


def _forced_attack(tree: ConceptTree) -> list[Signal]:
    """forced_attack — the attack compulsion (CR 508.1d). Structural arms
    mirroring the live ``force_attack`` category's two phase sources: a
    static def whose mode is ``MustAttack`` (Warmonger Hellkite's table-wide
    force; Juggernaut's SelfRef drawback stays IN to match live — the
    supplement recovers self/team statics), and the one-shot ``ForceAttack``
    EFFECT ("target creature … attacks … if able" — Alluring Siren). Goad is
    a distinct tag (Disrupt Decorum → ``goad_makers``, ported b4) and never
    fires.

    The MustAttack static is EXCLUDED when (a) its ``affected`` subject is
    ``LastCreated`` — a granted compulsion on a JUST-CREATED token
    (Legion Warboss's Goblin, Howlsquad Heavy's Goblin), not the card's OWN
    engine (phase's tags are position-relative post-producer-effect; the b3
    landmine lesson: never fold a nested grant's compulsion into the card's
    own lane), or (b) it and a sibling ``MustBlock`` mode BOTH affect the
    card ITSELF (``affected`` absent or ``SelfRef``) — Iron Golem / Khârn
    the Betrayer / Relentless Raptor's OWN "attacks or blocks each combat if
    able" is a COMBINED CR 508.1d + CR 509.1c compulsion legacy's own
    structural project.py classifies ``restriction``, never
    ``force_attack``. A GRANTED combo delivered to a target via a trigger's
    ``AddStaticMode`` (Boros Battleshaper's "up to one target creature
    attacks or blocks … if able", ``affected`` = ``ParentTarget``) is NOT
    excluded — legacy fires ``force_attack`` for it (the structural
    restriction override is project.py's card-level static reader only; a
    granted mode falls to the SAME text-level ``_FORCE_ATTACK`` regex
    Boros's own raw satisfies).

    Bucket-B fallback (no structural node at all — a full-residue
    Unimplemented clause): the SAME "attacks … if able" clause grammar
    supplement.py's recovery already tokenizes (``_FORCE_ATTACK``, imported
    single-source) OR the "attack only the nearest opponent" directional
    restriction (CR 508.1c) project.py's own card-level marker recovers
    (``_FORCE_ATTACK_REF``, imported single-source) — read off
    ``_kept(tree)`` when no structural "any" signal already fired, the
    card carries no self-combo restriction, and no ForceBlock-shaped clause
    competes (:func:`_attack_compulsion_hit`, per-clause — Magnetic Web
    carries BOTH a real team compulsion and a separate ForceBlock trigger,
    so the ForceBlock exclusion can't be a whole-tree gate). Scope "any"
    (live — a symmetric/table force, not a you-only payoff).

    A SEPARATE, independently-firing punisher idiom
    (:data:`_FORCED_ATTACK_PUNISH_RX`) covers the "didn't attack this turn"
    penalty family, scope "you".
    """
    out: list[Signal] = []
    seen_any = False
    # Whole-TREE self-combo scan (Iron Golem/Khârn/Relentless Raptor split
    # their MustAttack and MustBlock modes across TWO SEPARATE static
    # abilities — two units, not one — so the combo check can't be scoped
    # per-unit; it must union every self-affecting mode across the card).
    all_self_modes: set[str | None] = set()
    for unit in tree.units:
        for s in iter_static_defs(unit.node):
            a = getattr(s, "affected", None)
            if a is None or tag_of(a) == "SelfRef":
                all_self_modes.add(static_mode_tag(s))
    self_combo = "MustAttack" in all_self_modes and "MustBlock" in all_self_modes
    for unit in tree.units:
        for sdef in iter_static_defs(unit.node):
            if static_mode_tag(sdef) != "MustAttack":
                continue
            affected = getattr(sdef, "affected", None)
            aff_tag = tag_of(affected) if affected is not None else None
            if aff_tag == "LastCreated":
                continue
            if aff_tag in (None, "SelfRef") and self_combo:
                continue
            out.append(Signal("forced_attack", "any", "", "", tree.name, "high"))
            seen_any = True
        for c in unit.effects:
            if tag_of(c.node) == "ForceAttack":
                out.append(Signal("forced_attack", "any", "", c.raw, tree.name, "high"))
                seen_any = True
    kept = _kept(tree)
    if (
        not seen_any
        and not self_combo
        and _attack_compulsion_hit(kept, _FORCE_ATTACK, _FORCE_ATTACK_REF)
    ):
        out.append(Signal("forced_attack", "any", "", "", tree.name, "high"))
    if _FORCED_ATTACK_PUNISH_RX.search(kept):
        out.append(Signal("forced_attack", "you", "", "", tree.name, "high"))
    return out


def _damage_prevention(tree: ConceptTree) -> list[Signal]:
    """damage_prevention — the CR 615 prevention shield: a ``PreventDamage``
    effect (Fog — ``{amount: All, scope: CombatDamage}``; Story Circle's
    activated next-time shield). Second arm (b10 follow-up c, adjudicated):
    a ``DamageDone`` REPLACEMENT carrying ``shield_kind {Prevention}`` (the
    Palisade Giant family, 146 corpus) — prevention-shield MEMBERSHIP only;
    the redirect SEMANTICS deliberately stay uncaptured (``damage_redirect``
    is a settled KEPT — Pariah parses indistinguishably from a pure shield).
    Protection grants are a DIFFERENT node (Gods Willing →
    :func:`_keyword_grant_lanes`); the Aura/ward reminder-text tail rides
    the live byte mirror — SUPPLEMENT, logged. Scope "you" (live).
    """
    hits = tree.effect_concepts("prevent_damage")
    if hits:
        return [Signal("damage_prevention", "you", "", hits[0].raw, tree.name, "high")]
    # Third arm (v0.45.0 pin bump): phase v0.38.0 re-modeled the static
    # "prevent N of that damage" shield (Urza's Armor, Orbs of Warding,
    # Guardian Seraph) from a mis-typed ``PreventDamage`` spell effect into
    # a proper CR 614/615 REPLACEMENT whose ``damage_modification`` field
    # carries a ``PreventionMinus`` node. Corpus census at the bump: 19
    # PreventionMinus replacements, 16 filtered ``Player: Controller`` + 3
    # unfiltered creature-shields, zero opponent-directed — the kind tag
    # alone is the unambiguous prevention tell (the sibling ``Minus``
    # damage-REDUCTION kind is deliberately not read; Benevolent Unicorn /
    # Lashknife Barrier were never members).
    for unit in tree.units:
        if unit.origin != "replacement":
            continue
        dm = getattr(unit.node, "damage_modification", None)
        if dm is not None and tag_of(dm) == "PreventionMinus":
            return [Signal("damage_prevention", "you", "", "", tree.name, "high")]
    # [P29] / Tier-1 (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2 fold): a
    # ``DamageDone`` REPLACEMENT with ``shield_kind {Prevention}`` (Palisade
    # Giant family) parses identically for an OFFENSIVE curse ("All damage
    # that would be dealt to enchanted creature is dealt to its controller
    # instead" — Treacherous Link) — a redirect-to-controller shield, not a
    # real prevention shield (Mirror Strike shields YOU). The deleted
    # lane-time veto (the node's own description) is relocated verbatim to
    # the bucket-B ``synth_damage_prevention`` node
    # (:func:`_arm_damage_prevention`), read below.
    for c in tree.iter_concepts():
        if c.concept == "synth_damage_prevention":
            return [Signal("damage_prevention", "you", "", "", tree.name, "high")]
    return []


def _damage_redirect(tree: ConceptTree) -> list[Signal]:
    """damage_redirect (ADR-0039 W8) — CR 614.9 / 615: a card that PROTECTS by
    preventing/redirecting damage dealt to itself, or REDIRECTS damage to a
    different recipient ("... is dealt to [X] instead").

    The typed ``S_replacements.redirect_target`` field exists on only 8
    corpus replacements and Pariah itself parses with NO ``redirect_target``
    (a pure ``shield_kind: Prevention`` — CR 615, structurally identical to a
    plain shield; see :func:`_damage_prevention`'s docstring) — the lane's own
    KEPT rationale (settled, re-verified this wave). BOTH legacy arms ride a
    byte-identical b12 mirror over ``_kept(tree)`` (the DISJOINT-arm shape:
    commander-legal corpus overlap == 0, since phase's structural categories
    ~90%-over-fire either way — damage_prevention 396 vs 44, redirect/
    damage_replace(ment) 224 vs 25):

    * ARM A — NAME-AWARE self-prevention/self-redirect
      (:func:`_detect_self_damage_prevention`, the self_blink name-aware
      precedent): Cho-Manno, Uncle Istvan, the Phantom +1/+1-counter shield
      cycle — an unkillable body that prevents/redirects damage dealt TO
      ITSELF (the ideal Equipment/Aura carrier), matching legacy's OWN
      lane-membership shape (Cho-Manno's actual text is pure prevention, no
      "instead" — legacy serves it here regardless, so this lane mirrors
      that verbatim rather than second-guessing legacy's naming).
    * ARM B — the REDIRECT clause (``_DAMAGE_REDIRECT_MIRROR``, single-source
      from ``text_reads``): en-Kor / Reflect Damage / Nova Pentacle /
      Captain's Maneuver's "... is dealt to [X] instead" idiom.

    Scope "you" (the deleted producers' forced scope). CR 614.9 / 615.
    """
    kept = _kept(tree)
    if _detect_self_damage_prevention(kept, tree.name):
        return [Signal("damage_redirect", "you", "", "", tree.name, "high")]
    if _DAMAGE_REDIRECT_MIRROR.search(kept):
        return [Signal("damage_redirect", "you", "", "", tree.name, "high")]
    return []


def _base_power_matters(tree: ConceptTree) -> list[Signal]:
    """base_power_matters (ADR-0039 W8) — CR 613.4b sentence 2: an effect that
    REFERS to a creature's BASE power/toughness ("creatures you control with
    base power N" — Rapid Augmenter's haste grant, Sword of the Squeak's
    equip scale, Zinnia's go-wide pump, Primo's combat trigger). Distinct
    from base_pt_set (sentence 1, a SETTER) — a reference rewards creatures
    by their base P/T, it sets nothing.

    The OLD lossy IR (``_recover_base_power_ref``) had to REGEX-recover this:
    phase's ``PtComparison`` predicate collapsed to a base-BLIND string, so a
    structural read would have massively over-fired onto the 323/330
    CURRENT-power references (power_matters territory) it couldn't tell
    apart. GRADUATION (the graduation rule — a substrate improvement stands
    a gap-gated arm down): phase v0.20.0's typed ``PtComparison`` node now
    carries a ``scope`` field (``'Base'`` vs ``'Current'``, re-verified this
    session against Rapid Augmenter/Zinnia/Primo — all ``'Base'`` — and
    Colossal Majesty/Ruby, Daring Tracker/Heir of the Wilds — all
    ``'Current'``) the OLD IR's string predicate threw away. Reads the typed
    field directly: any ``PtComparison`` node reachable anywhere in the tree
    with ``scope == 'Base'``. Scope "you" (the deleted producer's forced
    scope, matching the OLD IR's ``add("base_power_matters", "you", ...)``).

    ADR-0039 task #82 grammar sprint: the 2 remaining live members — a
    CONJUNCTIVE "base power and toughness N/N" reference (Duskana, Bess)
    phase's clause grammar drops with zero trace, no typed node at all,
    unlike the single-stat form this arm reads structurally above —
    graduated off the ``duskana_bess_base_pt_and_toughness_ref``
    ledgered-bridge row into a ``tree_synthesis.py`` arm
    (``_arm_base_power_ref_conjunctive``): the regex read moves to
    tree-build time, and this lane reads the synthesized concept node
    structurally. CR 613.4b.
    """
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "PtComparison" and getattr(n, "scope", None) == "Base":
                return [Signal("base_power_matters", "you", "", "", tree.name, "high")]
    for c in tree.effect_concepts("base_power_matters"):
        if isinstance(c.node, SynthesizedNode):
            return [Signal("base_power_matters", "you", "", "", tree.name, "high")]
    return []


def _copy_limit(tree: ConceptTree) -> list[Signal]:
    """copy_limit (ADR-0039 W8) — CR 100.2a: the deck-construction relaxation
    "A deck can have any number of cards named X" / "up to N cards named X"
    (Relentless Rats, Hare Apparent, Seven Dwarves, Shadowborn Apostle,
    Dragon's Approach, Persistent Petitioners, Nazgûl, Rat Colony, Slime
    Against Humanity, Tempest Hawk, Templar Knight, Cid). Read structurally
    off :attr:`ConceptTree.many_copies` (the typed ``deck_copy_limit`` field —
    ``Unlimited`` or ``UpTo`` with a bound >= 2; ``UpTo:1`` RESTRICTS to one
    copy and is excluded), the SAME field the old-IR ``ir.many_copies``
    (``card_ir._allows_many_copies``) reads off the raw record — a genuinely
    DIFFERENT deck concern than ``named_synergy`` (a swarm-of-one-name, not a
    named-partner reference). Scope "you" (the deleted producer's forced
    scope). CR 100.2a.
    """
    if tree.many_copies:
        return [Signal("copy_limit", "you", "", "", tree.name, "high")]
    return []


def _dep_or_and_reaches_player(tgt: object, depth: int = 0) -> bool:
    """A damage recipient that is an ``Or`` / ``And`` CONTAINING a player member
    ("target creature or player" — Brion Stoutarm, Hellhole Flailer, Sarkhan the
    Mad). ``_damage_equal_power``'s ``_DEP_PLAYER_TAGS`` / Typed-Player read only
    saw a top-level player node, missing the disjunctive recipient that
    ``creature_ping`` already recurses. CR 120.3."""
    if depth > 6 or tag_of(tgt) not in ("Or", "And"):
        return False
    for sub in getattr(tgt, "filters", ()) or ():
        st = tag_of(sub)
        if st in _DEP_PLAYER_TAGS:
            return True
        if st == "Typed" and "Player" in filter_core_types(sub):
            return True
        if _dep_or_and_reaches_player(sub, depth + 1):
            return True
    return False


def _damage_equal_power(tree: ConceptTree) -> list[Signal]:
    """damage_equal_power — the Fling shape (CR 120.3 recipient rules): a
    ``DealDamage`` whose amount is a ``Ref`` over a POWER qty
    (:func:`ref_qty_tag`) reaching a PLAYER recipient — the "any target"
    ``Any`` (Fling), a DIRECT player node, or (recall-completion b2) an
    ``Or`` / ``And`` recipient CONTAINING a player ("target creature or
    player"). A ``ParentTarget`` re-reference is NOT accepted: it names an
    earlier CREATURE target ("Tap target creature. ~ deals damage equal to
    its power to that creature" — Abyssal Hunter, the bite/creature_ping
    shape). A fixed amount (Prodigal Sorcerer) never fires. Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("deal_damage"):
            if tag_of(c.node) != "DealDamage":
                continue
            if ref_qty_tag(c.node, "amount") != "Power":
                continue
            tgt = getattr(c.node, "target", None)
            tt = tag_of(tgt)
            player = (
                tt in _DEP_PLAYER_TAGS
                or (tt == "Typed" and "Player" in filter_core_types(tgt))
                or _dep_or_and_reaches_player(tgt)
            )
            if player:
                return [
                    Signal("damage_equal_power", "you", "", c.raw, tree.name, "high")
                ]
    return []


# ── Batch 11 lanes (ADR-0035 Stage 2) ────────────────────────────────────────

# Replacement quantity-modification kinds that INCREASE the count (CR 614.1a).
# Live's counter_doubling category is event==addcounter + an increase mod — the
# measured live set fires BOTH counter_doubling and counter_replace_bonus on
# Times AND Plus (Hardened Scales carries counter_doubling live), so both arms
# read the same increase set; Minus (Vizier of Remedies) / Prevent never fire.
_INCREASE_QTY_MODS: frozenset[str] = frozenset({"Times", "Plus"})
# DamageDone replacement damage-modification kinds that AMPLIFY (CR 614.1a +
# 120.3): Double (Furnace of Rath), Triple (Fiery Emancipation), Plus (Torbran
# — live's damage_doubling category includes the +N amplifiers, measured).
# LifeFloor (Ali from Cairo) / Minus (Lashknife Barrier) are shields/reducers.
_DAMAGE_AMP_MODS: frozenset[str] = frozenset({"Double", "Triple", "Plus"})


def _replacement_doubler_lanes(tree: ConceptTree) -> list[Signal]:
    """The CR 614.1a replacement-doubler cluster — one shared walk over the
    typed replacement units, split by ``event`` (granularity a):

    * ``token_doubling`` — a ``CreateToken`` replacement with an INCREASE
      ``quantity_modification`` (Doubling Season ``Times 2``, Parallel Lives;
      Primal Vigor's symmetric no-owner-scope form INCLUDED — the beneficiary
      includes you). Give-away gate (checklist #2): an Opponent-only
      ``token_owner_scope`` is excluded (zero corpus members; defensive).
      Co-fires ``token_copy_makers`` + ``tokens_matter`` (live's ADR-0027 C5
      read: a token doubler forks copies and is a go-wide payoff).
    * ``counter_doubling`` + ``counter_replace_bonus`` — an ``AddCounter``
      replacement with an INCREASE mod whose ``valid_card`` controller is
      You/null (checklist #6). Live subsumption reproduced: both keys co-fire
      on Times AND Plus (measured — Hardened Scales carries both). A
      ``Minus`` reducer (Vizier of Remedies) and the CreateToken event never
      fire. Case law: Vorel ruling "essentially double the counters".
    * ``counter_doubling`` arm b/c (the probe win — live's "phase mangles
      Vorel" byte-mirror complaint is STALE): the one-shot ``Double`` effect
      with ``target_kind {Counters}`` (Vorel, 12 corpus — LifeTotal/ManaPool/
      None target_kinds gated out) and the triggered ``MultiplyCounter``
      (Kalonian Hydra — live counter_doubling fires, measured).
    * ``damage_doubling`` — a ``DamageDone`` replacement carrying an AMPLIFY
      ``damage_modification`` (Double/Triple/Plus). Direction gate
      (checklist #2/#5, read off the replacement's OWN
      ``damage_target_filter``): a YOUR-side-only doubler (doubles damage TO
      you — a drawback) is vetoed; Gisela's opponent-side filter is the
      include case. Shield replacements with NO damage_modification
      (Palisade Giant) never fire. Co-fires ``direct_damage`` when the
      doubler reaches players (live ADR-0027 C7): a filterless doubler
      (Furnace of Rath) or a player-inclusive filter fires it; the
      creature-only ``"CreatureOnly"`` filter (Blind Fury) does not
      (measured live parity).

    All scope "you" (live).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for unit in tree.units:
        if unit.origin != "replacement":
            continue
        node = unit.node
        ev = replacement_event_tag(node)
        raw = getattr(node, "description", None) or ""
        if ev == "CreateToken":
            qm = replacement_qty_mod(node)
            if (
                qm is not None
                and qm[0] in _INCREASE_QTY_MODS
                and replacement_token_owner_scope(node) != "Opponent"
            ):
                fire("token_doubling", raw)
                fire("token_copy_makers", raw)
                fire("tokens_matter", raw)
        elif ev == "AddCounter":
            qm = replacement_qty_mod(node)
            vc = getattr(node, "valid_card", None)
            if (
                qm is not None
                and qm[0] in _INCREASE_QTY_MODS
                and filter_controller(vc) in (None, "You")
            ):
                fire("counter_doubling", raw)
                fire("counter_replace_bonus", raw)
        elif ev == "DamageDone":
            mod = replacement_damage_mod(node)
            if mod in _DAMAGE_AMP_MODS:
                tscope = damage_filter_scope(node, "damage_target_filter")
                if tscope != "you":  # the your-side-only drawback veto
                    fire("damage_doubling", raw)
                    if tscope in (None, "opponents", "each", "any"):
                        fire("direct_damage", raw)
    for c in tree.effect_concepts("double_quantity"):
        if double_target_kind(c.node) == "Counters":
            fire("counter_doubling", c.raw)
    for c in tree.effect_concepts("multiply_counter"):
        mult = getattr(c.node, "multiplier", None)
        if isinstance(mult, int) and mult >= 2:
            fire("counter_doubling", c.raw)
    return out


def _is_tribe_damage_source(vs: object) -> bool:
    """Whether a damage trigger's ``valid_source`` is a YOUR-controlled
    creature POPULATION (CR 510.1b): a Typed/Or filter with controller You
    and either the Creature core type (Coastal Piracy) or ANY subtype
    (Seshiro's Snakes; the AnyOf outlaw unions recurse). ADR-0038 W3 batch
    2 unit 6: ANY subtype, not just a CREATURE_SUBTYPES vocab hit — only a
    CREATURE can deal combat damage (CR 510.1a), so a source filtered by a
    non-creature-core subtype (Vehicle — Edward Kenway's "a Vehicle you
    control deals combat damage") is STILL a creature at the moment combat
    damage is dealt (an animated/crewed Vehicle). A ``SelfRef`` source
    (Hypnotic Specter — a single doer) is not a population."""
    if tag_of(vs) not in ("Typed", "Or", "And"):
        return False
    if filter_controller(vs) != "You":
        return False
    if "Creature" in filter_core_types(vs):
        return True
    return bool(filter_subtypes(vs))


def _damage_trigger_lanes(tree: ConceptTree) -> list[Signal]:
    """The damage-trigger cluster (CR 603.2 + 120.3 / 510.1b/c) — one shared
    trigger walk, direction read off each trigger's OWN ``valid_target`` /
    ``valid_source`` nodes (checklist #5):

    * ``damage_reflect`` — a ``DamageReceived`` trigger whose SAME unit deals
      damage back (Boros Reckoner; co-occurrence, granularity a). Phytohydra
      parses as a replacement with a PutCounter execute — out twice over.
      Case law: "Damage dealt by Boros Reckoner due to its first ability
      isn't combat damage."
    * ``damage_to_you_punish`` — ``DamageDone`` with ``valid_target
      {Controller}`` AND an Opponent-controlled ``valid_source`` (Michiko
      Konda — the exact probed shape; live's "no structural shape" comment
      was STALE). The ported ``damage_to_opp_matters`` direction (target
      Opponent/Player) and the You-controlled source never fire. Scope
      "opponents" (live's mirror scope).
    * ``combat_damage_to_creature`` — ``DamageDone`` + ``CombatOnly`` kind +
      a Creature-cored recipient (Serpentine Basilisk; CR 510.1c). A Player
      recipient (Seshiro) is the ported player-connect lanes. Scope "any".
    * ``tribe_damage_trigger`` — a player-reaching recipient AND a
      your-creature-population source (Seshiro / Coastal Piracy; both
      CombatOnly and Any damage kinds, live reads both; the batched
      ``DamageDoneOnceByController`` mode — Anowon — joins via the shared
      ``deals_damage`` event). Scope "you", bare key (live).

    Stage-A recovery (ADR-0038): a DamageReceived-shaped trigger def not
    surfaced as its own top-level ``trigger`` unit — nested inside a spell's
    ``CreateDelayedTrigger`` (Arcbond's targeted "whenever THAT creature is
    dealt damage" reflector) or a static's ``GrantTrigger`` modification
    (Spiteful Sliver's tribal grant) — or a top-level trigger whose compound
    subject ("~ or a creature it's paired with" — Donna Noble) defeats
    phase's own mode derivation (an ``Unknown``-mode wrapper). Read via
    :func:`is_damage_reflect_trigger_def` over EVERY unit's deep node walk,
    gated on the flat arm above not already firing (CR 120.3).

    ADR-0038 W3 batch 2 unit 6: ``tribe_damage_trigger`` ALSO reads
    :func:`damage_to_player_trigger_kind`'s validated (event + recipient)
    gate + :func:`_is_tribe_damage_source` over a nested trigger def, two
    tree positions the flat top-level walk never reaches: a Background's
    ``GrantTrigger`` (Feywild Visitor's "Commander creatures you own have
    '… deal combat damage to a player, you create a token'") and a
    planeswalker loyalty ability's ``CreateDelayedTrigger.condition``
    (Dovin's "[+1]: Until end of turn, whenever a creature you control
    deals combat damage to a player, put a loyalty counter" —
    :func:`iter_delayed_trigger_condition_defs`, the Subira/low_power_
    matters precedent).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", "", tree.name, "high"))

    def fire_tribe_if_match(trig: object) -> None:
        if damage_to_player_trigger_kind(trig) is not None and _is_tribe_damage_source(
            getattr(trig, "valid_source", None)
        ):
            fire("tribe_damage_trigger", "you")

    for unit in tree.units:
        if unit.origin == "trigger":
            if unit.trigger_event == "damage_received" and unit.has_effect(
                "deal_damage"
            ):
                fire("damage_reflect", "you")
            if unit.trigger_event == "deals_damage":
                node = unit.node
                vt = getattr(node, "valid_target", None)
                vs = getattr(node, "valid_source", None)
                if (
                    tag_of(vt) == "Controller"
                    and tag_of(vs) == "Typed"
                    and filter_controller(vs) == "Opponent"
                ):
                    fire("damage_to_you_punish", "opponents")
                if (
                    trigger_damage_kind(node) == "CombatOnly"
                    and tag_of(vt) == "Typed"
                    and "Creature" in filter_core_types(vt)
                    and "Player" not in filter_core_types(vt)
                ):
                    fire("combat_damage_to_creature", "any")
                if (
                    vt is not None
                    and damage_recipient_is_player(vt)
                    and _is_tribe_damage_source(vs)
                ):
                    fire("tribe_damage_trigger", "you")
        for trig in iter_nested_trigger_defs(unit.node):
            fire_tribe_if_match(trig)
        for trig in iter_delayed_trigger_condition_defs(unit.node):
            fire_tribe_if_match(trig)
    if "damage_reflect" not in seen:
        for unit in tree.units:
            if any(
                is_damage_reflect_trigger_def(n) for n in iter_typed_nodes(unit.node)
            ):
                fire("damage_reflect", "you")
                break
    return out


# ADR-0038 W3 batch 4 (combat-damage cluster) — creature_ping's power-as-
# damage DOER discriminators, SANCTIONED byte-identical mirrors of legacy's
# own raw-text confirmation (the deleted ``_signals_ir``'s power-as-damage cluster).
# The structural anchor (a ``DealDamage`` whose amount is a POWER-scaled
# ``Ref``) only fires today when the RECIPIENT is independently typed as a
# Creature (Ram Through). Legacy's actual discriminator is the DOER, not
# the recipient: "a creature deals damage equal to ITS OWN power" fires
# creature_ping regardless of WHO the damage reaches (a Fling-style "the
# sacrificed creature's power" names a DIFFERENT object's power and never
# matches these phrasings, so it correctly stays out — that shape is
# damage_equal_power only, already ported separately). CR 120.3.
_POWER_SELF_RECIP = re.compile(r"to itself|deals damage to itself", re.IGNORECASE)
_POWER_ITS_OWN_DOER = re.compile(r"deals damage equal to its power", re.IGNORECASE)
# The power-DOUBLING form ("equal to TWICE its power" — Polliwallop, Cut
# Propulsion, Animist's Might): phase folds the doubling into
# ``Multiply(factor, Ref(Power))`` (unwrapped by ``ref_count_qty``),
# dropping the "power" op the bare anchor reads. Gated by this DOER-confirm
# so a "twice the NUMBER of <X>" multiply burn (a different scaling
# quantity — Price of Progress) never enters.
_POWER_MULT_DOER = re.compile(
    r"(?:deals damage (?:to itself )?equal to (?:twice |\w+ times )?its power"
    r"|to itself equal to its power)",
    re.IGNORECASE,
)
# ADR-0038 W3 batch 6 — the RECIPIENT-side text confirm for a back-reference
# recipient tag (``ParentTarget``/``TriggeringSource``/``SelfRef``/``Any``)
# whose underlying Filter type phase drops: "power to target creature" (Lie
# in Wait, Dead Reckoning — the power SOURCE is a graveyard/library CARD's
# power, "that card's power", not the doer's own, so :data:`_POWER_ITS_OWN_
# DOER` never matches; legacy's OWN structural read fires creature_ping off
# the RECIPIENT alone when it is Creature-typed, regardless of whose power
# scales the damage — recipient-is-a-creature is the primary discriminator,
# doer-confirm is only the fallback for a non-creature-typed recipient).
# Anchored strictly to "power to <recipient>" (never a bare "to <n> creature"
# scan) — a Fling-style "damage equal to THAT CREATURE'S power to <player>"
# (Heart-Piercer Manticore/Grab the Reins's "to any target", Meglonoth/
# Agonizing Demise/Cinder Cloud/Boros Fury-Shield's "to that creature's
# CONTROLLER", Unnatural Hunger's "to that player") has NOTHING creature-
# shaped directly after "power" — a looser "damage ... to X creature" scan
# wrongly matched the "to" inside "equal TO THAT CREATURE'S power" itself
# (corpus-verified over-fire when tried, reverted to this anchor). CR 120.3
# (any object dealing power-scaled damage that connects with a creature is
# a creature_ping member).
_POWER_RECIP_CREATURE_TEXT = re.compile(
    r"power to (?:target|another target|that) creature\b", re.IGNORECASE
)


def _unit_is_repeatable(unit: AbilityUnit) -> bool:
    """The aoe_ping repeatable gate (mirrors live): an Activated ability whose
    cost leaves include Tap or Mana and do NOT include a Sacrifice
    (Pestilence's ``{B}``), or a trigger on a Phase (upkeep/end step) or
    SpellCast mode. A one-shot Spell (Pyroclasm), a sac-cost activation, and
    an ETB-trigger sweep (Chaos Maw — ChangesZone mode) all fail."""
    if unit.origin == "ability" and unit.kind == "Activated":
        leaves = {tag_of(n) for n in iter_cost_leaves(getattr(unit.node, "cost", None))}
        return bool(leaves & {"Tap", "Mana", "ManaDynamic"}) and (
            "Sacrifice" not in leaves
        )
    if unit.origin == "trigger":
        mode = getattr(unit.node, "mode", None)
        return mode in ("Phase", "SpellCast")
    return False


def _creature_ping_fires(node: TypedMirrorNode, raw: str, tree: ConceptTree) -> bool:
    """Whether a DealDamage/DamageAll/DamageEachPlayer ``node`` is
    ``creature_ping``'s exact shape (CR 120.3 — a creature dealing damage
    equal to ITS OWN power, OR any power-scaled damage that connects with a
    creature): a POWER-quantified ``amount`` (or a doubled
    ``Multiply(Ref(Power))``, confirmed via :data:`_POWER_MULT_DOER``) whose
    recipient reaches a Creature (structurally, OR — a back-reference
    recipient tag like ``ParentTarget`` whose Filter type phase drops —
    via :data:`_POWER_RECIP_CREATURE_TEXT`'s "to target creature" text
    confirm, Lie in Wait/Dead Reckoning's "that CARD's power" doer), OR
    whose clause text confirms a self-recip (:data:`_POWER_SELF_RECIP` "to
    itself") or its-own-power doer (:data:`_POWER_ITS_OWN_DOER` "deals
    damage equal to its power"). ``raw`` is the per-node text when the
    caller has one (a top-level effect); pass ``""`` for a deep-walked node
    with none — the confirm then reads the reminder-stripped whole-face
    oracle, the SAME empty-raw fallback shape every sibling arm in this
    module already uses.

    ADR-0038 W3 batch 6: the Multiply anchor also admits an
    ``EventContextAmount`` inner qty (Cut Propulsion's "it deals TWICE
    THAT MUCH damage to itself instead" — the doubled quantity anaphorically
    re-references an earlier, phase-uncaptured "equal to its power" clause
    rather than wrapping a bare ``Power`` ref) — gated the SAME as the
    ``Power``-inner Multiply case behind :data:`_POWER_MULT_DOER`'s literal
    "power" text confirm, so a non-power "twice that much" doubler (a fixed
    burn amount) never enters.
    """
    amt_tag = ref_qty_tag(node, "amount")
    mult_tag = None if amt_tag == "Power" else ref_count_qty(node, "amount")
    if amt_tag != "Power" and mult_tag not in ("Power", "EventContextAmount"):
        return False
    tgt = getattr(node, "target", None)
    tgt_tag = tag_of(tgt)
    recip_creature = tgt_tag in ("Typed", "Or", "And") and (
        "Creature" in filter_core_types(tgt)
    )
    src = raw if raw.strip() else _kept(tree)
    if not recip_creature and tgt_tag not in ("Typed", "Or", "And"):
        recip_creature = _POWER_RECIP_CREATURE_TEXT.search(src) is not None
    mult_confirmed = amt_tag == "Power" or _POWER_MULT_DOER.search(src) is not None
    return mult_confirmed and (
        recip_creature
        or _POWER_SELF_RECIP.search(src) is not None
        or _POWER_ITS_OWN_DOER.search(src) is not None
    )


def _mass_damage_lanes(tree: ConceptTree) -> list[Signal]:
    """symmetric_damage_each + aoe_ping + creature_ping — the effect-side
    damage lanes, scope from each effect's OWN player_filter / target node
    (checklist #5):

    * ``symmetric_damage_each`` — a ``DamageAll`` / ``DamageEachPlayer``
      whose ``player_filter`` is ``All`` (Pestilence; Earthquake's X-form —
      the recall the deleted regex's literal ``\\d+`` missed). The one-sided
      ``Opponent`` filter (Witty Roastmaster — 259 corpus, THE over-fire
      mass) and a player-less creature sweep never fire. Scope "each"
      (CR 102.2/102.3 — the each-player/each-opponent split is the gate).
    * ``aoe_ping`` — a ``DamageAll`` with a Creature-cored target on a
      REPEATABLE unit (:func:`_unit_is_repeatable` mirrors live's gate).
      One-shot sweeps (Pyroclasm — Spell kind) are mass_removal country.
      Scope "you".
    * ``creature_ping`` — a ``DealDamage`` whose amount is a POWER-scaled
      ``Ref`` (Ram Through) OR a doubled ``Multiply(Ref(Power))``
      (Polliwallop; CR 120.3). Structurally reaching a Creature-cored
      target fires outright; ADR-0038 W3 batch 4 widens the DOER side —
      the recipient may be ANY other shape (``ParentTarget``/``SelfRef``/
      ``TriggeringSource`` back-references, ``Any``, a player/planeswalker
      reach) as long as the clause text confirms the DOER deals ITS OWN
      power (:data:`_POWER_SELF_RECIP` "to itself" — Wave of Reckoning;
      :data:`_POWER_ITS_OWN_DOER` "deals damage equal to its power" —
      Abyssal Hunter, Ghitu Fire-Eater, Form of the Dinosaur). Reads the
      per-effect raw when phase carries one; falls back to the
      reminder-stripped whole-face oracle when phase drops it to an empty
      per-effect raw (a Saga chapter / loyalty-ability quote — The Akroan
      War, Garruk Relentless, The Bears of Littjara, Judgment of
      Alexander's ``TriggeringSource`` clause) — the SAME empty-raw
      fallback shape :func:`_damage_equal_power`'s sibling arms use
      elsewhere in this module, gated behind the structural power-damage
      anchor so it never runs as a free scan. Fixed amounts (Prodigal
      Sorcerer) and a DIFFERENT object's power (Fling's "the sacrificed
      creature's power" — the ported ``damage_equal_power``, may co-fire
      when the recipient also reaches a player) never fire. Scope "you".

      ADR-0038 W3 batch 4 adjudicated GAIN: Delirium ("Tap target
      creature that player controls. That creature deals damage equal to
      its power to the player.") is a genuine CR 120.3 doer-based
      creature_ping member — a creature legitimately deals damage equal
      to ITS OWN power, matching the exact shape legacy itself counts on
      Garruk Relentless / Alpha Brawl / Beastie Beatdown / Wisecrack
      (a doer creature reflexively burning a DIFFERENT recipient still
      counts). Legacy misses it only because its own empty-raw oracle
      fallback (``_CREATURE_PING_ORACLE``) is narrower than its
      raw-meaningful branch and Delirium's per-effect raw happens to be
      empty in the OLD projection — a legacy fallback-regex gap, not a
      principled exclusion; corpus-verified as the lane's only over-vs-
      legacy delta (see ``test_crosswalk.py``).
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    creature_ping_nodes: list[object] = []
    for unit in tree.units:
        repeatable = _unit_is_repeatable(unit)
        for c in unit.effect_concepts("deal_damage"):
            t = tag_of(c.node)
            if t in ("DamageAll", "DamageEachPlayer") and (
                player_filter_tag(c.node) == "All"
            ):
                fire("symmetric_damage_each", "each", c.raw)
            if t == "DamageAll" and repeatable:
                tgt = getattr(c.node, "target", None)
                if "Creature" in filter_core_types(tgt):
                    fire("aoe_ping", "you", c.raw)
            if t in ("DealDamage", "DamageAll", "DamageEachPlayer"):
                creature_ping_nodes.append(c.node)
                if _creature_ping_fires(c.node, c.raw or "", tree):
                    fire("creature_ping", "you", c.raw or "")
    # ADR-0038 W3 batch 6: a SECOND, DEEP pass over every unit's node reaches
    # a DealDamage/DamageAll/DamageEachPlayer node buried inside a GRANTED
    # ability's OWN definition (GrantAbility/GrantStaticAbility/
    # AddTargetReplacement — "gains '{T}: This creature deals damage equal
    # to its power to target creature.'", Burning Anger, Sinstriker's Will,
    # Brawl, Dead Before Sunrise, Commando Raid, Predatory Urge, Surestrike
    # Trident's Equipment grant), a node NO unit's own ``effects`` tuple
    # carries (the granting static/spell's own effect chain is the GRANT
    # modification, not the granted ability's inner effects — a DIFFERENT
    # node than the flat pass above reaches). No per-node ``raw`` exists at
    # this depth (only ability/trigger/static WRAPPER nodes carry
    # ``description``, never a bare effect leaf), so the doer-confirm reads
    # the reminder-stripped whole-face oracle directly — gated behind the
    # SAME structural Power-quantity anchor as the flat pass, never a free
    # scan. ``creature_ping`` only (``symmetric_damage_each``/``aoe_ping``
    # stay flat-pass-only — unaffected, no regression risk).
    if "creature_ping" not in seen:
        seen_ids = {id(n) for n in creature_ping_nodes}
        for unit in tree.units:
            for n in iter_typed_nodes(unit.node):
                if id(n) in seen_ids:
                    continue
                if tag_of(n) not in ("DealDamage", "DamageAll", "DamageEachPlayer"):
                    continue
                seen_ids.add(id(n))
                if _creature_ping_fires(n, "", tree):
                    fire("creature_ping", "you", "")
                    break
            if "creature_ping" in seen:
                break
    return out


LANES = (
    _spell_keyword_grant,
    _hand_disruption,
    _etb_trigger_lanes,
    _ltb_matters,
    _creature_cast_trigger,
    _opponent_cast_matters,
    _combat_damage_lanes,
    _second_spell_matters,
    _xspell_matters,
    _counter_control,
    _bounce_tempo,
    _power_double,
    _keyword_grant_lanes,
    _base_pt_set,
    _variable_pt,
    _trigger_doubling,
    _forced_attack,
    _damage_prevention,
    _damage_equal_power,
    _replacement_doubler_lanes,
    _damage_trigger_lanes,
    _mass_damage_lanes,
)


# ADR-0039 W8 (KEPT-twelve wave):
LANES_W8 = (
    _damage_redirect,
    _base_power_matters,
    _copy_limit,
)
