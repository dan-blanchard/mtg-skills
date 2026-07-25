"""Crosswalk signal lanes — counter makers/matters, counter hate, gain-control,
and the voltron cluster (split from crosswalk_signals.py)."""

from __future__ import annotations

import re

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptTree,
    count_operand_filter,
    count_operand_qty,
    counter_kind,
    counter_kind_any,
    counter_pred_kinds,
    effect_filter,
    effect_owner_player_scope,
    filter_controller,
    filter_predicates,
    filter_subtypes,
    iter_condition_sites,
    iter_cost_leaves,
    iter_mod_sites,
    iter_static_defs,
    iter_typed_nodes,
    mod_keyword_name,
    modify_cost_mode,
    modify_cost_spell_filter,
    recipient_tag,
    ref_count_filter,
    static_mode_field,
    static_mode_tag,
    tag_of,
    trigger_counter_filter,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _ATTACHMENT_PREDS,
    _DYNAMIC_PT_MODS,
    _EDICT_ACTORS,
    _VOLTRON_SUBTYPES,
    _YOU_EACH,
    _condition_leaves,
    _kept,
    _site_raw,
    _target_owner_beneficiary_scope,
    _voltron_collective_preds,
)
from mtg_utils._deck_forge.signal_base import Signal


def _any_counter_makers(tree: ConceptTree) -> list[Signal]:
    """any_counter_makers — a kind-AGNOSTIC counter DOER (CR 122.1 / 701.34a).
    Mirrors the deleted ``_signals_ir``'s lines ~8548/8566: a ``proliferate`` (adds one
    counter of
    EACH kind already there), a counter MOVE (relocates counters — Bioshift, The
    Ozolith), OR a ``remove_counter`` with NO specified kind (Aether Snap, Hex
    Parasite). A KIND-SPECIFIC remove (fade/time/oil — a card spending its own niche
    counter) is excluded. Scope "you".
    """
    for c in tree.effect_concepts("proliferate"):
        return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("move_counters"):
        return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    # np_counters item 3: the dropped-clause counter-move marker
    # (``tree_synthesis._arm_dropped_counter_move`` — Ambitious Augmenter,
    # Heroic Sacrifice) joins exactly like its typed ``MoveCounters``
    # classmates (The Ozolith, Iron Apprentice) do via the arm above.
    for c in tree.iter_concepts():
        if c.concept == "synth_counter_move":
            return [Signal("any_counter_makers", "you", "", "", tree.name, "high")]
    for c in tree.effect_concepts("remove_counter"):
        if not counter_kind(c.node):
            return [Signal("any_counter_makers", "you", "", c.raw, tree.name, "high")]
    return []


_MINUS_COUNTER_KEPT_RX = re.compile(r"-1/-1 counter", re.IGNORECASE)


def _minus_counters_matter(tree: ConceptTree) -> list[Signal]:
    """minus_counters_matter — a -1/-1 counter PLACEMENT maker (CR 122.1 / 122.6 /
    702.80 wither) PLUS the legacy's "-1/-1 counter" kept-mirror for the
    remove/cost/ward/replacement payoffs phase leaves textual (the same
    two-arm identity the deleted ``_signals_ir``'s ``_COUNTER_KIND_KEYS['m1m1']`` +
    ``_IR_KEPT_DETECTORS`` mirror carries — ADR-0027/ADR-0038 batch 4).

    Three structural arms, each a genuine "you place/receive a -1/-1
    counter" tell, before the text fallback:

    * a ``PutCounter``/``PutCounterAll`` whose ``counter_type`` is ``M1M1``
      (Hapatra, Blight Mamba) — checked first via ``effect_concepts`` (the
      unit's own payoff chain), then via a full node walk so a
      COST-embedded placement (Devoted Druid's "Put a -1/-1 counter on
      this creature: Untap this creature" — the ``PutCounter`` lives in the
      ability's own ``EffectCost``, invisible to ``effect_concepts`` which
      reads only the payoff chain) still fires. CR 601.2b (effect costs).
    * a ``ChangeZone`` with an ``M1M1`` entry in ``enter_with_counters`` —
      the Persist family's "return it to the battlefield ... with a -1/-1
      counter on it" (Kitchen Finks, Rendclaw Trow). The legacy project.py
      adapter modeled this as a discrete ``PutCounter`` Effect; v0.20.0's
      mirror instead carries it as a field on the re-entry ``ChangeZone`` —
      a substrate SHAPE change, not a lane gap. Persist's OWN reminder text
      is ENTIRELY parenthetical (the keyword's full explanation), so the
      kept-mirror below can't reach it (reminder-stripped) — this
      structural read is the only path to these cards. CR 122.6 / 702.79a.

    The kept-mirror text fallback (the deleted regex's exact "-1/-1
    counter" substring, over the reminder-stripped face oracle) recovers
    the CARES-ABOUT residue phase leaves scattered and unstructured: a
    counter-quantity REPLACEMENT (Vizier of Remedies' "-1/-1 counters minus
    one are put on it instead" — CR 122.1/614), a damage-as-counters
    REPLACEMENT (Soul-Scar Mage, CR 702.80 wither's non-keyword cousin), a
    ``counter_added`` PAYOFF trigger (Nest of Scarabs), a filter PREDICATE
    querying for the counter (Necroskitter's "-1/-1 counter on it" valid_card
    filter), a REMOVAL ability (Hapatra's Mark, Woeleecher), and a static
    restriction (Melira, Sylvok Outcast's "can't have -1/-1 counters put on
    them"). Since it's a substring match, cards where the ONLY occurrence is
    inside Persist/Wither's OWN reminder parens never reach it (correctly —
    those fire via the structural arms above instead, so there's no
    double-count concern). Scope "you" (the legacy's hard-forced scope for
    every arm, regardless of who the counter lands on).
    """
    for c in tree.effect_concepts("place_counter"):
        if counter_kind(c.node).upper() == "M1M1":
            return [
                Signal("minus_counters_matter", "you", "", c.raw, tree.name, "high")
            ]
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            t = tag_of(node)
            if t in ("PutCounter", "PutCounterAll"):
                if counter_kind(node).upper() == "M1M1":
                    return [
                        Signal(
                            "minus_counters_matter", "you", "", "", tree.name, "high"
                        )
                    ]
            elif t == "ChangeZone":
                ewc = getattr(node, "enter_with_counters", None)
                if isinstance(ewc, list):
                    for pair in ewc:
                        if (
                            isinstance(pair, (list, tuple))
                            and pair
                            and str(pair[0]).upper() == "M1M1"
                        ):
                            return [
                                Signal(
                                    "minus_counters_matter",
                                    "you",
                                    "",
                                    "",
                                    tree.name,
                                    "high",
                                )
                            ]
    if _MINUS_COUNTER_KEPT_RX.search(_kept(tree)):
        return [Signal("minus_counters_matter", "you", "", "", tree.name, "high")]
    return []


# ── ADR-0039 W8 KEPT-key promotions ────────────────────────────────────────
# Three byte-identical text mirrors of a deleted floor/SWEEP producer, each
# already proven (in the legacy IR docstrings) to reproduce the whole live
# firing set exactly (both == N, regex_only == 0, ir_only == 0) because
# phase v0.20 structures NO field that discriminates the idiom from its
# neighbors — same tier as ``_MINUS_COUNTER_KEPT_RX`` / ``_COST_*_KEPT_RX``
# above: a plain ``re.compile(...).search(_kept(tree))`` over the reminder-
# stripped face oracle, no clause_grammar / tree_synthesis involvement.

# excess_damage — CR 702.19 / 120.4a: "excess damage" is defined-terminology
# (damage dealt beyond lethal to a creature, or beyond loyalty to a
# planeswalker) that only 4 clean "is dealt excess damage" triggers bind
# structurally (a Trigger event=='excess_damage'; NOT re-derived here —
# those 4 already carry a payoff shape phase gives no OTHER field for). The
# other 24 references (a trample/fight "if excess damage was dealt" ETB
# CONDITION on a non-`excess_damage`-event trigger, or a spell's own
# "excess damage is dealt to ... instead" consequence — Flame Spill, Pigment
# Storm, Ram Through, Orbital Plunge, Goblin Negotiation, Aegar the Freezing
# Flame) live in Effect.raw with no structured "excess" tag anywhere on the
# tree, so the literal defined-term phrase is the only tell (the legacy
# _IR_KEPT_DETECTORS row is a flat `\bexcess damage\b`). Re-measured
# (ADR-0039 W8, commander-legal, dedupe oracle_id): both == 28, regex_only
# == 0, ir_only == 0 — byte-identical, all 28 genuine CR 120.4a excess-
# damage payoffs/conditions. Scope "you" matches the deleted producer's
# forced scope.
_EXCESS_DAMAGE_KEPT_RX = re.compile(r"\bexcess damage\b", re.IGNORECASE)


def _excess_damage(tree: ConceptTree) -> list[Signal]:
    """excess_damage — the "excess damage" build-around (CR 702.19 / 120.4a:
    damage beyond lethal/loyalty). Byte-identical KEPT-MIRROR of the deleted
    ``_IR_KEPT_DETECTORS`` row: no structural field survives the residual
    24/28 references (only the 4 clean ``event=='excess_damage'`` triggers
    would be structural, and even those carry no OTHER discriminating
    field this lane would gain by reading them separately). Scope "you".
    """
    if _EXCESS_DAMAGE_KEPT_RX.search(_kept(tree)):
        return [Signal("excess_damage", "you", "", "", tree.name, "high")]
    return []


# kicked_spell_matters — CR 702.33 (Kicker): the "whenever you cast a kicked
# spell" PAYOFF (Verazol, Hallar, Rumbling Aftershocks, Roost of Drakes) PLUS
# the "if (that|it) (spell) was kicked" CONDITION on a kicker spell's own ETB
# (Goblin Bushwhacker, Gatekeeper of Malakir, the Battlemage/Emissary
# cycles). NOT the bare Kicker keyword route (that's a different lane,
# +171 over-fire vs this one — every kicker card HAS kicker, only these 85
# CARE that a spell WAS paid-kicked). phase v0.20 carries neither the
# "whenever you cast a kicked spell" trigger's "kicked" qualifier nor the
# "if it was kicked" ETB condition as a structured field (CR 702.33f names
# the exact "if it was kicked" phrasing as reminder-text-only), so the
# byte-identical deleted ``_HAND_FLOOR`` regex is the only tell.
_KICKED_SPELL_KEPT_RX = re.compile(
    r"whenever you cast a kicked spell|if (?:that|it) (?:spell )?was kicked",
    re.IGNORECASE,
)


def _kicked_spell_matters(tree: ConceptTree) -> list[Signal]:
    """kicked_spell_matters — the Kicker (CR 702.33) build-around: casting a
    kicked spell as a PAYOFF trigger, or an ETB CONDITION keyed to a spell's
    own kicked state. Byte-identical KEPT-MIRROR of the deleted
    ``_HAND_FLOOR`` regex — phase structures neither shape's "kicked"
    qualifier. Re-measured (ADR-0039 W8, commander-legal, dedupe
    oracle_id): both == 85, regex_only == 0, ir_only == 0 — byte-identical,
    all 85 genuine (verified against actual Scryfall oracle text). Scope
    "you".
    """
    if _KICKED_SPELL_KEPT_RX.search(_kept(tree)):
        return [Signal("kicked_spell_matters", "you", "", "", tree.name, "high")]
    return []


# free_cast — CR 601.2b / 118.9 (alternative costs): casting a spell WITHOUT
# paying its mana cost (Beseech the Mirror, Baral's Expertise, As Foretold,
# Jodah/Nicol Bolas's "cast without paying its mana cost", Villainous
# Wealth). phase structures ``cast_from_zone``/``alt_cost`` but carries no
# 'free' discriminator distinguishing a genuine free-cast from a flash-
# grant/Bargain/Prototype alt-cost, so the deleted SWEEP regex (pinned
# ``FREE_CAST_REGEX`` in ``_sweep_detectors.py``) is the only tell — copied
# byte-identically here (NOT imported, matching the existing
# ``_MINUS_COUNTER_KEPT_RX`` / ``_COST_*_KEPT_RX`` inline-copy precedent in
# this module). The "without paying its mana cost" / "rather than pay ...
# mana cost" phrasing is specific + clause-local (no `[^.]` crossing a
# sentence), so a flat scan == the deleted per-clause SWEEP firing set.
_FREE_CAST_KEPT_RX = re.compile(
    r"rather than pay (?:its|their|the) mana cost"
    r"|without paying (?:its|their) mana cost"
    r"|may cast (?:it|that (?:card|spell)|those cards)[^.]*without paying",
    re.IGNORECASE,
)


def _free_cast(tree: ConceptTree) -> list[Signal]:
    """free_cast — casting a spell WITHOUT paying its mana cost (CR 601.2b /
    118.9). Byte-identical KEPT-MIRROR of the deleted SWEEP regex
    (``FREE_CAST_REGEX``): phase's ``cast_from_zone``/``alt_cost`` fields
    carry no 'free' discriminator, so the oracle phrase is the only tell.
    Re-measured (ADR-0039 W8, commander-legal, dedupe oracle_id): both ==
    328, regex_only == 0, ir_only == 0 — byte-identical (the per-face union
    over ``trees_for`` reproduces the legacy joined-oracle DFC recall
    without any extra DFC-specific logic). Scope "you"; task #91 — "any"
    when the free cast is the OWNER of an earlier-targeted permanent
    (:func:`_target_owner_beneficiary_scope` — Audacious Swap's "The owner
    of target nonenchantment permanent shuffles it into their library, then
    exiles the top card...Otherwise, they may cast it without paying its
    mana cost": every "they" in the sentence chains back to "the owner",
    never the caster, CR 108.3/601.2b). Gated narrowly on a same-unit
    ``CastFromZone`` beside a ``ParentTargetOwner`` recipient — the ONLY
    commander-legal free_cast card carrying that pairing (corpus-verified,
    2026-07); every other free_cast hit keeps its plain "you" (the caster's
    OWN free cast — Beseech the Mirror, As Foretold, Jodah).
    """
    if not _FREE_CAST_KEPT_RX.search(_kept(tree)):
        return []
    scope = "you"
    for unit in tree.units:
        # Audacious Swap's ``CastFromZone`` lives on an ``else_ability``
        # branch (the "Otherwise, they may cast it" fork off the land-put
        # arm), never on the linear ``sub_ability`` chain ``unit.effects``
        # walks — a deep node scan is needed to reach it.
        has_cast_from_zone = any(
            tag_of(n) == "CastFromZone" for n in iter_typed_nodes(unit.node)
        )
        has_owner_recipient = any(
            recipient_tag(c.node) == "ParentTargetOwner" for c in unit.effects
        )
        if has_cast_from_zone and has_owner_recipient:
            override = _target_owner_beneficiary_scope(unit)
            if override is not None:
                scope = override
            break
    return [Signal("free_cast", scope, "", "", tree.name, "high")]


# ADR-0038 W5 tails — the narrow gap-marker text fallback inside
# ``_plus_one_matters``: a P1P1 self-condition phase decorates as a typed
# marker with NO captured payload (``Not(Unrecognized(text=…))`` — Pipsqueak,
# Rebel Strongarm; an empty ``RequiresCondition`` — Skarrgan Hellkite). Read
# ONLY off the same unit's own description/text field, never the whole-card
# raw; a full commander-legal corpus census found exactly these 2 cards (3
# printings), zero false positives.
_P1P1_COND_TEXT_RX = re.compile(r"\+1/\+1 counter", re.IGNORECASE)

# np_boons task #4 (Rite of the Serpent): the PAST-TENSE "had a/one or more
# +1/+1 counter(s) on it" idiom (CR 122.1/603.6d — an object's last known
# information) gating a reward, read off the unit's own description when
# BOTH the typed condition AND the sub_ability's own condition are dropped
# (see the sibling arm's docstring inside ``_plus_one_matters``). np_counters
# widened the quantifier with "two or more" (Ochre Jelly's threshold form) —
# the removal+Token arm gains no member from it (corpus-verified), only the
# counter-scaled-reward sibling arm does.
_HAD_P1P1_COND_RX = re.compile(
    r"\bhad (?:a|one or more|two or more) \+1/\+1 counters? on it\b",
    re.IGNORECASE,
)
# Removal-shaped tags this arm pairs a dropped-condition Token reward
# against — a destroy/damage/exile effect on a TARGETED creature (CR 701.6
# / 701.3 / 701.20), the same population Rite of the Serpent's own
# "Destroy target creature. If that creature had ..." shape belongs to.
_HAD_P1P1_REMOVAL_TAGS: frozenset[str] = frozenset(
    {"Destroy", "DestroyAll", "DealDamage", "Exile"}
)


def _plus_one_matters(tree: ConceptTree) -> list[Signal]:
    """plus_one_matters — a +1/+1 counter PAYOFF (CR 122.1). The structural arms
    (the deleted ``_signals_ir``'s ~8556 / ~8278): a ``move_counters`` whose kind is
    ``P1P1`` (a
    p1p1 move relocates the engine — Bioshift), OR a subject / count-operand filter
    carrying a ``Counters`` predicate of kind ``P1P1`` ("creatures you control with a
    +1/+1 counter", "for each creature with a +1/+1 counter on it" — Inspiring Call).

    recall-completion b1 (ADR-0034) adds two arms:

    * the ``counter_added`` trigger whose ``counter_filter`` kind IS ``P1P1``
      (Fractal Harness, Hardened-Scales-style +1/+1-specific placement triggers) —
      a p1p1-SPECIFIC placement trigger is a genuine +1/+1 payoff, CO-FIRED alongside
      the kind-agnostic sibling ``counter_place_trigger`` (a kind-AGNOSTIC "whenever
      one or more counters are put" trigger correctly stays there, NOT here).
    * a ``CountersOn`` count-operand of kind ``P1P1`` ("~ for each +1/+1 counter on
      it" — Mycoloth) — the deleted ``_signals_ir``'s ``e.amount.op == "counters"``
      (IR:7666).

    ADR-0038 W4 giant batch adds the ``any_counter_matters`` sibling's whole-unit
    descents, gated to ``P1P1`` instead of ``Any`` (:func:`_any_counter_matters`'s
    own docstring — CR 122.1):

    * a mass STATIC grant/restriction whose OWN ``affected`` names a P1P1-bearing
      filter directly (Outlast's tribal anthem idiom — "Each creature you control
      with a +1/+1 counter on it has flying," Abzan Falconer / Ainok Bond-Kin /
      Tuskguard Captain), read off the whole static UNIT wrapper, never a
      per-modification concept.
    * a counter-HAVE TRIGGER — "whenever a creature you control with a +1/+1
      counter on it dies/attacks" (Marchesa the Black Rose, Cleopatra Exiled
      Pharaoh, Gladehart Cavalry, Meltstrider Eulogist) — the predicate rides the
      TRIGGER's own watched-object filter (``valid_card``), never an effect/static
      filter.
    * a nested static-def descent (:func:`iter_static_defs`) for a one-shot
      conferred grant buried inside a wrapping effect ("Each creature you control
      with a +1/+1 counter on it gains hexproof" riding a ``GenericEffect``).
    * a ``HasCounters`` whole-unit static CONDITION of kind P1P1 — the
      self-referencing "~ has flying as long as it has a +1/+1 counter on it"
      idiom (Lightwalker, Baloth Pup, Sigiled Contender, Ainok Artillerist):
      the condition rides ``SelfRef``, never a subject/count-operand filter, so
      none of the filter-reading arms above can reach it. CR 604.2 (a static
      ability's continuous effect applies only while its condition holds).
    * a ``RemoveCounter`` activation COST of kind P1P1 (mirrors
      ``_counter_manipulation``'s ``iter_cost_leaves`` walk) — "Remove a +1/+1
      counter from ~: …" (Triskelion, Walking Ballista, Crystalline Crawler) is a
      +1/+1 counter sink/outlet, the SAME shape the deleted ``_signals_ir``'s
      Shape 5 (~10597) reads off the cost. CR 118.7.

    :func:`trigger_counter_filter` (``_card_ir/crosswalk.py``) is widened
    alongside this batch: a THRESHOLD-less ``counter_filter`` (no Saga chapter
    number — a bare "whenever a +1/+1 counter is put on ~" trigger, Fathom Mage
    / Enduring Scalelord / Knighted Myr) loads the mirror runtime's untagged
    single-field collapse (``MirrorVariant``) instead of the full struct; both
    encodings are now read so the existing ``counter_added`` arm above actually
    reaches the P1P1-specific placement-trigger family.

    NOT ported — two DISTINCT legacy over-fire mechanisms, both corpus-verified,
    neither a genuine +1/+1-specific cares-about read (CR 122.1 defines a
    counter as KIND-carrying; a kind-agnostic reference belongs to
    ``any_counter_matters``, not here — the "Boundary" split this key
    deliberately preserves):

    * a ``counter_added`` TRIGGER whose kind is anything OTHER than P1P1
      (lore/Saga chapters, plan/Case, hour, or a bare M1M1/kindless "whenever a
      counter is put on ~" trigger — Nest of Scarabs, Hapatra). Legacy's OWN
      ``_PAYOFF_TRIGGER_KEYS["counter_added"]`` row (the deleted ``_signals_ir``'s
      ~10852)
      fires plus_one_matters UNCONDITIONALLY on every ``counter_added`` trigger
      event with NO kind gate at all (unlike the sibling
      ``counter_place_trigger`` row two lines below it, which DOES exclude
      Sagas) — a Saga's lore-counter chapter ability has nothing to do with
      +1/+1 counters; Nest of Scarabs / Hapatra fire off a -1/-1-counter
      trigger. Deliberately NOT reproduced.
    * a kind-AGNOSTIC "with/has a counter on it" reference whose OWN structural
      predicate kind is explicitly ``Any`` (The Swarmlord, Cleopatra Exiled
      Pharaoh, Puca's Covenant, Metropolis Angel — CR 122.1's kind carries the
      distinction). Legacy's per-ABILITY ``project._narrow_counter_refs``
      regex (``_P1P1_HAVE_REF``, distinct from the face-level
      ``_P1P1_HAVE_FACE`` this lane does NOT import) carries a kind-agnostic
      final alternative (``\\bwith (?:a )?counters? on (?:it|them|him|her)\\b``)
      despite the function's "+1/+1-counter ref recovery" framing — it fires
      on ANY ability with no structured placement of its own, regardless of
      the referenced kind, double-tagging cards the esub arm already correctly
      routes to any_counter_matters via the SAME ``Any``-kind predicate.
      Deliberately NOT reproduced.

    ADR-0038 W5 tails batch adds four more arms, each closing a genuinely
    distinct residual class the previous batch banked (2026-07 re-measure:
    live_only 307 pre-batch, 300 post-batch — 7 cards recovered, corpus-
    verified genuine — of which 225 are the counter_added-kind-other
    Saga/Plan class above, 26 are a THIRD adjudicated shed class — legacy's
    maker/matters CONFLATION: a pure ``PutCounter`` P1P1 placement with NO
    cares-about text of its own (Scholar of New Horizons's "enters with a
    +1/+1 counter" + a kind-agnostic removal outlet, The Duke Rebel
    Sentry's "enters with … / Remove a counter … Put a +1/+1 counter on
    another target") — already correctly routed to the sibling
    ``plus_one_makers`` lane instead (CR 122.1: making counters is not
    caring about them); mirrors the ``any_counter_matters``/
    ``any_counter_makers`` split ADR-0038 W4 already established. The
    remainder decomposes as documented below):

    * **self-ref CONDITION, any unit** — the ``HasCounters`` self-ref arm
      above was gated to ``unit.origin == "static"`` only; a P1P1-specific
      "if it has a +1/+1 counter on it" condition also rides a TRIGGER's own
      ``.condition`` (Sarulf Realm Eater's upkeep sac-outlet, Ingenious
      Prodigy's upkeep draw-outlet — CR 603.4's intervening-``if``) or an
      ``IsPresent``-tagged static condition instead of ``HasCounters``
      (Prehistoric Turtlesaurus's "costs {1} less to cast if you control a
      creature with a +1/+1 counter on it" — CR 604.2 / 601.2f). Both read
      through the shared :func:`iter_condition_sites` / ``_condition_leaves``
      descent (the same site-and-leaf walk ``_artifacts_enchantments_matter``
      already uses), so a unit's ``condition`` field AND its
      ``activation_restrictions`` entries are both covered, any origin.
    * **gap-marker text fallback, narrowly scoped** — two cards' P1P1
      self-condition never reaches phase's typed grammar at all: Pipsqueak,
      Rebel Strongarm's "can't attack alone unless he has a +1/+1 counter on
      him" decorates as ``Not(Unrecognized(text=…))`` (a raw parse residue,
      not a real condition node), and Skarrgan Hellkite's "Activate only if
      ~ has a +1/+1 counter on it" decorates as an EMPTY
      ``RequiresCondition`` (``data.inner is None`` — CR 602.5, the marker
      names a restriction phase couldn't structure). Both are read via a
      TEXT fallback narrowly scoped to the SAME unit's own
      ``description``/``Unrecognized.text`` field (never the whole-card
      raw) — a corpus census over every commander-legal card found exactly
      these 2 (3 printings), zero false positives.
    * **``CounterAddedThisTurn`` qty, sibling of ``CountersOn``** — "create a
      token for each +1/+1 counter you've put on creatures under your
      control this turn" (Iridescent Hornbeetle) is a DIFFERENT qty node
      (a THIS-TURN placement tally, not a live board-state count) whose kind
      rides a nested ``counters.data`` field rather than ``CountersOn``'s
      bare ``counter_type`` string; widened to accept either tag/field
      shape, both gated to P1P1.
    * **``ModifyCost``/``spell_filter``/``Targets``/``Counters`` descent** —
      Titanic Brawl's "costs {1} less to cast if it TARGETS a creature you
      control with a +1/+1 counter on it" nests the P1P1 predicate inside
      the spell_filter's OWN ``Targets`` property (:func:`
      modify_cost_spell_filter`), a shape distinct from Prehistoric
      Turtlesaurus's top-level ``condition`` (that card cares about a
      creature you control ANYWHERE; Titanic Brawl cares specifically about
      the spell's OWN target) — CR 601.2f.

    ADR-0038 W6 endgame batch adds two more arms and completes the shed-class
    adjudication (2026-07 re-measure: live_only 300 pre-batch, 296
    post-batch — 4 cards recovered, corpus-verified genuine):

    * **``QuantityCheck`` self-count condition** — a P1P1 THRESHOLD condition
      ("if it has a +1/+1 counter on it") sometimes rides ``QuantityCheck``
      (``lhs`` a ``Ref`` wrapping a ``CountersOn`` qty) rather than
      ``HasCounters``/``IsPresent`` — Incubation Druid's activated-ability
      sub_ability condition, Dual-Sun Technique / Oblivion's Hunger's spell
      sub_ability condition. Sometimes wrapped in a ``ConditionInstead`` (CR
      601.2f "instead" variant — Incubation Druid), unwrapped LOCALLY (not
      via the shared ``_condition_leaves`` helper — the corpus's 101
      ConditionInstead-wrapping-QuantityCheck instances span many unrelated
      conditions, a shared-helper widening would need its own full-corpus
      check). 11 commander-legal cards carry a P1P1-gated QuantityCheck
      condition corpus-wide (5 Theros Ordeals + Ayara's Oathsworn already
      fire via another arm on the same tree); non-P1P1 kinds (depletion/
      lore/quest/soul/time/landmark/omen/point) correctly gate out via the
      ``counter_type`` check. CR 122.1.
    * **``TargetHasKeywordInstead`` gap-marker text fallback** — Bring Low's
      "if that creature has a +1/+1 counter on it, ~ deals 5 damage instead"
      (CR 601.2f) decorates as ``TargetHasKeywordInstead`` whose ``keyword``
      field is an ``Unknown``-tagged raw-text residue rather than a real
      keyword. Narrowly scoped to the ``Unknown`` variant matching
      ``_P1P1_COND_TEXT_RX`` — the corpus's 14 TargetHasKeywordInstead
      instances split 3 P1P1-text / 3 named-keyword (Flying/Infect/Toxic,
      correctly excluded) / 8 unrelated power-toughness-comparison text.

    ADR-0039 W8 (2026-07-12) closes all 6 of the W6 endgame's genuinely-
    unclosed tail: 2 stay LEDGERED BRIDGES (Rock Hydra, Hierophant
    Bio-Titan — see the bridge block at the end of this function), 3
    graduated to structural/recovered-node arms this sprint (task #82:
    Rumbling Ruin / Deepwood Denizen via ``recovered_by``-gated arms,
    Tetravus via a fully-typed RemoveCounter/Token pairing arm — all
    three inline above, no bridge lookup), and the 6th (Winged Hive
    Tyrant) is re-adjudicated as a NEW member of the kind-mismatch shed
    class below — its static parser ALSO fails the whole line, but the
    residue text is "creatures ... with counters on them" (no "+1/+1"
    anywhere on the card), the SAME kind-agnostic ``_P1P1_HAVE_REF``
    regex branch already adjudicated as an over-fire (The Swarmlord /
    Yathan Tombguard) — a corpus-scoped bridge correctly does NOT fire
    on it. No sibling lane fires either (any_counter_matters hits the
    SAME structural gap — the whole line is an unreadable residue, not
    a kind-specific one — out of scope for a bridge this narrowly
    P1P1-scoped; a correct shed, not a mis-routed member). **Key
    PROMOTED** (removed from ``_STAGE4_RESIDUAL``): live_only now
    decomposes EXACTLY into adjudicated, CR-grounded, negative-pinned
    shed classes plus the 2 bridge-served + 3 structurally-served
    singletons — no unclosed tail remains.

    * **~246 cards — counter_added TRIGGER, kind other than P1P1** (Saga/Plan/
      hour/M1M1/kindless placement triggers, CR 122.1 vs CR 714.2b) — the
      original bullet-1 class above.
    * **~41 cards — a counter-kind reference whose kind is anything other
      than P1P1** (CR 122.1): a kind-agnostic (``Any``) OR named-non-P1P1
      HAVE reference on ANY of the structurally distinct sites legacy's
      whole-card-text ``_P1P1_HAVE_REF`` regex is blind to which field
      carries it — a trigger's ``valid_card`` (The Swarmlord), a
      ``deals_damage``/``attacks`` trigger's ``valid_source`` (Yathan
      Tombguard), a replacement's ``damage_source_filter`` (Raphael, the
      Muscle), a static's ``ControlsType`` condition (Delta Bloodflies), a
      kind-agnostic/named-non-P1P1 ``RemoveCounter`` activation COST whose
      card ALSO happens to mention "+1/+1 counter" elsewhere (Scholar of
      New Horizons, The Duke Rebel Sentry — legacy's Shape-5 cost arm is
      gated on the WHOLE CARD's oracle text, not the specific ability, so a
      kind-agnostic sink co-occurring with an unrelated P1P1 placement
      over-fires), OR a ``static_structure`` parse-failure residue whose
      OWN text is kind-agnostic (Winged Hive Tyrant, ADR-0039 W8 — the same
      branch, just phase-unstructured rather than typed). Generalizes (and
      supersedes) the original bullet-2 class and the "26-card maker/
      matters conflation" class documented in the W5 tails batch — all are
      instances of the SAME kind-mismatch principle.
    * **3 cards — CDA "power greater than its base power" text idiom, no
      counter node at all** (Baird, Kutzil, Ms. Marvel): CR 208.4b — "power
      greater than base power" is a layer-applied CURRENT-vs-BASE
      comparison true for ANY power-increasing effect (temporary pump,
      static anthem, Evolve), not specific to +1/+1 counters; the state
      carries no counter KIND (CR 122.1), so legacy's regex heuristic is a
      genuine over-fire, not a counter reference.
    * **1 card — EQ-0 "no counters" predicate** (Hindervines): the inverse of
      a counter-caring payoff; :func:`counter_pred_kinds` deliberately
      excludes it corpus-wide (shared by every counter lane).
    * **2 cards — served by ledgered bridges, ADR-0039 W8**: Rock Hydra
      (``upstream_parse_failure`` — the WHOLE damage-prevention-replacement
      line fails phase's static parser); Hierophant Bio-Titan
      (``dropped_clause`` — a ``ModifyCost.dynamic_count=
      PreviousEffectAmount`` scaler carries NO counter-kind field in
      phase's own encoding).
    * **3 cards — served structurally, grammar sprint task #82**: Rumbling
      Ruin / Deepwood Denizen — ``clause_grammar``'s ``count_operand`` /
      ``counter_cost_reduction`` verbs + ``recovery.ALLOWLIST`` re-decorate
      the Unimplemented residue, read here via a ``recovered_by``-gated
      arm (kind-checked on the raw, same precedent as "draw"/"discard"/
      "damage"); Tetravus — a fully-typed P1P1 ``RemoveCounter`` EFFECT
      paired with a Token count Ref'd to the same removed amount, a
      counter-to-token CONVERSION idiom read via a dedicated pairing arm
      (narrowly scoped: a corpus check found 39 commander-legal cards
      carry a P1P1 RemoveCounter EFFECT node outside any activation cost,
      but 38 of them pair with no scaled Token effect and correctly stay
      unserved).

    The raw-``"+1/+1 counter"`` idiom arms stay ``live_only`` raw-fold mirrors. Scope
    "you".
    """
    for unit in tree.units:
        if (
            unit.origin == "trigger"
            and unit.trigger_event == "counter_added"
            and trigger_counter_filter(unit.node)[0].upper() == "P1P1"
        ):
            return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
        if unit.origin == "static":
            filt = effect_filter(unit.node)
            if (
                filt is not None
                and filter_controller(filt) != "Opponent"
                and "P1P1" in counter_pred_kinds(filt)
            ):
                return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
        if unit.origin == "trigger":
            # task #85 (plus-one-counters preset conversion): a
            # ``deals_damage``/``attacks``-mode trigger's watched-object
            # filter rides ``valid_source`` (the creature DOING the
            # attacking/damage), never ``valid_card`` — "whenever a
            # creature you control with a +1/+1 counter on it deals
            # combat damage to a player" (Bred for the Hunt). The prior
            # code only read ``valid_card``, so this whole trigger SHAPE
            # (any mode keyed off the source, not a watched card) fell
            # through despite the module docstring already citing it.
            # CR 122.1 (a counter carries a kind) / 603.2 (triggered
            # ability watches an event, here the source's identity).
            for site in (
                getattr(unit.node, "valid_card", None),
                getattr(unit.node, "valid_source", None),
            ):
                if (
                    site is not None
                    and filter_controller(site) != "Opponent"
                    and "P1P1" in counter_pred_kinds(site)
                ):
                    return [
                        Signal("plus_one_matters", "you", "", "", tree.name, "high")
                    ]
        # ADR-0038 W5 tails — self-ref CONDITION, any unit origin (Sarulf
        # Realm Eater / Ingenious Prodigy's trigger-own HasCounters, CR
        # 603.4; Prehistoric Turtlesaurus's static IsPresent, CR 604.2 /
        # 601.2f), plus the two gap-marker text fallbacks (Pipsqueak's
        # Not(Unrecognized), Skarrgan Hellkite's empty RequiresCondition,
        # CR 602.5), each scoped to the SAME unit's own site/description.
        for site in iter_condition_sites(unit.node):
            for cond in _condition_leaves(site):
                ctag = tag_of(cond)
                if ctag == "HasCounters":
                    counters = getattr(cond, "counters", None)
                    kind = str(getattr(counters, "data", "") or "").upper()
                    if kind == "P1P1":
                        return [
                            Signal("plus_one_matters", "you", "", "", tree.name, "high")
                        ]
                elif ctag == "HadCounters":
                    # task #85 (v0.23 bump addition): the PAST-TENSE
                    # sibling of ``HasCounters`` — a died/left-battlefield
                    # trigger's "if it had a +1/+1 counter on it" check
                    # (Promising Duskmage). Reads ``counter_type`` DIRECTLY
                    # (no nested ``counters`` wrapper — a flatter shape
                    # than ``HasCounters``, since the object no longer
                    # exists to carry a live predicate). CR 122.1 / 603.6d
                    # (leaves-the-battlefield triggers see the object's
                    # last known information).
                    kind = str(getattr(cond, "counter_type", "") or "").upper()
                    if kind == "P1P1":
                        return [
                            Signal("plus_one_matters", "you", "", "", tree.name, "high")
                        ]
                elif ctag in ("IsPresent", "ControlsType"):
                    # task #85: ``ControlsType`` is the SAME "as long as
                    # you control an X" filter-condition shape as
                    # ``IsPresent`` (mirrors the artifacts_matter/
                    # enchantments_matter CONDITION-gate precedent a few
                    # hundred lines up in this file) — "if you control a
                    # creature with a +1/+1 counter on it" (Foundry
                    # Hornet's ETB gate) rides ``ControlsType``, which
                    # this arm previously didn't check. CR 603.2.
                    filt = getattr(cond, "filter", None)
                    if (
                        filt is not None
                        and filter_controller(filt) != "Opponent"
                        and "P1P1" in counter_pred_kinds(filt)
                    ):
                        return [
                            Signal("plus_one_matters", "you", "", "", tree.name, "high")
                        ]
                elif ctag == "Unrecognized":
                    text = str(getattr(cond, "text", "") or "")
                    if _P1P1_COND_TEXT_RX.search(text):
                        return [
                            Signal("plus_one_matters", "you", "", "", tree.name, "high")
                        ]
                elif ctag == "RequiresCondition":
                    data = getattr(cond, "data", None)
                    inner = data.inner if isinstance(data, MirrorVariant) else data
                    if inner is None:
                        desc = str(getattr(unit.node, "description", "") or "")
                        if _P1P1_COND_TEXT_RX.search(desc):
                            return [
                                Signal(
                                    "plus_one_matters",
                                    "you",
                                    "",
                                    "",
                                    tree.name,
                                    "high",
                                )
                            ]
                    else:
                        # phase v0.35.2 structures the former gap marker:
                        # RequiresCondition.data carries a real condition
                        # ("Activate only if ~ has a +1/+1 counter on it" —
                        # Skarrgan Hellkite's QuantityComparison over a
                        # CountersOn(Source, P1P1) Ref). CR 602.5.
                        inner_cond = getattr(inner, "condition", None) or inner
                        if tag_of(inner_cond) in (
                            "QuantityCheck",
                            "QuantityComparison",
                        ):
                            for side in (
                                getattr(inner_cond, "lhs", None),
                                getattr(inner_cond, "rhs", None),
                            ):
                                if tag_of(side) != "Ref":
                                    continue
                                qty = getattr(side, "qty", None)
                                if tag_of(qty) == "CountersOn" and (
                                    str(getattr(qty, "counter_type", "") or "").upper()
                                    == "P1P1"
                                ):
                                    return [
                                        Signal(
                                            "plus_one_matters",
                                            "you",
                                            "",
                                            "",
                                            tree.name,
                                            "high",
                                        )
                                    ]
                elif ctag in (
                    "QuantityCheck",
                    "QuantityComparison",
                    "ConditionInstead",
                ):
                    # ADR-0038 W6 endgame — a P1P1 self-count THRESHOLD
                    # condition rides ``QuantityCheck`` (Incubation Druid's
                    # activated-ability sub_ability condition, Oblivion's
                    # Hunger / Dual-Sun Technique's spell sub_ability
                    # condition — "If it has a +1/+1 counter on it, …"),
                    # sometimes wrapped in a ``ConditionInstead`` ("instead"
                    # variant, CR 601.2f) that the existing HasCounters/
                    # IsPresent leaves never reach. Corpus-verified: the
                    # ``CountersOn`` qty gate is a DIFFERENT node shape from
                    # the pump-scaling qty operand this key already reads
                    # (``count_operand_qty``) — this one lives under a
                    # condition's ``lhs``/``rhs`` Ref, not an effect's count.
                    # 11 commander-legal cards carry a P1P1-gated
                    # QuantityCheck condition (5 Theros Ordeals, Ayara's
                    # Oathsworn, Incubation Druid, Dual-Sun Technique,
                    # Oblivion's Hunger — the rest already fire via another
                    # arm on the same tree); non-P1P1 kinds (depletion/lore/
                    # quest/soul/time/landmark/omen/point) correctly gate
                    # out. CR 122.1.
                    qc = cond
                    if ctag == "ConditionInstead":
                        qc = getattr(cond, "inner", None)
                    if tag_of(qc) == "QuantityCheck":
                        for side in (
                            getattr(qc, "lhs", None),
                            getattr(qc, "rhs", None),
                        ):
                            if tag_of(side) != "Ref":
                                continue
                            qty = getattr(side, "qty", None)
                            qtytag = tag_of(qty)
                            if qtytag == "CountersOn":
                                kind = str(getattr(qty, "counter_type", "") or "")
                                if kind.upper() == "P1P1":
                                    return [
                                        Signal(
                                            "plus_one_matters",
                                            "you",
                                            "",
                                            "",
                                            tree.name,
                                            "high",
                                        )
                                    ]
                            elif qtytag == "ObjectCount":
                                # task #85: "draw a card if you control a
                                # creature with a +1/+1 counter on it"
                                # (Chronicler of Heroes) counts OBJECTS
                                # matching a filter, not counters
                                # directly — the filter (not the qty
                                # node itself) carries the P1P1 Counters
                                # predicate. Same reuse precedent as the
                                # artifacts_matter QuantityComparison/
                                # ObjectCount arm above.
                                filt = getattr(qty, "filter", None)
                                if (
                                    filt is not None
                                    and filter_controller(filt) != "Opponent"
                                    and "P1P1" in counter_pred_kinds(filt)
                                ):
                                    return [
                                        Signal(
                                            "plus_one_matters",
                                            "you",
                                            "",
                                            "",
                                            tree.name,
                                            "high",
                                        )
                                    ]
                elif ctag == "TargetHasKeywordInstead":
                    # ADR-0038 W6 endgame — a "if that creature has X
                    # instead" modal (CR 601.2f) whose keyword is a raw-text
                    # residue (Bring Low: "If that creature has a +1/+1
                    # counter on it, ~ deals 5 damage to it instead").
                    # Narrowly scoped to the ``Unknown``-tagged text field,
                    # matching the same ``_P1P1_COND_TEXT_RX`` gap-marker
                    # gate as the Pipsqueak/Skarrgan fallback above — a
                    # NAMED keyword (Flying, Infect, Toxic) never reaches
                    # here (the corpus's 14 TargetHasKeywordInstead
                    # instances split 3 P1P1-text / 3 named-keyword / 8
                    # unrelated power-toughness-comparison text).
                    kw = getattr(cond, "keyword", None)
                    if isinstance(kw, MirrorVariant) and kw.key == "Unknown":
                        text = str(kw.inner or "")
                        if _P1P1_COND_TEXT_RX.search(text):
                            return [
                                Signal(
                                    "plus_one_matters", "you", "", "", tree.name, "high"
                                )
                            ]
        # ADR-0038 W5 tails — a ModifyCost static whose spell_filter names
        # the SPELL'S OWN TARGET as P1P1-counter-bearing (Titanic Brawl, CR
        # 601.2f), distinct from the top-level condition arm above (that
        # cares about a creature ANYWHERE, this cares about the target).
        if unit.origin == "static":
            spell_filt = modify_cost_spell_filter(unit.node)
            if spell_filt is not None:
                for prop in getattr(spell_filt, "properties", ()) or ():
                    if tag_of(prop) != "Targets":
                        continue
                    nested = getattr(prop, "filter", None)
                    if (
                        nested is not None
                        and filter_controller(nested) != "Opponent"
                        and "P1P1" in counter_pred_kinds(nested)
                    ):
                        return [
                            Signal("plus_one_matters", "you", "", "", tree.name, "high")
                        ]
        for leaf in iter_cost_leaves(getattr(unit.node, "cost", None)):
            if tag_of(leaf) == "RemoveCounter" and counter_kind_any(leaf) == "P1P1":
                return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
        # ADR-0039 W8 grammar sprint (task #82) — two recovered-node arms,
        # both kind-gated on the raw (the "draw"/"discard"/"damage"
        # recovered-node raw-read precedent: a recovered node carries no
        # typed counter-kind field to re-check):
        # * ``count_operand`` — a counter TALLY clause (CR 122.1/701.6a):
        #   "count the number of +1/+1 counters on <filter>" (Rumbling
        #   Ruin's ETB), recovered by ``clause_grammar``'s ``count_operand``
        #   token + ``recovery.ALLOWLIST``.
        # * ``counter_cost_reduction`` — an activated ability's OWN
        #   "costs {N} less to activate for each +1/+1 counter" scaler (CR
        #   118.7/122.1, Deepwood Denizen), recovered by the
        #   ``counter_cost_reduction`` token.
        for cn in unit.effects:
            if cn.recovered_by in (
                "count_operand",
                "counter_cost_reduction",
            ) and _P1P1_COND_TEXT_RX.search(cn.raw):
                return [
                    Signal("plus_one_matters", "you", "", cn.raw, tree.name, "high")
                ]
        # ADR-0039 W8 grammar sprint (task #82) — the counter-to-token
        # CONVERSION idiom (CR 122.1/701.7): a P1P1 ``RemoveCounter`` EFFECT
        # (not an activation cost — the Shape-5 cost arm above already
        # covers that) paired with a ``Token`` effect whose ``count`` Refs
        # the SAME removed amount via ``EventContextAmount`` (Tetravus's
        # upkeep "remove any number of +1/+1 counters ... create that many
        # ... tokens"). Fully typed/structural — both node tags are real
        # phase output, no recovery involved. Narrowly paired (not a bare
        # "RemoveCounter anywhere in effects" walk): a corpus check found 39
        # commander-legal cards carry a P1P1 RemoveCounter EFFECT node
        # outside any cost, but 38 of them (self-shrink/drain idioms — the
        # Phantom cycle's evasion tax, the Clockwork cycle's counter-
        # draining activated ability, Protean Hydra's self-shrink) pair with
        # NO scaled Token effect at all, so this exact pairing gate excludes
        # them correctly.
        has_remove_p1p1 = False
        has_scaled_token = False
        for cn in unit.effects:
            node = cn.node
            if tag_of(node) == "RemoveCounter" and counter_kind_any(node) == "P1P1":
                has_remove_p1p1 = True
            elif tag_of(node) == "Token":
                cnt = getattr(node, "count", None)
                if (
                    tag_of(cnt) == "Ref"
                    and tag_of(getattr(cnt, "qty", None)) == "EventContextAmount"
                ):
                    has_scaled_token = True
        if has_remove_p1p1 and has_scaled_token:
            return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
        # np_boons task #4 (Rite of the Serpent) — a "had a +1/+1 counter on
        # it" PAST-TENSE condition (CR 122.1/603.6d) gating a TOKEN reward
        # off a REMOVAL effect (Destroy/DestroyAll/DealDamage/Exile), where
        # BOTH the removal's own condition and the reward's sub_ability
        # condition are dropped entirely — phase carries neither a
        # HadCounters/HasCounters node nor an Unimplemented residue for the
        # clause; the removal and the token creation are both REAL, fully-
        # typed SIBLING effects (Rite of the Serpent: a top-level ``Destroy``
        # ConceptNode and a top-level ``Token`` ConceptNode in the same
        # unit), only the conditional LINK between them vanishes. Basri's
        # Lieutenant / Promising Duskmage / Slurrk / Grakmaw already join
        # this payoff class via a real dies-trigger HadCounters node (a
        # DIFFERENT shape — a death watcher, not an immediate removal
        # spell); this arm covers the sibling shape the typed condition
        # walk can't reach. Gated on BOTH a removal-shaped sibling AND a
        # Token sibling in the SAME unit (never a bare "token maker anywhere
        # on the card" — an unrelated token maker must not join this lane),
        # plus the unit's own description literally carrying the "had ...
        # +1/+1 counter(s) on it" idiom so a differently-conditioned token
        # reward (Reyhan's "one or more +1/+1 counterS" place_counter
        # reward — a different reward SHAPE this gate's ``has_token``
        # requirement already excludes; Fangs of Kalonia's "had a +1/+1
        # counter put on it THIS WAY" self-referential doubler — a
        # different condition entirely, no removal sibling either) never
        # fires. Corpus-verified singleton at the v0.23.0 pin.
        has_removal = any(
            tag_of(cn.node) in _HAD_P1P1_REMOVAL_TAGS for cn in unit.effects
        )
        has_token = any(tag_of(cn.node) == "Token" for cn in unit.effects)
        if (
            has_removal
            and has_token
            and _HAD_P1P1_COND_RX.search(
                str(getattr(unit.node, "description", "") or "")
            )
        ):
            return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
        # np_counters item 1 — the SAME dropped "had ... +1/+1 counter(s) on
        # it" look-back condition (CR 122.1 / 603.10a: dies/leaves triggers
        # see last known information; Reyhan's own 2020-11-10 ruling pins the
        # amount to the counters it had), but with a counter-SCALED reward
        # instead of the Rite arm's Destroy+Token pairing:
        #
        # * a ``PutCounter`` whose kind is P1P1 and whose count Refs
        #   ``EventContextAmount`` — "put THAT MANY +1/+1 counters on target
        #   creature" (Reyhan, Last of the Abzan; both her dies and
        #   command-zone trigger units carry the shape); the Slurrk / Grakmaw
        #   classmates parse a real ``HadCounters`` condition and fire via
        #   the typed arm above, never reaching here.
        # * a ``CopyTokenOf`` reward scaled by the same look-back ("create a
        #   token that's a copy of it ... with half that many +1/+1 counters"
        #   — Ochre Jelly's threshold form, whose typed condition slot holds
        #   only the delayed-trigger ``AtNextPhase`` timing).
        #
        # The unit's own description must carry the past-tense P1P1 idiom, so
        # a power-comparison look-back (Drizzt Do'Urden's "had power greater
        # than"), an attack-requirement look-back (Firkraag's "had to attack
        # this combat"), a kind-AGNOSTIC condition (Yuna, Grand Summoner's
        # "had one or more counters on it" — the any-kind class whose typed
        # classmates deliberately serve via counter_move/any_counter_makers,
        # not a matters lane), and Fangs of Kalonia's same-resolution "had a
        # +1/+1 counter PUT on it this way" doubler (already served
        # structurally: MultiplyCounter → counter_doubling, the Kalonian
        # Hydra / Branching Evolution convention) all stay out.
        if unit.origin == "trigger" and _HAD_P1P1_COND_RX.search(
            str(getattr(unit.node, "description", "") or "")
        ):
            for cn in unit.effects:
                node = cn.node
                tag = tag_of(node)
                cnt = getattr(node, "count", None)
                scaled_put = (
                    tag == "PutCounter"
                    and counter_kind(node) == "P1P1"
                    and tag_of(cnt) == "Ref"
                    and tag_of(getattr(cnt, "qty", None)) == "EventContextAmount"
                )
                if scaled_put or tag == "CopyTokenOf":
                    return [
                        Signal("plus_one_matters", "you", "", "", tree.name, "high")
                    ]
    for c in tree.effect_concepts("move_counters"):
        if counter_kind(c.node).upper() == "P1P1":
            return [Signal("plus_one_matters", "you", "", c.raw, tree.name, "high")]
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        q = count_operand_qty(c.node)
        # ADR-0038 W5 tails — ``CounterAddedThisTurn`` (Iridescent
        # Hornbeetle's "for each +1/+1 counter you've put on creatures
        # under your control this turn") is a DIFFERENT qty shape than
        # ``CountersOn`` — the kind rides a nested ``counters.data`` field
        # (a ``Counters`` predicate object), not a bare ``counter_type``
        # string — but is still a P1P1-specific this-turn placement tally.
        qtag = tag_of(q)
        p1p1_qty = False
        if q is not None and qtag == "CountersOn":
            p1p1_qty = str(getattr(q, "counter_type", "")).upper() == "P1P1"
        elif q is not None and qtag == "CounterAddedThisTurn":
            counters = getattr(q, "counters", None)
            p1p1_qty = str(getattr(counters, "data", "") or "").upper() == "P1P1"
        if p1p1_qty:
            return [Signal("plus_one_matters", "you", "", c.raw, tree.name, "high")]
        filters = [effect_filter(c.node), count_operand_filter(c.node)]
        for stdef in iter_static_defs(c.node):
            filters.append(getattr(stdef, "affected", None))
        for filt in filters:
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            if "P1P1" in counter_pred_kinds(filt):
                return [Signal("plus_one_matters", "you", "", c.raw, tree.name, "high")]
    # LEDGERED BRIDGES (ADR-0039 W8/grammar sprint task #82): 2 corpus-
    # verified singleton gaps the structural arms above genuinely can't
    # reach yet — a static parser failure (Rock Hydra,
    # upstream_parse_failure) and a phase encoding with no counter-kind
    # field at all (Hierophant Bio-Titan's ModifyCost/PreviousEffectAmount,
    # dropped_clause). Rumbling Ruin / Deepwood Denizen (recovered-node
    # arms above) and Tetravus (the counter-to-token pairing arm above)
    # graduated off the bridge list this sprint. Each gap-gated +
    # corpus-bounded + self-retiring; the full rows live in
    # ``bridge_ledger.BRIDGES``.
    for bridge_id in (
        "plus_one_rock_hydra_static_parse_failure",
        "plus_one_hierophant_previouseffectamount_dropped_kind",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("plus_one_matters", "you", "", "", tree.name, "high")]
    return []


# ADR-0038 W3 batch 3 — the P/T-modifying node tags any_counter_matters' pump
# arm gates on: the FIXED forms (``Pump``/``PumpAll`` effects, ``AddPower``/
# ``AddToughness`` static mods — mapped to ``concept="pump"`` by
# ``EFFECT_CONCEPTS``/``_MOD_CONCEPTS``) AND the DYNAMIC forms
# (``AddDynamicPower``/``AddDynamicToughness`` — "+X/+X where X is …", Kyler /
# Luxior's counter-scaled anthem) which decorate as ``concept="other"`` since
# ``_MOD_CONCEPTS`` maps only the fixed pair. Read off the node's own tag, never
# ``concept``, so both forms are covered.
_PT_PUMP_TAGS: frozenset[str] = frozenset(
    {
        "Pump",
        "PumpAll",
        "AddPower",
        "AddToughness",
        "AddDynamicPower",
        "AddDynamicToughness",
    }
)

# ADR-0038 W3 batch 4 — Moira Brown, Guide Author's granted TOKEN ability
# ("Equipped creature gets +1/+1 for each quest counter among permanents you
# control") buries a genuine dynamic scale two levels deep (trigger →
# make_token effect → the token's OWN static_abilities), and phase's parse of
# that buried def drops the "for each quest counter" scale to a FIXED
# ``AddPower(value=1)``/``AddToughness(value=1)`` pair — :func:`count_operand_qty`
# finds no ``Ref``/``dynamic_count`` to read. A bucket-B text-idiom fallback on
# the def's OWN ``description`` (never the whole tree/card) recovers it,
# excluding "+1/+1 counter" wording (that scale already routes to
# plus_one_matters via the SAME def shape elsewhere). CR 122.1.
_ANY_COUNTER_SCALE_TEXT_RX = re.compile(
    r"for each(?:(?!\+1/\+1)[^.]){0,40}\bcounter\b", re.IGNORECASE
)


def _any_counter_matters(tree: ConceptTree) -> list[Signal]:
    """any_counter_matters — a kind-AGNOSTIC counter PAYOFF (CR 122.1). Two structural
    arms mirror the deleted ``_signals_ir``'s taxonomy exactly (ADR-0038 W3 batch 3):

    * arm (b), a subject / count-operand FILTER carrying a ``Counters`` predicate of
      the kind-agnostic ``Any`` form ("a permanent with a counter on it");
    * arm (a), a PUMP effect's dynamic count-operand QTY node
      (:func:`count_operand_qty`, ``CountersOn`` / ``CountersOnObjects``) whose
      ``counter_type`` is anything OTHER than ``P1P1`` — the legacy pump-scaling
      arm's own taxonomy (the deleted ``_signals_ir``'s ~10018, gated
      ``e.category=="pump"``:
      "+1/+1 counter" text routes to ``plus_one_matters``; every OTHER named kind
      (charge/soul/oil/growth/plague/valor/quest/blood/spore/feather/lore/strife/
      scream/acorn/rev/time/unity/fellowship/…) or a kind-agnostic count ("for
      each counter on ~" — Kyler) is NOT re-split into per-kind lanes here; it
      fans into this catch-all the same way legacy's raw-text gate does (a card
      can ALSO carry its own dedicated named-kind lane elsewhere — additive, not
      exclusive). The PUMP gate (the node's own tag — ``Pump``/``PumpAll``, or a
      ``AddPower``/``AddToughness``/``AddDynamicPower``/``AddDynamicToughness``
      static mod; NOT ``concept`` — the dynamic static forms decorate as
      ``concept="other"``, only ``_MOD_CONCEPTS`` maps the FIXED forms) matters: a
      non-pump effect that merely happens to scale by a counter count (draw /
      damage / mill / life-gain / token-count "for each charge counter on this
      artifact") is a DIFFERENT lane entirely and must NOT fire here — legacy's
      own gate excludes it too. CR 122.1.
    """
    for unit in tree.units:
        # A mass STATIC restriction/grant whose OWN ``affected`` names the
        # counter-bearing filter directly (Rishkar's "each creature you control
        # with a counter on it has …"; Nils's "each creature with one or more
        # counters on it can't attack …") lives on the whole-unit static
        # wrapper, never a per-modification concept (ADR-0038 W3 batch 3).
        if unit.origin == "static":
            filt = effect_filter(unit.node)
            if (
                filt is not None
                and filter_controller(filt) != "Opponent"
                and "Any" in counter_pred_kinds(filt)
            ):
                return [Signal("any_counter_matters", "you", "", "", tree.name, "high")]
        # ADR-0038 W3 batch 4 — a counter-HAVE TRIGGER: "whenever a creature you
        # control with a counter on it dies/attacks" (The Swarmlord, Cleopatra,
        # Exiled Pharaoh, Puca's Covenant, Skyboon Evangelist, Metropolis
        # Angel). The Counters predicate rides the TRIGGER's own watched-object
        # filter (``valid_card`` — CR 603.2's intervening-if object), never an
        # effect/static filter, mirroring legacy's ``trig.subject`` arm
        # (the deleted ``_signals_ir``'s ~10693).
        if unit.origin == "trigger":
            vc = getattr(unit.node, "valid_card", None)
            if (
                vc is not None
                and filter_controller(vc) != "Opponent"
                and "Any" in counter_pred_kinds(vc)
            ):
                return [Signal("any_counter_matters", "you", "", "", tree.name, "high")]
        # A granted-TOKEN static def whose "for each <kind> counter" scale
        # phase dropped to a fixed P/T value (Moira Brown — see
        # ``_ANY_COUNTER_SCALE_TEXT_RX`` above). Skip the unit's OWN top-level
        # def (``sd is unit.node``) — a real ``Ref``-carrying scale there is
        # already read by the ``tree.iter_concepts()`` pass below; re-reading
        # it here via text would double-fire on (and never exclude) the
        # dedicated-lane Experience scale (Kalemne, Kelsien, Minthara, Azula).
        # Gate per-modification on :func:`count_operand_qty` finding NOTHING
        # (the genuine buried-parse-drop signature) so a nested def that DOES
        # carry a proper structured scale is left to its own accessor.
        for sd in iter_static_defs(unit.node):
            if sd is unit.node:
                continue
            mods = getattr(sd, "modifications", None)
            if not isinstance(mods, list) or not any(
                isinstance(m, TypedMirrorNode)
                and tag_of(m) in _PT_PUMP_TAGS
                and count_operand_qty(m) is None
                for m in mods
            ):
                continue
            desc = getattr(sd, "description", "") or ""
            if _ANY_COUNTER_SCALE_TEXT_RX.search(desc):
                return [
                    Signal("any_counter_matters", "you", "", desc, tree.name, "high")
                ]
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        if tag_of(c.node) in _PT_PUMP_TAGS:
            q = count_operand_qty(c.node)
            qtag = tag_of(q) if q is not None else None
            # ADR-0038 W3 batch 4 — a PLAYER-counter scale ("gets +1/+1 for
            # each poison counter your opponents have" — Mycosynth Fiend,
            # Vishgraz, the Doomhive) is a distinct qty node
            # (``PlayerCounter``, ``kind`` field) from the permanent-scoped
            # ``CountersOn``/``CountersOnObjects`` (``counter_type`` field);
            # same kind-agnostic-catch-all taxonomy, different node shape.
            if q is not None and qtag in ("CountersOn", "CountersOnObjects"):
                kind = str(getattr(q, "counter_type", "") or "").upper()
                if kind != "P1P1":
                    return [
                        Signal(
                            "any_counter_matters", "you", "", c.raw, tree.name, "high"
                        )
                    ]
            elif q is not None and qtag == "DistinctCounterKindsAmong":
                # phase v0.31.0 routes "the number of different kinds of
                # counters among permanents you control" (Perrie, the
                # Pulverizer) to its own qty node — kind-agnostic by
                # definition, so no P1P1 carve-out applies.
                return [
                    Signal("any_counter_matters", "you", "", c.raw, tree.name, "high")
                ]
            elif q is not None and qtag == "PlayerCounter":
                # Experience carries its OWN dedicated lane (experience_matters,
                # ADR-0034 — Kalemne, Kelsien, Minthara, Azula) and is EXCLUDED
                # here exactly like P1P1 is above; the corpus's only other
                # PlayerCounter kind is Poison, which legacy DOES route through
                # this kind-agnostic catch-all.
                kind = str(getattr(q, "kind", "") or "").upper()
                if kind not in ("P1P1", "EXPERIENCE"):
                    return [
                        Signal(
                            "any_counter_matters", "you", "", c.raw, tree.name, "high"
                        )
                    ]
        filters = [effect_filter(c.node), count_operand_filter(c.node)]
        # A one-shot conferred grant ("Each creature you control with a counter
        # on it gains flying" — Baxter; "…has hexproof and indestructible" —
        # Bulwark Ox) carries its OWN filter on a NESTED static def's
        # ``affected``, never the wrapping ``GenericEffect``'s own fields
        # (:func:`effect_filter` reads only the top-level node) — descend via
        # :func:`iter_static_defs` (ADR-0038 W3 batch 3).
        for stdef in iter_static_defs(c.node):
            filters.append(getattr(stdef, "affected", None))
        for filt in filters:
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            if "Any" in counter_pred_kinds(filt):
                return [
                    Signal("any_counter_matters", "you", "", c.raw, tree.name, "high")
                ]
    return []


# task #93 item 6 (niche-7 re-triage, Blightbeetle): a counter-DENIAL hate
# piece — "Creatures your opponents control can't have +1/+1 counters put
# on them" — is a genuine, if narrow, anti-counters stax tell distinct from
# ``any_counter_matters`` (a PAYOFF for counters already present, which
# EXPLICITLY excludes an ``Opponent``-controlled filter — see the ``!=
# "Opponent"`` gates above) and from a SELF-protection "this creature can't
# have counters put on it" (Melira's Keepers, Tatterkite — protects the
# card ITSELF, no opponent scope at all, out of scope for this lane). Both
# corpus hits (Blightbeetle's unconditional static, Suncleanser's modal
# "Target opponent loses all counters. That player can't get counters..."
# branch) are a phase parser gap — CR 701.71 (the "can't have/get counters"
# restriction) has NO typed substrate at all; phase drops the whole clause
# to an ``Unimplemented`` "static_structure"/"can't" residue either way, so
# a raw-text regex bridge is the only way to read either. Corpus-verified
# exhaustively (32,521 commander-legal cards): exactly these 2 hits, 0
# false positives, 0 near-misses reachable by a broader phrasing. No
# ``theme_presets`` entry — 2 cards is too narrow a population for an
# archetype-level preset (matches how other single-digit-population lanes
# in this module stay preset-less). Scope "opponents". CR 701.71.
_COUNTER_HATE_OPPONENT_RE = re.compile(
    r"opponents?\s+control[^.]*can.t have[^.]*counters?\s+put\s+on\s+them"
    r"|target opponent[^.]*loses all counters[^.]*\.\s*that player can.t "
    r"(?:get|have) counters",
    re.IGNORECASE,
)


def _counter_hate(tree: ConceptTree) -> list[Signal]:
    """counter_hate — an opponent-directed counter-placement DENIAL (CR
    701.71), never a self-protection or an own-counter payoff. See the
    module note above for the corpus census + boundary against
    ``any_counter_matters``."""
    m = _COUNTER_HATE_OPPONENT_RE.search(_kept(tree))
    if m is None:
        return []
    return [Signal("counter_hate", "opponents", "", m.group(0), tree.name, "high")]


# np_boons task #5 (Biomancer's Familiar re-triage): adapt_matters — a card
# that SUPPORTS/ENABLES another creature's Adapt (CR 701.46a: "If this
# permanent has no +1/+1 counters on it, put N +1/+1 counters on it.") without
# performing Adapt itself. Cares-about doctrine: its population is the adapt
# DOER cards (self_counter_grow's ``tag_of == "Adapt"`` members, 24
# commander-legal cards at the v0.23.0 pin) — Biomancer's Familiar's "The next
# time target creature adapts this turn, it adapts as though it had no +1/+1
# counters on it" resets a creature that ALREADY has counters (and so would
# otherwise fail the 701.46a "no counters" gate) so it can adapt again, a
# genuine re-adapt enabler for that exact doer population, CR-verified via
# rulings-lookup (Biomancer's Familiar, 2019-01-25: "The last ability of
# Biomancer's Familiar doesn't add or remove any counters. It just lets the
# creature adapt despite already having +1/+1 counters on it.") Corpus
# census (32,521 commander-legal cards): 25 total
# cards reference the bare word "adapt" (``\badapt(s)?\b``, word-boundary
# safe — MTG oracle text uses "adapt" ONLY for this keyword, 0 unrelated
# English-word hits), 24 of which are the doers themselves (a typed ``Adapt``
# effect node, already served by ``self_counter_grow``); Biomancer's Familiar
# is the sole remaining reference — the ``not _has_structural_adapt`` gate
# below excludes the 24 typed doers. A 25th card, Jetfire, Air Guardian (the
# back face of Jetfire, Ingenious Scientist), turned up in the full-corpus
# verification: its "{U}{U}{U}: Convert Jetfire, then adapt 3" chained
# activated ability is a genuine Adapt DOER phase drops WHOLLY (no
# Transform-then-adapt residue survives at all — a bucket-B gap in
# ``self_counter_grow`` itself, out of THIS task's scope), so
# ``_has_structural_adapt`` alone doesn't exclude it — the literal "Adapt N"
# KEYWORD-INVOCATION shape (a number immediately after "adapt", the printed-
# keyword template every one of the 25 doers uses verbatim, CR 702.130a) is a
# second, TEXT-level veto that catches this exact class without needing the
# missing structural node: Biomancer's Familiar's own text never pairs
# "adapt" with a following number (it says "adapts"/"adapts as though",
# third-person verb form referencing something ELSE adapting), so the veto
# never excludes the genuine enabler. No ``theme_presets`` entry — a 1-card
# population is too narrow for an archetype-level preset, matching
# ``counter_hate``'s own precedent. Scope "you" (the enabler and its
# beneficiary are both under your control in every corpus example; CR
# 701.46a's "you" default).
_ADAPT_MATTERS_RE = re.compile(r"\badapts?\b", re.IGNORECASE)
_ADAPT_KEYWORD_INVOCATION_RE = re.compile(r"\badapt\s+\d+\b", re.IGNORECASE)


def _has_structural_adapt(tree: ConceptTree) -> bool:
    return any(tag_of(c.node) == "Adapt" for c in tree.iter_concepts())


def _adapt_matters(tree: ConceptTree) -> list[Signal]:
    """adapt_matters — see the module note directly above. CR 701.46a."""
    if _has_structural_adapt(tree):
        return []
    kept = _kept(tree)
    if _ADAPT_KEYWORD_INVOCATION_RE.search(kept):
        return []
    m = _ADAPT_MATTERS_RE.search(kept)
    if m is None:
        return []
    return [Signal("adapt_matters", "you", "", m.group(0), tree.name, "high")]


def _chooses_opponent(node: object) -> bool:
    """Whether a ``Choose`` effect picks an OPPONENT (the give-away beneficiary).

    Fateful Handoff / Rogue Skycaptain resolve "an opponent gains control of it" as
    a ``Choose`` of ``choice_type: Opponent`` feeding the gain-control's
    ``ParentTarget``. A directional / random ``Choose`` (Order of Succession's
    Left/Right, Scrambleverse's random Player) is instead caught by the player_scope
    arm; only the literal Opponent choice is read here.
    """
    return getattr(node, "choice_type", None) == "Opponent"


def _gives_control_to_other(node: TypedMirrorNode, unit: AbilityUnit) -> bool:
    """Whether a gain-control effect hands control to a NON-you player (CR 110.2 /
    603.10d) — a give-away / chaos swap, not a you-theft payoff. The beneficiary of a
    control change is structural; three typed markers say "not you":

    * a MASS give-away of your OWN board — ``GainControlAll`` whose target is
      ``controller: You`` ("target opponent gains control of all permanents YOU
      control": Sky Swallower). Restricted to the *mass* form: a single
      ``GainControl`` of ``controller: You`` is a phase MISLABEL of "target creature
      that <opponent> controls" (Nihiloor), a genuine you-theft, not a give-away;
    * a ``Choose`` of an OPPONENT in the unit feeding the gain-control's ``SelfRef`` /
      ``ParentTarget`` ("an opponent gains control of it / this" — Fateful Handoff,
      Rogue Skycaptain, Wishclaw Talisman, Rainbow Vale). Gaining control of THIS
      card / the just-targeted thing for an opponent is never a you-theft;
    * a non-controller ``player_scope`` on the gain-control's OWN ability wrapper
      ("each player gains control …": Order of Succession, Inniaz, Scrambleverse,
      Aminatou) — read per-effect (:func:`effect_owner_player_scope`), so an unrelated
      each-player action sharing the unit (Nihiloor's per-opponent tap loop) does NOT
      veto a genuine you-theft.
    """
    if tag_of(node) == "GainControlAll":
        sub = effect_filter(node)
        if sub is not None and filter_controller(sub) == "You":
            return True
    if tag_of(effect_filter(node)) in ("SelfRef", "ParentTarget") and any(
        tag_of(c.node) == "Choose" and _chooses_opponent(c.node) for c in unit.effects
    ):
        return True
    return effect_owner_player_scope(getattr(unit, "node", None), node) in (
        _EDICT_ACTORS
    )


def _gain_control(tree: ConceptTree) -> list[Signal]:
    """gain_control — YOU-THEFT (you take control of a permanent you don't own,
    CR 110.2 / 720). Mirrors the deleted ``_signals_ir``'s line ~9270: a ``GainControl``
    /
    ``GainControlAll`` effect (Threaten, Control Magic's reset-free theft), EXCLUDING:

    * a control-RESET — an ``Owned`` predicate on the target ("each player gains
      control of permanents they own", Brooding Saurian, CR 110.2a);
    * a GIVE-AWAY / chaos swap whose new controller is NOT you
      (:func:`_gives_control_to_other`): "target opponent gains control of all
      permanents you control" (Sky Swallower), "an opponent gains control of it"
      (Fateful Handoff, Rogue Skycaptain), "each player gains control …" (Order of
      Succession, Inniaz, Scrambleverse, Aminatou). The beneficiary being an opponent
      is structural (CR 110.2 / 603.10d), so these are NOT a you-gain payoff.

    A donate (``GiveControl`` — you give your OWN away) is a SEPARATE phase tag,
    never reaching this arm. A ``Control Magic`` enchant rides a ``ChangeController``
    STATIC modification (the new controller is you). Scope "you".
    """
    for unit in tree.units:
        for c in unit.effect_concepts("gain_control"):
            sub = effect_filter(c.node)
            if sub is not None and "Owned" in filter_predicates(sub):
                continue  # control-RESET, not theft
            if _gives_control_to_other(c.node, unit):
                continue  # give-away — the new controller is an opponent, not you
            return [Signal("gain_control", "you", "", c.raw, tree.name, "high")]
    # EXCHANGE-control THEFT (recall gap): an ``ExchangeControl`` swaps your
    # permanent for an opponent's — you gain control of theirs (Daring Thief,
    # Djinn of Infinite Deceits, Gilded Drake, Perplexing Chimera). phase's
    # lossy IR maps ``exchangecontrol`` → the ``gain_control`` category
    # (project.py), but the mirror keeps the ``exchange_control`` concept, so
    # the theft lane must read it — exactly the routing the ``_control_exchange``
    # docstring already anticipates ("live fires the 18 ExchangeControl swaps
    # under the PORTED gain_control lane"). A land-for-land swap (Political
    # Trickery) co-fires ``land_exchange`` (a separate lane), matching the live
    # path. CR 701.12b / 110.2.
    for c in tree.effect_concepts("exchange_control"):
        return [Signal("gain_control", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        for c in unit.statics:
            if tag_of(c.node) == "ChangeController":
                return [Signal("gain_control", "you", "", c.raw, tree.name, "high")]
    return []


def _resource_token_makers(tree: ConceptTree) -> list[Signal]:
    """treasure_makers / food_makers / clue_makers / blood_makers — a predefined
    artifact-token maker (CR 111.10 / 205.3g / 701.16a investigate). Mirrors
    the deleted ``_signals_ir``'s ~12297: a ``make_token`` whose token subtype is
    Treasure / Food /
    Clue / Blood, scope you/each; ``Investigate`` is a first-class Clue maker. The
    structural read improves on the raw-fallback (the resource subtype rides the
    token's typed ``types``). Scope "you".
    """
    keys = {
        "Treasure": "treasure_makers",
        "Food": "food_makers",
        "Clue": "clue_makers",
        "Blood": "blood_makers",
    }
    out: list[str] = []
    for c in tree.effect_concepts("make_token"):
        if c.scope not in _YOU_EACH:
            continue
        for sub, key in keys.items():
            if sub in c.subject:
                out.append(key)
    if tree.has_effect("investigate"):
        out.append("clue_makers")
    seen: set[str] = set()
    sigs: list[Signal] = []
    for key in out:
        if key not in seen:
            seen.add(key)
            sigs.append(Signal(key, "you", "", "", tree.name, "high"))
    return sigs


def _mill_makers(keywords: frozenset[str], name: str) -> list[Signal]:
    """mill_makers — a FIELD-LOOKUP on the Scryfall ``Mill`` keyword, NOT a structural
    port (ADR-0027 / CR 701.17a). The legacy survivor (the deleted ``_signals_ir``'s
    ``_IR_KEYWORD_MAP['mill']``) was DELIBERATELY moved to the keyword array to drop
    three phase mislabels of the ``Mill`` effect category — Bone Dancer (opp-GY →
    battlefield REANIMATION), Scroll Rack (library↔hand swap), Soldevi Digger (GY →
    library bottom) — none a CR 701.17a mill, none carrying the ``Mill`` keyword. Every
    genuine mill DOES carry it (0 keyword-less commander-legal fires), so the keyword
    route reproduces the deleted regex producer exactly. Scope "any" (self- or
    opponent-mill — the deleted preset's scope).
    """
    if any(k.lower() == "mill" for k in keywords):
        return [Signal("mill_makers", "any", "", "", name, "high")]
    return []


def _proliferate_makers(tree: ConceptTree) -> list[Signal]:
    """proliferate_makers — a proliferate DOER (CR 701.34a). A native ``Proliferate``
    effect (Atraxa, Evolution Sage; the keyword-less proliferators the Scryfall regex
    missed). The ``station`` keyword is a proliferate_matters payoff, not a doer —
    routed elsewhere. Scope "you".
    """
    for c in tree.effect_concepts("proliferate"):
        return [Signal("proliferate_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _energy_makers(tree: ConceptTree) -> list[Signal]:
    """energy_makers — an energy producer (CR 107.14 / 122.1). A ``GainEnergy`` effect
    (Aetherworks Marvel, Dynavolt Tower). phase models energy as a first-class effect
    (NOT a kind-dropped ``GivePlayerCounter``), so the structural read is clean. Scope
    "you".
    """
    for c in tree.effect_concepts("gain_energy"):
        return [Signal("energy_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _voltron_maker_unit_gear_attach(unit: AbilityUnit) -> bool:
    """Whether THIS unit performs a gear-attach whose target gear is named by a
    SIBLING effect rather than the ``Attach`` node's own ``attachment`` field.

    phase's back-reference tags are POSITION-relative (a ``ParentTarget`` /
    ``TriggeringSource`` ``attachment`` resolves to whatever an earlier
    sibling EFFECT in the SAME unit targeted — Ogre Geargrabber's "gain
    control of target Equipment … Attach it to this creature" [the
    ``GainControl`` node's own ``target`` is directly ``Typed(Equipment)``],
    Stolen Uniform's "Choose target creature … and target Equipment … Attach
    it" [a sibling ``TargetOnly`` node's own ``target`` is directly
    ``Typed(Equipment)``]). Narrowly scoped to avoid the Hammer of Nazahn /
    Ajani's Chosen / Sigarda's Aid over-fire class: (1) the ``Attach``'s own
    ``attachment`` must itself be an unresolved back-reference (never fires
    when ``attachment`` is absent — a self-attach — or already a direct
    Typed filter, both handled by the base arm above); (2) the resolving
    filter must be READ DIRECTLY off a ``TargetOnly``/``gain_control``
    sibling's own ``target`` field (never a deeper multi-hop resolution,
    never a ``static`` modification's ``affected`` filter — Hammer of
    Nazahn's unrelated "Equipment you control have hexproof" static is what
    the multi-hop-free gate excludes). CR 301.5 / 303.4 / 720 (gain control).
    """
    attach_unresolved = False
    for c in unit.effects:
        if c.concept != "attach":
            continue
        att = getattr(c.node, "attachment", None)
        if att is not None and tag_of(att) in ("ParentTarget", "TriggeringSource"):
            attach_unresolved = True
    if not attach_unresolved:
        return False
    for c in unit.effects:
        if c.concept != "gain_control" and tag_of(c.node) != "TargetOnly":
            continue
        tgt = getattr(c.node, "target", None)
        if tgt is not None and (
            {s.lower() for s in filter_subtypes(tgt)} & _VOLTRON_SUBTYPES
        ):
            return True
    return False


# The reanimate-with-attach idiom (CR 303.4 / 111.7): "return/put … Aura …
# attached" — Unfinished Business's multi-target Aura/Equipment return has an
# UNRESOLVED (non-Typed) ``ChangeZone.target`` back-reference, so it can't
# ride the primary structural check below; this is a LAST-RESORT per-ability
# description scan (never whole-card — no SequentialSibling bleed), gated to
# a unit that ALSO carries a real ``ChangeZone`` effect whose ``destination``
# is "Battlefield" (a genuine put/return-INTO-play, never a bounce). That
# gate is what keeps Portal of Sanctuary ("Return target creature … and each
# Aura attached to it to their owners' hands" — a Bounce, no Battlefield
# ChangeZone) and Seedling Charm ("Return target Aura attached to a creature
# to its owner's hand" — same) OUT: both match the bare text idiom but
# neither reanimates anything onto the battlefield.
_VOLTRON_REANIMATE_ATTACH_RX = re.compile(
    r"(?:return|put)[^.]*\baura\b[^.]*\battached\b", re.IGNORECASE
)
# The "becomes attached" trigger idiom (CR 301.5 / 303.4): phase has no
# structural trigger event for "an Aura/Equipment you control becomes
# attached to X" (Eriette, Siona) — its ``mode`` decorates as an unresolved
# ``MirrorVariant(key='Unknown', ...)`` carrying only the raw clause. Scoped
# to the SAME idiom (never whole-card).
_VOLTRON_BECOMES_ATTACHED_RX = re.compile(
    r"\b(?:aura|equipment) you control becomes attached\b", re.IGNORECASE
)
# The unattach maker idiom (CR 701.3d): a card that performs the unattach
# ACTION itself, either a structural ``Unattach``/``UnattachAll`` node
# (Disarm, Fulgent Distraction) or the word surviving only in a granted-
# ability / activated-ability / Unimplemented-residue description (Leonin
# Bola, Blinding Powder, Heartseeker, Razor Boomerang, Shuriken, Surestrike
# Trident, Sunforger, Elbrus, Toralf's Hammer, Akiri, Carry Away — every one
# of these has "unattach" verbatim in SOME node's own ``description``, never
# a cross-clause bleed since each node's description is that node's own
# grounding text). "unattach" is unambiguous CR 701.3d vocabulary — no other
# mechanic uses the word — so an unscoped-by-role scan is safe. EXCLUDED: a
# structural ``UnattachAll`` whose ``attachment`` is ``SelfRef`` — a
# Reconfigure creature's own "attach OR unattach [itself]" toolbox mode
# (Acquisition Octopus, Armguard Familiar, …, CR 702.151j) is a self-toggle,
# never a gear-fetch maker (the same self-attach exclusion as Bonesplitter's
# equip). Its "unattach" word lives ONLY inside the Reconfigure reminder
# PARENTHETICAL, which never reaches a ``description`` field here, so the
# exclusion is purely the structural ``SelfRef`` gate.
_UNATTACH_RX = re.compile(r"\bunattach\b", re.IGNORECASE)
# A residual attach-gear clause phase drops entirely into an ``Unimplemented``
# node (Reckless Crew / Goldwardens' Gambit: "For each of those tokens, you
# may attach an Equipment you control to it"; Liberated Livestock: "…you may
# put an Aura card from your hand and/or graveyard onto the battlefield
# attached to it" — the reversed "aura … attached" word order, so BOTH
# orderings are checked) — scoped to that node's OWN description (one
# clause), never the ability's full text.
_UNIMPLEMENTED_ATTACH_GEAR_RX = re.compile(
    r"\battach\b[^.]*\b(?:equipment|aura)\b"
    r"|(?:return|put)[^.]*\baura\b[^.]*\battached\b",
    re.IGNORECASE,
)


def _voltron_makers(tree: ConceptTree) -> list[Signal]:
    """voltron_makers — gear-attaching / Equipment-Aura tutor (CR 301.5 / 303.4 /
    701.23 / 701.3d). Mirrors the deleted ``_signals_regex``'s
    ``_detect_voltron_maker_ir``: (a) an
    ``Attach`` effect moving ANOTHER typed Equipment/Aura onto a creature (the
    ``attachment`` field is a separate typed gear, NOT absent — Kor Outfitter,
    Balan), scope not opponent; (b) a ``SearchLibrary`` whose searched filter
    SUBTYPE is Equipment/Aura (Stoneforge Mystic, Godo, Three Dreams); (c) an
    ``Attach`` whose gear is named by a SIBLING effect in the same unit
    (:func:`_voltron_maker_unit_gear_attach` — Ogre Geargrabber, Stolen Uniform);
    (d) the unattach maker idiom (Leonin Bola, Sunforger, Disarm, …); (e) the
    reanimate-with-attach / becomes-attached last-resort idioms (Hakim, Eriette,
    …), both corpus-verified against the known Portal of Sanctuary / Seedling
    Charm / Animal Friend over-fire class (bounce / payoff text that superficially
    matches "aura … attached" but performs no attach action). Self-attach
    (Bonesplitter's equip — ``attachment`` absent) is the payload, not a maker.
    Scope "you".
    """
    for c in tree.effect_concepts("attach"):
        if c.scope == "opponents":
            continue
        attachment = getattr(c.node, "attachment", None)
        if attachment is not None and (
            {s.lower() for s in filter_subtypes(attachment)} & _VOLTRON_SUBTYPES
        ):
            return [Signal("voltron_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("tutor"):
        sub = effect_filter(c.node)
        if sub is not None and (
            {s.lower() for s in filter_subtypes(sub)} & _VOLTRON_SUBTYPES
        ):
            return [Signal("voltron_makers", "you", "", c.raw, tree.name, "high")]
    # A ``ChangeZone`` reanimating an Aura/Equipment CARD onto the battlefield
    # (Hakim, Iridescent Drake, Storm Herald, Mantle of the Ancients, Nomad
    # Mythmaker, One Last Job, Academy Researchers, Danitha, Holy Avenger,
    # Evershrike, Forum Filibuster): CR 303.4c / 301.5c REQUIRE such a card to
    # enter attached to something (an unattached Aura/Equipment is a state-
    # based sacrifice, CR 704.5n/704.5m) — so this is a fully STRUCTURAL tell
    # (the target's own subtype), no text idiom needed, and it's what covers
    # One Last Job's Spree mode (whose ability carries no ``description`` at
    # all to text-scan). Never fires on a Bounce (Portal of Sanctuary,
    # Seedling Charm stay excluded — they return TO HAND, not onto the
    # battlefield).
    for c in tree.effect_concepts("change_zone"):
        if c.scope == "opponents":
            continue
        if getattr(c.node, "destination", None) != "Battlefield":
            continue
        tgt = getattr(c.node, "target", None)
        if tgt is not None and (
            {s.lower() for s in filter_subtypes(tgt)} & _VOLTRON_SUBTYPES
        ):
            return [Signal("voltron_makers", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if _voltron_maker_unit_gear_attach(unit):
            return [Signal("voltron_makers", "you", "", "", tree.name, "high")]
    for unit in tree.units:
        for n in iter_typed_nodes(unit.node):
            if tag_of(n) == "Unattach":
                return [Signal("voltron_makers", "you", "", "", tree.name, "high")]
            if tag_of(n) == "UnattachAll":
                att = getattr(n, "attachment", None)
                if att is None or tag_of(att) != "SelfRef":
                    return [Signal("voltron_makers", "you", "", "", tree.name, "high")]
            desc = getattr(n, "description", None)
            if not isinstance(desc, str):
                continue
            if _UNATTACH_RX.search(desc):
                return [Signal("voltron_makers", "you", "", desc, tree.name, "high")]
            if tag_of(n) == "Unimplemented" and _UNIMPLEMENTED_ATTACH_GEAR_RX.search(
                desc
            ):
                return [Signal("voltron_makers", "you", "", desc, tree.name, "high")]
            if _VOLTRON_BECOMES_ATTACHED_RX.search(desc):
                return [Signal("voltron_makers", "you", "", desc, tree.name, "high")]
        if any(
            c.concept == "change_zone"
            and getattr(c.node, "destination", None) == "Battlefield"
            for c in unit.effects
        ):
            desc = getattr(unit.node, "description", None)
            if isinstance(desc, str) and _VOLTRON_REANIMATE_ATTACH_RX.search(desc):
                return [Signal("voltron_makers", "you", "", desc, tree.name, "high")]
    return []


def _voltron_equip_style_keyword(mod: TypedMirrorNode) -> bool:
    """True if an ``AddKeyword`` modification grants Equip/Reconfigure/Fortify
    (CR 702.6 / 702.151 / 702.19c) — an attach-mechanic keyword conferred onto
    a creature that doesn't natively carry one (Nahiri, Storm of Stone grants
    a cost-reduced Equip). ``mod_keyword_name`` normalizes both the plain and
    the parameterized (cost-carrying) grant shapes."""
    name = mod_keyword_name(mod)
    return isinstance(name, str) and name.lower() in {
        "equip",
        "reconfigure",
        "fortify",
    }


# ADR-0038 W6 endgame — last-resort per-node text reads for two structural
# parse failures the ``_voltron_matters`` gate above otherwise misses
# entirely (never a whole-card scan; each reads ONLY the one node's own
# preserved raw field, mirroring the module's established ``_unknown_mode_*``
# family — see ``_unknown_mode_creature_etb`` / ``_unknown_mode_combat_
# damage_to_player`` for the same fallback-only contract).
_UNKNOWN_MODE_VOLTRON_ATTACHMENT_RE = re.compile(
    r"\b(?:equipment|auras?)\b[^.]{0,60}\battached\b"
    r"|\battached\b[^.]{0,60}\b(?:equipment|auras?)\b",
    re.IGNORECASE,
)


def _unknown_mode_voltron_attachment(trig: object) -> bool:
    """Whether trigger DEFINITION ``trig`` is an Unknown-mode node whose OWN
    ``description`` field confirms an attachment-STATE PAYOFF phase
    couldn't structure at all (Kassandra, Eagle Bearer: "Whenever a
    creature you control with a legendary Equipment attached to it deals
    combat damage to a player, draw a card" — ``mode`` is a bare
    ``Unknown`` MirrorVariant carrying only the raw clause and
    ``valid_card`` is ``None``, so the structural attachment-predicate scan
    above never reaches it). Read ONLY when this exact node's own mode
    failed to structure — never a whole-card scan. CR 301.5c/303.4b.
    """
    mode = getattr(trig, "mode", None)
    if not (isinstance(mode, MirrorVariant) and mode.key == "Unknown"):
        return False
    desc = getattr(trig, "description", "") or ""
    return _UNKNOWN_MODE_VOLTRON_ATTACHMENT_RE.search(desc) is not None


def _mana_restriction_equip_tell(effect: object) -> bool:
    """Whether a ``Mana`` effect's own ``restrictions`` list scopes the
    produced mana to Equipment/Aura spells or an equip/reconfigure/fortify
    activation (Freya Crescent, Codsworth Handy Helper, Tournament Grounds,
    Ronin, Shadow Stalker — "Spend this mana only to cast an Equipment
    spell or activate an equip ability") — a genuine "this resource exists
    to fund gear" build-around tell distinct from the ability-cost /
    cast-cost REDUCERS already read above. CR 106.6 (mana that restricts
    how it can be spent). ``SpellType``'s own payload is a free-text label
    ("Aura And/or Equipment", "Knight or Equipment"), not a structured
    filter, so this reads it as node-scoped residue text (word-boundary,
    case-insensitive) — the SAME per-node last-resort idiom as the
    Unrecognized-condition text read below, never a whole-card scan.
    """
    restrictions = getattr(effect, "restrictions", None)
    stack: list[object] = list(restrictions) if isinstance(restrictions, list) else []
    while stack:
        r = stack.pop()
        if not isinstance(r, MirrorVariant):
            continue
        if r.key == "Any" and isinstance(r.inner, list):
            stack.extend(r.inner)
        elif r.key == "SpellType" and isinstance(r.inner, str):
            if re.search(r"\b(?:equipment|auras?)\b", r.inner, re.IGNORECASE):
                return True
        elif r.key == "ActivateTagged" and tag_of(r.inner) == "Equip":
            return True
    return False


def _voltron_modal_aggregate_tell(node: object) -> bool:
    """A trigger/ability's own MODAL mode whose effect carries a mana-value
    CONSTRAINT scaled on the greatest mana value among Equipment/Aura
    (Tetsuo, Imperial Champion: "cast an instant or sorcery spell ... with
    mana value less than or equal to the greatest mana value among
    Equipment attached to it") — a ``Ref`` over an ``Aggregate`` qty,
    which :func:`ref_count_filter` doesn't cover (it only unwraps
    ``ObjectCount``). Read ONLY off ``execute.mode_abilities`` — a mode's
    own EFFECT, never a whole-card scan. CR 107.3/301.5c."""
    execute = getattr(node, "execute", None)
    modes = getattr(execute, "mode_abilities", None)
    if not isinstance(modes, list):
        return False
    for m in modes:
        eff = getattr(m, "effect", None)
        constraint = getattr(eff, "constraint", None)
        data = getattr(constraint, "data", None)
        value = getattr(data, "value", None) if data is not None else None
        if tag_of(value) != "Ref":
            continue
        qty = getattr(value, "qty", None)
        if tag_of(qty) != "Aggregate":
            continue
        filt = getattr(qty, "filter", None)
        if filt is not None and (
            {s.lower() for s in filter_subtypes(filt)} & _VOLTRON_SUBTYPES
        ):
            return True
    return False


def _voltron_matters(tree: ConceptTree) -> list[Signal]:
    """voltron_matters — an Aura/Equipment PAYOFF build-around (CR 301.5c / 303).
    Mirrors the deleted ``_signals_regex``'s ``_detect_voltron_payoff_ir``: (a) a
    ``cast_spell`` trigger
    whose watched subject SUBTYPE is Equipment/Aura (Sram, Kor Spiritdancer); (b) an
    attachment-STATE predicate (``AttachedToRecipient`` / ``HasAnyAttachmentOf`` — "for
    each Aura attached to it", "enchanted or equipped creatures" — Reyav, Koll) on any
    effect / count-operand / trigger-CONDITION subject (a ``dies``-if-``enchanted or
    equipped`` gate — Koll — carries the predicate on the trigger's
    ``condition.filter``, not ``valid_card``); (c) an Equip/Reconfigure/
    Fortify ability-cost reducer (CR 702.6c "equip abilities you activate
    cost {1} less" — Bureau Headmaster, Fervent Champion, Éowyn; or a
    granted cost-reduced Equip keyword — Nahiri, Storm of Stone);
    (d) a cast-cost reducer whose ``spell_filter`` is Equipment/Aura (CR 601.2f — "Aura
    spells you cast cost {1} less" — Transcendent Envoy, Bureau Headmaster) or a
    ``CastWithKeyword`` grant (Flash) to Aura/Equipment spells (CR 702.8a — Sigarda's
    Aid); (e) the ability's OWN activation ``cost_reduction`` scaling on an Equipment/
    Aura COUNT (Plate Armor's equip cost, "{1} less for each OTHER Equipment you
    control"); (f) a ``SourceIsEquipped`` self-referential CONDITION (CR 301.5c — "as
    long as ~ is equipped" gating a static/ability — Patriot, Cloud, Auriok
    Steelshaper); (g) an effect's damage/count operand scaled on a bare Equipment/Aura
    COUNT ("deals damage … equal to the number of Equipment you control" — Armed
    Response, Slash of Light; a genuine "cares how much gear I have" tell, distinct
    from a bare subtype on a TARGET/effect subject, which stays excluded — that covers
    Aura hate / an Equipment's own "Equipped creature gets +X/+X" ``EquippedBy``
    payload-pump). Scope "you".
    """
    self_subtypes = frozenset(s.lower() for s in tree.card_subtypes)
    for unit in tree.units:
        if unit.trigger_event == "cast_spell":
            vc = getattr(unit.node, "valid_card", None)
            if {s.lower() for s in filter_subtypes(vc)} & _VOLTRON_SUBTYPES:
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a trigger whose MODE itself failed to structure at all (Kassandra,
        # Eagle Bearer's "creature ... with a legendary Equipment attached to
        # it deals combat damage" — mode=Unknown, valid_card=None). CR
        # 301.5c/303.4b.
        if _unknown_mode_voltron_attachment(unit.node):
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a Mana effect's own restrictions scoping the produced mana to
        # Equipment/Aura spells or an equip/reconfigure/fortify activation
        # (Freya Crescent, Codsworth, Tournament Grounds, Ronin, Shadow
        # Stalker). CR 106.6.
        eff = getattr(unit.node, "effect", None)
        if tag_of(eff) == "Mana" and _mana_restriction_equip_tell(eff):
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a modal mode's own effect scaled on the greatest Equipment/Aura
        # mana value (Tetsuo, Imperial Champion). CR 107.3/301.5c.
        if _voltron_modal_aggregate_tell(unit.node):
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # an attachment-STATE watched subject ("enchanted or equipped creature you
        # control attacks" — Reyav) carries the predicate on the trigger's valid_card.
        for fname in ("valid_card", "valid_source"):
            wf = getattr(unit.node, fname, None)
            if wf is not None and _voltron_collective_preds(wf, self_subtypes):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a trigger CONDITION's own filter ("dies, if it was enchanted or
        # equipped" — Koll): the predicate rides condition.filter, not
        # valid_card/valid_source (which only carry the DIES subject's own
        # NonToken/Another gate). CR 301.5c.
        cond = getattr(unit.node, "condition", None)
        cond_filt = getattr(cond, "filter", None) if cond is not None else None
        if cond_filt is not None and _voltron_collective_preds(
            cond_filt, self_subtypes
        ):
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a self-referential "as long as ~ is equipped" CONDITION gating a
        # static/ability (Patriot, Cloud, Auriok Steelshaper) — CR 301.5c.
        if tag_of(cond) == "SourceIsEquipped":
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a condition phase couldn't structure but preserved as raw residue
        # (``Unrecognized`` — Enkira's "~ is equipped, it [must be blocked]"):
        # last-resort text scan for the SAME self-referential "is equipped" /
        # "is enchanted" tell (d), narrow to the two literal phrases. CR 301.5c.
        if tag_of(cond) == "Unrecognized":
            ctext = (getattr(cond, "text", "") or "").lower()
            if "is equipped" in ctext or "is enchanted" in ctext:
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # cast-cost / equip-ability-cost reducers (CR 601.2f / 702.6c): a
        # ``ModifyCost`` static whose spell_filter is Equipment/Aura (Bureau
        # Headmaster, Transcendent Envoy, Cid), a ``ReduceAbilityCost`` static
        # keyed on equip/reconfigure/fortify (Fervent Champion, Éowyn), or a
        # ``CastWithKeyword`` (Flash) grant to Aura/Equipment spells (Sigarda's
        # Aid, CR 702.8a).
        if modify_cost_mode(unit.node) == "Reduce":
            spell_filt = modify_cost_spell_filter(unit.node)
            if spell_filt is not None and (
                {s.lower() for s in filter_subtypes(spell_filt)} & _VOLTRON_SUBTYPES
            ):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        if static_mode_tag(unit.node) == "ReduceAbilityCost":
            kw = static_mode_field(unit.node, "keyword")
            if isinstance(kw, str) and kw.lower() in {
                "equip",
                "reconfigure",
                "fortify",
            }:
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        if static_mode_tag(unit.node) == "CastWithKeyword":
            cwk_filt = effect_filter(unit.node)
            if cwk_filt is not None and (
                {s.lower() for s in filter_subtypes(cwk_filt)} & _VOLTRON_SUBTYPES
            ):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # a granted Equip/Reconfigure/Fortify keyword (Nahiri, Storm of Stone);
        # a static's own ``affected`` filter carrying the attachment-STATE
        # predicate (Hemlock Vial, Blacksmith's Talent, Resistance Reunited) —
        # ``unit.iter_concepts()`` yields the MODIFICATION as the concept
        # node, not the static def that actually carries ``affected``, so
        # this needs the (static_def, mod) pair ``iter_mod_sites`` yields.
        for sdef, mod in iter_mod_sites(unit.node):
            if _voltron_equip_style_keyword(mod):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
            aff = getattr(sdef, "affected", None)
            if aff is not None and _voltron_collective_preds(aff, self_subtypes):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        # the ability's OWN activation cost_reduction scaling on an Equipment/
        # Aura COUNT (Plate Armor: "costs {1} less for each other Equipment
        # you control"). CR 601.2f.
        cred = getattr(unit.node, "cost_reduction", None)
        if cred is not None:
            cred_filt = ref_count_filter(cred, "count")
            if cred_filt is not None and (
                {s.lower() for s in filter_subtypes(cred_filt)} & _VOLTRON_SUBTYPES
            ):
                return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            for filt in (effect_filter(c.node), count_operand_filter(c.node)):
                if filt is not None and _voltron_collective_preds(filt, self_subtypes):
                    return [
                        Signal("voltron_matters", "you", "", c.raw, tree.name, "high")
                    ]
            # a damage/count operand scaled on a bare Equipment/Aura COUNT
            # ("deals damage equal to the number of Equipment you control" —
            # Armed Response; a Sum of two counts — Slash of Light). Distinct
            # from a bare subtype on a TARGET/effect subject (Aura hate /
            # EquippedBy payload), which stays excluded.
            for scale_filt in _voltron_count_filters(c.node):
                if {s.lower() for s in filter_subtypes(scale_filt)} & (
                    _VOLTRON_SUBTYPES
                ):
                    return [
                        Signal("voltron_matters", "you", "", c.raw, tree.name, "high")
                    ]
    # DYNAMIC self-pump on an ATTACHED count (recall gap): "+X/+X for each
    # Aura/Equipment attached to it" (Champion of the Flame, Auramancer's Guise)
    # — the ``AttachedToRecipient`` ObjectCount filter the pump value scales on.
    # The value hides under a ``Multiply`` scalar, so effect_filter /
    # count_operand_filter (read above) never reach it; ``ref_count_filter``
    # unwraps it. CR 301.5c.
    for unit in tree.units:
        for sdef, mod in iter_mod_sites(unit.node):
            if tag_of(mod) not in _DYNAMIC_PT_MODS:
                continue
            filt = ref_count_filter(mod, "value")
            if filt is not None and (set(filter_predicates(filt)) & _ATTACHMENT_PREDS):
                raw = _site_raw(sdef)
                return [Signal("voltron_matters", "you", "", raw, tree.name, "high")]
    # ADR-0039 W7 ledgered bridges — the residual dropped-clause bucket
    # (bridge_ledger.py rows, docstring there for the full corpus
    # accounting): an attachment-count scaling clause dropped to a bare
    # Fixed value (Animal Friend / Sage's Reverie — Judgment Bolt's
    # scaling structured upstream at the v0.35.2 bump and left the row's
    # pins), a trigger condition surviving only in description text
    # (Warchanter Skald), and an unlinked equip-cost alternative-payment
    # PayCost (Forge Anew).
    for bridge_id in (
        "voltron_attach_count_scaling_dropped",
        "warchanter_skald_condition_dropped",
        "forge_anew_equip_cost_paycost_unlinked",
    ):
        if bridge_fires(bridge_id, tree):
            return [Signal("voltron_matters", "you", "", "", tree.name, "high")]
    return []


def _voltron_count_filters(node: TypedMirrorNode) -> list[object]:
    """Every ``ObjectCount`` FILTER an effect's damage/count operand scales on,
    including a top-level ``Sum`` of two Refs (Slash of Light: "the number of
    creatures you control PLUS the number of Equipment you control") in
    addition to the direct / ``Multiply``-wrapped single-Ref form (Armed
    Response; "TWICE the number of Equipment you control" — Nahiri, Heir of
    the Ancients) ``ref_count_filter`` already reads. CR 107.3."""
    filts: list[object] = []
    for fname in ("amount", "count", "value"):
        f = ref_count_filter(node, fname)
        if f is not None:
            filts.append(f)
        val = getattr(node, fname, None)
        if tag_of(val) != "Sum":
            continue
        for expr in getattr(val, "exprs", None) or ():
            if tag_of(expr) != "Ref":
                continue
            qty = getattr(expr, "qty", None)
            if tag_of(qty) == "ObjectCount":
                sf = getattr(qty, "filter", None)
                if sf is not None:
                    filts.append(sf)
    return filts


LANES = (
    _any_counter_makers,
    _minus_counters_matter,
    _excess_damage,
    _kicked_spell_matters,
    _free_cast,
    _plus_one_matters,
    _any_counter_matters,
    _counter_hate,
    _adapt_matters,
    _gain_control,
    _resource_token_makers,
    _proliferate_makers,
    _energy_makers,
    _voltron_makers,
    _voltron_matters,
)
