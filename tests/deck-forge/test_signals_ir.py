"""Signal-lane tests for real cards, run through the production hybrid extractor.

Originally this file probed the deleted projected-IR engine (``_signals_ir``)
directly against hand-built ``Card`` IR fixtures. That engine, and the regex
engine it stood beside, are both gone (repoint per docs/adr — the substrate
now lives in ``signal_base`` / ``text_reads`` / ``membership_floor`` /
``crosswalk_signals``); the ONLY extractor is
``signals.extract_signals``. The synthetic-fixture tests were deleted
during the repoint (no production analogue — a hand-built IR object was never
something ``extract_signals`` accepts). What remains is real-card
coverage: every surviving test resolves a named card from the committed
snapshot via ``mtg_utils.testkit`` and asserts on the SAME Signal objects
production emits.
"""

from __future__ import annotations

from mtg_utils.testkit import test_card_ir, test_signals

# ── Real-card path (task #25): a card looked up by NAME from the committed snapshot
# (``mtg_utils.testkit``), run through production ``extract_signals`` over its
# REAL projected IR. Each call site passes the card name as a literal arg to
# ``test_signals`` inline (not behind a wrapper) so the usage scanner in
# ``build-card-snapshot`` discovers the name and snapshots the card. (Names containing
# an apostrophe can't ride that scanner — its delimiter regex stops at the quote —
# so those stay out of this file's real-card coverage.)


def _striples(sigs: list) -> list[tuple[str, str, str]]:
    """Sorted (key, scope, subject) triples production emits for a real card."""
    return sorted((s.key, s.scope, s.subject) for s in sigs)


def _skeys(sigs: list) -> set[str]:
    return {s.key for s in sigs}


# ── lifegain_matters: ADR-0027 C10 — A2 grant-lifelink + ARM-B self-loss ───────


def test_lifegain_from_grant_lifelink_source():
    # Talus Paladin "Allies you control gain lifelink": granting lifelink makes them a
    # lifegain SOURCE (CR 702.15b), same lane as the card's own lifelink keyword.
    # _matters sweep (ADR-0034): granting a lifegain source is the MAKER arm →
    # lifegain_makers (parallel to the own-lifelink keyword map).
    assert ("lifegain_makers", "you", "") in _striples(test_signals("Talus Paladin"))


def test_lifegain_from_scaling_self_loss():
    # Dark Confidant "You lose life equal to its mana value" — a scaling self-bleed
    # (op=count) that wants lifegain to sustain it (CR 119.3).
    assert ("lifegain_matters", "you", "") in _striples(test_signals("Dark Confidant"))


def test_lifegain_from_recurring_upkeep_bleed():
    # Benthic Djinn "At the beginning of your upkeep, you lose 2 life" — a recurring
    # fixed >=2 upkeep bleed.
    assert ("lifegain_matters", "you", "") in _striples(test_signals("Benthic Djinn"))


def test_lifegain_from_draw_bleed_engine():
    # Disciple of Perdition: a death-triggered ability that BOTH draws and makes you
    # lose life is a Necropotence-style draw-bleed engine — recurrence is the
    # significance, so the fixed-factor-1 floor does not apply.
    assert ("lifegain_matters", "you", "") in _striples(
        test_signals("Disciple of Perdition")
    )


# ── graveyard_matters pass 2 (from:graveyard recursion / search, exile-in-GY
#    hate, scope fidelity — ADR-0027) ───────────────────────────────────────────


def test_graveyard_bounce_from_graveyard_scoped_you():
    """A bounce returning cards FROM your graveyard to hand (Metallurgic Summonings,
    from:graveyard) fires graveyard_matters at you — the broad graveyard-mention mirror
    fires on the "your graveyard" oracle (the structural recursion arm also fires the
    graveyard_makers MAKER, _matters sweep ADR-0034)."""
    assert ("graveyard_matters", "you", "") in _striples(
        test_signals("Metallurgic Summonings")
    )


def test_removecounter_cost_with_p1p1_oracle_fires():
    """An ability whose COST removes +1/+1 counters (Triskelion ping) fires
    plus_one_matters when the oracle names '+1/+1 counter'."""
    assert "plus_one_matters" in _skeys(test_signals("Triskelion"))


def test_removecounter_cost_without_p1p1_oracle_excluded():
    """A removecounter cost on a NON-+1/+1 counter card (Gemstone Mine — a mining /
    depletion sink) stays out of the +1/+1 lane (CR 122.1)."""
    assert "plus_one_matters" not in _skeys(test_signals("Gemstone Mine"))


# ── removal shapes (ADR-0027) ─────────────────────────────────────────


def test_damage_to_creature_fires_removal_matters():
    """A damage effect to a target creature (Flame Slash) fires removal — the
    regex routed this only to direct_damage; the lane was never wired to damage."""
    assert ("removal", "you", "") in _striples(test_signals("Flame Slash"))


def test_cast_spell_trigger_fires_spellcast_matters():
    # ADR-0027 (SIDECAR 50): the structural arm fires on a `cast_spell` trigger
    # scope='any' over a typed-noncreature subject (Instant/Sorcery) when the card
    # oracle says "you cast" — the Talrand you-cast PAYOFF. phase scopes "you cast" and
    # the symmetric "a player casts" both 'any', so the oracle "you cast" is the gate.
    assert ("spellcast_matters", "you") in {
        (k, s) for (k, s, _u) in _striples(test_signals("Talrand, Sky Summoner"))
    }


def test_combat_damage_matters_fires_from_recipient_structure():
    """ADR-0027 (SIDECAR v41): the base CR-510.1b combat_damage_matters lane reads the
    STRUCTURED recipient TYPE phase carries on the combat_damage trigger's valid_target
    (project → trig.recipient). A player/planeswalker recipient ("to one of your
    opponents" → Typed{controller:Opponent} → recipient=("player",)) fires the base lane
    (scope opponents); the three recipient-word mirrors are deleted."""
    assert ("combat_damage_matters", "opponents", "") in _striples(
        test_signals("Edric, Spymaster of Trest")
    )


# ── composite-filter lanes (Batch 12) ─────────────────────────────────────────


def test_nonhuman_attackers_from_attack_trigger():
    """Winota: 'whenever a non-Human creature you control attacks' — NotSubtype:Human
    on the attacking subject, controller you."""
    assert ("nonhuman_attackers", "you", "") in _striples(
        test_signals("Winota, Joiner of Forces")
    )


def test_base_pt_set_fires():
    # ADR-0027 Cluster C: the base_pt_set arm fires only when the effect's raw NAMES a
    # base P/T (the fixed-set toolbox) or carries the v32 SelfBasePt marker — so a bare
    # land/artifact mass-animate ("is a N/N creature") stays out of the lane. Lignify's
    # raw names "base power and toughness 0/4".
    assert ("base_pt_set", "any", "") in _striples(test_signals("Lignify"))


# ── ADR-0027 #24 — GRANTED damage-reflection structural recovery (REAL oracle) ──
# phase has no first-class node for a reflection ability granted/quoted onto a CLASS
# of creatures (Spiteful Sliver → a `board_grant` raw + a split `damage` static), a
# targeted grant (Arcbond), or a paired-subject trigger phase couldn't model (Donna
# Noble). The supplement `_recover_damage_reflect` synthesizes a damage_reflect
# Effect from the raw oracle, so the previously-dead `cat=='damage_reflect'` IR read
# becomes load-bearing. CR 120.3.


def test_spiteful_sliver_granted_reflection_recovers_damage_reflect():
    """Spiteful Sliver grants every Sliver 'Whenever this creature is dealt damage,
    it deals that much damage to target player or planeswalker' — phase folds the
    quoted reflection into a board_grant. The recovery synthesizes a damage_reflect
    Effect so the lane reads STRUCTURE."""
    card = test_card_ir("Spiteful Sliver")
    assert any(
        e.category == "damage_reflect"
        for ab in card.all_abilities()
        for e in ab.effects
    )
    assert "damage_reflect" in _skeys(test_signals("Spiteful Sliver"))


def test_arcbond_targeted_reflection_grant_fires_damage_reflect():
    """Arcbond: 'Whenever that creature is dealt damage this turn, it deals that much
    damage to each other creature and each player' — a targeted reflection grant phase
    leaves unstructured. Recovered structurally."""
    assert "damage_reflect" in _skeys(test_signals("Arcbond"))


def test_donna_noble_paired_reflection_fires_damage_reflect():
    """Donna Noble: 'Whenever Donna Noble or a creature it's paired with is dealt
    damage, Donna Noble deals that much damage to target opponent' — a compound-
    subject trigger phase couldn't model. Recovered structurally."""
    assert "damage_reflect" in _skeys(test_signals("Donna Noble"))


def test_silence_addrestriction_opp_is_stax_taxes():
    """Silence: AddRestriction whose restriction.affected_players is
    OpponentsOfSourceController projects to a restriction scope='opp' (CR 604.1)."""
    assert "stax_taxes" in _skeys(test_signals("Silence"))


def test_enters_tapped_opponents_is_stax_taxes():
    """Imposing Sovereign / Kinjalli's Sunwing: the enters-tapped ChangeZone
    replacement projects to enters_tapped scope='opp' (valid_card.controller). CR
    614.1c."""
    keys = _skeys(test_signals("Imposing Sovereign"))
    assert "stax_taxes" in keys
    assert "symmetric_stax" not in keys


def test_enters_tapped_symmetric_is_symmetric_stax():
    """Orb of Dreams: 'Permanents enter tapped' (valid_card.controller null) is
    symmetric — scope='each' (CR 604.1)."""
    keys = _skeys(test_signals("Orb of Dreams"))
    assert "symmetric_stax" in keys
    assert "stax_taxes" not in keys


def test_symmetric_cost_tax_cofires_stax_taxes():
    """Sphere of Resistance / Thalia: a symmetric cost-tax (ModifyCost-Raise,
    counter_kind='stax_tax') is symmetric_stax AND co-fires stax_taxes — a symmetric
    tax still hobbles opponents (CR 601.2f)."""
    keys = _skeys(test_signals("Sphere of Resistance"))
    assert "stax_taxes" in keys
    assert "symmetric_stax" in keys


# ── ADR-0027 #24 — OPPONENT cast-lock structural recovery (REAL oracle) ────────
# phase drops the "your opponents can't cast spells [during your turn/combat]"
# player-lock static WHOLLY (Dragonlord Dromoka parses to ZERO abilities). The
# supplement `_recover_opponent_cast_lock` synthesizes a restriction Effect (scope
# opp) from the raw, so the migrated stax arm reads STRUCTURE and the residue mirror
# defers to it via `(?! cast)`. CR 601.3 / 604.1.


def test_dragonlord_dromoka_opponent_cast_lock_recovers_restriction():
    """Dragonlord Dromoka: 'Your opponents can't cast spells during your turn' — phase
    emits ZERO abilities. The recovery synthesizes a restriction Effect scope='opp' so
    stax_taxes reads STRUCTURE, not the byte-mirror."""
    card = test_card_ir("Dragonlord Dromoka")
    assert any(
        e.category == "restriction" and e.scope == "opp"
        for ab in card.all_abilities()
        for e in ab.effects
    )
    assert "stax_taxes" in _skeys(test_signals("Dragonlord Dromoka"))


def test_myrel_opponent_cast_lock_recovers_restriction():
    """Myrel, Shield of Argive: 'During your turn, your opponents can't cast spells or
    activate abilities …' — phase drops the lock (keeps only the token ETB). Recovered
    structurally as a restriction scope='opp'."""
    assert "stax_taxes" in _skeys(test_signals("Myrel, Shield of Argive"))


def test_failure_comply_split_face_castlock_fires():
    """Failure // Comply: the Comply aftermath face ('your opponents can't cast spells
    with the chosen name') is a split face phase emits NO RECORD FOR AT ALL — confirmed
    empirically (task #74): phase's ``card-data.json`` has exactly one entry keyed
    ``"failure"`` (carrying the split card's shared ``scryfall_oracle_id``) and none
    keyed ``"comply"`` anywhere in the corpus, so the build-time supplement can't see
    it. This is DIFFERENT from the DFC face-drop task #74 otherwise fixed (a DFC's
    back face DOES have its own phase record, sharing the oracle_id, that a
    first-record-wins index dropped — ``_ir_lookup.trees_for`` now reads every face
    record per oracle_id and unions their signals); here there is no second phase
    record to read.

    ADR-0038 W2c closes this specific gap: ``trees_for`` now also synthesizes a
    zero-unit TEXT-ONLY tree per phase-missing face, off the bulk (MTGJSON) record's
    own ``card_faces`` text — the bulk record is the text source of record when
    phase never parses the face at all. Comply's text-only tree's whole-card
    ``oracle`` field carries "...your opponents can't cast spells with the chosen
    name", which the EXISTING ``_stax_lanes`` bucket-B residue scan
    (``_STAX_TAXES_RESIDUE_RE``, unchanged) reads directly — no new stax machinery,
    just a tree for it to read now. DOCUMENTED REPLACEMENT of the prior
    ``..._is_a_known_crosswalk_gap`` test (same precedent as the Planar Genesis /
    ADR-0037 promotions): flag ON now FIRES stax_taxes structurally, matching
    flag-OFF's legacy residue-mirror behavior, so both paths agree."""
    keys = _skeys(test_signals("Failure // Comply"))
    assert "stax_taxes" in keys, f"keys={sorted(keys)}"


def test_symmetric_untap_lock_is_symmetric_only():
    """Back to Basics: a symmetric UNTAP lock (no stax_tax marker) is symmetric_stax
    only — it is not a cost/cast tax, so it does not co-fire stax_taxes."""
    keys = _skeys(test_signals("Back to Basics"))
    assert "symmetric_stax" in keys
    assert "stax_taxes" not in keys


def test_debuff_anthem_on_opponents_is_not_stax():
    """Elesh Norn / Cower in Fear: 'Creatures your opponents control get -2/-2' is a
    pump (debuff), NOT a restriction — the deleted byte-mirror's over-fire. The
    structural arm correctly keeps it OUT of stax (it rides debuff_makers)."""
    keys = _skeys(test_signals("Elesh Norn, Grand Cenobite"))
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_single_target_aura_untap_lock_is_not_symmetric_stax():
    """Dehydration: 'Enchanted creature doesn't untap' is a single-target Aura lock
    (CR 303.4) — restriction scope='any' pred=EnchantedBy — NOT a symmetric lock. The
    deleted byte-mirror wrongly fired symmetric_stax on it; the residue mirror drops
    the `doesn't untap during` branch, so it stays out."""
    assert "symmetric_stax" not in _skeys(test_signals("Dehydration"))


def test_residue_mirror_recovers_wholly_dropped_opponent_cast_lock():
    """Dragonlord Dromoka: phase drops 'Your opponents can't cast spells during your
    turn' entirely (zero restriction Effect). The narrow residue keep-mirror recovers
    it as stax_taxes off the reminder-stripped oracle."""
    # STRUCTURAL GAP (task #24): phase emits ZERO restriction Effect for Dromoka's
    # "Your opponents can't cast spells during your turn" — the narrow residue
    # keep-mirror recovers it as stax_taxes off the reminder-stripped oracle.
    assert "stax_taxes" in _skeys(test_signals("Dragonlord Dromoka"))


# ── ADR-0027 C6 over-fire fix — single-attached pacify Aura is NOT stax ────────
# Real cards from the snapshot, so the full hybrid path exercises
# _is_single_attached_restriction + _restriction_scope + the stax_tax marker gate over
# the EXACT production IR (built on demand from the snapshot's stored phase records).


def test_pacify_aura_arrest_is_not_stax():
    """Arrest: 'its activated abilities can't be activated' (CantBeActivated,
    who=AllPlayers) on a SelfRef Aura host is single-target pacify (CR 303.4), NOT a
    board-wide tax. The over-fire fix gates it out of BOTH stax lanes despite the
    AllPlayers ``who`` (which only says no player may act on that one creature)."""
    keys = _skeys(test_signals("Arrest"))
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_symmetric_static_orb_still_symmetric_stax():
    """Static Orb: a symmetric 'players can't untap …' lock STILL fires symmetric_stax
    (untap-lock — no stax_tax co-fire), proving the fix does not over-suppress genuine
    board-wide stax."""
    keys = _skeys(test_signals("Static Orb"))
    assert "symmetric_stax" in keys
    assert "stax_taxes" not in keys


def test_prison_piece_null_rod_still_fires_both():
    """Null Rod: 'Activated abilities of artifacts can't be activated' — a real
    card-CLASS source_filter (Typed Artifact, no attach predicate) is genuine symmetric
    stax. It keeps firing symmetric_stax AND co-fires stax_taxes (stax_tax marker)."""
    keys = _skeys(test_signals("Null Rod"))
    assert "symmetric_stax" in keys
    assert "stax_taxes" in keys


# ── ADR-0027 C6 FINAL — AFFECTED-ENTITY discriminator (not card type) ──────────
# What a restriction taxes is decided by WHO/WHAT it restricts, never by the host's
# card type (CR 303.4: an Aura attaches to an object OR a PLAYER — an "Enchant player"
# Curse is a player tax, an "Enchant creature" Aura is single-target pacify). The
# discriminator reads the restriction's AFFECTED ENTITY two ways: from a STRUCTURED
# EnchantedBy/EquippedBy subject (phase v0.9.0 cleanly structures Lost in Thought's
# host as Typed Creature EnchantedBy), and — for older/mangled parses where phase
# leaked the Effect to scope='opp' subject=None — from the raw clause. A SINGLE
# creature → drop both lanes; a PLAYER / BOARD → keep. CR 303.4 / 301.5 / 608.2.


def test_pacify_aura_lost_in_thought_is_not_stax():
    """Lost in Thought: "Enchanted creature can't attack or block, and its activated
    abilities can't be activated." A single-attach ability-lock aura (CR 303.4 — one
    object), NOT a board-wide tax. phase v0.9.0 structures the host as a Typed Creature
    EnchantedBy subject, so the `restriction_single_creature` gate reads the structured
    EnchantedBy predicate (the v0.8.0 subject=None raw-supplement path is the backstop)
    and excludes it from BOTH stax lanes."""
    keys = _skeys(test_signals("Lost in Thought"))
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_pacify_aura_trapped_in_the_tower_is_not_stax():
    """Trapped in the Tower: 'Enchant creature without flying' on line 1 + 'can't
    attack' on line 2 form ONE un-split clause; the old residue regex bridged the
    newline (and matched `with` inside 'without'). The tightened regex AND the
    affected-entity ('Enchanted creature' = single) residue guard both keep it out of
    BOTH stax lanes."""
    keys = _skeys(test_signals("Trapped in the Tower"))
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_aura_player_tax_curse_of_exhaustion_fires_stax():
    """Curse of Exhaustion ('Enchant player' Aura): 'Enchanted player can't cast more
    than one spell each turn' is a genuine PLAYER tax (Rule-of-Law on one opponent),
    NOT single-target creature pacify. The affected-entity discriminator KEEPS it —
    the card-type gate wrongly dropped every Aura-hosted player tax."""
    assert "stax_taxes" in _skeys(test_signals("Curse of Exhaustion"))


def test_vow_single_target_cant_attack_you_is_not_stax():
    """Vow of Duty (single-target 'Enchant creature' Aura): 'Enchanted creature …
    can't attack you or planeswalkers you control' restricts the ONE enchanted
    creature — single-target pacify, NOT a board pillowfort. The `can't attack you`
    residue branch is ambiguous; the affected-entity guard ('Enchanted creature' =
    single, no player/board tell) keeps it out of BOTH lanes."""
    keys = _skeys(test_signals("Vow of Duty"))
    assert "stax_taxes" not in keys
    assert "symmetric_stax" not in keys


def test_board_counter_tax_with_that_creature_rider_still_fires():
    """Nils, Discipline Enforcer: 'Each creature with one or more counters … can't
    attack you … where X is the number of counters on that creature' is a BOARD tax —
    the trailing 'that creature' names the per-creature count, NOT the affected entity.
    'Each creature' is a board tell, so the discriminator keeps it firing (regression:
    a naive single-creature regex would match 'that creature' and wrongly drop it)."""
    assert "stax_taxes" in _skeys(test_signals("Nils, Discipline Enforcer"))


# ── named_synergy / copy_limit (Task #19 SPLIT of the old named_permanent) ────────
# named_synergy (CR 201.4 named refs / 201.5 self-reference) is the named-card SYNERGY
# lane — a card referencing a specific OTHER card by name. phase drops the referenced
# name, so it rides a kept word mirror (_NAMED_PERMANENT_SWEEP_RE in _IR_KEPT_DETECTORS
# over the reminder-stripped oracle, scope 'you'). copy_limit (CR 100.2a) is its
# SIBLING — the deck copy-limit relaxation, read STRUCTURALLY off the IR `many_copies`
# field. They are genuinely different deck concerns (named-partner vs swarm-of-copies).


def test_named_card_synergy_fires_named_synergy_from_kept_mirror():
    """A card naming a specific partner (CR 201.4) fires the named_synergy mirror —
    NOT copy_limit (no deck-relaxation field). Festering Newt names Bogbrew Witch."""
    keys = _skeys(test_signals("Festering Newt"))
    assert "named_synergy" in keys
    assert "copy_limit" not in keys


def test_copy_limit_field_fires_copy_limit_not_named_synergy():
    """The CR 100.2a copy-limit population (ir.many_copies) fires its OWN structural
    lane, copy_limit. Relentless Rats' pump phrasing ("each other creature on the
    battlefield named …") does NOT match the named_synergy mirror (which anchors on
    "control a creature named" / "permanent named"), so it fires copy_limit ALONE —
    confirming the two lanes are genuinely distinct populations."""
    keys = _skeys(test_signals("Relentless Rats"))
    assert "copy_limit" in keys
    assert "named_synergy" not in keys


def test_pure_copy_limit_does_not_fire_named_synergy():
    """A bare copy-limit card (only "A deck can have any number of cards named X", no
    "creature/permanent named X" synergy clause) fires copy_limit ALONE."""
    keys = _skeys(test_signals("Shadowborn Apostle"))
    assert "copy_limit" in keys
    assert "named_synergy" not in keys


def test_seven_dwarves_fires_both_lanes():
    """Seven Dwarves is many_copies True AND names itself ("creature named Seven
    Dwarves") — the lone overlap card, it fires BOTH copy_limit (the field) and
    named_synergy (the mirror clause)."""
    keys = _skeys(test_signals("Seven Dwarves"))
    assert "named_synergy" in keys
    assert "copy_limit" in keys


def test_voltron_maker_attach_other_object():
    # _matters sweep (ADR-0034): Kor Outfitter attaches ANOTHER Equipment onto a
    # creature (a doer) — the MAKER arm voltron_makers, not the payoff lane.
    assert ("voltron_makers", "you", "") in _striples(test_signals("Kor Outfitter"))


def test_voltron_payoff_cast_aura_equipment_trigger():
    # Sram, Senior Edificer — a cast-an-Aura/Equipment/Vehicle-spell trigger (PAYOFF).
    assert ("voltron_matters", "you", "") in _striples(
        test_signals("Sram, Senior Edificer")
    )


def test_voltron_maker_tutor_for_equipment_card():
    # _matters sweep (ADR-0034): Godo searches the library for an Equipment card (a
    # fetch doer) — the MAKER arm voltron_makers, not the payoff lane.
    assert ("voltron_makers", "you", "") in _striples(
        test_signals("Godo, Bandit Warlord")
    )


def test_voltron_payoff_attachment_state_predicate():
    # Koll, the Forgemaster — cares about "enchanted or equipped" creatures.
    assert ("voltron_matters", "you", "") in _striples(
        test_signals("Koll, the Forgemaster")
    )


def test_voltron_payoff_excludes_etb_self_attach():
    # "When Mithril Coat enters, attach it to target legendary creature you control" is
    # still self-attach (the gear), not a build-around.
    assert ("voltron_matters", "you", "") not in _striples(test_signals("Mithril Coat"))


def test_voltron_payoff_excludes_removal_aura():
    # Pacifism — a static "enchant creature" removal Aura carries no Attach EFFECT,
    # so it never opens the voltron lane (parity with the regex floor).
    assert ("voltron_matters", "you", "") not in _striples(test_signals("Pacifism"))


def _smatters(sigs: list) -> set[tuple[str, str]]:
    return {
        (s.key, s.subject)
        for s in sigs
        if s.key in ("artifacts_matter", "enchantments_matter")
    }


def test_type_tutor_fires_matters_lane():
    # Idyllic Tutor — "search your library for an enchantment card" (subtypes empty).
    assert _smatters(test_signals("Idyllic Tutor")) == {("enchantments_matter", "")}


def test_type_dig_fires_matters_lane():
    # Glint-Nest Crane — "look at the top four cards, put an artifact into your hand".
    assert _smatters(test_signals("Glint-Nest Crane")) == {("artifacts_matter", "")}


def test_composite_tutor_fires_both_lanes():
    # Enlightened Tutor — "an artifact or enchantment card" fires BOTH lanes.
    assert _smatters(test_signals("Enlightened Tutor")) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


def test_subtype_tutor_does_not_fire_matters_lane():
    # Open the Armory — "search for an Aura or Equipment card" is the narrower
    # voltron care, NOT artifacts_matter (the subtypes==() gate excludes it).
    assert _smatters(test_signals("Open the Armory")) == set()


def test_generic_permanent_tutor_does_not_fire_matters_lane():
    # Wargate — "a permanent card" is neither Artifact nor Enchantment.
    assert _smatters(test_signals("Wargate")) == set()


def test_mass_recursion_fires_matters_lane():
    # Replenish — "Return ALL enchantment cards from your graveyard to the battlefield"
    # (mass tell, graveyard-sourced, controller you). A non-artifact host so the only
    # _smatters member is the recursion payoff, not own-type membership.
    assert _smatters(test_signals("Replenish")) == {("enchantments_matter", "")}


def test_single_target_recursion_fires_matters_lane():
    # SETTLED RULE (ADR-0027): a single-target TYPE-RESTRICTED recursion fires the lane
    # — the discriminator is the target FILTER's card-type, not mass-vs-single (CR
    # 115.1/115.10), since type-gating = only useful in that type's deck. Auramancer
    # ("return TARGET enchantment card", a non-artifact host) fires enchantments_matter;
    # Argivian Find (single-target COMPOSITE "artifact OR enchantment card") fires BOTH.
    assert _smatters(test_signals("Auramancer")) == {("enchantments_matter", "")}
    assert _smatters(test_signals("Argivian Find")) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


def test_generic_target_recursion_does_not_fire_matters_lane():
    # The over-fire boundary: a GENERIC-target recursion ("return target card" —
    # Regrowth) is NOT type-gated, so it fires nothing.
    assert _smatters(test_signals("Regrowth")) == set()


def test_composite_mass_recursion_fires_both_lanes_any_controller():
    # Open the Vaults — "return all artifact and enchantment cards from all graveyards"
    # (composite, controller any) fires both lanes.
    assert _smatters(test_signals("Open the Vaults")) == {
        ("artifacts_matter", ""),
        ("enchantments_matter", ""),
    }


# ── token-maker + sac-payoff + cost-payer + becomes + ability-payoff (ADR-0027) ─


def test_artifact_token_maker_fires_artifacts_lane():
    # Beza, the Bounding Spring — a Treasure-token maker phase carries by SUBTYPE with
    # an empty card_types tuple (CR 205.3g) still fires artifacts_matter.
    assert _smatters(test_signals("Beza, the Bounding Spring")) == {
        ("artifacts_matter", "")
    }


def test_sac_artifact_effect_fires_artifacts_lane():
    # Giant Opportunity — "sacrifice two Foods" (artifact-token sac payoff) fires
    # artifacts_matter (Food is an artifact token).
    assert _smatters(test_signals("Giant Opportunity")) == {("artifacts_matter", "")}


def test_sac_an_artifact_cost_fires_artifacts_lane():
    # Atog — "Sacrifice an artifact: …" (cost-payer); project surfaces the typed
    # sacrifice marker so artifacts_matter fires.
    assert _smatters(test_signals("Atog")) == {("artifacts_matter", "")}


def test_becomes_artifact_grant_fires_artifacts_lane():
    # Sydri, Galvanic Genius — a noncreature artifact "becomes an artifact creature"
    # animate (the becomes/animate-artifact marker) fires artifacts_matter.
    assert _smatters(test_signals("Sydri, Galvanic Genius")) == {
        ("artifacts_matter", "")
    }


def test_ability_of_artifact_trigger_fires_artifacts_lane():
    # Kurkesh, Onakke Ancient — "whenever you activate an ability of an artifact"
    # (event='other', typed subject, scope != opp).
    assert _smatters(test_signals("Kurkesh, Onakke Ancient")) == {
        ("artifacts_matter", "")
    }


def test_investigate_keyword_fires_artifacts_lane():
    # Deduce — Investigate (CR 701.27) makes a Clue (a colorless ARTIFACT); the Scryfall
    # keyword is the anchor (phase drops the Clue subtype).
    assert _smatters(test_signals("Deduce")) == {("artifacts_matter", "")}


def test_devour_keyword_opens_plus_one_makers():
    """Devour (CR 702.82) enters with +1/+1 counters per sacrificed creature — a
    definitional +1/+1 MAKER, so the printed keyword opens plus_one_makers (_matters
    sweep ADR-0034) as well as has_devour (Preyseizer Dragon, whose devour rides the
    keyword + a board_count, not a structured `devour` effect)."""
    keys = _skeys(test_signals("Preyseizer Dragon"))
    assert "has_devour" in keys
    assert "plus_one_makers" in keys


# ── plus_one_makers granted/token-body class (task #87) ────────────────────────


def test_token_own_devour_keyword_opens_plus_one_makers():
    """Dragon Broodmother's OWN top-level keywords are just ``Flying`` — the
    Devour (CR 702.82) lives on the CREATED Dragon token's own keyword
    profile (``{Devour: 2}``), not on Dragon Broodmother's card. See
    ``crosswalk.nested_plus_one_keyword_grant``'s token-profile arm."""
    keys = _skeys(test_signals("Dragon Broodmother"))
    assert "plus_one_makers" in keys


def test_granted_bloodthirst_static_opens_plus_one_makers():
    """Twins of Discord's "Each other colorless creature you control has
    bloodthirst 2" (CR 702.54) is a top-level static AddKeyword grant to
    OTHER creatures — never Twins of Discord's own keyword array."""
    keys = _skeys(test_signals("Twins of Discord"))
    assert "plus_one_makers" in keys


def test_granted_scavenge_static_opens_plus_one_makers():
    """Varolz's "Each creature card in your graveyard has scavenge" (CR
    702.97) grants the keyword to graveyard cards, not Varolz itself."""
    keys = _skeys(test_signals("Varolz, the Scar-Striped"))
    assert "plus_one_makers" in keys


def test_granted_evolve_static_opens_plus_one_makers():
    """Propagator Drone's "Creature tokens you control have evolve" grants
    Evolve (CR 702.106) to tokens it makes, not itself."""
    keys = _skeys(test_signals("Propagator Drone"))
    assert "plus_one_makers" in keys


def test_granted_training_static_opens_plus_one_makers():
    """Elder Arthur Maxson's "Creature tokens you control have training"
    grants Training (CR 702.149) to tokens, not itself."""
    keys = _skeys(test_signals("Elder Arthur Maxson"))
    assert "plus_one_makers" in keys


def test_copy_exception_dethrone_opens_plus_one_makers():
    """Dack's Duplicate's "...except it has haste and dethrone" is a
    BecomeCopy replacement's ``additional_modifications`` copy-exception
    grant (CR 702.103 Dethrone) — a different field than a static's
    ``modifications``."""
    keys = _skeys(test_signals("Dack's Duplicate"))
    assert "plus_one_makers" in keys


def test_equip_granted_mentor_opens_plus_one_makers():
    """Aegis of the Legion's "Equipped creature gets +1/+1 and has mentor"
    (CR 702.134) grants Mentor via Equip, not Enchant — the granted-keyword
    read doesn't gate on the attach mechanism (Aura vs Equipment), unlike
    the separate pacify_makers concept."""
    keys = _skeys(test_signals("Aegis of the Legion"))
    assert "plus_one_makers" in keys


# ── plus_one_makers ChooseOneOf modal-branch class (task #93) ───────────────


def test_fabricate_choose_one_of_branch_opens_plus_one_makers():
    """Glint-Sleeve Artisan's Fabricate 1 (CR 702.146) is a ``ChooseOneOf``
    modal with a "+1/+1 counter" branch and a "Servo token" branch — the
    genuine ``PutCounter``/``P1P1`` node sits INSIDE the branch, which
    ``effect_concepts`` never reaches."""
    keys = _skeys(test_signals("Glint-Sleeve Artisan"))
    assert "plus_one_makers" in keys


def test_tizerus_charger_escape_choice_opens_plus_one_makers():
    """Tizerus Charger's Escape-cost replacement ("your choice of a +1/+1
    counter or a flying counter") is the SAME ChooseOneOf-branch shape,
    off a REPLACEMENT-origin unit rather than a triggered ETB."""
    keys = _skeys(test_signals("Tizerus Charger"))
    assert "plus_one_makers" in keys


def test_iteration_kind_rebind_does_not_open_plus_one_makers():
    """Negative pin: Quarry Hauler's "for each kind of counter on target
    permanent, put ANOTHER counter of that kind on it or remove one from
    it" is a kind-AGNOSTIC loop — phase's own iteration-kind rebind marker
    on the branch means the "P1P1" typed value is a loop-iteration
    sentinel, not a genuine +1/+1 reference (the card's own text never
    says "+1/+1"). Must stay OUT of plus_one_makers."""
    keys = _skeys(test_signals("Quarry Hauler"))
    assert "plus_one_makers" not in keys


def test_saga_created_token_custom_trigger_opens_plus_one_makers():
    """Ral and the Implicit Maze's chapter III creates a Spellgorger Weird
    token whose OWN "whenever you cast a noncreature spell, put a +1/+1
    counter" is a CUSTOM triggered ability, not a keyword — the created
    Token effect node carries an empty ``keywords`` list and no
    ``static_abilities`` field at all (same predefined/custom-ability
    substrate gap as the Mutagen/Young-Hero-Role token cycles). Task
    #np_roles CLOSED that gap: "Spellgorger Weird" joined
    ``_KNOWN_TOKEN_WIRED_DISPLAY_NAMES``, so the known-tokens substrate now
    appends the token's text-only tree and the SAME arms that serve Young
    Hero's self-counter attack trigger fire here (plus_one_makers via
    ``_arm_plus_one_makers``, spellcast_matters via
    ``_arm_spellcast_matters``) — this pin flipped from stays-out to opens
    when the wiring landed."""
    keys = _skeys(test_signals("Ral and the Implicit Maze"))
    assert "plus_one_makers" in keys
    assert "spellcast_matters" in keys


def test_sunburst_grant_stays_out_of_plus_one_makers():
    """Lux Artillery grants Sunburst (CR 702.44) to a cast artifact
    CREATURE spell — but Sunburst itself branches +1/+1 counters (creature)
    vs charge counters (noncreature) depending on the affected permanent's
    own type, a fork ``nested_plus_one_keyword_grant`` can't resolve off
    the bare ``TriggeringSource``/``ParentTarget`` affected-ref alone.
    Deliberately excluded from the keyword set — genuinely different from
    the unconditionally-P1P1 keywords (Devour/Bloodthirst/Scavenge/
    Dethrone/Evolve/Training)."""
    keys = _skeys(test_signals("Lux Artillery"))
    assert "plus_one_makers" not in keys


def test_riot_grant_stays_out_of_plus_one_makers():
    """Domri, Chaos Bringer grants Riot (CR 702.136) to a creature spell —
    a haste-OR-counter CHOICE, never a guaranteed placement. Native Riot
    isn't in the plus-one-counters Preset's own keyword list either; this
    doesn't reopen that call."""
    keys = _skeys(test_signals("Domri, Chaos Bringer"))
    assert "plus_one_makers" not in keys


# ── plus_one_makers GrantTrigger-nested class (task #94) ────────────────────


def test_aura_granted_dies_trigger_opens_plus_one_makers():
    """Eternal Thirst's "Enchanted creature has lifelink and 'Whenever a
    creature an opponent controls dies, put a +1/+1 counter on this
    creature.'" is a top-level static's ``GrantTrigger`` modification
    whose OWN granted trigger's ``execute`` chain carries the genuine
    ``PutCounter``/``P1P1`` node — a level deeper than
    ``effect_concepts`` reaches, and a different shape than the granted-
    KEYWORD class ``nested_plus_one_keyword_grant`` already covers."""
    keys = _skeys(test_signals("Eternal Thirst"))
    assert "plus_one_makers" in keys


def test_commander_anthem_granted_attack_trigger_opens_plus_one_makers():
    """Agent of the Shadow Thieves's "Commander creatures you own have
    'Whenever this creature attacks a player, ... put a +1/+1 counter on
    this creature. ...'" is the SAME GrantTrigger-nested-effect shape, off
    a commander-only anthem rather than an Aura."""
    keys = _skeys(test_signals("Agent of the Shadow Thieves"))
    assert "plus_one_makers" in keys


def test_soulbond_granted_spellcast_trigger_opens_plus_one_makers():
    """Thundering Mightmare's Soulbond-paired "each of those creatures has
    'Whenever an opponent casts a spell, put a +1/+1 counter on this
    creature.'" is the same GrantTrigger-nested shape gated behind a
    ``SourceIsPaired`` static condition rather than an Enchant/Equip/
    Commander filter."""
    keys = _skeys(test_signals("Thundering Mightmare"))
    assert "plus_one_makers" in keys


def test_mutagen_token_ability_opens_plus_one_makers():
    """Mutagen Man's created Mutagen token has its OWN activated ability
    ("{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target
    creature") — phase's card-data parse carries NO ability body at all
    for this predefined token (the Token effect node's ``keywords``/
    ``static_abilities`` fields are both empty), a genuine substrate gap
    rather than a missed structural read. Task #92's known-tokens
    substrate closes it: the source card's ``metadata.related_token_ids``
    joins to phase's own ``known-tokens.toml`` data, contributing an extra
    text-only tree carrying the token's real rules text, which the
    existing ``plus_one_makers`` bucket-B idiom then reads structurally."""
    keys = _skeys(test_signals("Mutagen Man, Living Ooze"))
    assert "plus_one_makers" in keys


def test_young_hero_role_token_opens_plus_one_makers():
    """Cut In's created Young Hero Role token has its OWN triggered
    ability ("Whenever this creature attacks, if its toughness is 3 or
    less, put a +1/+1 counter on it") — same predefined-token substrate
    gap as the Mutagen cycle, closed the same way by task #92's
    known-tokens substrate (see
    ``test_mutagen_token_ability_opens_plus_one_makers``)."""
    keys = _skeys(test_signals("Cut In"))
    assert "plus_one_makers" in keys


# ── pacify_makers (task #87) — Pacifism/Arrest class ────────────────────────


def test_pacifism_separate_cantattack_cantblock_opens_pacify_makers():
    """Pacifism's two SEPARATE static defs (CantAttack, CantBlock — each
    its own top-level static_abilities entry) both carry an EnchantedBy
    affected filter (CR 508.1a/509.1b); one is enough to open the lane."""
    keys = _skeys(test_signals("Pacifism"))
    assert "pacify_makers" in keys


def test_arrest_combined_cantattackorblock_opens_pacify_makers():
    """Arrest's single CantAttackOrBlock static (plus a co-occurring
    CantBeActivated rider that doesn't need to gate anything separately)."""
    keys = _skeys(test_signals("Arrest"))
    assert "pacify_makers" in keys


def test_negative_pt_rider_stays_in_pacify_makers():
    """Cast into Darkness's "-2/-0 and can't block" — a DEBUFF alongside
    the restriction (mod_value < 0) is the same "shut this down" archetype
    as a pure Pacifism, not a compensating benefit — stays IN."""
    keys = _skeys(test_signals("Cast into Darkness"))
    assert "pacify_makers" in keys


def test_rider_activated_ability_does_not_veto_pacify_makers():
    """Gelid Shackles's OPTIONAL "{S}: Enchanted creature gains defender
    until end of turn" lives in a DIFFERENT, ability-origin unit (a rider
    the Aura's controller must additionally pay for) — it must not veto
    the top-level CantBlock static's own pacify_makers firing."""
    keys = _skeys(test_signals("Gelid Shackles"))
    assert "pacify_makers" in keys


def test_positive_pump_rider_vetoes_pacify_makers():
    """Cagemail's "+2/+2 and can't attack" — a POSITIVE combat buff
    alongside the restriction is the "Rage" cycle's aggro-enabler
    archetype (cast on YOUR OWN creature to trade blocking for stats),
    never the Pacifism/Arrest neutralize-a-threat shape."""
    keys = _skeys(test_signals("Cagemail"))
    assert "pacify_makers" not in keys


def test_granted_keyword_rider_vetoes_pacify_makers():
    """Vow of Malice's "+2/+2, has intimidate, and can't attack you or
    planeswalkers you control" — the "Vow" cycle grants a keyword
    alongside a DIRECTED restriction (protect yourself specifically), a
    political/protection tool, not a neutralizer."""
    keys = _skeys(test_signals("Vow of Malice"))
    assert "pacify_makers" not in keys


def test_removal_and_pacify_makers_stay_disjoint():
    """Pacifism must never open the `removal` structural view (CR 611.2 —
    the enchanted creature stays on the battlefield), and Murder (a real
    destroy effect) must never open pacify_makers — the two lanes stay
    partitioned per budgets.py's `_INTERACTION_PRESETS` comment."""
    assert "removal" not in _skeys(test_signals("Pacifism"))
    assert "pacify_makers" not in _skeys(test_signals("Murder"))


def test_equipment_pacify_admitted_structurally():
    """task #93: `EquippedBy` joined the pacify-attach predicate set (CR
    613's layer system treats an Equipment's can't-attack/can't-block
    grant identically to an Aura's — no rules distinction). Pin the
    admission directly against the underlying predicate/veto helpers
    (rather than a real card) since the sole commander-legal
    `EquippedBy`-affected CantBlock/CantAttack static in the corpus,
    Copper Carapace, is ALSO the sole compensating-benefit case (see the
    negative pin below) — there is no genuine Equipment-only pacify
    printing yet to pin a positive real-card case against."""
    from mtg_utils._deck_forge.crosswalk_signals import _PACIFY_ATTACH_PREDS

    assert "EnchantedBy" in _PACIFY_ATTACH_PREDS
    assert "EquippedBy" in _PACIFY_ATTACH_PREDS


def test_copper_carapace_equipment_pacify_vetoed_by_compensating_pt():
    """Copper Carapace ("Equipped creature gets +2/+2 and can't block.") is
    the ONLY commander-legal Equipment with a can't-attack/can't-block
    static tied to an `EquippedBy` affected filter (task #93 corpus
    census, 32,521 cards) — and it is the Rage/Vow-cycle compensating-
    benefit shape (a positive P/T buff riding the SAME restriction), so it
    stays OUT of pacify_makers even with `EquippedBy` now admitted —
    widening the predicate set changed nothing in the live corpus."""
    keys = _skeys(test_signals("Copper Carapace"))
    assert "pacify_makers" not in keys


# ── opp_top_exile (ADR-0027 q2-D2 — name-lock / impulse-cast steal) ────────────


def test_opp_top_exile_from_impulse_cast_co_occurrence():
    # Sub-shape A: an exile Effect scope='opp' co-occurring (same ability) with a
    # cast_from_zone Effect scope='opp' — the "you may cast them" follow-through
    # (Villainous Wealth). Scope is the engine controller 'you'.
    assert ("opp_top_exile", "you", "") in _striples(test_signals("Villainous Wealth"))


def test_opp_top_exile_from_library_tag():
    # Sub-shape B: an exile Effect scope='opp' carrying an 'in:library' zone tag
    # (Brainstealer Dragon) — phase tagged the library origin directly, so no
    # cast_from_zone co-occurrence is required.
    assert ("opp_top_exile", "you", "") in _striples(
        test_signals("Brainstealer Dragon")
    )


def test_opp_top_exile_does_not_fire_on_bare_opponent_exile_removal():
    # Precision: opponent-targeted exile-as-REMOVAL (Path to Exile) is exile scope='opp'
    # with NO cast_from_zone and NO 'in:library' — it must never open the steal lane
    # (CR 406 — exile is public, but only the play-it follow-through is this lane).
    assert "opp_top_exile" not in _skeys(test_signals("Path to Exile"))


# ── direct_damage from a player-reaching damage doubler (ADR-0027 C7) ──────────


def test_player_reaching_doubler_emits_direct_damage():
    # A damage_doubling Effect with subject=None (absent / {Player} target_filter —
    # Furnace of Rath) reaches a player (CR 115.4): it feeds direct_damage AND
    # damage_doubling.
    keys = _skeys(test_signals("Furnace of Rath"))
    assert "damage_doubling" in keys
    assert "direct_damage" in keys


def test_creature_only_doubler_is_not_direct_damage():
    # A CreatureOnly doubler carries a Creature subject from the projection (Blind
    # Fury): players excluded (CR 120.1), so it stays out of direct_damage but still
    # opens damage_doubling.
    keys = _skeys(test_signals("Blind Fury"))
    assert "damage_doubling" in keys
    assert "direct_damage" not in keys


# ── facedown_matters (ADR-0027 C9 — CR 708 Face-Down Spells and Permanents) ───
# Real-card IR shapes verified against the v49 sidecar (see commit body).


def test_facedown_from_turn_face_up_trigger_event():
    # Bonethorn Valesk: "Whenever a permanent is turned face up, this creature
    # deals 1 damage to any target." phase emits a turn_face_up TRIGGER event
    # (Permanent/any subject) — the generic phrasing the byte mirror's narrow
    # "turn it/that face up" pattern misses. Arm B.
    assert "facedown_matters" in _skeys(test_signals("Bonethorn Valesk"))


def test_facedown_from_subtype_marker_subject():
    # Ixidor, Reality Sculptor: "Face-down creatures get +1/+1." phase narrows the
    # static pump subject to subtype "Face-down". Arm C (exact subtype token).
    assert "facedown_matters" in _skeys(test_signals("Ixidor, Reality Sculptor"))


def test_facedown_from_predicate_marker_subject():
    # Sumala Sentry: "Whenever a face-down permanent you control is turned face up,
    # put a +1/+1 counter on it and on this creature." phase marks the trigger
    # subject with the FaceDown predicate. Arm C (exact predicate token) + arm B.
    assert "facedown_matters" in _skeys(test_signals("Sumala Sentry"))


def test_facedown_from_cloak_keyword():
    # Unexplained Absence: keyword Cloak (CR 701.58) — a face-down 2/2 maker that
    # phase does NOT carry in IR kw (cloak rides an effect category). The Scryfall
    # keyword array is the uniform anchor. Arm A. _matters sweep (ADR-0034): the
    # keyword MAKER arm emits facedown_makers.
    assert "facedown_makers" in _skeys(test_signals("Unexplained Absence"))


def test_facedown_from_morph_keyword():
    # Lumbering Laundry — a Disguise body (CR 702.166 / 702.37 morph family) with no
    # structural face-down anchor — keyword-array re-key. Arm A. Confirms
    # morph/megamorph/disguise re-key → facedown_makers (ADR-0034 maker arm).
    assert "facedown_makers" in _skeys(test_signals("Lumbering Laundry"))


# ── ADR-0027 C8 (SIDECAR v50) — topdeck_selection / dig_until owner-resolved arms ──
# The OWNER now rides an additive top:you / top:opp zone tag
# (project._recover_top_of_library_owner); the signal arms gate on the OWNER, not the
# (often-'any') scope. CR 401.1 / 701.18 / 701.23.


def test_topdeck_selection_from_top_you_reveal():
    # Fact or Fiction — a reveal scope='any' (an opponent separates) whose library is
    # YOURS via the top:you tag. The owner-resolved arm fires topdeck_selection.
    assert "topdeck_selection" in _skeys(test_signals("Fact or Fiction"))


def test_topdeck_selection_excludes_opponent_library():
    # Gonti, Lord of Luxury — a top:opp peek at an opponent's library is theft (CR
    # 401.1), NOT the controller's own top-of-deck curation. The owner gate keeps it OUT.
    assert "topdeck_selection" not in _skeys(test_signals("Gonti, Lord of Luxury"))


def test_dig_until_from_cheat_play_top_you_until():
    # Mass Polymorph — a reveal-UNTIL re-categorized to cheat_play, owner top:you, with
    # an "until you reveal" body → the owner-resolved dig_until arm fires.
    assert "dig_until" in _skeys(test_signals("Mass Polymorph"))


def test_dig_until_not_fired_by_until_end_of_turn_duration():
    # A reveal-the-top-card with an "until end of turn" DURATION rider (Stormchaser
    # Chimera) is NOT a dig-until-a-condition — the `until you` discriminator keeps it
    # out of dig_until (it is topdeck_selection only).
    keys = _skeys(test_signals("Stormchaser Chimera"))
    assert "dig_until" not in keys
    assert "topdeck_selection" in keys


# ── task #93 item 6 (niche-7 re-triage): Cosima // The Omenkeel ─────────────


def test_cosima_voyage_counter_already_served_by_landfall_and_draw_for_each():
    """Cosima, God of the Voyage's front-face delayed replacement ("you may
    exile Cosima... it gains 'Whenever a land you control enters... put a
    voyage counter on it. If you don't, return Cosima to the battlefield
    with X +1/+1 counters on it and draw X cards...'") is ALREADY well
    served, no new lane needed: the granted trigger genuinely cares about
    lands entering (``landfall``) and the return scales a draw by a
    counted resource (``draw_for_each``) — both fire structurally today.
    Documented here as the task #93 finding (not a gap)."""
    keys = _skeys(test_signals("Cosima, God of the Voyage // The Omenkeel"))
    assert "landfall" in keys
    assert "draw_for_each" in keys
