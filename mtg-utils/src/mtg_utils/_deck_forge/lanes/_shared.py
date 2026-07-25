"""Helpers and constants shared across the lane-family modules (split from
crosswalk_signals.py — see this package's ``__init__``)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    effect_owner_player_scope,
    filter_controller,
    filter_core_types,
    filter_inzone_zones,
    filter_owned_controller,
    filter_predicates,
    filter_subtypes,
    tag_of,
    trigger_scope,
    trigger_subject_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._deck_forge.signal_base import Signal

# The b13 conferred-grant / condition-payoff raw anchors (soulbond / undying /
# changeling / cascade / the Stage-3b madness/affinity/mutate re-categorizers)
# were T9-finalize folded to bucket-B tree_synthesis arms
# (``_arm_b13_raw_anchor`` / ``_arm_b13_node_anchor``); the pinned regexes now
# live there, imported single-source from project.py's ``_narrow_*`` marker
# sources.
# W3 batch-3 (ADR-0038, combat-coercion cluster): the per-effect "attacks …
# if able" clause grammar (CR 508.1d) that supplement.py's
# ``_recover_static_pattern`` uses to reclassify a bucket-B Unimplemented
# clause — imported single-source (never re-typed) so the crosswalk's
# ``_kept(tree)`` text-idiom fallback reproduces the SAME clause the legacy
# recovery grammar already tokenizes, no new grammar/verb/arm added.
#
# ADR-0038 W3 batch 3 — clone_makers back-reference recovery reuses the
# legacy ``_recover_clone_subjects`` text-scan (CR 707.2's copied-type word
# right after "copy of") single-source from the OLD projection's own
# supplement pass, rather than re-deriving an equivalent regex here.
#
# ADR-0038 W3 batch 4 (draw-etb-tokens cluster) — topdeck_stack's
# back-reference (ParentTarget/TrackedSet/ExiledBySource/untyped-Or) direction
# disambiguation reuses the legacy ``_topdeck_stack_self`` self-anchor scan
# ("on top of your library" / "top of your library in any order") verbatim,
# single-source from the OLD projection's own supplement pass — the SAME
# idiom legacy's own comment documents as necessary because phase's
# PutAtLibraryPosition/Dig carry NO library-owner field at all, so a self
# top-stack (Scroll Rack) and an opponent-library tuck (Cruel Fate, Sealed
# Fate) are byte-identical nodes; the self/opponent split lives only in
# oracle text.
#
# ADR-0038 W3 batch 6 (combat-trio) — combat_damage_matters/combat_damage_to_opp's
# bare-quoted-grant residual tail (a trigger QUOTED inside an activated ability
# / one-shot grant, a "would deal combat damage" REPLACEMENT, or the passive
# "was dealt combat damage by" reference — Predators' Hour, Sokrates, Steel
# Hellkite, the Unfinity Sticker Sheet TK-templates) reuses the legacy
# ``combat_damage_recipients_from_text`` recipient-recovery scan verbatim,
# single-source from the OLD projection's own supplement pass (public
# specifically for this kind of reuse per its own docstring) — the SAME
# synthetic-trigger recovery ``old_ir_for`` itself runs when phase leaves the
# combat-damage connect wholly unstructured. CR 510.1b/510.1c/510.2/615.
# The b15 opponent_counter_grant co-tap anaphora fallback (the supplement's
# tap-opp combinators) was T9-finalize folded to the
# ``_arm_opponent_counter_grant`` bucket-B synth arm; the combinators now
# live in tree_synthesis.py, imported single-source from supplement.py.
# The Tier-1 death_matters arms (ADR-0036/0037) share the LIVE structural reads
# with the ``tree_synthesis`` bucket-B gap gate — one source, no drift: the morbid
# creature-death state check and the ``CreatureDying`` trigger-doubler.
# ADR-0038 W3 batch 4 — topdeck_stack's fallback for an idiom with NO
# topdeck_stack node at all (Leashling/Penance/Hidden Retreat's
# activation-cost put; Munda, Ambush Leader's/Diabolic Vision's modal
# reveal-then-place ``Dig``) reuses the legacy kept-mirror
# TOPDECK_STACK_SWEEP_REGEX verbatim, single-source from ``_sweep_detectors``
# (a sibling ``_deck_forge`` module, no import cycle) — narrower than the
# self-anchor scan on purpose (see ``_topdeck_stack``'s docstring).
#
# ADR-0038 W3 batch 6 (combat-trio) — combat_damage_matters/combat_damage_to_opp's
# bare-quoted-grant residual tail (Predators' Hour, Sokrates, Steel Hellkite's
# passive "was dealt combat damage by" filter, the Unfinity Sticker Sheet
# templates) reuses the legacy ``COMBAT_DAMAGE_TO_OPP_DS_GRANT_REGEX`` LOW-
# confidence double-strike-grant mirror verbatim (Raphael/Blade Historian/
# Berserkers' Onslaught — a disjoint, corpus-bounded 3-card class).
# The b12 SANCTIONED byte-identical mirror ports import the LIVE constants
# (never re-typed copies): the pinned shared sources from _sweep_detectors,
# and the private live mirrors/kind-sets now homed in text_reads / signal_base
# (the _resolve_subject precedent) — one source, zero drift.

# Cast-from-graveyard keyword family (CR 601.3 / 702.62a …) — a card that re-casts
# ITSELF from a graveyard PERFORMS self-recursion → ``graveyard_makers`` you. A
# Scryfall keyword field-lookup (the live ``_IR_KEYWORD_MAP`` survivors): these are
# NOT a ``ChangeZone`` effect (phase carries them on castable-zone metadata, no
# effect node), so the structural substrate cannot read them — re-introducing them
# structurally is impossible, dropping them a regression (checklist #3).
_GY_CAST_KEYWORDS: frozenset[str] = frozenset(
    {
        "flashback",
        "escape",
        "disturb",
        "embalm",
        "eternalize",
        "encore",
        "aftermath",
        "retrace",
        "jump-start",
        "recover",
        "unearth",
    }
)

# Graveyard-payoff keyword family (CR 702.51 dredge / 702.66 delve / 702.91
# scavenge) — a card that CONSUMES a stocked graveyard as fuel → ``graveyard_matters``
# you. Keyword field-lookup, same survivor rationale.
_GY_MATTERS_KEYWORDS: frozenset[str] = frozenset({"dredge", "delve", "scavenge"})

# Attachment predicates that mark a SINGLE-Aura / single-target shrink (CR 303) — the
# affected creature is the one enchanted, not a mass population. A base-P/T-shrink
# debuff carrying one is a neutralize, not a -1/-1 enabler.
_DEBUFF_SINGLE_AURA_PREDS: frozenset[str] = frozenset(
    {"EnchantedBy", "AttachedToRecipient", "HasAnyAttachmentOf"}
)

# Equipment / Aura / Role subtypes that mark a voltron build-around (CR 301.5 /
# 303.4 / 702.5). Mirrors the deleted ``_signals_regex``'s ``_EQUIP_AURA_SUBTYPES``
# (+ Role, a Aura subtype phase carries on Virtuous Role tokens).
_VOLTRON_SUBTYPES: frozenset[str] = frozenset({"aura", "equipment", "role"})

# Attachment-STATE predicate tags (CR 301.5c / 303). Mirrors
# the deleted ``_signals_regex``'s ``_ATTACHMENT_PREDICATES``.
_ATTACHMENT_PREDS: frozenset[str] = frozenset(
    {"AttachedToRecipient", "HasAnyAttachmentOf", "HasAttachment"}
)

# EquippedBy / EnchantedBy mark BOTH an Equipment/Aura's OWN self-referential
# payload ("Equipped creature gets +X/+X" — every Equipment ever printed) AND
# a genuine SEPARATE collective payoff ("Each equipped creature and Equipment
# you control gains deathtouch" — Hemlock Vial; "Equipped creatures you
# control gain indestructible" — Resistance Reunited). The two are gated by
# the CARD'S OWN type: a card that is itself an Equipment/Aura using its own
# EquippedBy/EnchantedBy static is the payload (excluded, CR 301.5c/303.4b);
# a non-Equipment/non-Aura card using the SAME tag is a real build-around.
_SELF_PAYLOAD_SUBTYPE: dict[str, str] = {
    "EquippedBy": "equipment",
    "EnchantedBy": "aura",
}


def _voltron_collective_preds(filt: object, self_subtypes: frozenset[str]) -> set[str]:
    """Attachment-STATE predicate tags on ``filt`` that count as a voltron_
    matters tell: the unconditional set (:data:`_ATTACHMENT_PREDS`) plus an
    EquippedBy/EnchantedBy predicate gated OFF when the tree's own card is
    the matching Equipment/Aura (the self-payload exclusion)."""
    out: set[str] = set()
    for p in filter_predicates(filt):
        if p in _ATTACHMENT_PREDS or (
            p in _SELF_PAYLOAD_SUBTYPE and _SELF_PAYLOAD_SUBTYPE[p] not in self_subtypes
        ):
            out.add(p)
    return out


# Core-type → matters lane. A composite (Artifact AND/OR Enchantment) subject fires
# BOTH. Mirrors the deleted ``_signals_ir``'s identically-named ``_TYPE_MATTERS_LANE``.
_TYPE_MATTERS_LANE: dict[str, str] = {
    "Artifact": "artifacts_matter",
    "Enchantment": "enchantments_matter",
}

# Effect/owner scopes that count as "your" resource for a maker lane.
_YOU_EACH = ("you", "each")

# Phase ``produced.type`` values that are intrinsically FIXING (a choice of ≥2
# colors / any-color / any-type) — mirrors ``project._FIXING_PRODUCED_TYPES``. A
# land whose ramp is fixing is real ramp, not the mana base. CR 106.1 / 605.1a.
_FIXING_PRODUCED_TYPES: frozenset[str] = frozenset(
    {
        "AnyInCommandersColorIdentity",
        "AnyTypeProduceableBy",
        "ChoiceAmongCombinations",
        "ChosenColor",
        "OpponentLandColors",
        "DistinctColorsAmongPermanents",
        "AnyOneColorAmongPermanents",
        "ChoiceAmongExiledColors",
    }
)


# ── Batch-12 mirror constants + census sets ──────────────────────────────────
# (the entered_attacker ``ENTERED_ATTACKER_REGEX`` mirror and the Johan word
# mirror were ADR-0036/0037 folded — entered_attacker to a fully structural
# read (see ``_entered_attacker``), exert_matters's Johan residual to the
# ``tree_synthesis`` stage's ``_JOHAN_MIRROR``-relocated
# ``synth_exert_matters`` bucket-B arm. The manland sibling — land_protection
# — was likewise folded earlier; see ``_arm_manland``.)

# Reminder-text strip — the same paren-substitution the live path applies to
# build ``kept_oracle`` (the deleted ``_signals_ir``'s line ~11091).
_REMINDER_RX = re.compile(r"\([^)]*\)")

# Land subtype words the land-animate arms accept when the animated filter
# names the land by SUBTYPE ("target Forest" — Awakener Druid). CR 205.3i.
_LAND_SUBTYPE_WORDS: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "desert",
        "gate",
        "lair",
        "locus",
        "cave",
        "mine",
        "power-plant",
        "sphere",
        "tower",
        "urza's",
    }
)


def _kept(tree: ConceptTree) -> str:
    """The reminder-stripped face oracle — the b12 mirror ports' scan text."""
    return _REMINDER_RX.sub(" ", tree.oracle or "")


# W3 batch-3 (ADR-0038, combat-coercion cluster) — the shared discriminator
# for the "attacks … if able" family of bucket-B text idioms
# (forced_attack's ``_FORCE_ATTACK``/``_FORCE_ATTACK_REF``, goad_makers'
# ``_GOAD_STYLE_FORCE``): a raw whole-face ``_kept(tree)`` scan can't tell a
# genuine self/team/targeted attack compulsion apart from two false-positive
# classes, both excluded PER-CLAUSE (the period-delimited sentence
# containing the match — a card can genuinely carry a real compulsion AND
# an unrelated excluded clause in DIFFERENT abilities, Magnetic Web's own
# "attack if able" team force + its SEPARATE "block that creature … if
# able" ForceBlock trigger, so a whole-tree/whole-card gate over-excludes):
#
# * ForceBlock — "Whenever ~ attacks, target creature … blocks it this
#   combat if able" (Avalanche Tusker, Fighter Class, Grappling Hook,
#   Impetuous Devils, Tower Above, Magnetic Web's 2nd trigger, Tolsimir's
#   "blocks that Wolf") is CR 509.1c's provoke-style force-a-BLOCK, a
#   narrower mechanic legacy keeps out of forced_attack/goad_makers
#   entirely — "attacks" here is only the TRIGGER condition; the compelled
#   action is "block(s) it/that <noun>/…", always a pronoun/demonstrative
#   back-reference to the ATTACKER, never the disjunctive same-subject
#   "attacks OR blocks" of a genuine compulsion (Boros Battleshaper's
#   GRANTED AddStaticMode MustAttack+MustBlock combo, Iron Golem's OWN
#   combo — legacy DOES fire force_attack for the former, the
#   ``self_combo`` structural check below excludes the latter). Detected by
#   "block(s) it/that <noun>/them/him/her" in the SAME clause as the match.
# * Created-token — "create … tokens … that attack … if able" (Furygale
#   Flocking) is the SAME LastCreated-style exclusion the structural
#   MustAttack arm applies (the compulsion belongs to a fresh token, not
#   the card's own engine — the Legion Warboss / Howlsquad Heavy
#   precedent). Detected by a "token(s)" word anywhere in the same clause.
_FORCE_BLOCK_SHAPE_RX = re.compile(
    r"\bblocks?\s+(?:it\b|that \w+\b|them\b|him\b|her\b)", re.IGNORECASE
)
_TOKEN_WORD_RX = re.compile(r"\btokens?\b", re.IGNORECASE)


def _sentence_span(text: str, start: int, end: int) -> str:
    """The period-delimited clause containing ``text[start:end]``."""
    prev = text.rfind(".", 0, start)
    nxt = text.find(".", end)
    lo = prev + 1 if prev != -1 else 0
    hi = nxt if nxt != -1 else len(text)
    return text[lo:hi]


def _attack_compulsion_hit(kept: str, *patterns: re.Pattern[str]) -> bool:
    """True when one of ``patterns`` matches a genuine attack compulsion
    clause in ``kept`` — excludes the ForceBlock and created-token false
    positives (see the module comment above), gated per-CLAUSE so an
    unrelated excluded clause elsewhere on the same card never suppresses a
    real compulsion."""
    for rx in patterns:
        m = rx.search(kept)
        if m is None:
            continue
        span = _sentence_span(kept, m.start(), m.end())
        if _FORCE_BLOCK_SHAPE_RX.search(span) or _TOKEN_WORD_RX.search(span):
            continue
        return True
    return False


# player_scope actor tags that are NOT the ability's controller (an edict makes
# someone ELSE sacrifice; the controller never does). CR 701.21a / 800.4a.
_EDICT_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "All", "EachPlayer", "Each"}
)


def _sac_is_edict(unit: AbilityUnit, sac_node: TypedMirrorNode) -> bool:
    """Whether a ``Sacrifice`` EFFECT is an EDICT (someone ELSE sacrifices their own).

    Phase tags "each opponent / each other player sacrifices" edicts with a
    ``player_scope`` of ``Opponent`` / ``All`` on the ability WRAPPER that OWNS the
    sacrifice — a trigger's ``execute``, a sequential ``sub_ability``, or a modal
    ``mode_abilities`` arm (Baleful Beholder's "Each opponent sacrifices an
    enchantment") — while MISLABELING the sacrificed permanent's filter
    ``controller: You``. Per CR 701.21a a player can only sacrifice a permanent THEY
    control, so the effect is an EDICT, not a self-sac outlet. Reading the scope of
    the sacrifice's OWN wrapper (not a sibling's) rejects the edict (Grave Pact,
    Dictate of Erebos, Baleful Beholder's modal arm) while a genuine self-sac
    (Mycoloth's Devour — no non-controller scope on the sac's wrapper) still fires.
    """
    return effect_owner_player_scope(getattr(unit, "node", None), sac_node) in (
        _EDICT_ACTORS
    )


def _condition_leaves(cond: object) -> list[object]:
    """Flatten an And/Or/Not condition tree to its LEAF condition nodes
    (ADR-0038 W4 giant, deep descent). "If you control an artifact and an
    enchantment" (When We Were Young, Okiba Salvage, Banishing Slash) types
    as a single ``T_condition__And`` wrapping TWO ``QuantityCheck`` leaves
    (one per type), not one compound tag the flat ``tag_of`` switch in
    :func:`_artifacts_enchantments_matter` can read directly. CR 608.2b: a
    natural-language "and"/"or" join is structurally a conjunction/
    disjunction of independently-true-or-false checks, so unwrapping to the
    leaves is lossless — an Or's members are each still a standalone
    condition, the SAME shape a bare (non-compound) condition site already
    is. A ``Not``-wrapped leaf is kept (not dropped): mirrors legacy's
    ANY-comparator-direction philosophy (a "control NO artifacts" floor
    punisher still wants an artifacts deck).
    """
    tag = tag_of(cond)
    if tag in ("And", "Or"):
        out: list[object] = []
        for sub in getattr(cond, "conditions", ()) or ():
            out.extend(_condition_leaves(sub))
        return out
    if tag == "Not":
        inner = getattr(cond, "condition", None)
        return _condition_leaves(inner) if inner is not None else []
    return [cond]


def _is_generic_creature_filter(filt: object) -> bool:
    """A GENERIC "creatures you control" filter (CR 604.3) — Creature in core types,
    NO subtype, controller you, ON THE BATTLEFIELD (CR 110.1 default zone for
    "creature" absent an explicit zone qualifier — phase sometimes states
    ``InZone: Battlefield`` explicitly, e.g. a Counters-predicate filter's
    "with a +1/+1 counter on it" reading — CR 400.2, that's still the
    default population, NOT a zone restriction). A tribal (subtyped)
    filter is ``type_matters``, a different lane; a single-target
    removal/buff (controller any) fails the gate. ADR-0039 W7: an
    explicit NON-battlefield ``InZone`` predicate (Wire Surgeons' "each
    artifact creature card in your GRAVEYARD has encore" — a graveyard-
    recursion care, not a battlefield population) fails the gate —
    corpus-verified via the ADR-0039 W7 deep static-def descent, which
    reaches these buried graveyard-zone static defs a shallower walk
    never surfaced. A ``SharesQuality`` predicate (Haunted One's granted
    "... other creatures you control that SHARE A CREATURE TYPE with
    it" — a TRIBAL restriction phase encodes as a predicate, not a
    ``Subtype`` type_filters entry, so :func:`filter_subtypes` alone
    misses it) fails the gate too — CR 205.3 territory (``type_matters``),
    not a generic population.
    """
    zones = filter_inzone_zones(filt)
    return (
        filter_controller(filt) == "You"
        and "Creature" in filter_core_types(filt)
        and not filter_subtypes(filt)
        and "SharesQuality" not in filter_predicates(filt)
        and (not zones or set(zones) <= {"Battlefield"})
    )


# task #91 — the ParentTargetOwner beneficiary-scope helper (CR 108.3). Some
# lanes stamp a chain's whole-card DOER scope "you" even when the actual
# resource lands with the OWNER of an EARLIER-targeted permanent/card, not
# the caster: "The owner of target permanent shuffles it into their
# library, then reveals..., they put it onto the battlefield" (Chaos Warp),
# "...shuffles it into their library, then draws two cards" (Oblation),
# "...shuffles it into their library, then exiles the top card...they may
# cast it" (Audacious Swap), "...shuffles it into their library. Then that
# player discovers X" (Zoyowa's Justice), "search its owner's graveyard,
# hand, and library...That player shuffles, then draws" (Deadly Cover-Up).
# :func:`_root_target_filter` finds the chain's real, single-object CHOICE
# (never a mass/symmetric effect's filter, and never a back-reference tag)
# that ``ParentTarget``/``ParentTargetOwner`` resolve through;
# :func:`_target_owner_beneficiary_scope` maps its ownership constraint to a
# lane scope: 'opponents' when the filter itself names ``Owned: Opponent``
# (Deadly Cover-Up's "a card from an OPPONENT's graveyard" — the beneficiary
# is ALWAYS an opponent), else 'any' (Chaos Warp/Oblation/Audacious Swap/
# Zoyowa's Justice's unconstrained "target permanent"/"target nonland
# permanent"/"target artifact or creature" can be YOURS or an opponent's —
# the beneficiary follows whoever you chose to target).
#
# A unit with NO real root filter returns ``None`` — the caller keeps its
# default scope, since a SelfRef-anchored "its owner" names an object whose
# owner never varies with a target at all (Yes Man, Personal Securitron's
# stolen-creature-leaves-battlefield token grant; Oft-Nabbed Goat's own
# dies-trigger draw) — the object IS the analyzed card itself, whose owner
# is definitionally the deckbuilder ("you"), not a variable target's owner.
# Corpus-verified (2026-07, every commander-legal unit carrying a
# ParentTargetOwner recipient, 63 cards): the ONLY units with BOTH a
# ParentTargetOwner recipient AND a real root target filter are the five
# named cards above plus Path of Peace / Misfortune's Gain ("Destroy target
# creature. Its owner gains 4 life." — lifegain_makers, also fixed here) and
# Pharika / Funeral Pyre ("Exile target card from a graveyard. Its owner
# creates a token." — token_maker's OWN membership gate is scope-coupled
# [``concept.scope not in _YOU_EACH``], so correcting its scope would DROP
# these two from the lane's membership; that membership+scope call was out
# of scope for #91 and deferred — FIXED together in task #93: ``_token_maker``
# now calls this SAME helper per-unit and admits a ``ParentTargetOwner``
# recipient whose beneficiary resolves "any", firing scope "any" instead of
# the hardcoded "you"). Every other
# hit is a "shuffle THIS card into its own owner's library" tuck-cycle
# (Beacon of Immortality, Blitz Hellion, Cerulean Sphinx, …) whose ONLY
# ParentTargetOwner-tagged effect is an ``Shuffle``/``other`` concept no
# lane reads for scope at all — genuinely no bug, nothing to fix.
_MASS_EFFECT_TAGS: frozenset[str] = frozenset(
    {"DestroyAll", "ChangeZoneAll", "PutCounterAll", "DamageAll", "DamageEachPlayer"}
)
_TARGET_OWNER_BACKREF_TAGS: frozenset[str] = frozenset(
    {
        "ParentTarget",
        "ParentTargetOwner",
        "ParentTargetController",
        "SelfRef",
        "TriggeringSource",
        "TriggeringPlayer",
        "TrackedSet",
        "TrackedSetFiltered",
        "Any",
        "Controller",
        "OriginalController",
        "Player",
        "TargetPlayer",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "ScopedPlayer",
        "AllPlayers",
        "Each",
        "EachPlayer",
    }
)


def _root_target_filter(unit: AbilityUnit) -> object | None:
    """The FIRST real object-filter target in ``unit``'s effect chain — the
    object ``ParentTarget``/``ParentTargetOwner`` resolve through — skipping
    a mass/symmetric effect (:data:`_MASS_EFFECT_TAGS`, CR 601.2c: "all"/
    "each" names no single chosen object, so a later back-reference in the
    SAME chain can't mean IT) and any back-reference tag
    (:data:`_TARGET_OWNER_BACKREF_TAGS`). ``None`` when no unit effect names
    a genuine filter (Or/And/Typed) — a self-referencing chain (Mirror-Mad
    Phantasm's "this creature's owner shuffles IT into their library" — the
    SAME card, never a variable target)."""
    for c in unit.effects:
        if tag_of(c.node) in _MASS_EFFECT_TAGS:
            continue
        tgt = getattr(c.node, "target", None)
        if tgt is None:
            continue
        tt = tag_of(tgt)
        if tt is None or tt in _TARGET_OWNER_BACKREF_TAGS:
            continue
        return tgt
    return None


def _target_owner_beneficiary_scope(unit: AbilityUnit) -> str | None:
    """'opponents' when the root target filter constrains ownership to an
    opponent (``Owned: Opponent``), 'any' when it names no owner constraint
    at all, ``None`` (no override — the caller keeps its default scope) when
    :func:`_root_target_filter` finds no real target."""
    filt = _root_target_filter(unit)
    if filt is None:
        return None
    return "opponents" if filter_owned_controller(filt) == "Opponent" else "any"


_RING_CONDITIONS: frozenset[str] = frozenset({"IsRingBearer"})
# Permission tags marking a cast/play-FROM-EXILE build-around (CR 116 / 702.170).
_CAST_FROM_EXILE_PERMS: frozenset[str] = frozenset({"PlayFromExile", "Plotted"})


def _whole_card_maker(
    tree: ConceptTree, concept: str, key: str, scope: str
) -> list[Signal]:
    """A whole-card presence maker (granularity c): the first ``concept`` effect →
    one ``Signal(key, scope)``. The shared shape for the batch-5 phase-native
    makers (discover / venture / amass / incubate / dice / facedown / day-night /
    phasing) — each a clean structural read off a first-class effect node.
    """
    for c in tree.effect_concepts(concept):
        return [Signal(key, scope, "", c.raw, tree.name, "high")]
    return []


# ── Batch 8 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# Battlefield permanent types a single-target exile/removal subject may name
# (CR 115.1 / 406.1) — mirrors the deleted ``_signals_ir``'s identically-named type set.
_PERMANENT_TYPES: frozenset[str] = frozenset(
    {"Creature", "Permanent", "Artifact", "Enchantment", "Planeswalker", "Battle"}
)

# task #88 — a reveal/mill/dig producer concept. When ONE of these appears
# BEFORE a ``change_zone``(->Library)/``put_library_position`` concept in
# the SAME unit's ``effects`` chain, the put/change_zone's target filter
# describes a CARD among the just-revealed/milled population ("Put all Elf
# cards revealed this way into your hand and the rest on the bottom of
# your library" — Sylvan Messenger/Goblin Ringleader/Enlistment Officer's
# tribal-reveal cycle; "mill four cards, then you may put a creature or
# land card from among the milled cards on top" — Lluwen), never a
# targeted BATTLEFIELD permanent — even though the filter can carry a bare
# permanent core type (Creature/Land) or a creature-race SUBTYPE
# (Elf/Goblin/Merfolk/Zombie/Soldier/Kavu) that ``_perm_subject`` would
# otherwise treat as a permanent tell. The REVERSE order (a genuine tuck
# FOLLOWED BY a reveal — Chaos Warp's "shuffle it into their library, then
# reveals the top card…", Audacious Swap's "shuffles it into their
# library, then exiles the top card…", Proteus Staff's "Put target
# creature on the bottom of its owner's library. That creature's
# controller reveals cards…") is unaffected — those don't match this
# ordering, so the genuine tuck target is untouched. Corpus-verified
# false-positive class (task #88 sweep): Sylvan Messenger, Brass Herald,
# The Fourteenth Doctor, Tidal Courier, Goblin Ringleader, Enlistment
# Officer, Grave Defiler, Kavu Howler, Sages of the Anima (all `reveal_top`
# selection cycles), Lluwen Imperfect Naturalist (`mill`), Ajani
# Unyielding's +2 / Garruk Caller of Beasts' +1 / Enshrined Memories / Lair
# Delve (the SAME reveal-then-filter idiom on a DIFFERENT ability of a
# multi-mode card — the genuine removal on Ajani/Garruk comes from an
# UNRELATED ability, exile/battlefield-put respectively, not this one).
_TUCK_SELECTION_SIBLINGS: frozenset[str] = frozenset(
    {"mill", "dig", "reveal_top", "reveal_until", "exile_top"}
)


def _tuck_preceded_by_selection(effects: Sequence[ConceptNode], idx: int) -> bool:
    """Whether a reveal/mill/dig producer (:data:`_TUCK_SELECTION_SIBLINGS`)
    appears BEFORE index ``idx`` in ``effects`` — the task #88 card-
    selection veto (see that constant's docstring)."""
    return any(e.concept in _TUCK_SELECTION_SIBLINGS for e in effects[:idx])


# Discard-owning wrapper actors that mark an OPPONENT-directed discard (CR
# 701.9): phase mislabels a modal/saga/per-opponent "each opponent discards"
# recipient ``Controller`` but hangs ``player_scope: Opponent`` on the wrapper
# (The Eldest Reborn ch. 2, Aclazotz). ``All``/``Each`` are deliberately
# ABSENT — a symmetric wheel (Dark Deal) hits YOU too and stays loot fuel.
_OPP_DISCARD_ACTORS: frozenset[str] = frozenset(
    {"Opponent", "Opponents", "EachOpponent", "TargetPlayer"}
)
# Sibling-return target tags marking the SAME exiled object coming back (CR
# 603.6e) — the blink tell the exile_removal lane vetoes on.
_RETURN_TARGET_TAGS: frozenset[str] = frozenset(
    {"ParentTarget", "TrackedSet", "TrackedSetFiltered"}
)
# ExileTop owners naming ANOTHER player's library (a theft-impulse — Gonti,
# Night Minister exiles from the damaged OPPONENT's library): not the
# your-library impulse engine.
_OPP_TOP_OWNERS: frozenset[str] = frozenset(
    {
        "ParentTarget",
        "ParentTargetController",
        "Player",
        "Target",
        "Opponent",
        "Opponents",
        "EachOpponent",
        "TriggeringPlayer",
        "ScopedPlayer",
    }
)
# +1/+1 / -1/-1 counter kinds (upper) — the counter_manipulation discriminator
# vs charge/oil/loyalty/fade (split-lane #4, CR 122.1 / 122.6).
_PT_COUNTER_KINDS: frozenset[str] = frozenset({"P1P1", "M1M1"})
# Dynamic-P/T modification tags (a +X/+X anthem/pump whose X is computed) —
# the scaling_pump / count_anthem mod-site anchor. The ``Set*`` forms are
# characteristic-defining */* bodies (variable_pt), NOT a pump — excluded.
_DYNAMIC_PT_MODS: frozenset[str] = frozenset({"AddDynamicPower", "AddDynamicToughness"})


def _negative_pt_field(node: TypedMirrorNode, field: str) -> bool:
    """Whether a Pump-style node's P/T ``field`` (``toughness``) is NEGATIVE —
    the mass-debuff arm's lethality tell (CR 704.5f: a creature with
    toughness 0 or less dies; a "-2/-0" power dip never kills). Reads THREE
    shapes phase emits for a shrink: ``Fixed N`` (Languish's "-4/-4", Drown
    in Sorrow's "-2/-2" — the literal magnitude); ``Variable "-X"`` (Toxic
    Deluge's "-X/-X" — the magnitude is unknown at parse time, but the
    Variable's own string carries the sign); and ``Quantity`` wrapping a
    ``Multiply`` whose OUTERMOST ``factor`` is negative (task #85 re-
    measurement at v0.23.0 — the "dynamic P/T pump scaling by source
    intensity" bump feature: Cloudkill/Mutilate/Olivia's Wrath's mass "-X/-X
    where X is <count>" and Death Wind/Nightmarish End/Flunk's single-target
    kill class, 69-card corpus census, project to ``Quantity(value=
    Multiply(factor=-1, inner=Ref(...)))`` — a genuinely negative sign
    regardless of the inner expression's own shape, since every corpus
    ``inner`` resolves a non-negative count (a hand/graveyard/board size);
    Flunk's "7 minus the number of cards in hand, clamped to 0" nests a
    SECOND ``Multiply(-1, ...)`` under a ``ClampMin``/``Offset`` pair the
    magnitude-reading ``ref_count_qty`` can't unwrap, but the sign is fully
    decided by the OUTER factor alone — the clamp only floors the
    non-negative inner count at 0, it never flips the outer sign). Reading
    only the outermost factor (not recursing to check for a sign-flipping
    inner ``Multiply`` too) is deliberately shallow: no corpus card double-
    negates via nested ``Multiply`` factors, and a hypothetical one would be
    a vanishingly narrow edge case not worth a general negate-count walk
    here."""
    p = getattr(node, field, None)
    tag = tag_of(p)
    if tag == "Fixed":
        v = getattr(p, "value", None)
        return isinstance(v, int) and v < 0
    if tag == "Quantity":
        val = getattr(p, "value", None)
        if tag_of(val) == "Multiply":
            factor = getattr(val, "factor", None)
            if isinstance(factor, int) and factor < 0:
                return True
    if tag == "Variable":
        v = getattr(p, "value", None)
        return isinstance(v, str) and v.strip().startswith("-")
    return False


def _site_raw(sdef: object) -> str:
    """A static-def site's grounding clause (its ``description``, else "")."""
    desc = getattr(sdef, "description", None)
    return desc if isinstance(desc, str) else ""


# ── Batch 9 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# Land subtypes (CR 205.3i — basic + nonbasic): the fix-(a) membership test
# that keeps a SUBTYPE-only put from resurrecting a land put as a cheat.
_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "gate",
        "desert",
        "lair",
        "locus",
        "mine",
        "power-plant",
        "tower",
        "urza's",
        "cave",
        "sphere",
        "town",
    }
)
# Spell-cast keywords (CR 702 — flash 702.8, flashback 702.34, cascade
# 702.85, …): an ``AddKeyword`` grant of one of these is a grant to a SPELL /
# castable card, never a battlefield keyword anthem (team_buff). Normalized
# lower/spaceless/hyphenless (phase spells ``JumpStart``).
_SPELL_GRANT_KEYWORDS: frozenset[str] = frozenset(
    {
        "flashback",
        "flash",
        "cascade",
        "storm",
        "replicate",
        "conspire",
        "jumpstart",
        "retrace",
        "convoke",
        "improvise",
        "delve",
        "demonstrate",
        "casualty",
        "rebound",
        "escape",
        "affinity",
        "buyback",
        "madness",
    }
)
# RevealHand static ``who`` values that reach an OPPONENT's hand (CR 402.3):
# Telepathy's ``Opponents``, Zur's Weirding's symmetric ``AllPlayers`` (it
# reveals their hands too). A ``Controller`` self-reveal (Enduring Renewal)
# is not disruption.
_REVEAL_WHO_OPP: frozenset[str] = frozenset({"Opponents", "AllPlayers"})


def _discard_watch_is_opponent(unit: AbilityUnit) -> bool:
    """Whether a discarded-family trigger watches an OPPONENT's discard.

    phase carries the watched discarder on ``valid_target`` (Archfiend of
    Ifnir — ``Controller``) or on ``valid_card``'s controller (Megrim —
    ``Typed controller=Opponent``); either naming the opponent routes the
    trigger to the punisher lane (checklist #5 — the recipient nodes, never
    the mislabeled trigger_scope).
    """
    return (
        trigger_scope(unit.node) == "opponents"
        or trigger_subject_scope(unit.node) == "opponents"
    )


# ADR-0038 W3 batch 4 — a phase-parser gap distinct from the mirror above: a
# GRANTED/DELAYED trigger def (a pump-attached ``CreateDelayedTrigger``, a
# Saga-granted watcher) whose ``mode`` phase leaves ``MirrorVariant(key=
# "Unknown")`` entirely (Fire Giant's Fury's "Whenever it deals combat
# damage to a player this turn, exile ..."; Kang Dynasty's "whenever any of
# those creatures deals combat damage to a player, draw a card" — both
# verified via direct node inspection: mode.key=="Unknown", damage_kind
# left the generic "Any", so :func:`damage_to_player_trigger_kind` bails on
# the event-tag check before it ever reaches the recipient). phase DOES
# keep the clause on that ONE node's own ``description`` field, so this is
# a per-node structural read (never a whole-card scan): CR 510.1b/c.
_UNKNOWN_MODE_COMBAT_DAMAGE_TO_PLAYER = re.compile(
    r"deals combat damage to (?:a player|target player|that player"
    r"|an opponent|each opponent|target opponent|one of your opponents"
    r"|a player or planeswalker|target player or planeswalker)\b",
    re.IGNORECASE,
)


def _unknown_mode_combat_damage_to_player(trig: object) -> bool:
    """Whether trigger DEFINITION ``trig`` is an Unknown-mode node whose OWN
    ``description`` field confirms the "deals combat damage to a player"
    shape phase couldn't classify structurally at all (see module note
    above). Read ONLY when :func:`damage_to_player_trigger_kind` already
    returned ``None`` for this exact node — never overrides a structural
    miss into a wrong kind, matching the existing whole-card mirrors'
    fallback-only contract in this module.
    """
    mode = getattr(trig, "mode", None)
    if not (isinstance(mode, MirrorVariant) and mode.key == "Unknown"):
        return False
    desc = getattr(trig, "description", "") or ""
    return _UNKNOWN_MODE_COMBAT_DAMAGE_TO_PLAYER.search(desc) is not None


# Trigger modes marking a tap/untap payoff (CR 701.26a): phase's ``Taps`` /
# ``TapsForMana`` (both "becomes tapped" family) + ``Untaps`` (Inspired).
_TAP_EVENTS: frozenset[str] = frozenset({"taps", "untaps", "tapsformana"})
# Self-return target tags for the self-blink return half (CR 611.2b): the
# delayed return names the exiled object as ParentTarget / TrackedSet
# (Aetherling) or SelfRef / TriggeringSource (granted-quote forms).
_SELF_BLINK_RETURN_TAGS: frozenset[str] = frozenset(
    {"ParentTarget", "TrackedSet", "SelfRef", "TriggeringSource"}
)

# (suspect_matters was ADR-0036/0037 folded to a bucket-B ``tree_synthesis``
# arm; see ``_arm_suspect_matters``. The suspect verb/state discriminators
# — CR 701.60a/701.60b — now live there. cant_block_grant was T9-finalize
# folded the same way; ``_PACIFY_SIBLING_MODES`` / ``_CANT_BLOCK_THEMEABLE``
# now live in ``tree_synthesis.py`` alongside ``has_structural_cant_block_
# grant``.)

# global_ability_grant QUOTED-grant modification tags (CR 113.3 / 613.1f).
_GRANT_ABILITY_MOD_TAGS: frozenset[str] = frozenset(
    {"GrantAbility", "GrantTrigger", "GrantStaticAbility"}
)
