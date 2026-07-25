"""Crosswalk signal lanes — named-mechanic makers (ring, discover, phasing,
facedown, dice, cast-from-exile), the b5/b7 keyword-field tables, counter-kind
lanes, opponent discard, and cost reduction (split from crosswalk_signals.py)."""

from __future__ import annotations

import re
from dataclasses import fields

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    additional_phase_kind,
    change_zone_dirs,
    color_count_preds,
    condition_tags,
    control_recipient_scope,
    count_operand_filter,
    count_operand_qty,
    counter_kind,
    counter_pred_kinds,
    damage_to_player_trigger_kind,
    discard_recipient_scope,
    effect_filter,
    effect_owner_player_scope,
    filter_controller,
    filter_predicates,
    has_nested_flip_coin,
    iter_condition_sites,
    iter_cost_leaves,
    iter_delayed_trigger_condition_defs,
    iter_static_defs,
    iter_typed_nodes,
    ki_counter_kind_refs,
    mana_restricted_to_multicolored,
    oil_counter_kind_refs,
    permission_tag,
    player_counter_kind,
    power_threshold_preds,
    recipient_tag,
    tag_of,
    trigger_scope,
)
from mtg_utils._card_ir.mirror.runtime import (
    MirrorVariant,
    TypedMirrorNode,
)
from mtg_utils._card_ir.text_idioms import _CAST_FROM_EXILE_P
from mtg_utils._card_ir.tree_synthesis import has_structural_dice_makers
from mtg_utils._deck_forge.bridge_ledger import bridge_fires
from mtg_utils._deck_forge.lanes._shared import (
    _CAST_FROM_EXILE_PERMS,
    _GY_CAST_KEYWORDS,
    _GY_MATTERS_KEYWORDS,
    _OPP_DISCARD_ACTORS,
    _RING_CONDITIONS,
    _discard_watch_is_opponent,
    _kept,
    _target_owner_beneficiary_scope,
    _whole_card_maker,
)
from mtg_utils._deck_forge.signal_base import Signal

_RING_BEARER_REF = re.compile(r"\bring-bearer\b", re.IGNORECASE)


def _ring(tree: ConceptTree) -> list[Signal]:
    """ring_tempters / ring_matters — The Ring Tempts You (CR 701.54).

    MAKER: a ``RingTemptsYou`` effect (the card performs the tempt — Boromir,
    Warden of the Tower) → ``ring_tempters`` (the live maker key). MATTERS,
    three structural shapes:

    * an ``IsRingBearer`` payoff condition (Sauron, the Necromancer — a
      buried Ring-bearer reference with NO tempt trigger, which the typed
      condition recovers STRUCTURALLY where the live path needed a raw
      "ring-bearer" marker);
    * a top-level trigger whose event is ``RingTemptsYou`` (CR 701.54d
      "Whenever the Ring tempts you" — Aragorn, Company Leader; Faramir,
      Field Commander; Galadriel of Lothlórien; Gandalf, Friend of the
      Shire; Nazgûl; Sauron, the Dark Lord; Sméagol, Helpful Guide — a
      payoff for ANY tempt, including one from a DIFFERENT card, not just
      the card's own maker trigger);
    * a whole-card "Ring-bearer" reference the flat condition-tag walk
      doesn't reach (Call of the Ring's "whenever you choose a creature
      as your Ring-bearer"; Dúnedain Rangers' "if you don't control a
      Ring-bearer" tempt-gating condition; Frodo Baggins / Frodo,
      Adventurous Hobbit's "is your Ring-bearer" static-mode condition
      with no decorated concept node; Galadriel, Elven-Queen's "put a
      +1/+1 counter on your Ring-bearer" — a mode-only static/vote-branch
      shape the typed condition walk misses). Mirrors legacy's own
      raw-text discriminator (project.py's ring split: a ``ring_tempt``
      marker whose raw contains "whenever the ring tempts you" or
      "ring-bearer" routes to ring_matters) — a SANCTIONED byte-identical
      mirror for the "ring-bearer" half (the trigger-event half above is
      the honest structural upgrade: legacy's own text match requires the
      literal word "whenever", so it MISSES a "When the Ring tempts you,
      ..." phrasing — Ringwraiths — a genuine crosswalk improvement, not
      shed).

    Both scope "you".
    """
    out: list[Signal] = []
    out += _whole_card_maker(tree, "ring_tempt", "ring_tempters", "you")
    matters = (
        bool(condition_tags(tree) & _RING_CONDITIONS)
        or any(unit.trigger_event == "ringtemptsyou" for unit in tree.units)
        or bool(_RING_BEARER_REF.search(_kept(tree)))
    )
    if matters:
        out.append(Signal("ring_matters", "you", "", "", tree.name, "high"))
    return out


def _discover_makers(tree: ConceptTree) -> list[Signal]:
    """discover_makers — a ``Discover N`` DOER (CR 701.57). Read STRUCTURALLY off the
    typed ``Discover`` effect (Geological Appraiser; the keyword-LESS re-trigger
    "whenever you discover, discover again" also carries a second ``Discover``
    effect — the inner Unimplemented "discover again" action re-decorates to
    concept="discover" via the ADR-0038 clause-grammar recovery ALLOWLIST). A
    "Discover N" granted via a static's ``GrantAbility`` text (Swashbuckler's
    Whip) is never its own concept node at all (folded into the grant's raw
    text) — ``tree_synthesis._arm_discover_makers`` fills that irreducible
    no-node gap, ALSO emitting the real "discover" concept, so this single
    structural read covers both without a marker special-case. A discover-
    PAYOFF trigger with no ``Discover`` effect is a separate lane (out of
    batch). Scope "you"; task #91 — "any" when the discoverer is the OWNER
    of an earlier-targeted permanent (:func:`_target_owner_beneficiary_scope`
    — Zoyowa's Justice's "The owner of target artifact or creature...
    shuffles it into their library. Then that player discovers X": the
    target is unconstrained, so the discoverer could be YOU or an opponent,
    CR 108.3). Unrolled from :func:`_whole_card_maker` (rather than widening
    that shared helper's scope parameter for every OTHER caller — venture/
    amass/incubate/dice/facedown/day-night/phasing all stay a bare "you")
    but preserves its exact first-hit-wins iteration order (whole-card,
    units in order), so membership is unchanged.
    """
    for unit in tree.units:
        for c in unit.effect_concepts("discover"):
            scope = "you"
            if recipient_tag(c.node) == "ParentTargetOwner":
                override = _target_owner_beneficiary_scope(unit)
                if override is not None:
                    scope = override
            return [Signal("discover_makers", scope, "", c.raw, tree.name, "high")]
    return []


def _daynight_makers(tree: ConceptTree) -> list[Signal]:
    """daynight_makers — a ``SetDayNight`` transition DOER (CR 731). The card itself
    flips the day/night state ("it becomes day/night" — Brimstone Vandal, The
    Celestus). The daybound/nightbound transforming werewolves (the PAYOFF that
    flips ON the state) ride a ``daynight_matters`` keyword field-lookup, NOT this
    arm — a daybound werewolf carries no ``SetDayNight`` effect. Scope "you".
    """
    return _whole_card_maker(tree, "set_daynight", "daynight_makers", "you")


# ADR-0038 deferral sweep unit 2: Perch Protection's "If the gift was
# promised, all permanents you control phase out, and until your next
# turn, ..." conditional clause is a NO-RESIDUE gap — phase drops the
# WHOLE segment (no PhaseOut node, no Unimplemented raw carrying the text
# anywhere in the tree; the surrounding CantGainLife/CantLoseLife/
# Protection statics parse fine on their own). Last-resort raw-oracle-text
# idiom match (CR 702.26a's "phase(s) in/out" verb — the SAME idiom
# ALLOWLIST["phasing"]/_THEN_PHASING already trust structurally), a
# reference-arm-style text fallback (ADR-0038) tried only after BOTH
# structural arms above miss. Corpus-verified (65 commander-legal matches):
# every OTHER match is already a "both" member via an existing structural
# arm (cw_only=0 pre-fix), so this fallback is reachable ONLY for the one
# genuine no-residue card — it never second-guesses an already-decided
# card. A "can't phase out" DENIAL (Spatial Binding) also matches the bare
# idiom, but legacy's OWN project.py is equally permissive there (fires
# phasing_makers on ANY "phase out" mention regardless of negation) and
# Spatial Binding already fires via an existing structural arm, so no
# negation guard is needed — this fallback is never the deciding vote for
# a denial-only card in the current corpus. Matched against :func:`_kept`
# (the reminder-stripped oracle), NOT the raw ``tree.oracle`` — the CR
# 702.26a REMINDER text itself carries the identical "phases in or out"
# idiom on every card that merely GRANTS the Phasing keyword to something
# else (Cloak of Invisibility, Shimmer, Teferi's Curse — corpus-caught:
# these 3 flipped cw_only before the strip), never a genuine doer.
_PHASING_TEXT_RE = re.compile(r"\bphase(?:s)?\s+(?:in|out)\b", re.IGNORECASE)


def _phasing_makers(tree: ConceptTree) -> list[Signal]:
    """phasing_makers — a ``PhaseOut`` / ``PhaseIn`` DOER (CR 702.26). Matching the
    live ``phasing`` doer, this is a BLANKET maker (scope "you") that does NOT split
    by direction: a self phase-out (protection — Blink Dog) and an opponent-directed
    phase-out (denial — Divine Smite's "creature an opponent controls phases out")
    both fire. The direction split checklist gate (#6) is moot because the live
    target lane is a single undirected key; collapsing the two directions matches
    it. Scope "you".

    ADR-0037/0038 W3: legacy's OWN project.py deliberately appends a "phasing
    payoff marker" to ANY trigger whose raw mentions "phase out" even when its
    own event categorization is 'other' (test_trigger_other_phasing_payoff_
    marker) — a WATCHER of phasing (The War Doctor: "Whenever one or more
    other permanents phase out, put a time counter on ~") counts as
    phasing_makers too, not just an active doer. Mirrored structurally via
    phase's own native ``PhaseOut``/``PhaseIn`` TRIGGER MODE (normalizes to
    trigger_event "phaseout"/"phasein" — the CR 702.26e "phases out" EVENT a
    permanent's own leaves-play watcher fires on, not text).

    ADR-0038 deferral sweep unit 2: a coin-flip MODAL branch (Frenetic
    Efreet: "Flip a coin. If you win the flip, ~ phases out.") carries its
    PhaseOut effect NESTED inside the ``FlipCoin`` node's own ``win_effect``/
    ``lose_effect`` sub-ability — never a top-level unit effect, so
    ``tree.effect_concepts`` (a per-unit walk) never reaches it.
    :func:`iter_typed_nodes`'s generic deep walk does (the same descent
    precedent as the hand_disruption GrantAbility-nested RevealHand read).
    """
    hits = _whole_card_maker(tree, "phasing", "phasing_makers", "you")
    if hits:
        return hits
    for unit in tree.units:
        if unit.origin == "trigger" and unit.trigger_event in ("phaseout", "phasein"):
            return [Signal("phasing_makers", "you", "", "", tree.name, "high")]
        for c in unit.iter_concepts():
            if c.role != "effect" or tag_of(c.node) != "FlipCoin":
                continue
            for n in iter_typed_nodes(c.node):
                if tag_of(n) in ("PhaseOut", "PhaseIn"):
                    return [
                        Signal("phasing_makers", "you", "", c.raw, tree.name, "high")
                    ]
    if _PHASING_TEXT_RE.search(_kept(tree)):
        return [Signal("phasing_makers", "you", "", "", tree.name, "high")]
    return []


def _voting_makers(tree: ConceptTree) -> list[Signal]:
    """voting_makers — a council/dilemma VOTE the card instructs (CR 701.38). Fires
    on a ``Vote`` effect whose ``voter_scope`` is ``AllPlayers`` ("each player votes"
    — Coercive Portal, Expropriate, Tivit). phase OVER-TAGS the Battlebond
    "for each player, choose friend or foe" mechanic (``voter_scope:
    ControllerLabels`` — Pir's Whim, Zndrsplt's Judgment) and the "each opponent
    chooses X" cards (``voter_scope: EachOpponent`` — Seize the Spotlight, Master of
    Ceremonies) as ``Vote`` too; the ``AllPlayers`` gate excludes them STRUCTURALLY
    — a clean improvement over the live ``_VOTE_EFFECT_GUARD`` raw-idiom regex.
    Scope "each" (every player votes), matching the live structural maker arm.
    """
    for c in tree.effect_concepts("vote"):
        if tag_of(getattr(c.node, "voter_scope", None)) == "AllPlayers":
            return [Signal("voting_makers", "each", "", c.raw, tree.name, "high")]
    return []


def _amass_makers(tree: ConceptTree) -> list[Signal]:
    """amass_makers — an ``Amass N`` DOER (CR 701.47): grow / create a Zombie or
    Orc Army (Aven Eternal, Eternal Taskmaster). A NEW dedicated lane (the live path
    routes amass into the broad ``tokens_matter`` keyword arm); the typed ``Amass``
    effect gives it its own Army-population key. Scope "you".
    """
    return _whole_card_maker(tree, "amass", "amass_makers", "you")


def _incubate_makers(tree: ConceptTree) -> list[Signal]:
    """incubate_makers — an ``Incubate N`` DOER (CR 701.53): make an Incubator token
    with N +1/+1 counters that transforms into a 0/0 artifact creature (Brimaz,
    Blight of Oreskos, Chrome Host Seedshark). A NEW dedicated lane (the live path
    has no incubate key). The Incubator co-feeds ``artifacts_matter`` only when a
    card MAKES the token via ``make_token``; the ``Incubate`` effect is its own
    maker. Scope "you".
    """
    return _whole_card_maker(tree, "incubate", "incubate_makers", "you")


def _amass_incubate_keyword_fallback(
    keywords: frozenset[str], name: str
) -> list[Signal]:
    """amass_makers / incubate_makers — Scryfall KEYWORD-ARRAY fallback (np_boons
    task #1): a genuine bucket-B gap, not a bucket-A projection loss. Some
    amass/incubate spells park the WHOLE "amass Zombies X" / "incubate N" clause
    inside a chained (Draw-then-X, counter-then-X) ability's ``description``
    string with NO effect node of its own at all — not even an ``Unimplemented``
    placeholder the ADR-0038 recovery stage could re-decorate (Commence the
    Endgame: phase's own ``T_effect__Draw`` node carries the FULL description
    "Draw two cards, then amass Zombies X, ..." but its ``effect`` field is bare
    ``Draw``, no sub-ability/sibling at all; Assimilate Essence / Excise the
    Imperfect / Tangled Skyline: an "incubate N" rider on a Counter/Exile/ETB
    effect is folded into a bare ``other``/Unimplemented raw with no allowlisted
    grammar token, since ``parse_clause``/``scan_clause`` don't carry an
    "incubate" verb row). Scryfall's own ``keywords`` array carries ``"Amass"``/
    ``"Incubate"`` for every card that performs the action (CR 701.47/701.53) —
    verified corpus-wide: of 61 Amass-keyword and 32 Incubate-keyword
    commander/brawl-legal cards, every one but these four already fires the
    structural ``_amass_makers``/``_incubate_makers`` read; the keyword bag is a
    precise field-lookup for the remainder, the SAME "route iii" pattern as
    ``_keyword_field_signals``' phasing/lifelink/prowess rows. Corpus-verified
    (same sweep): across every OTHER structurally-firing amass/incubate card,
    the mechanic NEVER also opens ``plus_one_makers`` or ``token_maker`` from
    the Amass/Incubate effect itself (Norn's Inquisitor / Bloated Processor's
    ``plus_one_makers`` comes from a wholly SEPARATE +1/+1-counter clause on
    those cards, not the Incubate rider) — ``amass_makers``/``incubate_makers``
    stay their own dedicated population key by design (see both functions'
    own docstrings), so this fallback mirrors that and fires ONLY the maker
    key, matching the existing membership shape exactly. Scope "you" (CR
    701.47a/701.53a: both actions are performed by the spell/ability's
    controller)."""
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if "amass" in low:
        out.append(Signal("amass_makers", "you", "", "", name, "high"))
    if "incubate" in low:
        out.append(Signal("incubate_makers", "you", "", "", name, "high"))
    return out


def _facedown_makers(tree: ConceptTree) -> list[Signal]:
    """facedown_makers — a ``Manifest`` / ``Cloak`` DOER (CR 701.40 / 701.58 / 708):
    put a card onto the battlefield face down as a 2/2 (Cloudform, Cryptic Coat).
    The ``TurnFaceUp`` effect REFERENCES an existing face-down permanent (a payoff →
    ``facedown_matters``, out of batch) and the ``FaceDown`` filter PREDICATE
    ("face-down creature spells you cast cost less" — Dream Chisel) is the
    cares-about state, NOT a maker — neither surfaces as the ``facedown`` effect
    concept, so both are excluded structurally. The morph / megamorph / disguise /
    manifest-dread printed keywords (no ``Manifest`` / ``Cloak`` effect node — they
    are CAST face down) ride the keyword field-lookup in
    :func:`_keyword_field_signals_b5`. Scope "you".
    """
    return _whole_card_maker(tree, "facedown", "facedown_makers", "you")


def _dice_makers(tree: ConceptTree) -> list[Signal]:
    """dice_makers — a ``RollDie`` DOER (CR 706): the card instructs a die roll
    (Adorable Kitten, the d20 Dungeons & Dragons engines). A "whenever you roll"
    PAYOFF trigger is a separate lane (out of batch). Scope "you".

    Stage-A recovery (ADR-0038): :func:`has_structural_dice_makers` widens
    the flat ``roll_die`` concept-node read (RollDie / RollToVisitAttractions,
    "the *Endeavor cycle", Command Performance) with a nested-tag fallback
    (Clay Golem's Monstrosity cost roll, Captain Rex Nebula's Crash Land
    grant) and the reroll-only synthesis arm (Monitor Monitor, CR 706.8b) —
    ONE shared gate, so this lane never special-cases any of the three.
    """
    if not has_structural_dice_makers(tree):
        return []
    for c in tree.effect_concepts("roll_die"):
        return [Signal("dice_makers", "you", "", c.raw, tree.name, "high")]
    return [Signal("dice_makers", "you", "", "", tree.name, "high")]


def _cast_from_exile_zone_evidence(node: object) -> bool:
    """A structural producer that actually deposits a card IN EXILE (CR 406.1) —
    the gate that separates a genuine cast-from-exile permission from phase's
    reuse of the SAME ``PlayFromExile`` permission tag for a cast-from-GRAVEYARD
    ability (CR 702.34's Flashback governs that zone; Skyclave Shade "you may
    cast it from your graveyard", Ark of Hunger / Tablet of Discovery "Mill a
    card [destination: Graveyard]. You may play that card"). Four typed shapes:
    ``ExileTop`` (its whole point is exile — Abbot of Keral Keep), ``ChangeZone``
    / ``ChangeZoneAll`` with ``destination == "Exile"`` (Campus Renovation's
    recursion-then-exile, Hex Magic), ``Dig`` with ``destination == "Exile"``
    (Gonti, Thief of Sanity), and an ``EffectCost`` wrapping any of the above
    (Primordial Mist pays its OWN exile as the activation cost).
    ``ExileFromTopUntil`` (Territorial Bruntar, Tibalt's Trickery, Black Widow's
    dig-until) is exile BY DEFINITION (the node name), so it isn't gated here —
    :func:`_cast_from_exile_unit_evidence` treats it as always-true alongside
    this predicate.
    """
    tag = tag_of(node)
    if tag == "ExileTop":
        return True
    if tag in ("ChangeZone", "ChangeZoneAll"):
        return getattr(node, "destination", None) == "Exile"
    if tag == "Dig":
        return getattr(node, "destination", None) == "Exile"
    if tag == "EffectCost":
        return _cast_from_exile_zone_evidence(getattr(node, "effect", None))
    return False


def _cast_from_exile_unit_evidence(unit: AbilityUnit) -> bool:
    """Does this UNIT carry exile-zone evidence usable by a
    ``grant_cast_permission`` it contains? Costs always count (paid before the
    grant). Effects only count up to and including the unit's OWN grant (a
    ``ChangeZone{Exile}`` appearing AFTER the grant is a post-hoc redirect —
    Mission Briefing's "if that spell would be put into your graveyard, exile
    it instead" describes the SPELL'S FATE after casting FROM THE GRAVEYARD,
    not its source zone, so it does not count). A unit with no grant of its
    own (Muse Vessel's exile-into-the-artifact ability, read by a SEPARATE
    activated ability's grant) scans its full effect list.
    """
    for c in unit.costs:
        if _cast_from_exile_zone_evidence(c.node) or tag_of(c.node) == (
            "ExileFromTopUntil"
        ):
            return True
    effs = list(unit.effects)
    grant_idx = next(
        (i for i, c in enumerate(effs) if c.concept == "grant_cast_permission"),
        None,
    )
    scan = effs if grant_idx is None else effs[: grant_idx + 1]
    return any(
        _cast_from_exile_zone_evidence(c.node) or tag_of(c.node) == "ExileFromTopUntil"
        for c in scan
    )


def _cast_from_exile(tree: ConceptTree) -> list[Signal]:
    """cast_from_exile — a play/cast-FROM-EXILE build-around (CR 406.1 / 601.2 /
    601.3 / 702.170d). Reads the ``GrantCastingPermission`` effect's
    ``permission`` node STRUCTURALLY (:func:`permission_tag`): ``PlayFromExile``
    (impulse exile-and-play — Act on Impulse, Abbot of Keral Keep) or
    ``Plotted`` (plot — Aloe Alchemist, unconditional: CR 702.170d's exile is
    inherent to activating Plot itself, and phase's ``description`` for a
    keyword-ability unit is the templated short form with no reminder text to
    corpus-check against). This is the batch's marquee fidelity gain — the live
    path kept a byte-identical word-mirror because the OLD lossy IR dropped the
    from-exile zone off the cast.

    ``PlayFromExile`` additionally requires :func:`_cast_from_exile_unit_evidence`
    on SOME unit of this face (corpus census, 2026-07: phase emits the SAME
    ``PlayFromExile`` tag for a handful of cast-from-GRAVEYARD abilities that
    happen to use the same "you may cast/play it [later]" shape — a real
    zone-fidelity gap in the substrate, not something clause-grammar growth can
    fix from here; CR 702.34 Flashback governs that zone, not CR 406). Named,
    corpus-verified sheds (6, all commander-legal, 2026-07 census): Ark of
    Hunger / Tablet of Discovery (``Mill`` destination Graveyard, no exile
    anywhere), Skyclave Shade / Hildibrand Manderville / Mosswood Dreadknight
    ("you may cast it from your graveyard as an Adventure" — a dies-rider
    distinct from the standard exile-based Adventure recast, which phase
    doesn't represent as a grant node at all on either face), Mission Briefing
    (chooses a graveyard card to cast; the ``ChangeZone{Exile}`` sibling is a
    POST-cast redirect, not the source).

    Keyword cast-from-exile mechanics (foretell / suspend) are kept OUT of this
    lane (they have their own maker field-lookups), avoiding double counting;
    a plain ``Exile`` removal (Banisher Priest, Path to Exile) carries no
    permission → no fire.

    TEXT-IDIOM FALLBACK (bucket-d, reminder-stripped kept idiom): a self-cast
    permission phase represents via a bare ``CastFromZone`` effect carrying NO
    zone at all (Eternal Scourge, Misthollow Griffin), a payoff Trigger with
    ``spell_cast_origin: NotEquals(Hand)`` (Vega's "cast a spell from anywhere
    other than your hand" — deliberately NOT read as its own structural arm:
    ``CastFromZone`` is a GENERIC any-zone cast-permission node phase reuses
    for graveyard-cast grants too — Yawgmoth's Will, Snapcaster Mage, Torrential
    Gearhulk — so treating its bare presence as evidence would flood the lane
    with graveyard recursion), or a dropped-zone static (Squee's "from your
    graveyard or from exile" collapses to ``active_zones=['Graveyard']``,
    losing the exile branch entirely — a genuine phase information-loss gap,
    not fixable without clause-grammar growth from here). Reuses
    :func:`mtg_utils._card_ir.supplement._CAST_FROM_EXILE_P` — the SAME
    six-armed word-grammar the OLD projection's
    ``_recover_cast_from_exile_zone`` already runs against this exact oracle
    text (not a new grammar; corpus census, 2026-07: matches all 60
    commander-legal live_only cards, ZERO of the 6 named sheds above). CR
    601.3b / 702.143.
    """
    grant: ConceptNode | None = None
    for unit in tree.units:
        for c in unit.effects:
            if c.concept != "grant_cast_permission":
                continue
            tag = permission_tag(c.node)
            if tag not in _CAST_FROM_EXILE_PERMS:
                continue
            if tag == "Plotted":
                return [Signal("cast_from_exile", "you", "", c.raw, tree.name, "high")]
            grant = grant or c
    if grant is not None and any(
        _cast_from_exile_unit_evidence(unit) for unit in tree.units
    ):
        return [Signal("cast_from_exile", "you", "", grant.raw, tree.name, "high")]
    stripped = re.sub(r"\([^)]*\)", " ", tree.oracle or "")
    low = stripped.lower()
    if (
        "exile" in low or "plot" in low or "anywhere other than your hand" in low
    ) and _CAST_FROM_EXILE_P.run(stripped) is not None:
        return [Signal("cast_from_exile", "you", "", "", tree.name, "high")]
    return []


# Batch-5 Scryfall-keyword field-lookups (checklist #3 — NO typed effect tag for
# these; the live path keeps them as keyword survivors). Each keyword tags the
# BEARER / enabler (the maker), NOT a payoff (unlike Explore / Connive whose
# keyword also tags payoffs), so a clean keyword array read is precise.
_FORETELL_KEYWORDS: frozenset[str] = frozenset({"foretell"})
_CASCADE_KEYWORDS: frozenset[str] = frozenset({"cascade"})
_SUSPEND_KEYWORDS: frozenset[str] = frozenset({"suspend"})
# infect / toxic / poisonous (CR 702.90 / 702.164) — the poison-counter DEALERS.
_POISON_KEYWORDS: frozenset[str] = frozenset({"infect", "toxic", "poisonous"})
# daybound / nightbound (CR 702.145) — the transforming werewolves REWARDED by the
# day↔night flip (the daynight_matters payoff side).
_DAYNIGHT_KEYWORDS: frozenset[str] = frozenset({"daybound", "nightbound"})
# The face-down 2/2 KEYWORD makers (CR 708): morph / megamorph (702.37) and
# disguise (702.168) are CAST face down and ride the Scryfall keyword array (phase
# emits no Manifest/Cloak effect for them); manifest dread (701.55) likewise.
# manifest / cloak ALSO carry the keyword (the structural ``facedown`` effect arm
# dedups the overlap). Every keyword puts a face-down permanent on the battlefield
# → the maker lane. Exact-key match keeps "Ceremorphosis" (morph substring) out.
_FACEDOWN_KEYWORDS: frozenset[str] = frozenset(
    {"morph", "megamorph", "disguise", "manifest", "cloak", "manifest dread"}
)


def _keyword_field_signals_b5(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-5 Scryfall-keyword field-lookups (checklist #3 survivors):

    * ``foretell`` → ``foretell_makers`` you (CR 702.143);
    * ``cascade`` → ``cascade_makers`` you (CR 702.85);
    * ``suspend`` → ``suspend_makers`` you (CR 702.62);
    * ``infect`` / ``toxic`` / ``poisonous`` → ``poison_makers`` opponents (CR
      702.90 / 702.164 — the poison-counter dealers; a ``OpponentPoisonAtLeast``
      Corrupted PAYOFF with no such keyword stays out, the typed condition being a
      separate ``poison_matters`` lane);
    * ``daybound`` / ``nightbound`` → ``daynight_matters`` you (CR 702.145);
    * morph / megamorph / disguise / manifest / cloak / manifest dread →
      ``facedown_makers`` you (CR 708 — every face-down 2/2 maker; the
      keyword-only morph / disguise bodies carry NO ``Manifest`` / ``Cloak``
      effect, so the keyword array is the uniform anchor over all six, deduped
      against the structural :func:`_facedown_makers` arm).

    Reading the STRUCTURED keyword array (not oracle text) makes the lanes immune to
    the name / ability-word collisions the deleted regex floors suffered (a card
    naming the mechanic only in its title can never carry the keyword). ADR-0038
    W3 batch 4: the poison GRANTERS ("gains infect") and the structural
    ``GivePlayerCounter:poison`` givers phase carries off the keyword array are
    now recovered — the former by ``_player_counter_makers``'s
    ``_POISON_WORD_MIRROR`` whole-card fallback, the latter by its
    ``_PLAYER_COUNTER_MAKER["poison"]`` row.
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _FORETELL_KEYWORDS:
        out.append(Signal("foretell_makers", "you", "", "", name, "high"))
    if low & _CASCADE_KEYWORDS:
        out.append(Signal("cascade_makers", "you", "", "", name, "high"))
    if low & _SUSPEND_KEYWORDS:
        out.append(Signal("suspend_makers", "you", "", "", name, "high"))
    if low & _POISON_KEYWORDS:
        out.append(Signal("poison_makers", "opponents", "", "", name, "high"))
    if low & _DAYNIGHT_KEYWORDS:
        out.append(Signal("daynight_matters", "you", "", "", name, "high"))
    if low & _FACEDOWN_KEYWORDS:
        out.append(Signal("facedown_makers", "you", "", "", name, "high"))
    return out


def _keyword_field_signals(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-4 Scryfall-keyword field-lookups — survivor routes the live path
    DELIBERATELY keeps because phase carries no effect node (checklist #3):

    * cast-from-GY family (flashback / escape / …) → ``graveyard_makers`` you;
    * dredge / delve / scavenge → ``graveyard_matters`` you;
    * ``spectacle`` (the condition is reminder-text-only, no structural ``LoseLife``)
      → ``lifeloss_matters`` opponents;
    * ``goad`` → ``goad_makers`` opponents — UNLIKE explore / connive (whose keyword is
      ALSO carried by PAYOFFS — Wildgrowth Walker, Copycrook — forcing structural-only
      there), the Scryfall ``Goad`` keyword marks only the ACTION's makers (every
      goader, incl. the Impetus / Bloodthirsty-Blade auras that goad the enchanted
      creature), so the field-lookup is precise (CR 701.15a).
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _GY_CAST_KEYWORDS:
        out.append(Signal("graveyard_makers", "you", "", "", name, "high"))
    if low & _GY_MATTERS_KEYWORDS:
        out.append(Signal("graveyard_matters", "you", "", "", name, "high"))
    if "spectacle" in low:
        out.append(Signal("lifeloss_matters", "opponents", "", "", name, "high"))
    if "goad" in low:
        out.append(Signal("goad_makers", "opponents", "", "", name, "high"))
    # recall-completion b1 (ADR-0034): prowess (CR 702.108) is a you-cast
    # Spellslinger payoff — the creature is rewarded when you cast a noncreature
    # spell. The deleted ``_signals_ir`` read it off the Scryfall keyword array (~line
    # 824);
    # no prowess row existed in the crosswalk keyword tables.
    if "prowess" in low:
        out.append(Signal("spellcast_matters", "you", "", "", name, "high"))
    # recall-completion (ADR-0034/0035 Stage-A): the OWN printed lifelink keyword
    # marks a lifegain SOURCE — a lifelink bearer gains life in combat (CR
    # 702.15b), the MAKER arm. Mirrors the deleted ``_signals_ir``'s
    # ``_IR_KEYWORD_MAP["lifelink"]``
    # → ``lifegain_makers`` you. The ``_lifegain_makers`` typed lane reads only a
    # ``gain_life`` effect + a GRANTED ``AddKeyword(Lifelink)``, so a vanilla-
    # lifelink creature (no grant node) was the residual ``live_only`` gap.
    if "lifelink" in low:
        out.append(Signal("lifegain_makers", "you", "", "", name, "high"))
    # ADR-0037/0038 W3: the printed Phasing KEYWORD (CR 702.26a) carries NO
    # effect node at all — phase emits it purely as a keyword-array entry
    # (Breezekeeper: keywords=["Flying", "Phasing"], zero abilities/
    # triggers/statics) — so the structural ``_phasing_makers`` lane's
    # ``PhaseOut``/``PhaseIn`` effect-node read never reaches it. Mirrors
    # the deleted ``_signals_ir``'s own keyword-field route for this exact keyword.
    if "phasing" in low:
        out.append(Signal("phasing_makers", "you", "", "", name, "high"))
    return out


# ── Batch 6 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# place_counter ``counter_type`` (upper-cased) → its off-+1/+1 MAKER lane (CR
# 122.1). The card PERFORMS the placement. p1p1 / m1m1 are ported elsewhere.
_PLACE_COUNTER_MAKER_KINDS: dict[str, str] = {
    "OIL": "oil_counter_makers",
    "KI": "ki_counter_makers",
    "SHIELD": "shield_counter_makers",
}
# Predicate-side counter-KIND payoff routing (CR 122.1) — mirrors the live
# ``_COUNTER_KIND_KEYS`` dispatch a "creature WITH an X counter" subject filter
# rides. Only ``oil`` has a structural payoff filter in the v0.9.0 substrate
# (the ki / shield counter PAYOFFS are cost-side "remove an X counter" or
# un-structured → a documented ``live_only`` residue); the full map is kept for
# fidelity (the unported ki_counter_matters key slices out in the extractor).
_COUNTER_PRED_LANES: dict[str, tuple[str, str]] = {
    "oil": ("oil_counter_matters", "you"),
    "shield": ("shield_counter_makers", "you"),
    "rad": ("rad_counter_makers", "opponents"),
    "ki": ("ki_counter_matters", "you"),
}
# GivePlayerCounter ``counter_kind`` (lower-cased) → its player-resource MAKER
# lane + the FIXED lane scope (CR 122.1 / 728). rad lands on opponents (a kill
# clock — the live ``_PLAYER_COUNTER_KEYS`` scopes it ``opponents`` regardless of
# the giver's recipient); experience is a personal resource (scope ``you``).
# ADR-0038 W3 batch 4 (combat-damage cluster): the poison giver ALSO belongs
# here — a direct ``GivePlayerCounter(poison)`` DOER (Pit Scorpion, Marsh
# Viper, Decimator Web, Caress of Phyrexia, Vraska's Fall — "that player gets
# N poison counters" with NO infect/toxic/poisonous keyword at all) is a
# poison_makers member the keyword-array arm (``_keyword_field_signals_b5``)
# can't reach (CR 120.3b / 104.3d — poison counters, no static ability
# involved). Fixed scope ``opponents`` (a kill clock, same as rad).
_PLAYER_COUNTER_MAKER: dict[str, tuple[str, str]] = {
    "rad": ("rad_counter_makers", "opponents"),
    "experience": ("experience_makers", "you"),
    "poison": ("poison_makers", "opponents"),
}
# Player-reference tags naming an opponent — the only direction that takes a
# party/poison-style count off YOUR resource (CR 700.8 — "your party").
_OPP_PLAYER_TAGS: frozenset[str] = frozenset({"Opponent", "Opponents", "EachOpponent"})


def _counter_kind_lanes(tree: ConceptTree) -> list[Signal]:
    """oil / ki / shield counter lanes (CR 122.1). Three structural arms:

    * **MAKER** — a ``place_counter`` (``PutCounter`` / ``PutCounterAll``) whose
      ``counter_type`` is an off-+1/+1 ported kind (oil / ki / shield), mirroring
      ``plus_one_makers`` / ``minus_counters_matter``. The card PERFORMS the
      placement (Glistener Seer's oil, Petalmane Baku's ki, Boon of Safety's
      shield). The kind discriminates — a +1/+1 / loyalty placement never fires.
    * **MATTERS (flat)** — a non-cost subject / count-operand filter carrying a
      ``Counters`` predicate of a ported kind (Urabrask's Anointer scales off "oil
      counters on creatures you control"). Routed via :data:`_COUNTER_PRED_LANES`,
      controller-gated against an opponent filter (checklist #6). Only oil has a
      structural payoff filter in v0.9.0; ki / shield payoffs are cost-side and
      stay ``live_only``.
    * **MATTERS (deep, oil / ki)** — :func:`oil_counter_kind_refs`'s whole-unit
      deep walk (ADR-0038 batch-2), for an oil reference phase buries below the
      flat concept-node level (Armored Scrapgorger / Ichor Synthesizer's static
      ``condition``, Ichorplate Golem's static ``affected``, Kuldotha Cackler's
      scaling Pump, Cinderslash Ravager's cost-reduction, Oil-Gorger Troll's
      gating sub-ability), PLUS its ADR-0039 W8 sibling
      :func:`ki_counter_kind_refs` for the Kamigawa flip cycle's triggered
      ``HasCounters`` self-check ("if there are two or more ki counters on
      ~, you may flip it" — Faithful Squire, Callow Jushi, Hired Muscle,
      Cunning Bandit, Budoka Pupil), which lives on the trigger's own
      ``condition`` field, above the flat walk's ``Unimplemented(name=
      'flip')`` effect node. shield stays on the flat read only.
    """
    out: list[Signal] = []
    seen: set[tuple[str, str]] = set()

    def fire(key: str, scope: str, raw: str) -> None:
        if (key, scope) not in seen:
            seen.add((key, scope))
            out.append(Signal(key, scope, "", raw, tree.name, "high"))

    for c in tree.effect_concepts("place_counter"):
        key = _PLACE_COUNTER_MAKER_KINDS.get(counter_kind(c.node).upper())
        if key:
            fire(key, "you", c.raw)
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if filt is None or filter_controller(filt) == "Opponent":
                continue
            for kind in counter_pred_kinds(filt):
                lane = _COUNTER_PRED_LANES.get(kind.lower())
                if lane:
                    fire(lane[0], lane[1], c.raw)
    for unit in tree.units:
        if ki_counter_kind_refs(unit.node):
            fire("ki_counter_matters", "you", "")
        if oil_counter_kind_refs(unit.node):
            fire("oil_counter_matters", "you", "")
    return out


_RAD_REF = re.compile(r"\brad counters?\b", re.IGNORECASE)
# ADR-0038 W3 batch 4 — a SANCTIONED byte-identical mirror of legacy's
# whole-card poison_makers word regex (the deleted ``_signals_ir``'s
# ``_IR_KEPT_DETECTORS`` "poison_makers" row): the keyword-array arm
# (``_keyword_field_signals_b5``) only sees infect/toxic/poisonous on the
# BEARER's own Scryfall keyword list, missing every GRANTED occurrence —
# an Aura/anthem/static that gives the word to ANOTHER creature (Snake Cult
# Initiation "has poisonous 3", Virulent Sliver "have poisonous 1",
# Corrupted Conscience / Phyresis "has infect", Triumph of the Hordes
# "gain ... infect", token-definition grants inside a CreateToken's own
# ability text — Basilica Shepherd's toxic Mites). CR 702.90/702.70/702.164.
_POISON_WORD_MIRROR = re.compile(r"\bpoisonous\b|\btoxic\b|\binfect\b", re.IGNORECASE)


def _has_native_rad_counter(tree: ConceptTree) -> bool:
    """Whether a NATIVE rad-kind counter source already fires structurally
    (a ``GivePlayerCounter`` OR a ``PutCounter`` typed to "rad") — the
    ADR-0038 whole-card residue mirror's gate, mirroring old-IR's own
    ``has_rad`` check (``project.py``'s ``_RAD_REF`` face marker)."""
    for c in tree.effect_concepts("give_player_counter"):
        if player_counter_kind(c.node).lower() == "rad":
            return True
    for c in tree.effect_concepts("place_counter"):
        if counter_kind(c.node).upper() == "RAD":
            return True
    return False


def _player_counter_makers(tree: ConceptTree) -> list[Signal]:
    """rad_counter_makers / experience_makers / poison_makers — a
    ``GivePlayerCounter`` DOER (CR 122.1i / 728 / 120.3b) OR a rad-counter
    clause phase mangles/drops entirely (a whole-card residue mirror). The
    card gives a player a rad (a mill-and-bleed kill clock, fixed scope
    ``opponents``), an experience counter (a personal resource, scope
    ``you``), or a poison counter (ADR-0038 W3 batch 4 — Pit Scorpion, Marsh
    Viper, Decimator Web: a direct "gets a poison counter" giver with no
    infect/toxic/poisonous keyword at all, joining the keyword-bearer arm in
    ``poison_makers``, scope ``opponents``) — read off the typed
    ``counter_kind``, the kind the OLD lossy IR split into per-kind effect
    categories. Tato Farmer → rad; Mizzix / Ezuri → experience.

    ADR-0038 W1 batch-4: most rad clauses land as an Unimplemented "get ...
    rad counters" effect (Contaminated Drink, Feral Ghoul, Mariposa
    Military Base, Nuclear Fallout, Nuka-Nuke Launcher, Struggle for
    Project Purity, Vexing Radgull), inside a granted quoted ability text
    with no node at all (Harold and Bob, First Numens), or on the OTHER
    direction entirely ("loses all rad counters" — Survivor's Med Kit).
    The shared clause grammar's generic "get(s) ... counter(s)" token is
    KIND-BLIND (it also matches +1/+1, ki, oil, shield, poison, energy —
    recovering it to a concrete concept would misroute every OTHER
    counter kind sharing that idiom), so this is NOT a
    :data:`recovery.ALLOWLIST` case. Legacy's OWN detection for this key
    is likewise a WHOLE-CARD raw-text fallback (``project._RAD_REF``,
    scope "opponents", gated to cards with no structural rad effect, ANY
    direction) — mirrored byte-for-byte here (a SANCTIONED byte-identical
    mirror port, like the stax census / entered_attacker lanes) rather
    than widened into the shared grammar.
    """
    out: list[Signal] = []
    seen: set[str] = set()
    for c in tree.effect_concepts("give_player_counter"):
        lane = _PLAYER_COUNTER_MAKER.get(player_counter_kind(c.node).lower())
        if lane and lane[0] not in seen:
            seen.add(lane[0])
            out.append(Signal(lane[0], lane[1], "", c.raw, tree.name, "high"))
    if (
        "rad_counter_makers" not in seen
        and not _has_native_rad_counter(tree)
        and _RAD_REF.search(_kept(tree))
    ):
        out.append(Signal("rad_counter_makers", "opponents", "", "", tree.name, "high"))
    # ADR-0038 W3 batch 4 — a poison GivePlayerCounter buried inside a
    # CreateToken's OWN granted-ability definition (Serpent Generator:
    # "Create a ... token. It has 'Whenever this creature deals damage to
    # a player, that player gets a poison counter.'"). The top-level
    # ``effect_concepts`` walk only sees the CreateToken effect itself,
    # never the created token's own nested ability tree; a deep walk
    # (:func:`iter_typed_nodes`) reaches it (CR 111.7 — a token's copiable
    # values include its printed abilities). The SAME deep walk also
    # reaches a poison giver buried inside a ``CreateEmblem``'s granted
    # trigger (Ajani, Sleeper Agent's ultimate: "You get an emblem with
    # 'Whenever you cast a creature or planeswalker spell, target
    # opponent gets two poison counters.'" — CR 114.1). This is an
    # ADJUDICATED GAIN over legacy: the OLD lossy IR projects the whole
    # "You get an emblem with ..." clause as ONE opaque ``emblem``-
    # category effect with no further decomposition at all (verified via
    # ``old_ir_for`` — no ``GivePlayerCounter`` sub-effect survives), so
    # legacy's poison_makers can never see into it; the crosswalk's
    # structural deep walk is strictly more precise (CR 122.1 / 114.1).
    if "poison_makers" not in seen:
        for unit in tree.units:
            if any(
                tag_of(n) == "GivePlayerCounter"
                and player_counter_kind(n).lower() == "poison"
                for n in iter_typed_nodes(unit.node)
            ):
                seen.add("poison_makers")
                out.append(
                    Signal("poison_makers", "opponents", "", "", tree.name, "high")
                )
                break
    if "poison_makers" not in seen and _POISON_WORD_MIRROR.search(_kept(tree)):
        out.append(Signal("poison_makers", "opponents", "", "", tree.name, "high"))
    return out


def _count_operand_lanes(tree: ConceptTree) -> list[Signal]:
    """devotion / party / domain / experience_matters — a NAMED count-operand
    SCALER payoff (CR 700.5 / 700.6 / 700.8 / 122.1). Reads the qty tag of an
    effect's (or static P/T mod's) dynamic count operand
    (:func:`count_operand_qty`):

    * ``Devotion`` / ``DevotionGE`` → ``devotion_matters`` (Gray Merchant, a
      "lose life equal to your devotion" scaler) — intrinsically your permanents
      (CR 700.5), no extra gate;
    * ``PartySize`` → ``party_matters`` (Burakos), gated off an opponent's-party
      reference (checklist #6);
    * ``BasicLandTypeCount`` → ``domain_matters`` (Tribal Flames), controller-
      gated against an opponent's lands (the old "not modeled" classification was
      wrong — the substrate carries ``BasicLandTypeCount``);
    * ``PlayerCounter`` with ``kind == experience`` → ``experience_matters``
      (Ezuri's "+1/+1 counter for each experience counter you have"); a ``Poison``
      PlayerCounter (Mycosynth Fiend) is gated out by the kind check (it is a
      separate ``poison_matters`` lane). All scope ``you``.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        qty = count_operand_qty(c.node)
        if qty is None:
            continue
        t = tag_of(qty)
        if t in ("Devotion", "DevotionGE"):
            fire("devotion_matters", c.raw)
        elif t == "PartySize" and (
            tag_of(getattr(qty, "player", None)) not in _OPP_PLAYER_TAGS
        ):
            fire("party_matters", c.raw)
        elif t == "BasicLandTypeCount" and (
            getattr(qty, "controller", None) != "Opponent"
        ):
            fire("domain_matters", c.raw)
        elif t == "PlayerCounter" and (
            str(getattr(qty, "kind", "")).lower() == "experience"
        ):
            fire("experience_matters", c.raw)
    # recall-completion b2 (ADR-0034): the DIRECT (non-Ref) named scaler on an
    # effect's PRIMARY amount. count_operand_qty above only catches a Ref DIRECTLY
    # on amount/count/value (plus AddDynamicPower statics), so a scaler nested under
    # a Pump.power/toughness Quantity (Aspect of Hydra), an Offset.inner (Artillery
    # Blast's "1 plus your domain"), a Mana.produced.count (Ardent Electromancer's
    # party mana), or a static ModifyCost.dynamic_count (Daybreak Chimera's devotion
    # cost-reduction) is missed. The old IR reads e.amount.op=='devotion'/'party'/
    # 'domain' — but only via a supplement ORACLE recovery ("devotion to", "your
    # party", "basic land types"); this reads the scaler STRUCTURALLY off the
    # substrate (ADR-0035 prefer-structural). Devotion / PartySize / BasicLandType-
    # Count are EXCLUSIVELY count operands (CR 700.5 / 700.6 / 700.8), never filter
    # predicates, so the deep-node walk cannot collide with a subject/target filter.
    # Keeps the party opponent's-party gate and the domain opponent-controller gate.
    # Chroma (phase emits it AS a Devotion node — Heartlash Cinder, Primalcrux) rides
    # devotion_matters, a genuine catch the oracle-regex IR misses; DevotionGE gods
    # (Nykthos, Nylea's as-long-as gate) fire too, matching the IR devotion-condition
    # arm.
    for unit in tree.units:
        for node in iter_typed_nodes(unit.node):
            st = tag_of(node)
            if st in ("Devotion", "DevotionGE"):
                fire("devotion_matters", "")
            elif st == "PartySize" and (
                tag_of(getattr(node, "player", None)) not in _OPP_PLAYER_TAGS
            ):
                fire("party_matters", "")
            elif st == "BasicLandTypeCount" and (
                getattr(node, "controller", None) != "Opponent"
            ):
                fire("domain_matters", "")
    return out


def _modified_matters(tree: ConceptTree) -> list[Signal]:
    """modified_matters — a Kamigawa-NEO "modified creature" payoff (CR 700.9: a
    permanent is modified if it has a counter, is equipped, or is enchanted by an
    Aura its controller controls). phase DERIVES the CR-700.9 union as a single
    ``Modified`` predicate, so the lane reads that tag off a non-cost subject /
    count-operand / static-affected filter, controller-gated to ``You`` (Chishiro,
    Thundering Raiju). A removal "destroy target modified creature" (controller
    any) is NOT a build-around. The bare ``\\bmodified\\b`` word references stay a
    ``live_only`` mirror. Scope ``you``.
    """
    for c in tree.iter_concepts():
        if c.role == "cost":
            continue
        for filt in (effect_filter(c.node), count_operand_filter(c.node)):
            if (
                filt is not None
                and "Modified" in filter_predicates(filt)
                and filter_controller(filt) == "You"
            ):
                return [Signal("modified_matters", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if not unit.statics:
            continue
        aff = getattr(unit.node, "affected", None)
        if (
            aff is not None
            and "Modified" in filter_predicates(aff)
            and filter_controller(aff) == "You"
        ):
            return [Signal("modified_matters", "you", "", "", tree.name, "high")]
    # recall-completion b2 (ADR-0034): the TRIGGER-subject Modified predicate. The
    # effect_filter / count_operand_filter / static-affected reads above never see a
    # trigger's watched subject, so "whenever a MODIFIED creature you control
    # attacks / deals combat damage" (Arna Kennerüd, Kami of Celebration, One with
    # the Kami) was missed. Reads the trigger's ``valid_card`` for a Modified
    # predicate, controller You (a symmetric / opponent modified reference is not a
    # your-board payoff — same gate the effect arm uses). CR 700.9.
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if (
            vc is not None
            and "Modified" in filter_predicates(vc)
            and filter_controller(vc) == "You"
        ):
            return [Signal("modified_matters", "you", "", "", tree.name, "high")]
    return []


def _predicate_build_around(tree: ConceptTree) -> list[Signal]:
    """multicolor / colorless / power / low_power / vanilla matters — color- and
    P/T-property BUILD-AROUND lanes (CR 105.2 / 208.1 / 113.3). Mirrors the
    deleted legacy IR engine's ``_predicate_build_around_lanes`` over a non-cost subject
    /
    count-operand / static-affected filter, scope ``you``:

    * **multicolor_matters** — a ``ColorCount`` ``GE``≥2 / ``EQ``≥2 predicate
      (Knight of New Alara's "other multicolored creatures you control"),
      controller ``You`` (a single-color / hoser reference is not a build-around);
    * **colorless_matters** — a ``ColorCount`` ``EQ 0`` predicate (Forsaken
      Monument; Ancient Stirrings' unscoped reveal), controller ``You`` or
      unscoped (the regex reads colorless unscoped too);
    * **power_matters** / **low_power_matters** — a FIXED ``PtComparison`` on
      Power, split by comparator direction (``GE``/``GT`` high — Shaman of the
      Great Hunt; ``LE``/``LT`` low — Arabella), controller ``You``. A relative /
      dynamic comparison (the old ``:*``) is a fight-style check, excluded by
      :func:`power_threshold_preds`. A "destroy target creature with power 4 or
      greater" removal (controller any — Big Game Hunter) never fires;
    * **vanilla_matters** — a ``HasNoAbilities`` predicate (Muraganda, Ruxa),
      controller ``You`` or unscoped (a shared-board static is unscoped).

    The condition-subject power gate (Challenger Troll's Ferocious "as long as you
    control a creature with power 4+") and the trigger-subject sites the substrate
    does not surface through ``iter_concepts`` are a documented ``live_only``
    residue.
    """
    out: list[Signal] = []
    seen: set[str] = set()

    def fire(key: str, raw: str) -> None:
        if key not in seen:
            seen.add(key)
            out.append(Signal(key, "you", "", raw, tree.name, "high"))

    def handle(filt: object, raw: str) -> None:
        if filt is None:
            return
        ctrl = filter_controller(filt)
        you = ctrl == "You"
        shared = ctrl in ("You", "Any", None)  # you or an unscoped global
        for cmp_, cnt in color_count_preds(filt):
            if cmp_ == "EQ" and cnt == 0:
                if shared:
                    fire("colorless_matters", raw)
            elif you and ((cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)):
                fire("multicolor_matters", raw)
        if you:
            for stat, cmp_, _v in power_threshold_preds(filt):
                if stat != "Power":
                    continue
                if cmp_ in ("GE", "GT"):
                    fire("power_matters", raw)
                elif cmp_ in ("LE", "LT"):
                    fire("low_power_matters", raw)
        if shared and "HasNoAbilities" in filter_predicates(filt):
            fire("vanilla_matters", raw)

    for c in tree.iter_concepts():
        if c.role == "cost":
            # ADR-0037/0038 W3: a COST-role colorless filter is still a
            # genuine cares-about hook (Barrage Tyrant: "Sacrifice
            # ANOTHER colorless creature" as an activation cost) — narrow
            # exception, colorless_matters ONLY (multicolor/power/vanilla
            # stay cost-role-excluded per the original checklist gate: an
            # unrelated "sacrifice a creature" cost must not open EVERY
            # creature-type-matters lane, but a color-FILTERED sac cost
            # is unambiguously a colorless build-around). The cost NODE
            # itself is often a ``Composite`` bundling Mana + Sacrifice —
            # :func:`iter_cost_leaves` recurses ``costs`` lists to the
            # Sacrifice leaf that actually carries the ``target`` filter.
            for leaf in iter_cost_leaves(c.node):
                filt = effect_filter(leaf)
                if filt is not None and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(filt)
                ):
                    fire("colorless_matters", c.raw)
                    break
            continue
        handle(effect_filter(c.node), c.raw)
        handle(count_operand_filter(c.node), c.raw)
    for unit in tree.units:
        # ADR-0038 W3 batch 2 unit 5: every static-ability DEF reachable
        # from this unit (top-level OR nested inside a one-shot
        # ``GenericEffect.static_abilities`` — Merry-Go-Round's Attraction
        # Visit granting horsemanship "until end of turn"; the
        # :func:`iter_mod_sites` sibling walk, but def-level not mod-level
        # since a mode-only static like Delney's CantBeBlockedBy carries no
        # ``modifications`` list to pair with).
        for defn in iter_static_defs(unit.node):
            handle(getattr(defn, "affected", None), "")
        if unit.origin == "trigger":
            # The trigger's OWN watched-subject filter ("whenever a
            # creature you control with power N or less enters/attacks" —
            # Ezuri, Cavalcade of Calamity) is a build-around exactly like
            # an effect/static filter; ``iter_concepts`` never surfaces a
            # trigger's ``valid_card`` as a role=effect/cost/static concept
            # of its own, so it needs this dedicated read.
            handle(getattr(unit.node, "valid_card", None), "")
        elif unit.origin == "ability":
            # An activated ability's OWN top-level ``target`` (Subira,
            # Tulzidi Caravanner's "Another target creature with power 2 or
            # less can't be blocked" — the PtComparison lives on the
            # ability's target, not the nested CantBeBlocked static's bare
            # ParentTarget ``affected``).
            handle(getattr(unit.node, "target", None), "")
        for trig in iter_delayed_trigger_condition_defs(unit.node):
            # A CreateDelayedTrigger's OWN watcher (Subira's second
            # ability: "Until end of turn, whenever a creature you control
            # with power 2 or less deals combat damage …" — the filter
            # lives on the delayed trigger's ``valid_source``, a Boros
            # Reckoner/damage-reflect-precedent nesting, not co-located
            # with the top-level activated-ability unit).
            handle(getattr(trig, "valid_card", None), "")
            handle(getattr(trig, "valid_source", None), "")

    # multicolor_matters structural arm: a Mana effect's SpellType==Multicolored
    # spend restriction ("Spend this mana only to cast a multicolored spell" —
    # Obsidian Obelisk, Pillar of the Paruns). CR 105.2c.
    for c in tree.iter_concepts():
        if mana_restricted_to_multicolored(c.node):
            fire("multicolor_matters", c.raw)
            break
    # Stage-A recovery (ADR-0038): the multicolor cares-about REFERENCE idiom
    # phase drops the "multicolored" qualifier from entirely (Fallaji
    # Wayfarer's granted-keyword affected filter) or discards on an
    # Unimplemented node's parseable-verb prefix (Niv-Mizzet Reborn's "for
    # each color pair"). tree_synthesis._arm_multicolor_matters fills the gap
    # from tree.oracle, gated on has_structural_multicolor_matters (the SAME
    # typed read the checks above run) — read here by concept NAME, mirroring
    # the synth_power_matters precedent below.
    for c in tree.iter_concepts():
        if c.concept == "multicolor_matters":
            fire("multicolor_matters", c.raw)
            break
    # ADR-0038 deferral sweep unit 6: the colorless cares-about REFERENCE
    # idiom phase drops the "colorless" qualifier from entirely (Ghostfire
    # Blade / Ugin the Ineffable's dropped-predicate cost_reduction,
    # Consign to Memory's colorless-blind counter_spell subject).
    # tree_synthesis._arm_colorless_matters fills the gap from tree.oracle,
    # gated on has_structural_colorless_matters (the SAME typed read the
    # checks above run) — read here by concept NAME, mirroring the
    # multicolor_matters precedent directly above.
    for c in tree.iter_concepts():
        if c.concept == "colorless_matters":
            fire("colorless_matters", c.raw)
            break

    # recall-completion b1 (ADR-0034): the Ferocious/Formidable power-threshold
    # CONDITION ("as long as you control a creature with power 4 or greater" —
    # Challenger Troll, Beastbond Outcaster). The deleted ``_signals_ir``'s
    # ``_condition_power_matters``
    # reads the condition-subject filter for a fixed ``PtComparison:Power:GE/GT``,
    # controller you — the SAME condition-site machinery tapped_matters reads. GE/GT
    # only (LE/LT would drift the sibling low_power_matters). CR 208.1 / 207.2c.
    for unit in tree.units:
        for site in iter_condition_sites(unit.node):
            for n in iter_typed_nodes(site):
                ctrl = filter_controller(n)
                if ctrl == "You" and any(
                    stat == "Power" and cmp_ in ("GE", "GT")
                    for stat, cmp_, _v in power_threshold_preds(n)
                ):
                    fire("power_matters", "")
                # ADR-0037/0038 W3: the colorless-count CONDITION sibling —
                # "as long as you control another colorless creature"
                # (Dust Stalker, Eldrazi Aggressor) / "if you control
                # another colorless creature" (Dominator Drone). The
                # SAME condition-site machinery, ColorCount EQ 0 instead
                # of a Power threshold. ``ScopedPlayer`` joins ``You`` —
                # a condition binds to the ABILITY's own controller by
                # default (Dominator Drone's condition sits under an
                # ``Opponent`` player_scope for its LoseLife EFFECT, but
                # phase still resolves the CONDITION's own filter
                # controller contextually, never to the literal
                # opponent CR 208.1 would require "you control").
                if ctrl in ("You", "ScopedPlayer") and any(
                    cmp_ == "EQ" and cnt == 0 for cmp_, cnt in color_count_preds(n)
                ):
                    fire("colorless_matters", "")
    # recall-completion b1 (ADR-0035 backstop, folded to Tier-1 ADR-0036/0037):
    # the "greatest/total/combined power of creatures you control" AGGREGATE
    # scaler (Ghalta, Rishkar's Expertise, The Great Henge) + the Formidable
    # ability word — phase folds the threshold into an empty-predicate
    # board_count carrier, so no structural datum distinguishes it; the
    # ``tree_synthesis`` bucket-B ``synth_power_matters`` node (the deleted
    # ``_POWER_MATTERS_MIRROR`` relocated verbatim) is the residual source.
    for c in tree.iter_concepts():
        if c.concept == "synth_power_matters":
            fire("power_matters", "")
            break
    # recall-completion b2 (ADR-0034): the TRIGGER-subject ColorCount build-around.
    # handle() above reads effect / count-operand / static-affected filters but never
    # a trigger's watched subject, so "whenever you cast a multicolored spell" (Cloven
    # Casting, Aurora Eidolon) / "a spell that's exactly two colors" (Guildpact
    # Paragon) and a colorless-cast / colorless-ETB trigger (Kozilek's Sentinel,
    # Eldrazi Mimic) were missed. Reads the trigger ``valid_card``'s ColorCount, with
    # the same you / shared gates as handle(): the spell filter of a "you cast …"
    # trigger is unscoped, so its you-scope comes from the subject controller OR the
    # trigger's own you-scope (``trigger_scope``). CR 105.2.
    for unit in tree.units:
        if unit.origin != "trigger":
            continue
        vc = getattr(unit.node, "valid_card", None)
        if vc is None or tag_of(vc) is None:
            continue
        ctrl = filter_controller(vc)
        you = ctrl == "You" or (ctrl is None and trigger_scope(unit.node) == "you")
        shared = ctrl in ("You", "Any", None)  # you or an unscoped global
        for cmp_, cnt in color_count_preds(vc):
            if cmp_ == "EQ" and cnt == 0:
                if shared:
                    fire("colorless_matters", "")
            elif you and ((cmp_ == "GE" and cnt >= 2) or (cmp_ == "EQ" and cnt >= 2)):
                fire("multicolor_matters", "")
    return out


def _coin_flip(tree: ConceptTree) -> list[Signal]:
    """coin_flip — a ``FlipCoin`` / ``FlipCoins`` / ``FlipCoinUntilLose`` DOER (CR
    705.1), OR a flip-FIXING static (CR 705.3 — "the first time you flip ...,
    those coins come up heads and you win those flips", Edgar, King of
    Figaro's "Two-Headed Coin"; both land as an Unimplemented node the ADR-
    0038 clause-grammar STATIC_TOKENS recovery re-decorates to the native
    "flip_coin" concept, so this read covers them with no special-case).
    Mirrors the legacy category's own conflated scope (``_sweep_detectors``
    labels it "coin-flip payoffs plus flip-fixing"; ``project.
    _narrow_trigger_other_refs`` folds the "win/lose a coin flip" trigger
    condition and the doer into the SAME ``coin_flip`` category) — the
    win/lose-a-flip PAYOFF trigger phase flattens to ``event='other'`` is a
    separate no-residue class covered by
    ``tree_synthesis._arm_coin_flip_payoff``, ALSO emitting the real
    "flip_coin" concept. A ``FlipCoin`` buried inside a GRANTED activated
    ability's definition (Frenetic Sliver's "All Slivers have '{0}: ... flip
    a coin ...'") is never its own concept node — the structural fallback
    below (:func:`has_nested_flip_coin`) reaches it. A die roll (``RollDie``
    → ``dice_makers``, CR 706) is a SEPARATE lane — kept split. Scope
    ``you``.
    """
    for c in tree.effect_concepts("flip_coin"):
        return [Signal("coin_flip", "you", "", c.raw, tree.name, "high")]
    for unit in tree.units:
        if has_nested_flip_coin(unit.node):
            return [Signal("coin_flip", "you", "", "", tree.name, "high")]
    return []


# A SYMMETRIC "whenever a player discards a card" watcher (Confessor, Spirit
# Cairn, Telekinetic Bonds): phase's ``Discarded`` trigger leaves BOTH
# ``valid_card.controller`` and ``valid_target`` unset for this idiom — the
# identical shape a genuinely SELF-only "whenever you discard" watcher
# (Archfiend of Ifnir) also carries, so no typed field distinguishes them
# (:func:`trigger_subject_scope` reads "any" for both). A per-unit
# reminder-stripped ``description`` text check is the only discriminator —
# scoped to the SAME trigger unit :func:`_discard_watch_is_opponent` already
# gated on "discarded", never a whole-card scan. CR 701.9 / 102.2.
_SYMMETRIC_DISCARD_WATCH_RX = re.compile(r"\ba player discards\b", re.IGNORECASE)


def _nested_owner_player_scope(root: object, target: object) -> str | None:
    """The ``player_scope`` actor tag INHERITED by ``target`` from the
    CLOSEST ancestor (along the unique path from ``root``) that carries
    one, found by a GENERIC depth-first walk of every dataclass field /
    list / variant payload reachable from ``root`` — unlike
    :func:`effect_owner_player_scope`, which only follows the fixed
    ``effect``/``sub_ability``/``execute``/``mode_abilities`` chain
    (:data:`_EFFECT_CHILD_FIELDS` in ``_card_ir.crosswalk``).

    ADR-0038 W5 tails: a discard nested under a ``GrantAbility``'s
    ``definition`` (Mindlash Sliver: "All Slivers have '{1}, Sacrifice ~:
    Each player discards a card.'" — the owning wrapper is
    ``modifications[i].definition``) or under a ``Vote``'s
    ``per_choice_effect`` branch (Capital Punishment's "Each opponent
    ... discards a card for each taxes vote", Sail into the West's "each
    player may discard their hand" — the owning wrapper is
    ``effect.per_choice_effect[i]``) sits behind a field neither on that
    fixed chain, so the shared helper returns ``None`` for both. Kept
    LANE-LOCAL rather than widening the shared helper: that helper backs
    several OTHER lanes (``discard_outlet``, ``group_hug_draw``, the
    ``opponent_cast_matters`` grant descent) a blanket widening would
    need a full-corpus sibling check across, per the ADR-0038 shared-
    helper-widening landmine — this walk only ever runs from
    ``_opponent_discard``. CR 613.1f (a static ability's Layer 6
    ability-granting continuous effect) / 701.38 (Vote).

    ADR-0038 W6 endgame: an INHERITED read, not merely the immediate
    parent's own field — Memory Jar / Magus of the Jar's "each player
    discards their hand" sits inside a ``CreateDelayedTrigger`` (CR
    603.7)'s ``.effect`` (an ``S_effect`` wrapper with NO ``player_scope``
    field of its own at all), several ``SequentialSibling`` hops below
    the ROOT ability's ``player_scope: All`` — the immediate-parent-only
    read the original version of this walk performed returns ``None``
    there even though the whole multi-part ability is genuinely
    each-player-scoped throughout. Threading the last-seen non-``None``
    ``player_scope`` DOWN the recursion (reset only when a closer node
    re-asserts its own) generalizes cleanly: every pre-existing case
    (Mindlash Sliver, Capital Punishment, Sail into the West) already had
    its OWN player_scope on the immediate wrapper, so the closest-
    ancestor read gives the identical answer for them — verified via the
    full-corpus ALL-KEY diff (0 changed idents outside
    ``opponent_discard``).
    """
    seen: set[int] = set()

    def walk(node: object, inherited: str | None) -> str | None:
        if node is target:
            return inherited
        if isinstance(node, TypedMirrorNode):
            if id(node) in seen:
                return None
            seen.add(id(node))
            ps = getattr(node, "player_scope", None)
            if ps is not None:
                if isinstance(ps, TypedMirrorNode):
                    inherited = tag_of(ps)
                elif isinstance(ps, MirrorVariant):
                    inherited = ps.key
                elif isinstance(ps, str):
                    inherited = ps
            for f in fields(node):
                result = walk(getattr(node, f.name), inherited)
                if result is not None:
                    return result
            return None
        if isinstance(node, MirrorVariant):
            return walk(node.inner, inherited)
        if isinstance(node, list):
            for item in node:
                result = walk(item, inherited)
                if result is not None:
                    return result
            return None
        return None

    return walk(root, None)


# ADR-0038 W6 endgame: a ``Discard``/``DiscardCard`` node buried inside a
# ``S_replacements`` unit (Breathstealer's Crypt's "If a player would draw a
# card, instead they draw a card and reveal it. If it's a creature card,
# that player discards it unless they pay 3 life") — the DiscardCard's
# ``target=ParentTarget`` chains back through a ``RevealTop`` (no player
# field of its own, only ``.player``), so the position-relative read this
# function's ``fire`` docstring warns about can't tell a genuine per-
# instance ANY-player replacement apart from a self card-filter (Sindbad) by
# the DiscardCard node alone. The replacement's OWN ``valid_player`` field
# (CR 614.1/614.6 — the replaced event's affected player) is the
# authoritative direction instead: ``Opponent`` is a one-sided hand attack,
# ``AnyPlayer`` is symmetric (it replaces ANY player's draw, including
# yours — the same "a wheel hits you too" convention this lane already
# applies to ``All``-scoped wrappers), ``You``/unset is self only. Corpus
# census: exactly 2 commander-legal replacement units carry a nested
# Discard/DiscardCard AND a non-empty ``valid_player`` — Chains of
# Mephistopheles (``AnyPlayer``, already correctly "opponents" via its own
# plain ``Discard{target: ParentTargetController}`` node, untouched by this
# table since it's not a ``DiscardCard``) and Breathstealer's Crypt.
_REPLACEMENT_VALID_PLAYER_SCOPE: dict[str, str] = {
    "Opponent": "opponents",
    "AnyPlayer": "each",
}


def _unit_has_nested_reveal_hand(node: object) -> bool:
    """Whether a ``RevealHand`` typed node is reachable ANYWHERE under
    ``node`` via a full :func:`iter_typed_nodes` deep walk — unlike
    :meth:`AbilityUnit.has_effect`, which only follows the FIXED
    effect/sub_ability chain, this reaches a ``RevealHand`` buried inside a
    ``GrantAbility.definition`` (Dementia Sliver's tribal static: "All
    Slivers have '{T}: Choose a card name. Target opponent reveals a card
    at random from their hand. If that card has the chosen name, that
    player discards it.'" — the reveal and the ``DiscardCard`` both live
    under the SAME buried ``GrantAbility.definition`` chain, invisible to
    the unit-level ``has_effect`` fixed-chain read). Same descent
    precedent as ``hand_disruption``'s own static-origin
    :func:`iter_typed_nodes` ``RevealHand`` scan. CR 613.1f.
    """
    if node is None:
        return False
    return any(tag_of(n) == "RevealHand" for n in iter_typed_nodes(node))


def _sibling_reveal_direction(unit: AbilityUnit) -> str | None:
    """The direction (``"opponents"``/``"each"``/``"you"``) of a SIBLING
    ``reveal_hand`` concept on the SAME unit, read via
    :func:`discard_recipient_scope` applied to the reveal node itself (its
    ``target`` field uses the identical ``_SCOPE_FIELDS`` shape a discard's
    own recipient does). The reveal-then-discard BACK-REFERENCE idiom
    (Nebuchadnezzar's "target opponent reveals X cards at random from
    their hand. Then that player discards all cards with that name
    revealed this way", Hint of Insanity's "Target player reveals their
    hand. That player discards all nonland cards ...", Rise // Fall's
    "Fall" half): the recovered ``discard`` residue (ADR-0038 post-giants
    ALLOWLIST row) carries NO typed recipient of its own — its whole
    clause is an ``Unimplemented`` token — but a SIBLING ``RevealHand``
    naming a player establishes the "that player"/"revealed this way"
    back-reference the prose defers to. ``None`` when the unit has no
    ``reveal_hand`` concept at all. CR 701.9 (the discard) / 701.20 (the
    reveal establishing "that player").
    """
    for c in unit.effect_concepts("reveal_hand"):
        sc = discard_recipient_scope(c.node)
        if sc is not None:
            return sc
    return None


def _choose_opponent_bound_discard(unit: AbilityUnit) -> object | None:
    """The Discard/DiscardCard effect immediately bound to a unit-root
    ``Choose(choice_type='Opponent')`` (CR 601.2c — choosing a player as
    part of resolving a spell/ability), or ``None``.

    Fervent Mastery: "If the {2}{R}{R} cost was paid, AN OPPONENT discards
    any number of cards, then draws that many cards." parses to a root
    ``Choose{choice_type: Opponent}`` immediately followed by a
    ``Discard{target: Controller}`` — the chosen opponent has no typed
    carrier of its own to re-read structurally (``Choose`` doesn't record
    WHERE its choice gets consumed), so POSITION is the only signal: the
    VERY NEXT effect in the chain, never a deeper sibling. Corpus-
    verified: Fervent Mastery is the ONLY commander-legal
    ``Choose(Opponent)``-root card with any discard concept at all in its
    unit, and its OWN second, unrelated "discard three cards at random"
    self-cost deep in the SAME chain (post-tutor, its own ``Controller``
    target genuinely means you) is excluded by the immediate-successor
    requirement — it is not this function's return value.
    """
    root = getattr(unit, "node", None)
    eff = getattr(root, "effect", None)
    if tag_of(eff) != "Choose" or getattr(eff, "choice_type", None) != "Opponent":
        return None
    sub = getattr(root, "sub_ability", None)
    return getattr(sub, "effect", None) if sub is not None else None


# ADR-0038 W6 endgame — the Aftermath text-only-tree last resort (W2c):
# Consign // Oblivion's "Oblivion" half ("Target opponent discards two
# cards.") has NO phase record at all (a zero-unit text-only ``ConceptTree``
# carrying only bulk oracle text — see the ``_ir_lookup`` module comment),
# so this function's entire units-scoped walk is a structural no-op for it.
# A raw whole-face scan is the ONLY possible read for a text-only tree (no
# typed substrate exists to walk); scoped to ``not tree.units`` so it never
# competes with — or risks over-firing against — the structural reads above
# for any phase-BUILT tree. Corpus census over every commander-legal
# text-only tree (4336): exactly one match, Consign // Oblivion's
# "Oblivion" — Driven // Despair's "Despair" ("that player discards a
# card") is a back-reference into a GRANTED trigger's quoted text with no
# "opponent"/"target player"/"each player" anchor at all, correctly NOT
# matched (deferred, bridge-ledger input). CR 701.9.
_TEXT_ONLY_OPP_DISCARD_RX = re.compile(
    r"\btarget opponent\b[^.\"]{0,40}?\bdiscards?\b"
    r"|\beach opponent\b[^.\"]{0,40}?\bdiscards?\b"
    r"|\btarget player\b[^.\"]{0,40}?\bdiscards?\b",
    re.IGNORECASE,
)
_TEXT_ONLY_EACH_DISCARD_RX = re.compile(
    r"\beach player\b[^.\"]{0,40}?\bdiscards?\b", re.IGNORECASE
)

# ADR-0039 grammar sprint (task #82) — two grammar_straggler idioms whose
# recovered "discard" concept-node (the ADR-0038 ALLOWLIST re-decoration)
# carries no recipient field of its own, so the direction survives ONLY in
# the residue's own preserved ``description`` text: Bladecoil Serpent's
# "for each {B}{B} spent to cast it, each opponent discards a card" (a
# mana-spent SCALING prefix, CR 601.2f — phase's own dominant recovered
# token is the non-concept-bearing "for") and Words of Waste's "The next
# time you would draw a card this turn, each opponent discards a card
# instead" (a REPLACEMENT "next time ... instead" rider, CR 614.1 — no
# imperative verb survives to peel, phase's dominant token is the leading
# determiner "the"). Both anchors are read inside :func:`_opponent_discard`
# 's ``fire()`` fallback chain, tight and idiom-specific — see that read
# site's own comment. Corpus-verified sole hits, 2026-07-12, phase v0.20.0,
# 31,622 commander-legal (Hollow Marauder's superficially similar "for
# each ... discard" residue is a DIFFERENT, unrelated draw payoff —
# excluded, its clause doesn't END in "each opponent discards a card").
_OPP_DISCARD_SCALING_PREFIX_RX = re.compile(
    r"each opponent discards a card\s*$", re.IGNORECASE
)
_OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX = re.compile(
    r"next time you would draw a card this turn, each opponent discards "
    r"a card instead",
    re.IGNORECASE,
)


def _opponent_discard(tree: ConceptTree) -> list[Signal]:
    """opponent_discard — a forced OPPONENT discard / hand attack (CR 701.9). A
    ``Discard`` effect whose recipient is a targeted / opponent player ("target
    player discards two cards" — Mind Rot → ``opponents``) or a symmetric
    each-player wheel (``each`` — it hits opponents too). Direction is read off the
    discard's OWN recipient node (:func:`discard_recipient_scope`), NOT phase's
    mis-scoped trigger scope ([P5]). A you-scoped self-loot ("draw, then discard"
    — Faithless Looting) is the ported ``discard_makers`` lane, NOT this one.

    ADR-0038 W4 giants — the WHEEL wrapper fallback: phase tags "each player
    discards their hand" (Wheel of Fortune) and "each opponent discards a
    card" (Burglar Rat, Herald of Anguish) with the discard's OWN recipient
    as plain ``Controller`` (the per-iteration actor of an ability-level
    ``player_scope`` loop, not a real self-target) — :func:`discard_
    recipient_scope` reads that as "you" and the effect is skipped. The
    wrapper actor that OWNS this discard (:func:`effect_owner_player_scope`
    — the same reader ``discard_outlet``'s Dark-Deal-is-not-vetoed check and
    ``group_hug_draw``'s Temple-Bell arm use) disambiguates: ``All`` is the
    symmetric wheel (``each`` — mirrors :func:`discard_recipient_scope`'s
    own Each/AllPlayers/EachPlayer mapping); an opponent-shaped actor
    (:data:`_OPP_DISCARD_ACTORS`) is the per-opponent edict (``opponents``).
    Only consulted when the node's own recipient did NOT already resolve —
    never overrides a genuine you/each/opponents read. CR 701.9 / 102.2.

    ADR-0038 W5 tails: the discard-effect node is not always a direct
    per-unit surface concept (:meth:`AbilityUnit.effect_concepts` — a
    granularity-a per-ability sibling read). A discard GRANTED via a
    tribal ``GrantAbility`` (Mindlash Sliver: "All Slivers have '{1},
    Sacrifice ~: Each player discards a card.'") lives under
    ``GrantAbility.definition.effect``, and a discard inside one ``Vote``
    branch (Sail into the West's "each player may discard their hand and
    draw seven", Capital Punishment's "Each opponent ... discards a card
    for each taxes vote") lives under a ``per_choice_effect`` wrapper —
    neither is the unit's own direct effect chain, so ``effect_concepts``
    never reaches them. :func:`iter_typed_nodes`'s generic deep walk does
    (the same descent precedent as ``phasing_makers``'s coin-flip branch
    read and ``hand_disruption``'s GrantAbility-nested RevealHand read).
    The DIRECT wrapper that owns each buried node still carries its OWN
    ``player_scope`` (``S_definition``/``S_per_choice_effect``), but
    neither field is on :func:`effect_owner_player_scope`'s fixed
    effect/sub_ability/execute/mode_abilities chain, so that shared
    reader returns ``None`` for both — :func:`_nested_owner_player_scope`
    (a lane-local generic walk, kept OUT of the shared helper per the
    ADR-0038 shared-helper-widening landmine) resolves it instead. CR
    701.9 / 613.1f / 701.38.

    ADR-0038 W6 endgame: five more structural arms close the bulk of the
    68-card live_only tail down to genuinely diverse, individually-shaped
    residue:

    * :func:`_nested_owner_player_scope` is now an ANCESTOR-INHERITED
      read (see its own docstring) — Memory Jar / Magus of the Jar's OWN
      discard (a ``CreateDelayedTrigger`` (CR 603.7) several
      ``SequentialSibling`` hops below the root ``player_scope: All``,
      distinct from their both-matching "each player exiles..."
      ``ChangeZoneAll`` arm) now inherits the ability-wide "each" scope.
    * a buried ``DiscardCard`` (Dementia Sliver's tribal
      ``GrantAbility.definition``) is no longer vetoed by
      :meth:`AbilityUnit.has_effect`'s fixed-chain blind spot —
      :func:`_unit_has_nested_reveal_hand`'s deep scan finds its sibling
      reveal.
    * a recovered ``discard`` residue with no typed recipient of its own
      resolves through :func:`_sibling_reveal_direction` (Nebuchadnezzar,
      Hint of Insanity, Rise // Fall's "Fall" half).
    * a ``DiscardCard`` inside a REPLACEMENT unit resolves through the
      replacement's OWN ``valid_player`` field
      (:data:`_REPLACEMENT_VALID_PLAYER_SCOPE`), bypassing the reveal-
      sibling veto entirely (Breathstealer's Crypt — CR 614.1/614.6).
    * a discard bound to a unit-root ``Choose(choice_type='Opponent')``
      resolves through :func:`_choose_opponent_bound_discard`'s
      immediate-successor position read (Fervent Mastery — CR 601.2c).

    Plus the Aftermath text-only-tree last resort at the top (Consign //
    Oblivion — see :data:`_TEXT_ONLY_OPP_DISCARD_RX`'s module comment).

    The remaining 63-card tail decomposes into exactly three shed classes
    (52 cards, all negative-pinned) plus 9 genuinely un-closed structural
    gaps this session characterized but did NOT force-fit:

    * the PRE-EXISTING wheel-mirror-duplicate shed (47 cards — the legacy
      byte-mirror's redundant "opponents" tag for an "each"-scoped wheel
      this lane's own :func:`discard_recipient_scope` Each/AllPlayers/
      EachPlayer mapping already resolves correctly to "each" alone,
      pinned by ``test_opponent_discard_wheel_wrapper_is_each`` — now
      also covering the three cards this session's closers newly resolve
      to "each": Memory Jar, Magus of the Jar, Breathstealer's Crypt);
    * the Cephalid-Looter loot shape (5 cards — :func:`_is_target_player_
      loot`, CR 701.9);
    * a NEWLY adjudicated past-tense-watcher / self-discard shed (2 cards
      — Tinybones, Trinket Thief has NO discard EFFECT node anywhere, only
      a ``QuantityComparison`` CONDITION reading ``CardsDiscardedThisTurn``
      — CR 608.2b, a condition doesn't itself cause a discard, the SAME
      "cares about" shape the disjoint ``discard_matters`` lane already
      covers; Azula, Ruthless Firebender's genuine ``Discard{target:
      Controller}`` is YOUR OWN optional self-discard, and the trailing
      "for each player who discarded a card this turn" is an unrelated
      dropped-clause experience tally, never a second discard effect —
      both negative-pinned this session).

    ADR-0039 W7 BRIDGES wave (2026-07-12) — PROMOTED. The final 9
    genuinely diverse gaps close via eight ledgered bridges
    (bridge_ledger.py, each row's own module comment for the corpus
    census): a shared "Unsupported unless clause" residue bucket
    (``opp_discard_unless_clause``, reusing lifeloss_makers' own
    ``_unless_clause_failure_descs`` — Tainted Specter, Remorseless
    Punishment; Wand of Ith carries the same residue class but is served
    independently via its own typed ``DiscardCard``); a Stickers {TK}
    parse failure (``opp_discard_tk_sticker_parse_failure`` — Yawgmoth
    Merfolk Soul, the base_pt_set TK-frontier sibling); two zero-residue
    dropped conjuncts sharing ``_no_typed_discard_node`` (the
    ``sacrifice_outlets`` broad-gap/narrow-match precedent — Fungal
    Shambler, Mindculling); a zero-unit text-only-tree back-reference
    (``opp_discard_driven_despair_missing_face`` — Driven // Despair's
    "Despair" half, wired into the text-only branch at the top of this
    function).

    The grammar sprint (ADR-0039 task #82, 2026-07-12) PROMOTED the other
    three W7 bridges off text-residue ``bridge_fires`` reads onto real
    structure — rows deleted from bridge_ledger.py, membership unchanged.
    All three already carry a recovered concept="discard" ConceptNode (the
    ADR-0038 ALLOWLIST re-decoration — the "discard" grammar token
    matches somewhere in each residue's own preserved text even though
    phase's OWN dominant-token classification differs), but that node has
    no recipient field of its own for :func:`discard_recipient_scope` to
    read, so the direction resolves in-line inside ``fire()``'s own
    fallback chain instead (each read site's own comment for detail): a
    "for"-dominant scaling-prefix straggler (Bladecoil Serpent's
    mana-spent idiom, CR 601.2f) and a replacement-idiom determiner-token
    residue (Words of Waste's "next time ... instead" clause, CR 614.1)
    both resolve via :data:`_OPP_DISCARD_SCALING_PREFIX_RX` /
    :data:`_OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX` — tight, idiom-specific
    anchors over the residue's own preserved description. A combat-
    damage-trigger Player-vs-Opponent scope ambiguity (Jagged Poppet's
    Hellbent "that player discards cards equal to the damage") resolves
    the same way: a combat-damage-to-a-player trigger's recipient can
    only be a DEFENDING (non-active) player (CR
    506.2 / 510.1b) — never the attacker themselves — so an unresolved
    recovered discard sharing that exact trigger shape directionally
    resolves to "opponents", scoped lane-locally to this one idiom.

    live_only == exactly the 3 pre-existing adjudicated, negative-pinned
    shed classes (wheel-mirror-duplicate, Cephalid-Looter loot,
    past-tense-watcher/self-discard) plus the 8 bridged-then-structural
    cards moved to both — the landfall rule. CR 701.9 / 701.9a / 119.4 /
    601.2f / 123.1 / 614.1 / 506.2 / 510.1b verified this session.
    """
    # ADR-0039 W7 BRIDGES wave: "no REAL (phase-parsed) unit" rather than
    # the original bare ``not tree.units`` — Driven // Despair's "Despair"
    # half's own text ALSO trips an UNRELATED ``apply_tree_synthesis`` arm
    # (a whole-card scan gated on the SAME "deals combat damage to a
    # player" wording this face's granted-ability text carries), which
    # appends a synthetic ``origin="synth"`` wrapper unit — so the tree is
    # no longer literally zero-unit by the time this lane runs, even
    # though it still carries NO real phase-parsed structure at all. This
    # generalizes the original check (an empty ``tree.units`` still
    # vacuously satisfies it) rather than narrowing it.
    if not any(u.origin != "synth" for u in tree.units):
        kept = _kept(tree)
        if _TEXT_ONLY_EACH_DISCARD_RX.search(kept):
            return [Signal("opponent_discard", "each", "", "", tree.name, "high")]
        if _TEXT_ONLY_OPP_DISCARD_RX.search(kept):
            return [Signal("opponent_discard", "opponents", "", "", tree.name, "high")]
        # Driven // Despair's "Despair" half (bridge_ledger.py row, its
        # own module comment for the corpus census) — a "that player"
        # back-reference the pre-existing text-only sweep above
        # deliberately doesn't anchor.
        if bridge_fires("opp_discard_driven_despair_missing_face", tree):
            return [Signal("opponent_discard", "opponents", "", "", tree.name, "high")]
        return []

    out: list[Signal] = []
    seen: set[str] = set()

    def fire(
        node: TypedMirrorNode,
        raw: str,
        unit: AbilityUnit,
        choose_opp_bound: object | None = None,
    ) -> None:
        is_discard_card = type(node).__name__ == "T_effect__DiscardCard"
        if node is choose_opp_bound:
            sc: str | None = "opponents"
        elif is_discard_card and unit.origin == "replacement":
            vp = getattr(getattr(unit, "node", None), "valid_player", None)
            sc = _REPLACEMENT_VALID_PLAYER_SCOPE.get(vp)
        else:
            # ADR-0038 W4 giants — the ``DiscardCard`` reveal-and-choose
            # arm's ``target=ParentTarget`` is POSITION-relative
            # (checklist #7i/landmine): after a player-facing
            # ``RevealHand`` (Thoughtseize) it names the REVEALED PLAYER,
            # but after a card-facing producer — ``RevealTop`` (Sindbad,
            # Fa'adiyah Seer's "draw and reveal it. If it isn't a land,
            # discard it"), Dig/Search — it names the PRODUCED CARD
            # instead. Corpus-verified 89/92: every genuine hand-attack
            # DiscardCard shares its unit with a sibling ``reveal_hand``
            # concept (direct OR buried — :func:`_unit_has_nested_
            # reveal_hand`); the 3 that don't are self-loot card-filters
            # (Sindbad, Fa'adiyah Seer) or a Replacement whose "that
            # player" resolves via ``valid_player`` above (Breathstealer's
            # Crypt). Gate on the sibling to keep the DiscardCard arm from
            # reading a card-reference as a player.
            if is_discard_card and not (
                unit.has_effect("reveal_hand")
                or _unit_has_nested_reveal_hand(getattr(unit, "node", None))
            ):
                return
            sc = discard_recipient_scope(node)
            if sc not in ("opponents", "each"):
                owner = effect_owner_player_scope(getattr(unit, "node", None), node)
                if owner is None:
                    owner = _nested_owner_player_scope(
                        getattr(unit, "node", None), node
                    )
                if owner == "All":
                    sc = "each"
                elif owner in _OPP_DISCARD_ACTORS:
                    sc = "opponents"
            if sc not in ("opponents", "each") and type(node).__name__ == (
                "T_effect__Unimplemented"
            ):
                reveal_sc = _sibling_reveal_direction(unit)
                if reveal_sc in ("opponents", "each"):
                    sc = reveal_sc
            # ADR-0039 grammar sprint (task #82) —
            # opp_discard_jagged_poppet_combat_scaling: "Hellbent —
            # Whenever ~ deals combat damage to a player, if you have no
            # cards in hand, that player discards cards equal to the
            # damage." recovers a concept="discard" node via the "discard"
            # ALLOWLIST token, but the residue carries no recipient field
            # of its own (its dropped subject is "that player", the
            # trigger's OWN bare ``Player`` valid_target). A combat-damage-
            # to-a-player trigger's recipient can ONLY be a DEFENDING
            # (non-active) player — CR 506.2 "the nonactive player is the
            # defending player"; CR 510.1b "an unblocked creature assigns
            # its combat damage to the player ... it's attacking" — never
            # the attacking player themselves, so it directionally
            # resolves to "opponents". Scoped LANE-LOCALLY to THIS exact
            # idiom (the "equal to the damage" wording AND a genuine
            # combat-damage-to-player trigger shape, both required) rather
            # than a general Player-vs-Opponent owner-scope widening,
            # which would risk over-firing a genuinely symmetric
            # multiplayer group-hug trigger elsewhere in this fallback
            # chain.
            if (
                sc not in ("opponents", "each")
                and type(node).__name__ == "T_effect__Unimplemented"
                and "equal to the damage"
                in (getattr(node, "description", "") or "").lower()
                and damage_to_player_trigger_kind(getattr(unit, "node", None))
                is not None
            ):
                sc = "opponents"
            # ADR-0039 grammar sprint (task #82) — two more grammar_
            # straggler bridges whose recovered "discard" node ALSO
            # carries no recipient field: Bladecoil Serpent's "for each
            # {B}{B} spent to cast it, each opponent discards a card" (a
            # mana-spent SCALING prefix, CR 601.2f — phase's own dominant
            # recovered token is the non-concept-bearing "for") and Words
            # of Waste's "The next time you would draw a card this turn,
            # each opponent discards a card instead" (a REPLACEMENT "next
            # time ... instead" rider, CR 614.1 — no imperative verb
            # survives to peel, phase's dominant token is the leading
            # determiner "the"). Both idioms' own preserved residue text
            # still names the opponent-directed discard inline, so a
            # tight, idiom-specific anchor resolves the direction without
            # any general widening.
            if sc not in ("opponents", "each") and type(node).__name__ == (
                "T_effect__Unimplemented"
            ):
                desc = getattr(node, "description", "") or ""
                if _OPP_DISCARD_SCALING_PREFIX_RX.search(
                    desc
                ) or _OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX.search(desc):
                    sc = "opponents"
            # The Cephalid-Looter loot veto is a discriminator for THIS
            # branch's typed-recipient inference only (a targeted "target
            # player draws, then discards" where BOTH share one targeted
            # player — the controller is filtering their OWN hand, not
            # attacking). It does not apply to the replacement/valid_player
            # or Choose-bound arms above: Breathstealer's Crypt's REPLACED
            # Draw shares the SAME ``ParentTarget`` position tag as its
            # discard purely because both chain off the same replaced
            # event, not because a controller aimed a loot at one player —
            # ``valid_player`` already gave the authoritative direction.
            if _is_target_player_loot(unit, node):
                return
        if sc not in ("opponents", "each"):
            return
        if sc in seen:
            return
        seen.add(sc)
        out.append(Signal("opponent_discard", sc, "", raw, tree.name, "high"))

    for unit in tree.units:
        seen_ids: set[int] = set()
        choose_opp_bound = _choose_opponent_bound_discard(unit)
        for c in unit.effect_concepts("discard"):
            seen_ids.add(id(c.node))
            fire(c.node, c.raw, unit, choose_opp_bound)
        if getattr(unit, "node", None) is not None:
            for n in iter_typed_nodes(unit.node):
                if id(n) in seen_ids:
                    continue
                if type(n).__name__ not in (
                    "T_effect__Discard",
                    "T_effect__DiscardCard",
                ):
                    continue
                seen_ids.add(id(n))
                fire(n, getattr(n, "description", "") or "", unit, choose_opp_bound)
        # Batch 9 — the PUNISHER trigger arm: "whenever an opponent discards
        # a card, …" (Megrim, Liliana's Caress). phase watches the discarder
        # on the trigger's ``valid_card`` controller (Megrim — Opponent) or
        # ``valid_target``; the self/any-scope complement is the disjoint
        # ``discard_matters`` lane (checklist #5 — the discarder scope is
        # read off the trigger's own recipient nodes, never the mislabeled
        # trigger_scope). CR 701.8a / 102.2.
        is_punisher_watch = unit.trigger_event == "discarded" and (
            _discard_watch_is_opponent(unit)
            or _SYMMETRIC_DISCARD_WATCH_RX.search(
                getattr(unit.node, "description", "") or ""
            )
        )
        if is_punisher_watch and "opponents" not in seen:
            seen.add("opponents")
            out.append(
                Signal("opponent_discard", "opponents", "", "", tree.name, "high")
            )
    # ADR-0039 W7 BRIDGES wave — the residual dropped-clause / upstream-
    # parse-failure bucket (bridge_ledger.py rows, each row's own module
    # comment for the full corpus accounting). The grammar sprint (task
    # #82) PROMOTED the three grammar_straggler rows this bucket used to
    # carry off text-residue ``bridge_fires`` reads onto real structure —
    # all three now resolve in-line inside ``fire()``'s own fallback
    # chain above (the ``_OPP_DISCARD_SCALING_PREFIX_RX`` /
    # ``_OPP_DISCARD_REPLACEMENT_NEXT_TIME_RX`` / combat-damage-trigger
    # branches, each with its own comment) and are retired from BRIDGES.
    if "opponents" not in seen:
        for bridge_id in (
            "opp_discard_unless_clause",
            "opp_discard_tk_sticker_parse_failure",
            "opp_discard_fungal_shambler_dropped_conjunct",
            "opp_discard_mindculling_dropped_conjunct",
        ):
            if bridge_fires(bridge_id, tree):
                out.append(
                    Signal("opponent_discard", "opponents", "", "", tree.name, "high")
                )
                break
    return out


# Recipient tags naming a SINGLE targeted player (not an explicit opponent / each).
_TARGETED_PLAYER_TAGS: frozenset[str] = frozenset({"ParentTarget", "Player", "Target"})


def _is_target_player_loot(unit: AbilityUnit, discard: TypedMirrorNode) -> bool:
    """Whether a discard is a "target player draws, then discards" LOOT, not a hand
    attack (CR 701.9 / 701.8a).

    Cephalid Looter / Cephalid Broker resolve "target player draws a card, then
    discards a card": phase tags the discard recipient ``ParentTarget`` (the
    just-targeted player), so :func:`discard_recipient_scope` reads ``opponents`` —
    but a SIBLING draw targets the SAME single player, so the controller points it
    at THEMSELVES to filter cards (the ported ``discard_makers`` role), never at an
    opponent. The gate fires only when BOTH the discard AND a sibling draw name a
    single targeted player; a one-sided attack with no draw (Mind Rot, Blightning)
    and a wheel whose draw is for YOU while an opponent discards (Cruel Ultimatum —
    draw recipient ``Controller``) are correctly NOT loots.

    ``discard`` is the verbatim typed node (ADR-0038 W5 tails: the caller may
    hand this a buried ``iter_typed_nodes`` find with no owning
    :class:`ConceptNode` wrapper at all, so this reads the raw node
    directly, not ``.node``).
    """
    if recipient_tag(discard) not in _TARGETED_PLAYER_TAGS:
        return False
    return any(
        recipient_tag(d.node) in _TARGETED_PLAYER_TAGS
        for d in unit.effect_concepts("draw")
    )


# ── Batch 7 lanes (ADR-0035 Stage 2) ─────────────────────────────────────────

# AdditionalPhase.phase values (lowercased) that are a COMBAT phase (CR 505 / 506)
# — the only phase the live ``extra_combats`` lane reads (project._EXTRA_PHASE). An
# extra upkeep / draw / end phase is mis-routed by phase to combat and recovered by
# a separate ``project`` marker (a documented KEPT-DETECTOR), so the combat gate
# mirrors the live ``extra_combats`` exactly.
_COMBAT_PHASES: frozenset[str] = frozenset({"begincombat", "combat"})

# GiveControl recipient scopes that are a give-AWAY (the beneficiary is NOT you —
# checklist #2): a targeted player ("any"), an opponent, or each player. A
# you-recipient (no real card) is excluded.
_GIVE_AWAY_SCOPES: frozenset[str] = frozenset({"any", "opponents", "each"})


def _extra_combats(tree: ConceptTree) -> list[Signal]:
    """extra_combats — an ADDITIONAL combat phase (CR 505 / 506). Mirrors the live
    ``_DOER_EFFECT_KEYS["extra_combat"]`` doer: an ``AdditionalPhase`` effect whose
    ``phase`` is a combat phase (Aurelia, Moraug, Combat Celebrant). Distinct from
    ``extra_turns`` (``ExtraTurn`` — Time Warp): a different effect tag, never read
    here. The phase gate discriminates against the mis-routed extra-upkeep/draw/end
    forms (a documented KEPT-DETECTOR ``project`` marker). Scope "you" — the active
    player takes the phase (the live forces "you").

    task #85: falls back to the ``illusionists_gambit_additional_combat_
    swallowed`` ledgered bridge (``bridge_ledger``) for Illusionist's
    Gambit, whose whole "after this phase, there is an additional combat
    phase" sentence phase swallows via a ``Condition_If`` parse-warning,
    leaving no ``AdditionalPhase`` node anywhere on the tree.
    """
    for c in tree.effect_concepts("extra_phase"):
        if additional_phase_kind(c.node) in _COMBAT_PHASES:
            return [Signal("extra_combats", "you", "", c.raw, tree.name, "high")]
    if bridge_fires("illusionists_gambit_additional_combat_swallowed", tree):
        return [Signal("extra_combats", "you", "", "", tree.name, "high")]
    return []


# cost_reduction kept-mirror (ADR-0038 W3 batch 4) — the same three textual
# gates :func:`mtg_utils._card_ir.tree_synthesis._cost_reducer_node_ok`
# applies node-scoped, duplicated here per-clause over the whole reminder-
# stripped face oracle for the residual cards with NO node at all (see
# :func:`_cost_reduction`'s docstring).
_COST_LESS_KEPT_RX = re.compile(r'\bcosts?\b[^."]{0,40}?\bless\b', re.IGNORECASE)
_COST_SELF_DISCOUNT_KEPT_RX = re.compile(
    r"\bthis spell costs\b|\bthis ability costs\b|\bthis costs\b"
    r"|\b(?:that|the) copy costs\b",
    re.IGNORECASE,
)
_COST_INCREASE_KEPT_RX = re.compile(
    r"\bcost(?:s)?[^.\"]{0,30}?\b(?:more|an additional)\b|would cost less than",
    re.IGNORECASE,
)
_COST_FREE_CAST_KEPT_RX = re.compile(
    r"without paying|\bit costs?\b[^.\"]*?\bthis way\b",
    re.IGNORECASE,
)


def _cost_reduction(tree: ConceptTree) -> list[Signal]:
    """cost_reduction — a static spell-cost REDUCER build-around (CR 601.2f / 118.7).
    Mirrors the live ``cost_reduction`` doer: a ``static_ability`` whose ``mode`` is a
    ``ModifyCost`` of direction ``Reduce`` (Goblin Electromancer, Helm of Awakening,
    Ruby Medallion).

    * **direction** — :func:`modify_cost_mode` reads the typed ``mode``; a ``Raise``
      tax (Thalia) / ``Minimum`` floor is excluded (the live ``_COST_INCREASE`` raw
      screen);
    * **not a self-discount, unambiguous shape** — a ``SelfRef`` ``affected``
      filter is phase's canonical self-discount shape (220/226 of the "this
      spell costs" statics, A-Demilich) — Tier-1, no text.

    Tier-1 (ADR-0036/0037 T10-finalize2 GLOBAL FINALIZE-2 fold): the six
    residual self-discounts parse as a bare ``Typed[Card]`` (``spell_filter``
    null) — byte-identical to the symmetric Helm-of-Awakening reducer,
    distinguishable only by the static's own ``description`` ([P8], refined
    2026-07-02) — so the deleted lane-time "this spell costs" description
    screen is relocated verbatim to the bucket-B ``synth_cost_reduction``
    node (:func:`_arm_cost_reduction`, which also covers the unambiguous
    majority), read below.

    A flat ramp rock (no ``ModifyCost``) never reaches the gate.

    ADR-0038 W3 batch 4: a final kept-mirror text fallback closes the last
    corpus residuals phase drops with NO node at all anywhere in the tree —
    not even an ``Unimplemented`` placeholder (:func:`_arm_cost_reduction`'s
    node-scoped scan has nothing to read) — Henzie "Toolbox" Torre's second
    sentence ("Blitz costs you pay cost {1} less ...") is entirely absent
    from phase's record, and a Saga chapter collapses to a bare "Chapter N"
    raw (Invasion of the Giants' chapter III reducer, Catalyst Stone's
    "Flashback costs you pay cost {2} less"). Same three gates as the
    bucket-B node scan (genuine "cost(s) ... less", not a self/copy
    discount, not an increase) PLUS the free-cast exclusion (Bre of Clan
    Stoutarm/Rashmi and Ragavan/Breaching Dragonstorm's "cast ... without
    paying its mana cost if ... mana value is N or less" idiom pop-verified
    False — the comparator "less" never denotes a reduction), scanned
    per-CLAUSE (period-delimited) over the reminder-stripped face oracle so
    an unrelated clause on the same card never silences/fires past its own
    boundary (the Magnetic-Web per-clause lesson) — EXCEPT the self-discount
    tell, which is a CARD-LEVEL veto, not per-clause: a multi-sentence
    self-discount rider (Geistlight Snare — "This spell costs {1} less to
    cast if you control a Spirit. It ALSO costs {1} less to cast if you
    control an enchantment.") only names "this spell costs" in its FIRST
    sentence; the continuation anaphora ("It also costs ... less") is the
    SAME rider, not an unrelated clause, so it must inherit the veto rather
    than slip through a per-clause scan blind to the earlier "this spell".
    Scope "you".
    """
    for c in tree.iter_concepts():
        if c.concept == "synth_cost_reduction":
            return [Signal("cost_reduction", "you", "", "", tree.name, "high")]
    kept = _kept(tree)
    if _COST_SELF_DISCOUNT_KEPT_RX.search(kept):
        return []  # a self-discount rider anywhere on the card poisons every
        # "It (also) costs ... less" continuation clause too
    for raw_clause in kept.split("."):
        clause = raw_clause.strip()
        if (
            clause
            and _COST_LESS_KEPT_RX.search(clause)
            and not _COST_INCREASE_KEPT_RX.search(clause)
            and not _COST_FREE_CAST_KEPT_RX.search(clause)
        ):
            return [Signal("cost_reduction", "you", "", "", tree.name, "high")]
    return []


# The "'s controller gains/gain control" REVENGE idiom (CR 110.2): control
# passes to whoever's SOURCE damaged/destroyed/targeted the permanent (Crag
# Saurian's "that source's controller", Contested War Zone's "that
# creature's controller", Starke of Rath's "that permanent's controller",
# Fractured Loyalty's "that spell or ability's controller", Act of
# Authority's "its controller") — a consequence of an OPPONENT's own
# action, never a deliberate gift. Mirrors live's OWN text-anchored split:
# ``_DONATE_RAW`` (donate_makers) deliberately excludes this phrasing,
# which lives only in ``_GIVE_CONTROL_AWAY`` (the SEPARATE gain_control
# theft-exclusion regex).
_CONTROL_REVENGE_RE = re.compile(
    r"\b(?:\w+'s|its|their) controller (?:gains?|gain) control\b", re.IGNORECASE
)


def _donate_makers(tree: ConceptTree) -> list[Signal]:
    """donate_makers — give a permanent YOU control to ANOTHER player (CR 110.2).
    Mirrors the live ``donate_makers`` doer (which folds the recipient from raw
    because the OLD lossy IR dropped it): a ``GiveControl`` effect whose ``recipient``
    is a non-you player (Donate, Bazaar Trader, Harmless Offering) — the give-away
    direction read STRUCTURALLY off the recipient node (checklist #2,
    :func:`control_recipient_scope`, which ALSO resolves the three dynamically-bound
    "that player" recipient shapes phase emits for a triggered/chosen give-away —
    Blim's/Kain's/Drooling Ogre's combat-damage-or-cast TriggeringPlayer, Alexios's/
    Risky Move's each-upkeep-cycle ScopedPlayer, Discerning Financier's/Goblin
    Festival's choose-a-player ParentTargetController). Those same three tags ALSO
    carry the textually-DIFFERENT "'s controller gains/gain control" REVENGE idiom
    (Crag Saurian's "that source's controller", Contested War Zone's "that
    creature's controller", Starke of Rath's "that permanent's controller",
    Fractured Loyalty's "that spell or ability's controller", Act of Authority's
    "its controller") — the CONTROLLER of a damage-source/destroyed-target/targeting-
    spell, never a CHOSEN player, and live's own ``_DONATE_RAW`` deliberately
    excludes this idiom (it lives only in the theft-lane's broader exclusion regex,
    ``_GIVE_CONTROL_AWAY``) — :data:`_CONTROL_REVENGE_RE` mirrors that exclusion so
    the structural read draws the SAME line live's narrower text anchor draws. A
    ``GainControl`` / ``GainControlAll`` whose beneficiary is a non-you player is the
    SAME give-away direction under phase's THEFT tag, but ONLY the narrow mass-self-
    give-away shape (Sky Swallower's "target opponent gains control of all other
    permanents you control" — mirrors the FIRST of ``_gives_control_to_other``'s
    three branches, the ``GainControlAll`` + controller='You' one), EXCLUDING an
    ``Owned`` target predicate (Herald of Leshrac's "each player gains control of
    each land they own that you control" is a control-RESET to the original OWNER,
    not a give-away — CR 110.2a, the SAME exclusion ``_gain_control`` applies). The
    other two ``_gives_control_to_other`` branches ("an opponent gains control of
    it/this" — Fateful Handoff, Rogue Skycaptain, Wishclaw Talisman; "each player
    gains control …" — Order of Succession, Scrambleverse, Aminatou) are corpus-
    measured OVER-broad for THIS key: reusing them wholesale pulled in control-
    RESET cards (Brooding Saurian, Homeward Path) and cards whose gained object was
    never "your board" in the mass-give-away sense. Deliberately narrower than
    ``_gain_control``'s own exclusion set. Scope "you" (the controller performs the
    gift).
    """
    for unit in tree.units:
        for c in unit.effect_concepts("give_control"):
            if control_recipient_scope(c.node) not in _GIVE_AWAY_SCOPES:
                continue
            unit_desc = getattr(unit.node, "description", "") or ""
            if _CONTROL_REVENGE_RE.search(unit_desc):
                continue  # "'s controller gains control" — a revenge idiom, not a gift
            return [Signal("donate_makers", "you", "", c.raw, tree.name, "high")]
    for c in tree.effect_concepts("gain_control"):
        if tag_of(c.node) == "GainControlAll":
            sub = effect_filter(c.node)
            if (
                sub is not None
                and filter_controller(sub) == "You"
                and "Owned" not in filter_predicates(sub)
            ):
                return [Signal("donate_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _conjure_makers(tree: ConceptTree) -> list[Signal]:
    """conjure_makers — a ``Conjure`` DOER (DD2 / DD5): create a real card from
    outside the deck into a zone (an Alchemy mechanic; NOT a token, NOT a copy).
    Mirrors the live ``\\bconjure\\b`` regex but reads the typed ``Conjure`` effect —
    a fidelity GAIN: the regex over-fires on a card whose ABILITY NAME contains
    "Conjure" (Silvanus's Invoker — "Conjure Elemental — {8}: …", an animate-land
    with no ``Conjure`` effect node), which the structural read correctly drops. A
    token maker (``make_token`` — Krenko) is a different effect tag. Scope "you".
    """
    for c in tree.effect_concepts("conjure"):
        return [Signal("conjure_makers", "you", "", c.raw, tree.name, "high")]
    return []


def _blocked_matters(tree: ConceptTree) -> list[Signal]:
    """blocked_matters — a combat-block payoff (CR 509). Mirrors the live
    ``_PAYOFF_TRIGGER_KEYS`` ``becomes_blocked`` / ``blocks`` rows: a trigger whose
    derived event is ``becomes_blocked`` (the attacker-side "whenever ~ becomes
    blocked" — CR 509.1h) or ``blocks`` (the blocker-side "whenever ~ blocks" — CR
    509.1g). An ``attacks`` trigger is a different lane (``attack_matters``). The
    disjunctive "attacks or blocks" membership fold (phase → event='other') stays a
    ``live_only`` mirror. Scope "you" (the live forces it; no opponent-side ``blocks``
    trigger exists to over-fire).
    """
    for unit in tree.units:
        if unit.trigger_event in ("becomes_blocked", "blocks"):
            return [Signal("blocked_matters", "you", "", "", tree.name, "high")]
    return []


def _initiative(tree: ConceptTree) -> list[Signal]:
    """initiative_makers / initiative_matters — The Initiative (CR 726). Mirrors the
    live ``\\btake the initiative\\b`` / ``\\bhave the initiative\\b`` regex pair,
    read structurally:

    * **MAKER** — a ``TakeTheInitiative`` effect node (Caves of Chaos Adventurer,
      White Plume Adventurer, Seasoned Dungeoneer). Read off the typed ``_tag``
      DISTINCTLY from ``VentureIntoDungeon`` (both fold to the ``venture`` concept),
      so ``venture_makers`` keeps co-firing — matching the live DOUBLE-fire (an
      initiative card fires both ``venture_makers`` structurally AND
      ``initiative_makers``). A pure-venture card (Acererak — ``VentureIntoDungeon``)
      fires ``venture_makers`` only, NEVER ``initiative_makers``;
    * **MATTERS** — an ``IsInitiative`` payoff CONDITION ("as long as / if you have
      the initiative" — Passageway Seer, Sarevok's Tome), read via
      :func:`condition_tags`. A maker that only TAKES the initiative carries no such
      condition. A monarch-gated card (``IsMonarch`` → ``monarch_matters``) is a
      different designation.

    Both scope "you".
    """
    out: list[Signal] = []
    for c in tree.effect_concepts("venture"):
        if tag_of(c.node) == "TakeTheInitiative":
            out.append(Signal("initiative_makers", "you", "", c.raw, tree.name, "high"))
            break
    if "IsInitiative" in condition_tags(tree):
        out.append(Signal("initiative_matters", "you", "", "", tree.name, "high"))
    return out


def _end_the_turn(tree: ConceptTree) -> list[Signal]:
    """end_the_turn — an ``EndTheTurn`` DOER (CR 724): expedite the rest of the turn,
    exiling whatever is on the stack (Time Stop, Sundial of the Infinite). Mirrors
    the live ``_DOER_EFFECT_KEYS["end_the_turn"]`` doer. Obeka's player-scoped grant
    ("The player whose turn it is may end the turn") is ADR-0038 recovery-promoted:
    a real Unimplemented EFFECT-role node the shared clause grammar re-decorates to
    concept="end_the_turn" via ``recovery.ALLOWLIST``, so this single typed read
    covers both. Distinct from ``ExtraTurn`` (``extra_turns`` — Time Warp) and an
    ``EndCombatPhase`` fog: different effect tags, never read here. Scope "you"
    (the build-around marker the live forces).
    """
    for c in tree.effect_concepts("end_the_turn"):
        return [Signal("end_the_turn", "you", "", c.raw, tree.name, "high")]
    return []


def _opponent_exile_makers(tree: ConceptTree) -> list[Signal]:
    """opponent_exile_makers — GRAVEYARD HATE the card PERFORMS (CR 406 / 701.17a).
    Mirrors the live ``opponent_exile_makers`` doer (a kept word-mirror over phase's
    scattered exile forms), ported as the CLEAN structural arm: a role=effect
    ``ChangeZone`` moving cards ``(Graveyard → Exile)`` that targets a whole PLAYER's
    graveyard (``target`` is a ``Player`` node — Bojuka Bog, Angel of Finality,
    Tormod's Crypt) OR is explicitly opponent-scoped (Author of Shadows). The
    player-target gate is the discriminator that isolates graveyard HATE from a
    self-graveyard-exile-for-value (an escape/fuel ``(Graveyard → Exile)`` of a
    specific CARD — controller you / a single Typed card), which it must NOT fire on.
    Self-blink (Cloudshift — origin not Graveyard), Leyline of the Void (a
    ``replacement``, origin not Graveyard), and an any-graveyard single-card exile
    (Scavenging Ooze — target a Typed card, not a player) are all naturally excluded;
    the replacement / mass-all-graveyards forms stay a documented ``live_only`` tail.
    Scope "opponents" (the live's fixed lane scope).
    """
    for c in tree.effect_concepts("change_zone"):
        if change_zone_dirs(c.node) != ("Graveyard", "Exile"):
            continue
        if (
            tag_of(getattr(c.node, "target", None)) == "Player"
            or c.scope == "opponents"
        ):
            return [
                Signal(
                    "opponent_exile_makers", "opponents", "", c.raw, tree.name, "high"
                )
            ]
    return []


# Batch-7 Scryfall-keyword field-lookups (checklist #3 — the live path keeps these
# as keyword survivors via ``_IR_KEYWORD_MAP`` / ``_PRESET_KEYWORD_SIGNALS``). Each
# keyword tags the BEARER (the maker), not a payoff, so a clean keyword-array read is
# precise. NB: the Scryfall keyword array (the bulk record) carries these — phase's
# OWN ``keywords`` does NOT (Boast / Magecraft / Exhaust are absent from the phase
# record), so the caller supplies the bulk array (the same source ``mill_makers``
# reads). ``flash`` is deliberately ABSENT: the live ``flash_makers`` fires from a
# grant-regex + a ``cast_with_keyword{flash}`` synth (both zero-node in v0.9.0), NOT
# the own ``Flash`` keyword (Snapcaster Mage fires nothing) — so it has no clean
# hook and stays a KEPT-DETECTOR.
_BOAST_KEYWORDS: frozenset[str] = frozenset({"boast"})
_EXHAUST_KEYWORDS: frozenset[str] = frozenset({"exhaust"})
_CONVOKE_KEYWORDS: frozenset[str] = frozenset({"convoke"})
_MAGECRAFT_KEYWORDS: frozenset[str] = frozenset({"magecraft"})


def _keyword_field_signals_b7(keywords: frozenset[str], name: str) -> list[Signal]:
    """The batch-7 Scryfall-keyword field-lookups (checklist #3 survivors):

    * ``boast`` → ``boast_makers`` you + ``attack_matters`` you (CR 702.142 — the
      Scryfall ``Boast`` keyword is the DOER; the live preset co-fires
      ``attack_matters`` because a boast creature attacks to use the ability —
      ``_IR_KEYWORD_MAP["boast"]``);
    * ``exhaust`` → ``exhaust_makers`` you (CR 702.177 — the once-only activated
      ability maker, ``_IR_KEYWORD_MAP["exhaust"]``);
    * ``convoke`` → ``convoke_makers`` you (CR 702.51 — the BEARER of convoke; the
      "spells you cast have convoke" GRANTER (Chief Engineer — no ``Convoke``
      keyword) is a SEPARATE typed read, ``_spell_keyword_grant``'s convoke arm
      (ADR-0037/0038 W1 batch-3) — both roles feed the SAME key, matching legacy's
      own conflated detection);
    * ``magecraft`` → ``magecraft_matters`` you (CR 207.2c — an ability WORD; the
      "whenever you cast or copy" trigger lives in stripped reminder text, so the
      Scryfall ``Magecraft`` keyword is the only reachable anchor. A plain
      "whenever you cast an instant or sorcery" creature WITHOUT the keyword (Young
      Pyromancer) carries none → ``spellcast_matters``, not this).

    Reading the STRUCTURED keyword array (not oracle text) makes the lanes immune to
    name / ability-word collisions.
    """
    out: list[Signal] = []
    low = {k.lower() for k in keywords}
    if low & _BOAST_KEYWORDS:
        out.append(Signal("boast_makers", "you", "", "", name, "high"))
        out.append(Signal("attack_matters", "you", "", "", name, "high"))
    if low & _EXHAUST_KEYWORDS:
        out.append(Signal("exhaust_makers", "you", "", "", name, "high"))
    if low & _CONVOKE_KEYWORDS:
        out.append(Signal("convoke_makers", "you", "", "", name, "high"))
    if low & _MAGECRAFT_KEYWORDS:
        out.append(Signal("magecraft_matters", "you", "", "", name, "high"))
    return out


LANES = (
    _ring,
    _discover_makers,
    _daynight_makers,
    _phasing_makers,
    _voting_makers,
    _amass_makers,
    _incubate_makers,
    _facedown_makers,
    _dice_makers,
    _cast_from_exile,
    _counter_kind_lanes,
    _player_counter_makers,
    _count_operand_lanes,
    _modified_matters,
    _predicate_build_around,
    _coin_flip,
    _opponent_discard,
    _extra_combats,
    _cost_reduction,
    _donate_makers,
    _conjure_makers,
    _blocked_matters,
    _initiative,
    _end_the_turn,
    _opponent_exile_makers,
)
