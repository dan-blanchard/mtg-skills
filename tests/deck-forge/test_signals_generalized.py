"""Tests for the generalized signal extractor (covers all commanders, not just
hand-coded cases).

Repointed after the legacy-engine deletion (post-migration consolidation):
``extract_signals`` (regex) and ``extract_signals_ir`` (projected IR) are gone —
the ONLY extractor is ``signals.extract_signals``, exercised here through
``mtg_utils.testkit`` real-card fixtures (``test_signals`` / ``test_card`` /
``test_card_ir``). Dual-engine agreement probes and deleted-engine internals were
removed; single-behavior pins were translated onto the production path (or, for
text helpers the membership floor still consumes, onto the helper directly).
Synthetic scenarios already proven by
``tests/deck-forge/test_signal_keys_real_cards.py`` or
``tests/mtg-utils/test_crosswalk.py`` were dropped as duplicates.
"""


from mtg_utils._deck_forge.signals import (
    Signal,
    _tinybones_scope,
    _voltron_double_strike_beater,
    _voltron_land_scaler,
    _voltron_self_heroic,
    _voltron_self_recurs,
    coverage_gate,
    extract_signals,
)
from mtg_utils._deck_forge.text_reads import (
    _resolve_scope,
    _scope,
    _self_dies_value,
    _self_etb_value,
)
from mtg_utils.card_ir import Card, Face
from mtg_utils.testkit import test_card, test_card_ir, test_signals


def _ksub_real(name):
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _ks_real(name):
    return {(s.key, s.scope) for s in test_signals(name)}


def _keys_real(name):
    return {s.key for s in test_signals(name)}


def test_type_matters_from_count_clause_and_token_maker_together():
    # ADR-0027: token_maker migrated to the Card IR (a SUBJECT-CARRYING UNION — a
    # structural make_token arm + a byte-identical kept mirror of the deleted
    # _detect_token_maker), so assert against the HYBRID path. type_matters (the
    # "for each Goblin you control" count operand) is NOT migrated and rides regex.
    s = _ksub_real("Krenko, Mob Boss")
    assert ("type_matters", "you", "Goblin") in s
    assert ("token_maker", "you", "Goblin") in s


def test_type_matters_count_clause_tolerates_state_adjective():
    # "the number of tapped Assassins you control" (Lydia Frye) — a state adjective
    # ("tapped") sits between "number of" and the tribe, so the bare
    # "number of <tribe> you control" anchor captured "tapped" (vocab-dropped) and lost
    # the Assassin tribe. Lydia thus never opened Assassin kindred and missed her whole
    # tribal package (Assassin Initiate / Rooftop Bypass). Real oracle.
    # ADR-0027: type_matters migrated → hybrid path.
    assert ("type_matters", "you", "Assassin") in _ksub_real("Lydia Frye")
    # The vocab gate still drops the generic card-type word in the same adjective form:
    # Foul-Tongue Shriek's "for each attacking creature you control" captures "creature"
    # (dropped). A noncreature, so no own-subtype membership tribal confounds the guard.
    assert "type_matters" not in _keys_real("Foul-Tongue Shriek")


def test_keyword_tribe_opens_on_flier_tutor():
    # Isperia tutors "a creature card with flying" — a fliers-matter (keyword-tribe)
    # payoff (CR 109.3 groups by the keyword characteristic). The keyword-tribe patterns
    # matched "creatures you control with flying" / "creature spell with flying" but not
    # the tutor's "creature CARD with flying", so a flying-tribal commander whose only
    # hook is the fetch stayed blind. Real oracle. ADR-0027: keyword_tribe migrated to
    # the Card IR (a subject-carrying kept mirror), so assert against the HYBRID path
    # with a bare IR (the mirror reads the record's oracle_text, not the IR structure).
    assert ("keyword_tribe", "you", "Flying") in _ksub_real("Isperia the Inscrutable")
    # The fetch verb is REQUIRED: a card that merely GAINS flying while "a creature card
    # with flying is in a graveyard" (Cairn Wanderer) is not a fliers-matter payoff — it
    # buffs itself off any graveyard, yours or not — so it must NOT open the tribe. Real
    # oracle.
    assert ("keyword_tribe", "you", "Flying") not in _ksub_real("Cairn Wanderer")


def test_direct_damage_opens_on_damage_to_a_creatures_controller():
    # Shocker deals "2 damage to target creature and 2 damage to that creature's
    # controller" — the second clause burns a PLAYER (CR 102 — a controller is a
    # player). ADR-0027: direct_damage migrated to the Card IR; phase collapses the
    # "to that creature's controller" rider to a Creature subject, so the lane fires
    # from the byte-identical _DIRECT_DAMAGE_MIRROR (hybrid path), not the deleted regex.
    assert "direct_damage" in _keys_real("Shocker, Unshakable")
    # A pure creature-only removal ping (no player/controller damage) stays out — on
    # BOTH the regex path (producer deleted) and the hybrid path (the scope='any' damage
    # Effect is creature-restricted → removal, and the mirror doesn't match
    # "to target creature").
    assert "direct_damage" not in _keys_real("Flame Slash")


def test_direct_damage_opens_on_target_first_variable_damage():
    # "deals damage to target player equal to N" (target-first) — the variable-damage
    # branch was amount-first ("deals damage equal to N to <target>"), missing this word
    # order. 84 burn cards (Anathemancer, Fanatic of Mogis, Corrupt). phase_crosscheck-
    # surfaced. Real oracle.
    # ADR-0027: direct_damage migrated to the Card IR. Anathemancer's "to target
    # player" parses a subject-less scope='any' damage Effect (player-reach) and Fanatic
    # of Mogis's "to each opponent" parses scope='opp' — both fire the structural arm;
    # the bare-IR hybrid path also re-supplies them via the byte-identical mirror.
    assert "direct_damage" in _keys_real("Anathemancer")  # to target player equal to N
    assert "direct_damage" in _keys_real("Fanatic of Mogis")  # to each opponent equal N
    # creature-only variable damage (to target CREATURE) must stay out — not player burn.
    assert "direct_damage" not in _keys_real("Rockslide Ambush")


def test_free_creature_payoff_opens_on_no_mana_spent_to_cast():
    # Satoru draws when creatures enter with "no mana was spent to cast them" — the
    # 0-cost creatures (Ornithopter / Memnite / Phyrexian Walker). ADR-0027 tranche2-C:
    # migrated to the Card IR — an ETB trigger whose condition tree carries a
    # manaspentcondition (phase nests it under an 'or' alongside 'not'>'wascast').
    assert "free_creature_payoff" in _keys_real("Satoru, the Infiltrator")
    # The 4 cast_spell-triggered manaspentcondition cards (Lavinia / Boromir / Roiling
    # Vortex / Vexing Bauble) TAX or COUNTER opponents' free spells — the etb-trigger
    # gate excludes them. Same manaspentcondition, wrong trigger event → no fire.
    assert "free_creature_payoff" not in _keys_real("Boromir, Warden of the Tower")
    # "wasn't cast" alone (Preston's blink/token payoff) is NOT the 0-cost "no mana
    # spent" hook — an ETB trigger gated on a bare wascast (no manaspentcondition) wants
    # reanimate/blink, not free creatures.
    assert "free_creature_payoff" not in _keys_real("Preston, the Vanisher")


def test_mass_death_payoff_opens_on_aggregate_death_count():
    # Tobias rewards creatures dying EN MASSE: "for each nontoken creature you
    # controlled that died this turn, create a 2/2 Zombie." A payoff that SCALES with
    # the number of deaths this turn wants board wipes + mass-reanimation. Real oracle.
    assert ("mass_death_payoff", "you") in _ks_real("Tobias, Doomed Conqueror")
    # Precision guard: a SINGLE-death conditional with a FIXED reward ("if a creature
    # died this turn, create a Food token") does NOT scale with mass death — Old
    # Flitterfang makes one Food whether 1 or 10 died, so it must NOT open this lane
    # (it's plain death_matters, not a wipe payoff). Real oracle.
    assert "mass_death_payoff" not in _keys_real("Old Flitterfang")


def test_per_target_payoff_opens_on_cost_less_per_target():
    # Hinata's "Spells you cast cost {1} less to cast for each target" makes MULTI-target
    # spells (Aurelia's Fury, Distorting Wake) wildly cheap — the more targets, the bigger
    # the discount. A unique mechanic; it opens a payoff lane that wants variable-target
    # spells. Real oracle.
    # ADR-0027 t2b5-B: migrated to the Card IR (kept_detector) — assert on the
    # production hybrid path (the regex path no longer emits it).
    assert ("per_target_payoff", "you") in _ks_real("Hinata, Dawn-Crowned")
    # Flat cost reduction (Goblin Electromancer: "cost {1} less to cast", no per-target
    # scaling) is NOT this — it doesn't reward casting one spell at many targets. Real
    # oracle.
    assert "per_target_payoff" not in _keys_real("Goblin Electromancer")


def test_ability_strip_payoff_opens_on_strip_and_buff():
    # ADR-0027: migrated to the Card IR. Abigale strips a creature's abilities and KEEPS
    # it as a beater (adds keyword counters), so she wants big cheap creatures whose
    # DRAWBACK she neutralizes — strip Rotting Regisaur's upkeep-discard, keep the 7/6.
    # CR 613.1f (ability-removing + keyword counters share layer 6); CR 122.1b (the
    # counters grant flying/first strike/lifelink). The IR arm fires when one ability has
    # a 'loses all abilities' effect-raw AND a place_counter effect, no base_pt_set
    # shrinker — so the regex path no longer emits it but the hybrid (IR) path does. Real
    # oracle; IR mirrors Abigale's ETB (the strip is phase's lose_life mis-type + three
    # keyword-counter place_counter effects).
    _abigale_strip_raw = (
        "When ~ enters, up to one other target creature loses all abilities. Put a "
        "flying counter, a first strike counter, and a lifelink counter on that creature."
    )
    assert ("ability_strip_payoff", "you") in _ks_real("Abigale, Eloquent First-Year")
    # Lizard ALSO says "loses all abilities" but SETS base power/toughness to 4/4 (CR
    # 613 layer 7b) — it shrinks the target rather than keeping a big body, so it is NOT
    # a drawback-beater payoff and must not open this lane. The IR arm's base_pt_set veto
    # drops it: phase types the strip-and-become as base_pt_set, so the ability carries a
    # base_pt_set effect (and no place_counter buff). Real oracle.
    _lizard_raw = (
        "up to one other target creature loses all abilities and becomes a green "
        "Lizard creature with base power and toughness 4/4."
    )
    assert "ability_strip_payoff" not in _keys_real("Lizard, Connors's Curse")


def test_arcane_matters_opens_on_arcane_payoff():
    # The Unspeakable returns Arcane cards; the Kamigawa Kirins reward casting Arcane
    # spells. Either way the commander wants Arcane-subtype spells (CR 205.3k). Real
    # oracle. ADR-0027: arcane_matters migrated to the Card IR via a byte-identical
    # `\barcane\b` kept word mirror (phase doesn't structure Arcane — a SPELL TYPE on
    # Instants/Sorceries), so it comes through the hybrid path, not pure regex.
    assert ("arcane_matters", "you") in _ks_real("The Unspeakable")
    # A commander with no Arcane care does not open it.
    assert "arcane_matters" not in _keys_real("Krenko, Mob Boss")


def test_enlist_matters_opens_on_enlist():
    # Aradesh has enlist and rewards enlisting, so he wants other enlist creatures plus
    # high-power tap fodder. ADR-0027: has_enlist is IR-served from the Scryfall
    # `enlist` keyword array, so it comes through the hybrid path, not pure regex.
    assert ("has_enlist", "you") in _ks_real("Aradesh, the Founder")


def test_power_tap_engine_opens_on_tap_ability_scaling_with_power():
    # Mona Lisa's "{T}: Add X mana, where X is Mona Lisa's power" wants UNTAP effects
    # (re-tap for more mana) and power pumps. A {T} ability that scales with a creature's
    # power is the tell; Krenko's {T} scales with Goblin count, not power. Real oracle.
    # ADR-0027: power_tap_engine migrated to the Card IR (an ACTIVATED ability cost~'tap'
    # + a power-scaling effect raw), so it is served via the hybrid path, not pure regex.
    assert ("power_tap_engine", "you") in {
        (s.key, s.scope) for s in test_signals("Mona Lisa, Science Geek")
    }
    assert "power_tap_engine" not in {s.key for s in test_signals("Krenko, Mob Boss")}


def test_recast_etb_opens_on_sneak():
    # Oroku Saki's Sneak (return an unblocked attacker, recast cheaply) replays a
    # creature's ETB, so he wants cheap aggressive-ETB creatures (recast = repeat the
    # bleed). ADR-0027: recast_etb migrated to the Card IR — the regex path no longer
    # emits it; the hybrid serves it from the Scryfall `Sneak` keyword. Real oracle.
    assert ("recast_etb", "you") in _ks_real("Oroku Saki, Shredder Rising")
    assert "recast_etb" not in _keys_real("Krenko, Mob Boss")


def test_type_change_opens_on_creature_type_hoser():
    # Gor Muldrak has "protection from Salamanders" and seeds opponents with Salamander
    # tokens — so he wants creature-type CHANGERS to turn the rest of their board into
    # Salamanders, which his protection then blanks (creature type is continuously
    # checked, CR 205.3 / 702.16). Real oracle.
    # ADR-0027 t2b4-C: type_change migrated to the Card IR — the regex path no longer
    # emits it; it fires from the _type_hoser_clause subtype-gated mirror (bare IR).
    assert ("type_change", "you") in _ks_real("Gor Muldrak, Amphinologist")
    # The captured word is validated against the subtype vocab, so a plain
    # "protection from black" (a color, not a creature type) is not a type hoser.
    assert "type_change" not in _keys_real("Krenko, Mob Boss")


def test_exert_matters_opens_on_pseudo_vigilance():
    # Johan grants "attacking doesn't cause creatures you control to tap", which makes an
    # exert creature's "won't untap next turn" cost free — so he wants exert creatures.
    # ADR-0027: exert_matters migrated to the Card IR — the regex path no longer emits
    # it; the Johan namesake is served by a kept word mirror (oracle scan → bare IR).
    # Real oracle.
    assert ("exert_matters", "you") in _ks_real("Johan")
    assert "exert_matters" not in _keys_real("Krenko, Mob Boss")


def test_tap_down_blockers_opens_on_unblockable_unless_all():
    # Tromokratis connects only if the defender can't field enough blockers, so it wants
    # to tap their creatures down. Real oracle.
    # ADR-0027 t2b4-C: tap_down_blockers migrated to the Card IR — the regex path no
    # longer emits it; it fires from a kept word mirror (bare IR routes to the IR path).
    assert ("tap_down_blockers", "you") in _ks_real("Tromokratis")


def _ir_effect_cats(name):
    return {e.category for ab in test_card_ir(name).all_abilities() for e in ab.effects}


def _ir_has_reveal_hand_opp(name):
    return any(
        e.category == "reveal_hand" and e.scope == "opp"
        for ab in test_card_ir(name).all_abilities()
        for e in ab.effects
    )


def test_hand_disruption_reads_recovered_opp_reveal_structure():
    # ADR-0027 #24i (SIDECAR v58): hand_disruption's broad regex mirror is DELETED; the
    # opponent-hand reveal/look structure phase folds is RECOVERED onto the IR by
    # supplement `_recover_hand_disruption`, so the scope-gated reveal_hand arm reads
    # STRUCTURE. Three recovery shapes, all real oracle:
    #   • a MODAL reveal-opponent-hand whose reveal_hand kept scope='any' off the mode
    #     (subject controller='opp') — scope recovered to 'opp' (bucket A).
    assert _ir_has_reveal_hand_opp("Mardu Charm")
    assert ("hand_disruption", "opponents") in _ks_real("Mardu Charm")
    #   • a look-at-an-opponent's-hand peek phase mis-typed as topdeck_select
    #     (Anointed Peacekeeper) — re-categorized to reveal_hand (bucket A).
    assert _ir_has_reveal_hand_opp("Anointed Peacekeeper")
    assert ("hand_disruption", "opponents") in _ks_real("Anointed Peacekeeper")
    #   • a "plays with their hand revealed" clause phase folds into a restriction
    #     (Sen Triplets) — synth reveal_hand scope='opp' from the raw oracle (bucket B).
    assert _ir_has_reveal_hand_opp("Sen Triplets")
    assert ("hand_disruption", "opponents") in _ks_real("Sen Triplets")


def test_keyword_grant_target_reads_recovered_single_target_grant():
    # ADR-0027 #24i (SIDECAR v58): keyword_grant_target's broad regex mirror is DELETED;
    # the single-target keyword grants phase folds to a bare grant_keyword (modal /
    # quoted-on-Aura / Saga-chapter) are RECOVERED as a single_target_grant Effect by
    # supplement `_recover_keyword_grant_target`, which the existing arm reads. Real
    # oracle.
    #   • a grant QUOTED on an Aura-on-a-land ("Enchanted land has '{T}: Target
    #     creature gains flying'").
    assert "single_target_grant" in _ir_effect_cats("Skygames")
    assert ("keyword_grant_target", "you") in _ks_real("Skygames")
    #   • a MODAL grant ("• Target creature you control gains menace and haste").
    assert "single_target_grant" in _ir_effect_cats("Ferocification")
    assert ("keyword_grant_target", "you") in _ks_real("Ferocification")


def test_keyword_grant_target_split_back_half_is_upstream_residue():
    # The split/aftermath BACK-HALF grant (Claim//Fame's "Fame") is a GENUINE UPSTREAM
    # phase gap: phase emits NO record for a split back face, so the supplement's
    # phase-records recovery never sees it (no single_target_grant in the IR). A narrow
    # layout-gated residue in signals keeps it firing. Real oracle.
    assert "single_target_grant" not in _ir_effect_cats("Claim // Fame")
    assert ("keyword_grant_target", "you") in _ks_real("Claim // Fame")


def test_island_matters_opens_on_island_attack_restriction():
    # Zhou Yu can only attack if the defender controls an Island, so he wants to turn
    # opponents' lands into Islands. Real oracle. ADR-0027: island_matters migrated to
    # the Card IR (a byte-identical kept word mirror of the Zhou Yu attack-restriction
    # phrase), so it is served from the hybrid (IR) path, not the legacy regex path.
    assert ("island_matters", "you") in _ks_real("Zhou Yu, Chief Commander")


def test_entered_attacker_opens_on_entered_this_turn_combat():
    # Samut rewards a creature that ENTERED this turn dealing combat damage, so she wants
    # haste + ETB-pump to let fresh creatures swing at once. Real oracle.
    # ADR-0027 β: entered_attacker migrated to the Card IR (a byte-identical kept-mirror
    # over the reminder-stripped oracle), so it serves from the hybrid path.
    assert ("entered_attacker", "you") in _ks_real("Samut, Vizier of Naktamun")


def test_land_protection_opens_on_land_animation():
    # Noyan Dar turns lands into creatures, which die to removal and wraths, so he wants
    # land protection. Real oracle.
    # ADR-0027: land_protection migrated to the Card IR — the land-animator predicate
    # (a base_pt_set with subject=None whose ability-level raw says "land … becomes a
    # creature"). Assert via the hybrid path.
    assert ("land_protection", "you") in _ks_real("Noyan Dar, Roil Shaper")


def test_lose_unless_hand_opens_on_cast_from_hand_drawback():
    # Phage loses you the game if not cast from hand, so she wants to negate that. Real
    # oracle. ADR-0027: lose_unless_hand migrated to the Card IR (an ETB trigger scoped
    # YOU + a lose_game effect), so it is served via the hybrid path, not pure regex.
    assert ("lose_unless_hand", "you") in {
        (s.key, s.scope) for s in test_signals("Phage the Untouchable")
    }


def test_land_denial_opens_on_phasing_lands():
    # Taniwha's lands phase back each turn, so symmetric land-denial stax hits opponents
    # permanently while it recovers. Real oracle.
    # ADR-0027: land_denial migrated to the Card IR — a `phasing` Effect on a Land
    # subject with controller=='you'. Assert via the hybrid path.
    assert ("land_denial", "you") in _ks_real("Taniwha")


def test_multicolor_matters_opens_on_color_pair_payoff():
    # Niv-Mizzet Reborn draws cards by exact color pair, so it's a gold-cards deck that
    # wants the multicolored payoffs. Real oracle. ADR-0027: multicolor_matters migrated
    # to the Card IR (the "for each color pair" / "exactly those colors" kept word
    # mirror), so it comes through the hybrid path, not pure regex.
    assert ("multicolor_matters", "you") in _ks_real("Niv-Mizzet Reborn")


def test_target_own_payoff_opens_on_targeted_your_creature():
    # Monk Gyatso airbends a creature you control whenever it becomes the target, so he
    # wants free ways to target your own creatures. Real oracle.
    # ADR-0027 SIDECAR v40: target_own_payoff reads STRUCTURE — a becomes_target trigger
    # with scope in (you,any) and NO src:opp tag (you can self-target it on demand).
    assert ("target_own_payoff", "you") in _ks_real("Monk Gyatso")


def test_life_payment_insurance_opens_on_repeatable_pay_life():
    # ADR-0027: life_payment_insurance migrated to the Card IR — Selenia's "Pay 2 life:"
    # is a repeatable activation COST ("paylife" in Ability.cost), read through the
    # hybrid IR path, not the regex.
    assert ("life_payment_insurance", "you") in {
        (s.key, s.scope) for s in test_signals("Selenia, Dark Angel")
    }


def test_land_exchange_opens_on_land_control():
    # ADR-0027: land_exchange reads the structural gain_control shape — phase parses
    # "exchange control of target X and target Y" as a gain_control effect with
    # subject=None. Political Trickery is the genuine swap. Sharkey (which copies /
    # taxes land abilities, never EXCHANGES control) was the legacy regex's lone
    # false positive — it emits no gain_control effect, so production drops it.
    assert ("land_exchange", "you") in _ks_real("Political Trickery")
    assert ("land_exchange", "you") not in _ks_real("Sharkey, Tyrant of the Shire")


def test_scavenge_fuel_opens_on_scavenge():
    # Varolz gives graveyard creatures scavenge (counters = the card's power), so he
    # wants high-power creatures as the biggest payloads. Real oracle.
    # ADR-0027: scavenge_fuel migrated to the Card IR — Varolz is a keyword-less
    # graveyard-wide GRANTER, recovered by a `scavenge` dropped-static face marker
    # (read via _DOER_EFFECT_KEYS), so the lane opens through the hybrid IR path.
    hybrid = {(s.key, s.scope) for s in test_signals("Varolz, the Scar-Striped")}
    assert ("scavenge_fuel", "you") in hybrid


def test_free_spell_storm_opens_on_cost_less_per_spell():
    # Thrasta's cost drops {3} per other spell cast this turn, so it wants free spells to
    # chain. Real oracle.
    # ADR-0027 β: free_spell_storm migrated to the Card IR — phase's SelfRef
    # ModifyCost{Reduce} static is dropped by project (a self-discount is excluded from
    # the build-around cost_reduction lane), so project._free_spell_storm_marker
    # re-surfaces it as a dedicated `free_spell_storm` STATIC Effect the hybrid reads.
    hybrid = {(s.key, s.scope) for s in test_signals("Thrasta, Tempest's Roar")}
    assert ("free_spell_storm", "you") in hybrid


def test_target_redirect_opens_on_draw_when_targeted():
    # Rayne draws when an opponent targets your stuff, so it wants target-redirect to
    # shunt the spell onto a cheap permanent. Real oracle.
    # ADR-0027 SIDECAR v40: target_redirect reads STRUCTURE — a becomes_target trigger
    # whose targeting source is an opponent (the src:opp zone tag).
    assert ("target_redirect", "you") in _ks_real("Rayne, Academy Chancellor")


def test_artifacts_matter_opens_on_investigate():
    # "Investigate" creates a Clue token — an artifact (keyword action) — so an
    # investigate commander (Sophina) is an artifact deck whose Clues trigger artifact
    # payoffs (Reckless Fireweaver / Ingenious Artillerist). "create a Clue token"
    # already opened the lane; the keyword action "investigate" must too. Real oracle.
    # ADR-0027: BOTH artifacts_matter and clue_matters migrated to the Card IR — each
    # rides a kept oracle mirror that catches \binvestigate\b. The hybrid path emits both.
    keys = _keys_real("Sophina, Spearsage Deserter")
    assert "artifacts_matter" in keys  # Clue tokens are artifacts
    assert "clue_matters" in keys  # still a Clue commander too


def test_token_copy_matters_opens_on_token_doubling():
    # A token DOUBLER ("twice that many tokens are created" — Adrix and Nev, Mondrak)
    # wants token-COPY effects: Rite of Replication / Esix make token copies, which the
    # doubler then doubles. So it IS a token-copy commander. The detector only knew
    # "token that's a copy" / populate, so token-doublers never opened the lane and lost
    # their copy spells. Real oracle.
    # ADR-0027 C5: token_copy_makers is now FULLY STRUCTURAL — a token DOUBLER projects
    # to a `token_doubling` Effect (phase's replacement category), which the structural
    # arm reads. A plain token MAKER (Krenko) projects to a bare make_token with no Copy
    # predicate and no token_doubling, so it does NOT open the lane.
    assert "token_copy_makers" in _keys_real("Adrix and Nev, Twincasters")
    assert "token_copy_makers" in _keys_real("Mondrak, Glory Dominus")
    assert "token_copy_makers" not in _keys_real("Krenko, Mob Boss")


def test_wants_cloning_opens_for_recurring_value_legendary():
    # "Clone your engine" is legitimate for a recurring-value LEGENDARY: copying it
    # forks the per-turn engine and the copy dodges the legend rule. Obeka ("{T}: end
    # the turn") and Obeka, Splitter of Seconds (combat damage -> additional upkeep
    # steps — extra-turn/phase generators are premium clone targets) qualify; a
    # vanilla legendary (Isamaru) does not. Commander-level (membership), so it must
    # NOT fire for the 99. Real snapshot cards.
    assert "wants_cloning" in _keys_real("Obeka, Brute Chronologist")  # {T} engine
    assert "wants_cloning" in _keys_real("Obeka, Splitter of Seconds")  # extra upkeeps
    assert "wants_cloning" not in _keys_real("Isamaru, Hound of Konda")  # vanilla
    # NOTE: the legacy engines suppressed wants_cloning under
    # include_membership=False (a commander-only membership cross-open); the
    # crosswalk serves it as a regular lane regardless of the flag, so that old
    # gating pin has no production analogue and is not asserted here.


def test_clone_engine_fires_for_legendary_with_intervening_card_type():
    # The engine-clone suggestion gated on the contiguous substring "legendary creature",
    # so a "Legendary ENCHANTMENT Creature" (Go-Shintai) or "Legendary ARTIFACT Creature"
    # was wrongly excluded — yet a Shrine whose mill SCALES per-Shrine is a textbook
    # clone-your-engine target: fork the end-step engine, dodge the legend rule. Real
    # oracle.
    # ADR-0027 v30: wants_cloning migrated — assert via the hybrid path (a bare IR routes
    # to the IR-side membership block where the cross-open is reproduced byte-identically).
    assert ("wants_cloning", "you", "") in _ksub_real("Go-Shintai of Lost Wisdom")
    # Precision: broadening the type gate must not bypass the ENGINE gate. A legendary
    # enchantment creature with only static abilities and a non-tap activated ability
    # (Heliod, Sun-Crowned — no per-turn trigger, no {T} ability) is not a clone-your-
    # engine target. Real oracle.
    assert ("wants_cloning", "you", "") not in _ksub_real("Heliod, Sun-Crowned")


def test_token_maker_prefers_creature_subtype_over_artifact_word():
    # ADR-0027: token_maker migrated to the Card IR — assert against the HYBRID path.
    # The byte-identical kept mirror (the deleted _detect_token_maker re-run per-clause
    # over the reminder-stripped oracle) still prefers the real subtype "Construct" over
    # the card-type word "artifact" in "Construct artifact creature token".
    assert ("token_maker", "you", "Construct") in _ksub_real(
        "Urza, Lord High Artificer"
    )


def test_typed_spellcast_captures_tribe():
    # ADR-0027: typed_spellcast migrated (a SUBJECT-CARRYING kept mirror of the
    # deleted producer for the STATIC "<Subtype> spells you cast" form) — asserted
    # against the production path.
    assert ("typed_spellcast", "you", "Sliver") in _ksub_real("The First Sliver")


def test_typed_spellcast_rejects_instant_and_sorcery():
    # "Instant and sorcery spells you cast" is spellslinger, NOT a tribe. ADR-0027:
    # assert against the HYBRID path (the migrated key no longer routes through regex).
    assert "typed_spellcast" not in _keys_real("Mizzix of the Izmagnus")


def test_plant_token_maker_keeps_subject_but_not_land_creatures():
    # Avenger makes Plant tokens — token_maker/Plant is CORRECT; it must not be
    # mistaken for the land-creatures theme. ADR-0027: both token_maker and
    # land_creatures_matter are IR-served, so assert via the hybrid path with a
    # Plant (not Land) token subject.
    s = _ksub_real("Avenger of Zendikar")
    assert ("token_maker", "you", "Plant") in s
    assert not any(k == "land_creatures_matter" for k, _, _ in s)


def test_yedora_forest_land_maker_opens_land_creatures():
    # Yedora returns dead creatures as face-down Forest LANDS ("It's a Forest
    # land."). Those lands are exactly what animate-your-lands payoffs (Life and
    # Limb, Living Plane) turn into a creature army, so she belongs in the
    # existing land-creatures lane, reached via her "It's a Forest land" tell.
    # ADR-0027: the "(it's|becomes) a forest land" maker tail rides the kept oracle
    # mirror (phase parses Yedora as a reanimate, dropping the Forest-land tell), so
    # assert via the hybrid path — any non-None IR routes to the mirror-bearing path.
    assert any(
        k == "land_creatures_matter" for k, _, _ in _ksub_real("Yedora, Grave Gardener")
    )


def test_repeatable_aoe_ping_opens_for_deathtouch_combo():
    # Tibor's recurring "deals 1 damage to each creature" is a REPEATABLE board
    # ping (whenever you cast a red spell) — with deathtouch on the source it's a
    # recurring board wipe (CR 702.2b). Pestilence is the same via an activated
    # ability. A one-shot ETB sweep (Chaos Maw) must NOT open it: deathtouch gear
    # can't be attached when the ETB resolves, so it's not the combo.
    # ADR-0027 tranche2-A: aoe_ping migrated to the Card IR — a counter_kind="all"
    # damage Effect over a Creature subject on a REPEATABLE-FRAME ability (a cast-trigger
    # for Tibor, an activated mana cost for Pestilence). A one-shot ETB sweep (Chaos Maw,
    # event="etb") is NOT repeatable and must stay out. Asserted via the hybrid.
    assert any(k == "aoe_ping" for k, _, _ in _ksub_real("Tibor and Lumia"))
    assert any(k == "aoe_ping" for k, _, _ in _ksub_real("Pestilence"))
    assert not any(k == "aoe_ping" for k, _, _ in _ksub_real("Chaos Maw"))
    # And the regex path no longer fires it (the _HAND_FLOOR producer is deleted).


def test_numot_repeatable_land_destruction_opens_lane():
    # Numot destroys lands every time she connects — a repeatable land-destruction
    # ENGINE (the commander herself), so she wants the LD support package (land
    # recursion to survive symmetric LD, land-loss punishers). Membership + creature
    # gated: a one-shot LD SPELL (Stone Rain) is not an LD commander, so it stays out.
    # ADR-0027: land_destruction migrated to the Card IR (the membership-gated
    # _LAND_DESTRUCTION_MIRROR arm, reproducing the deleted regex cross-open byte-
    # identically), so this asserts on the HYBRID path. A bare non-None IR routes the
    # hybrid to the IR path; the mirror reads type_line + oracle_text off the record.
    assert any(
        k == "land_destruction" for k, _, _ in _ksub_real("Numot, the Devastator")
    )
    assert not any(k == "land_destruction" for k, _, _ in _ksub_real("Stone Rain"))


def test_cheat_from_top_commander_opens_lane():
    # Vaevictis / Hans reveal the top card and cheat a permanent onto the battlefield,
    # so they want to STACK their top with a bomb (graveyard-to-top). Requires BOTH the
    # reveal-top tell AND the puts-onto-battlefield tell: a plain reanimation spell
    # (Reanimate) puts a creature onto the battlefield but never reveals the top, so it
    # is not a top-cheater and stays out.
    # ADR-0027: cheat_from_top migrated to the Card IR (the membership-gated byte-
    # identical _CHEAT_FROM_TOP_MIRROR arm — the v24 from:top zone is too coarse for a
    # structural arm), so this asserts on the HYBRID path. A bare non-None IR routes the
    # hybrid to the IR path; the mirror reads oracle_text off the record.
    assert any(
        k == "cheat_from_top" for k, _, _ in _ksub_real("Vaevictis Asmadi, the Dire")
    )
    assert any(k == "cheat_from_top" for k, _, _ in _ksub_real("Hans Eriksson"))
    assert not any(k == "cheat_from_top" for k, _, _ in _ksub_real("Reanimate"))


def test_repeatable_creature_kill_opens_kill_engine():
    # A commander that destroys creatures EVERY turn (Diaochan's {T}, Visara's {T})
    # is a reliable death-engine: each kill triggers death payoffs (Blood Artist,
    # Vicious Shadows). Requires a REPEATABLE frame (activated/triggered): a one-shot
    # removal spell (Murder) is not an engine and stays out. ADR-0027: kill_engine
    # migrated to the Card IR (signals-only — _is_kill_engine_ir reads ab.kind /
    # Trigger.event), so the lane fires from the hybrid IR path, not the regex.
    # A one-shot removal SPELL (Murder, an Instant) — not a creature, not a repeatable
    # frame: the kill_engine arm is creature-membership-gated and reads a `spell`-kind
    # destroy as non-repeatable, so it stays out.
    assert any(k == "kill_engine" for k, _, _ in _ksub_real("Diaochan, Artful Beauty"))
    assert any(k == "kill_engine" for k, _, _ in _ksub_real("Visara the Dreadful"))
    assert not any(k == "kill_engine" for k, _, _ in _ksub_real("Murder"))


def test_one_punch_efficient_beater_opens_lane():
    # An extreme power-for-cost beater (Lord 10/4, Yargle 18/6) wins by connecting once
    # for lethal, so it wants damage amplification (grant infect / double strike). Gated
    # power >= 8 AND power >= 2*cmc: an EXPENSIVE fatty (Emrakul 15/15 for 15) wins by
    # being huge rather than by amplification, and a small creature never qualifies.
    # ADR-0027: one_punch migrated to the Card IR (a pure numeric gate over card_pt_int
    # + cmc + type_line), so the lane is now served from the hybrid path — a bare
    # non-None IR routes the structural arm, which reads the same record fields.
    assert any(k == "one_punch" for k, _, _ in _ksub_real("Lord of Tresserhorn"))
    assert any(k == "one_punch" for k, _, _ in _ksub_real("Yargle and Multani"))
    # expensive fatty
    assert not any(
        k == "one_punch" for k, _, _ in _ksub_real("Emrakul, the Aeons Torn")
    )
    # low power
    assert not any(k == "one_punch" for k, _, _ in _ksub_real("Llanowar Elves"))


def test_nonhuman_attack_engine_opens_evasive_attackers():
    # Winota triggers when a non-Human creature attacks, so she wants evasive (flying)
    # attackers that reliably connect to fire her engine — fliers are a useful narrowing
    # (~a quarter of the pool), unlike "all non-Humans" (96%). A creature with no such
    # attack trigger never opens it.
    # ADR-0027: nonhuman_attackers is IR-served from the structural attacks-trigger
    # shape (NotSubtype:Human subject, you-controller), so it comes through the
    # hybrid path with the matching IR, not pure regex.
    assert any(
        k == "nonhuman_attackers" for k, _, _ in _ksub_real("Winota, Joiner of Forces")
    )
    assert not any(
        k == "nonhuman_attackers" for k, _, _ in _ksub_real("Llanowar Elves")
    )


def test_reclaim_owned_commander_opens_control_exchange():
    # Meneldor / The Neutrinos exile a creature YOU OWN and return it under your
    # control, so you can donate a dud via control-EXCHANGE (Puca's Mischief), keep
    # their bomb, then reclaim your own dud. A standard blink that exiles a creature
    # you CONTROL (Restoration Angel) can't reclaim a donated creature, so it stays
    # out. ADR-0027 (t2b2-A): control_exchange reads the structural `exile` Effect
    # whose subject carries the `Owned` predicate PAIRED with a to:battlefield return.
    assert any(
        k == "control_exchange" for k, _, _ in _ksub_real("Meneldor, Swift Savior")
    )
    assert any(k == "control_exchange" for k, _, _ in _ksub_real("The Neutrinos"))
    assert not any(
        k == "control_exchange" for k, _, _ in _ksub_real("Restoration Angel")
    )


def test_kira_targeting_shield_opens_protected_theft():
    # Kira grants your creatures "counter the FIRST spell/ability targeting them each
    # turn" — so a contingent steal (Sower: lost if the thief dies) can't be undone, and
    # a theft engine (Empress Galina) survives. That's the sticky-theft lock. WARD
    # ("counter it unless that player pays") is a different, single-creature shield and
    # must NOT open it (Spider-Rex).
    # ADR-0027 t2b5-C: theft_protection migrated to the Card IR (the kept word mirror),
    # so the regex path no longer emits it — assert via the hybrid (IR) path.
    assert any(
        k == "theft_protection" for k, _, _ in _ksub_real("Kira, Great Glass-Spinner")
    )
    assert not any(
        k == "theft_protection" for k, _, _ in _ksub_real("Spider-Rex, Daring Dino")
    )


def test_big_mana_generator_opens_x_spell_sink():
    # A commander that GENERATES big mana (Neheb: "add {R} for each life lost"; Sunastian:
    # "{T}: Add {C}{C}") wants X-spell mana sinks to dump it into. (Dan's clarification:
    # big-mana-GENERATING cards -> X-spells, not "high-cmc cards -> X".) A single-mana dork
    # (Llanowar Elves) is not a big-mana generator and stays out.
    # ADR-0027: big_mana migrated to the Card IR — assert via the hybrid path.
    # Sunastian ("{T}: Add {C}{C}") fires the STRUCTURAL `ramp` factor=2 arm; Neheb
    # ("add {R} for each …" → amount==None) rides the byte-identical _BIG_MANA_REGEX
    # kept mirror over its oracle (bare IR suffices — the mirror reads the dict oracle).
    assert any(k == "big_mana" for k, _, _ in _ksub_real("Neheb, the Eternal"))
    assert any(k == "big_mana" for k, _, _ in _ksub_real("Sunastian Falconer"))
    # A single-mana dork (Llanowar — `ramp` factor=1) is NOT big mana.
    assert not any(k == "big_mana" for k, _, _ in _ksub_real("Llanowar Elves"))


def test_opp_top_exile_opens_for_library_predators():
    # Circu (and Ragavan, Grenzo) exile/take the top card of a TARGET player's library,
    # so seeing opponents' tops (Field of Dreams) lets them exile/steal the BEST card and
    # target the right player. A commander with no opponent-library-top interaction
    # (Llanowar Elves) never opens it. ADR-0027 q2-D2: opp_top_exile is now IR-served —
    # Circu's exile scope phase reads as 'any' (no structural arm), so it fires from the
    # _IR_KEPT_DETECTORS word mirror (oracle scan → a bare IR routes to the IR path).
    assert any(
        k == "opp_top_exile" for k, _, _ in _ksub_real("Circu, Dimir Lobotomist")
    )
    assert not any(k == "opp_top_exile" for k, _, _ in _ksub_real("Llanowar Elves"))


def test_fblthp_free_plot_opens_for_zero_cost():
    # Fblthp makes the top card's plot cost EQUAL its mana cost, so 0-cost cards are FREE
    # to plot — the artifact-combo / storm engine (Hullbreaker + two 0-cost permanents =
    # infinite; Sai / Displacer chains). So he wants 0-cost cards. A commander without the
    # free-plot ability never opens it.
    # ADR-0027 t2b5-A: free_plot migrated to the Card IR (a kept word mirror), so it now
    # fires from the hybrid path, not the deleted _HAND_FLOOR producer.
    assert any(k == "free_plot" for k, _, _ in _ksub_real("Fblthp, Lost on the Range"))
    assert not any(k == "free_plot" for k, _, _ in _ksub_real("Llanowar Elves"))


def test_bargain_symmetric_sac_does_not_open_type_lanes():
    # ADR-0027 (CR 702.166a): Bargain ("sacrifice an artifact, ENCHANTMENT, or token")
    # projects a sacrifice Effect whose subject carries the catch-all 'Permanent' type
    # (the 'token' option) alongside Artifact/Enchantment. That is a GENERIC alt-cost,
    # NOT an artifacts/enchantments build-around (Torch the Tower / Beseech the Mirror
    # are burn / a generic tutor). The symmetric-list gate must keep BOTH type lanes
    # shut. Regression: the sidecar projection structures this sac, so it over-fired
    # both lanes in production until the gate landed.
    keys = _keys_real("Torch the Tower")
    assert "artifacts_matter" not in keys
    assert "enchantments_matter" not in keys
    # Positive control: a SINGLE-type artifact sac outlet (Atog-style) DOES open the
    # lane — the gate is narrow to the Permanent-containing symmetric list.
    assert "artifacts_matter" in _keys_real("Atog")


def test_stax_taxes_scoped_to_opponents():
    assert ("stax_taxes", "opponents") in _ks_real("Grand Arbiter Augustin IV")


def test_blink_flicker_exile_other_target_then_return():
    # "exile up to one OTHER target [permanent] ... return it/that card to the
    # battlefield" is a blink engine (CR — leaves then re-enters); the cross-sentence
    # detector's optional group only had "another/one", so "one other" slipped past
    # and these read as plain exile_removal. Real cards, full oracle text.
    # ADR-0027 v34: blink_flicker migrated — use the hybrid path. These cross-sentence
    # "exile … Return that card to the battlefield" engines ride the byte-identical kept
    # mirror (_detect_blink_fulltext), which scans the oracle directly.
    assert "blink_flicker" in _keys_real("Ennis, Debate Moderator")
    assert "blink_flicker" in _keys_real("Koya, Death from Above")
    assert "blink_flicker" in _keys_real("Phelia, Exuberant Shepherd")


def test_self_etb_variable_damage_opens_flicker_and_clone():
    # A commander whose own ETB deals VARIABLE damage ("deals damage equal to its
    # power", "deals X damage") is a Flametongue-Kavu-style value ETB the blink
    # membership cross-open rewards. The value-verb matching lives in
    # ``text_reads._self_etb_value`` (still consumed by the production membership
    # floor); probe the helper directly. Real oracle text.
    dong_zhou_text = (
        "When Dong Zhou enters, target creature an opponent controls deals "
        "damage equal to its power to that player."
    )
    assert _self_etb_value(dong_zhou_text, "Dong Zhou, the Tyrant")
    # Over-fire guard: an exile-removal ETB (Banisher Priest) is NOT a flicker
    # payoff — damage/value verbs qualify, "exile target" does not (O-Ring rule).
    banisher_text = (
        "When this creature enters, exile target creature an opponent controls "
        "until this creature leaves the battlefield."
    )
    assert _self_etb_value(banisher_text, "Banisher Priest") is None


def test_self_etb_modal_choose_requires_enters_not_dies():
    # The self-ETB payoff list includes the modal marker "choose one/two/three" — but it
    # MUST stay anchored to "when ~ enters". A DEATH-modal trigger ("When ~ dies, choose
    # one —") is re-used by sacrifice/reanimation, NOT by blink, so it must not open the
    # Blink avenue. Regression guard: the modal alternative was ungrouped, so it floated
    # to the top of the pattern and matched ANY "choose one" (Atsushi's death modal).
    # Real oracle.
    # ADR-0027 v34: blink_flicker migrated — use the hybrid path. Atsushi's death modal
    # exiles the top of the library to PLAY (no "return … to the battlefield"), so neither
    # the kept mirror nor the self-ETB avenue opener fires.
    assert "blink_flicker" not in _keys_real("Atsushi, the Blazing Sky")
    # A genuine ETB modal ("When ~ enters, choose one —") still opens Blink: flicker
    # re-fires the enter trigger (CR 603.6). Real oracle.
    # The cross-sentence "Exile … Return it to the battlefield" rides the kept mirror.
    assert "blink_flicker" in _keys_real("Charming Prince")


def test_xspell_matters_detects_x_cost_payoffs_not_hoser():
    # A commander that rewards/enables casting spells whose PRINTED mana cost contains
    # {X} (CR 107.3 / 202.1) opens xspell_matters — it wants the universe of X-spells +
    # X-doublers. ADR-0027 t2b4a-B: IR-served — the HasXInManaCost predicate on a
    # cast_spell trigger subject (Zaxara) + a kept effect-raw hook mirror minus the
    # "can't be cast" veto (Rosheen's mana-enabler) so an X-spell HOSER never reads as
    # wanting them. Real oracle; the regex path no longer fires it.
    assert "xspell_matters" in _keys_real("Zaxara, the Exemplary")
    # phase drops the {X}-in-cost predicate here (folds to a bare ramp effect); the
    # kept effect-raw hook mirror recovers it.
    assert "xspell_matters" in _keys_real("Rosheen Meanderer")
    # Hoser: Gaddock Teeg BANS X-spells ("can't be cast") — it does NOT want them. The
    # ban is a restriction effect (no payoff trigger predicate), and the kept hook
    # mirror's veto keeps the avenue closed even on the effect raw.
    assert "xspell_matters" not in _keys_real("Gaddock Teeg")


def test_self_heroic_commander_opens_voltron():
    # A commander with a SELF-targeting heroic trigger ("whenever you cast a spell that
    # targets [itself]", CR 702.86) is a suit-up-one-creature voltron deck: casting an
    # Aura/pump spell on it both fires heroic AND buffs it, so it wants the equipment /
    # pump-aura / protection package voltron_matters serves. Opens even with another
    # engine present (Brigone also has a counter sub-theme). Real oracle.
    assert "voltron_matters" in _keys_real("Brigone, Soldier of Meletis")
    # The "targets only <name>" form (Feather).
    assert "voltron_matters" in _keys_real("Feather, Radiant Arbiter")
    # Self-scoped: a trigger that targets ANOTHER creature (not itself) is NOT the
    # suit-up tell — the helper must not match it (isolates the rule from the power>=2
    # commander-damage fallback).
    assert (
        _voltron_self_heroic(
            "Whenever you cast a spell that targets another target creature you "
            "control, scry 1.",
            "Test Granter",
        )
        is False
    )


def test_land_scaling_power_opens_voltron():
    # A commander whose OWN power equals a basic-land-type count (Sima Yi: "power is
    # equal to the number of Swamps") is a single mono-color scaling threat you suit up —
    # its top synergy is the Swamp-scaling equipment (Nightmare Lash, Lashwrithe). Opens
    # voltron. Self-scoped so a team anthem ("creatures you control have power equal to
    # the number of Forests") doesn't qualify. Real oracle.
    assert "voltron_matters" in _keys_real("Sima Yi, Wei Field Marshal")
    # Self-scoped: a team anthem that sets OTHERS' power by a land count is not a single
    # suit-up threat — the helper must not match it.
    assert (
        _voltron_land_scaler(
            "Creatures you control have base power equal to the number of Forests "
            "you control.",
            "Test Anthem",
        )
        is False
    )


def test_self_recurring_commander_opens_voltron():
    # A commander that returns ITSELF from the graveyard (Akuta: "return Akuta from your
    # graveyard to the battlefield") is a resilient, hard-to-keep-dead threat — a prime
    # equipment carrier (its top synergy is Swamp-scaling equipment). Opens voltron.
    # Real oracle.
    assert "voltron_matters" in _keys_real("Akuta, Born of Ash")
    # Self-scoped: a reanimation spell returning ANOTHER creature is not the resilience
    # tell — the helper must not match it.
    assert (
        _voltron_self_recurs(
            "Return target creature card from your graveyard to the battlefield.",
            "Reanimator",
        )
        is False
    )


def test_creatures_are_lands_is_not_untap_engine():
    # Ashaya's nontoken creatures ARE Forest lands (a pure CR 205.1a type-change);
    # Ashaya's own ability untaps nothing itself, so the crosswalk fold sheds it as
    # lands_matter / land_creatures_matter synergy, NOT a genuine untap_engine
    # member (ADR-0036 Stage 5 — the deleted mirror's Ashaya inclusion was a false
    # positive). The pure-regex path never had a creatures-are-lands untap
    # detector, so it sheds Ashaya; the crosswalk sheds it too.
    keys = _keys_real("Ashaya, Soul of the Wild")
    assert "untap_engine" not in keys


def test_rampage_keyword_opens_blocked_matters():
    # Rampage's "whenever this creature becomes blocked" trigger lives in stripped
    # reminder text, so the deleted blocked_matters regex (reminder-stripped) missed it.
    # A Rampage commander (Marhault) wants the blocked-matters payoffs (Varchild's
    # War-Riders, Craw Giant, Retaliation). ADR-0027 Cluster D (SIDECAR v36):
    # blocked_matters migrated to the Card IR — phase parses rampage's reminder trigger
    # as a BecomesBlocked mode (projected to event=='becomes_blocked'), so the structural
    # becomes_blocked arm opens blocked_matters from the IR; the regex path must NOT emit
    # the migrated key. Real oracle.
    # The reminder-stripped regex path never emitted it (the deleted producer scanned
    # stripped oracle); the IR structural arm now does.
    assert "blocked_matters" in _keys_real("Marhault Elsdragon")


def test_permanents_with_counters_opens_counters():
    # Xolatoyac untaps "each permanent you control with a counter on it" — a counters-
    # matters commander (it wants counters on its permanents to untap them), but the
    # +1/+1-specific detector missed it (flood counters; "with a counter on it"). So it
    # missed counter producers (Forgotten Ancient, Master Biomancer, Vorel). Real oracle.
    # ADR-0039 W8: plus_one_matters PROMOTED — the crosswalk (flag-ON) correctly does
    # NOT fire it here: "with a counter on it" carries an explicit Any kind (CR
    # 122.1's kind carries the distinction: a kind-agnostic reference is not a
    # +1/+1-specific payoff), the SAME adjudicated shed class as The Swarmlord /
    # Yathan Tombguard / Winged Hive Tyrant. any_counter_matters is the correct
    # lane (mirrors the split ADR-0038 W4 established).
    assert "any_counter_matters" in _keys_real("Xolatoyac, the Smiling Flood")
    keys = _keys_real("Xolatoyac, the Smiling Flood")
    assert "plus_one_matters" not in keys


def test_planeswalker_type_opens_superfriends():
    # Leori cares about planeswalkers as a GROUP ("choose a planeswalker type ... activate
    # an ability of a planeswalker of that type, copy it") — a superfriends commander, but
    # the detector keyed only on "planeswalkers you control" / "loyalty counter" / "activate
    # a loyalty", missing the "planeswalker type" / "ability of a planeswalker" phrasing,
    # so it missed The Chain Veil / Ichormoon Gauntlet / Onakke Oathkeeper. Real oracle.
    # ADR-0027: superfriends_matters migrated to the Card IR (the byte-identical
    # SUPERFRIENDS_MATTERS_REGEX kept word mirror), so it now rides the hybrid path —
    # the regex path no longer emits the key.
    assert "superfriends_matters" in _keys_real("Leori, Sparktouched Hunter")
    # Over-fire guard: activating a CREATURE's ability is not a superfriends tell.


def test_three_zone_opponent_search_opens_theft():
    # Kotose rifles all THREE of an opponent's zones ("Search that player's graveyard,
    # hand, and library ... and exile them ... you may play one of the exiled cards") —
    # unambiguous steal-and-cast theft, but the detector keyed only on top-of-library
    # forms, so Kotose missed the theft payoffs (Gonti, Praetor's Grasp). Real oracle.
    # ADR-0027: theft_matters migrated to the Card IR (a byte-identical THEFT_MATTERS_
    # REGEX kept mirror over the reminder-stripped oracle), so it serves from the hybrid
    # path, not pure regex. ADR-0034 _matters sweep: the steal-and-cast MAKER arm now
    # emits theft_makers.
    assert "theft_makers" in _keys_real("Kotose, the Silent Spider")
    # Over-fire guard: searching YOUR OWN library is not theft.


def test_self_double_strike_beater_opens_voltron():
    # A commander that ITSELF has double strike and a real body (power >= 4) is a
    # single beater that doubles every equipment/aura bonus -> voltron. The gate
    # lives in ``_voltron_double_strike_beater`` (production: the membership floor's
    # voltron override); probe it helper-level. A double-strike TOKEN go-wide engine
    # (Oketra: makes Warriors, power 3) is excluded by BOTH the power>=4 and
    # no-token gates — the documented over-fire class stays out. Real oracle.
    sabin = {
        "name": "Sabin, Master Monk",
        "type_line": "Legendary Creature — Human Noble Monk",
        "power": "4",
        "toughness": "3",
        "keywords": ["Blitz", "Double strike"],
        "oracle_text": (
            "Double strike\nBlitz—{2}{R}{R}, Discard a card. (If you cast this spell "
            'for its blitz cost, it gains haste and "When this creature dies, draw a '
            'card." Sacrifice it at the beginning of the next end step.)\nYou may '
            "cast this card from your graveyard using its blitz ability."
        ),
    }
    oketra = {
        "name": "Oketra the True",
        "power": "3",
        "keywords": ["Indestructible", "Double strike"],
        "oracle_text": "{3}{W}: Create a 1/1 white Warrior creature token with vigilance.",
    }
    assert _voltron_double_strike_beater(oketra, oketra["oracle_text"]) is False
    assert _voltron_double_strike_beater(sabin, sabin["oracle_text"]) is True


def test_self_death_variable_damage_opens_payoff_and_clone():
    # Symmetric with the ETB case: a commander whose own DEATH trigger deals VARIABLE
    # damage ("deals damage equal to its power") is a value death trigger worth
    # re-firing. The name-aware value matching lives in ``text_reads._self_dies_value``
    # (still consumed by the production membership floor); probe it directly.
    orca_text = (
        "When Orca dies, it deals damage equal to its power divided as you choose "
        "among any number of targets."
    )
    assert _self_dies_value(orca_text, "Orca, Siege Demon")
    # Over-fire guard: a "deals damage equal to" clause NOT on a death trigger (a
    # combat trigger) must not open the death payoff.
    combat_text = (
        "Whenever this creature attacks, it deals damage equal to its power to "
        "any target."
    )
    assert _self_dies_value(combat_text, "Variable Combat Burner") is None


def test_proliferate_via_keyword_array():
    # ADR-0027: proliferate migrated to the Card IR; the proliferate keyword now
    # opens the lane via _IR_KEYWORD_MAP (the IR-only keyword path, reading the
    # record's Scryfall keyword array), so this asserts the hybrid. _matters sweep
    # (ADR-0034): Atraxa CARRIES the Proliferate keyword (it PERFORMS proliferate),
    # so the keyword arm now emits the MAKER key proliferate_makers, not the
    # cares-about payoff lane proliferate_matters.
    assert ("proliferate_makers", "you") in _ks_real("Atraxa, Praetors' Voice")


# --- narrow Tinybones scope fix (ADR-0009) ------------------------------------


def test_tinybones_combat_damage_zone_scoped_opponents():
    # ADR-0027 v29: graveyard_matters migrated to the IR — the narrow Tinybones rescope
    # (combat-damage-to-a-player + that-player's-zone → opponents) rides the
    # byte-identical _graveyard_matters_clauses mirror, so assert via the hybrid path.
    sigs = test_signals("Tinybones, the Pickpocket")
    assert any(s.key == "graveyard_matters" and s.scope == "opponents" for s in sigs)
    assert not any(s.key == "graveyard_matters" and s.scope == "you" for s in sigs)


# --- coverage gate (the agent-augmentation hook) -------------------------------


def test_coverage_gate_flags_zero_signal():
    # coverage_gate runs over production extractor output (its intended use): a
    # record that resolves no concept trees and fires no floor lane is a blind spot.
    c = {"name": "Vanilla", "oracle_text": "Flying"}
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "zero_signal"


def test_coverage_gate_passes_when_subject_present():
    # A card with a subject-bearing lane (Krenko's Goblin kindred) is not a blind
    # spot — production signals via the snapshot path.
    sigs = test_signals("Krenko, Mob Boss")
    assert any(s.subject for s in sigs)  # precondition: a real subject lane
    needs, _reason = coverage_gate(test_card("Krenko, Mob Boss"), sigs)
    assert needs is False


def test_coverage_gate_only_generic_creatures_matter():
    # Gate logic in isolation: a card whose only signal is the non-discriminating
    # creatures_matter is still flagged for the agent. (Built from a controlled
    # signal list — most real anthems now also carry a real anthem axis.)
    from mtg_utils._deck_forge.signals import Signal

    sigs = [Signal("creatures_matter", "you", "", "creatures you control", "Anthem")]
    c = {"name": "Anthem", "oracle_text": "Creatures you control are bigger."}
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "only_generic"


def test_coverage_gate_flags_partial_parse_ir():
    # ADR-0027 A4: a card with REAL signals but a PARTIAL Card-IR parse is flagged
    # partial_parse so the agent knows the structural read may miss a lane. Gate
    # logic in isolation (a controlled signal list — the signal-quality reasons
    # keep precedence; this is the residual blind-spot net).
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    partial = Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", abilities=()),),
        parse_confidence="partial",
    )
    sigs = [
        Signal("type_matters", "you", "Goblin", "other goblins you control", "Lord")
    ]
    needs, reason = coverage_gate(c, sigs, partial)
    assert needs is True
    assert reason == "partial_parse"


def test_coverage_gate_full_ir_does_not_trip_partial_parse():
    # The reason is additive: a FULL-confidence IR (the default) never flags
    # partial_parse.
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    full = Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))
    sigs = [
        Signal("type_matters", "you", "Goblin", "other goblins you control", "Lord")
    ]
    needs, reason = coverage_gate(c, sigs, full)
    assert needs is False
    assert reason == ""


# --- regression: baseline still fires -----------------------------------------


def test_reminder_text_does_not_produce_signals():
    # Ba Sing Se's earthbend REMINDER text (parenthetical) mentions exile+return;
    # it must not register as a blink/flicker engine (reminder text restates a
    # keyword and should never generate a signal).
    # ADR-0027 v34: assert via the hybrid path — the kept mirror runs over the reminder-
    # STRIPPED kept_oracle, so the parenthetical earthbend "exile … return it" never
    # fires the migrated lane.
    assert "blink_flicker" not in _keys_real("Ba Sing Se")


def test_enchantment_token_maker_opens_enchantments():
    # A commander that creates enchantment/Aura tokens (Scriv "create a white Aura
    # enchantment token", The Rani, Preston Garvey) is an enchantment deck — it wants
    # enchantment payoffs (Eriette, Sphere of Safety). Real oracle.
    # ADR-0027: enchantments_matter migrated to the Card IR — the make_token DOER fires
    # off the Enchantment-typed token subject (the Aura token), so this serves from the
    # hybrid path against the structured make_token Effect.
    assert ("enchantments_matter", "you") in _ks_real("Scriv, the Obligator")
    assert ("enchantments_matter", "you") not in _ks_real("Grizzly Bears")


def test_legendary_permanent_trigger_opens_legends():
    # A commander with a legendary-permanent trigger (Yomiji "whenever a legendary
    # permanent ... is put into a graveyard, return it", Cleopatra) is a legends-matter
    # deck — it wants legendary payoffs (Yoshimaru, Search for Glory). Real oracle.
    # ADR-0027: legends_matter migrated to the Card IR, so the textual refs phase
    # leaves unstructured fire via the kept word mirror in the hybrid path, not regex.
    assert ("legends_matter", "you") in _ks_real("Yomiji, Who Bars the Way")
    # Also the TUTOR form (Captain Sisay) and BUFF form.
    assert ("legends_matter", "you") in _ks_real("Captain Sisay")
    assert ("legends_matter", "you") not in _ks_real("Grizzly Bears")


def test_double_damage_of_counter_creatures_opens_counters():
    # "Double all damage that creatures you control WITH COUNTERS ON THEM would deal"
    # (Raphael, Tidus) — the ADR-0027 author read this as a +1/+1-counters DAMAGE
    # payoff (the damage-doubling context implies POSITIVE counters), but the text
    # itself is a kind-agnostic Any reference (CR 122.1's kind carries the
    # distinction). ADR-0039 W8: plus_one_matters PROMOTED — the crosswalk
    # correctly does NOT fire it here: a replacement's damage_source_filter carrying
    # an Any-kind Counters predicate is the SAME kind-mismatch shed class as The
    # Swarmlord / Xolatoyac / Winged Hive Tyrant.
    # NOTE (deferred, not this wave's key): any_counter_matters ALSO does not fire —
    # its own arms never read a replacement's damage_source_filter at all, a
    # genuine structural gap in that SIBLING key, out of scope for the
    # plus_one_matters wave.
    keys = _keys_real("Raphael, the Muscle")
    assert "plus_one_matters" not in keys


def test_type_grant_opens_tribal():
    # A commander that CONVERTS its creatures to a tribe — "it's a Zombie in addition to
    # its other creature types" (Lim-Dûl reanimates as Zombies), Chainer (Nightmare) —
    # makes its board that tribe, so it wants that tribe's lords (Death Baron, Undead
    # Warchief). The tribal detector keyed on "Xs you control", not the type-GRANT form.
    # ADR-0027: type_matters migrated → hybrid path.
    assert ("type_matters", "you", "Zombie") in {
        (s.key, s.scope, s.subject) for s in test_signals("Lim-Dûl the Necromancer")
    }
    # Over-fire guard: a vanilla creature grants no type.
    assert not any(
        s.key == "type_matters" and s.subject == "Zombie"
        for s in test_signals("Grizzly Bears")
    )


def test_color_hoser_opens_and_serves_color_change_toolbox():
    # A color-HOSER commander (punishes/restricts/bounces a named COLOR) wants the
    # color-changing "Painter" toolbox to force its color payoff onto every
    # permanent. The extractor firing is pinned by test_crosswalk's
    # test_color_hoser_mirror_and_direct_structural_carrier; here the SERVE is the
    # color-change toolbox (Painter's Servant, Sleight of Mind), not a
    # protection-from-color trick or a mana fixer.
    from mtg_utils._deck_forge.signal_specs import spec_for

    sp = spec_for(Signal(key="color_hoser", scope="you", subject="", text="", source=""))
    painters = {
        "name": "Painter's Servant",
        "type_line": "Artifact Creature — Scarecrow",
        "oracle_text": (
            "As this creature enters, choose a color.\nAll cards that aren't on the "
            "battlefield, spells, and permanents are the chosen color in addition to "
            "their other colors."
        ),
    }
    sleight = {
        "name": "Sleight of Mind",
        "type_line": "Instant",
        "oracle_text": (
            "Change the text of target spell or permanent by replacing all instances "
            "of one color word with another."
        ),
    }
    bad_moon = {
        "name": "Bad Moon",
        "type_line": "Enchantment",
        "oracle_text": "Black creatures get +1/+1.",
    }
    assert sp.serve.matches(painters)
    assert sp.serve.matches(sleight)
    assert not sp.serve.matches(bad_moon)


def test_extra_combat_served_by_combat_signals():
    # A combat-damage / voltron commander wants EXTRA COMBATS: each added combat phase is
    # another round of attack + combat-damage triggers (Neheb -> Relentless Assault, Seize
    # the Day). attack_matters already served these; combat_damage / voltron did not.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    relentless = {
        "name": "Relentless Assault",
        "type_line": "Sorcery",
        "oracle_text": (
            "Untap all creatures that attacked this turn. After this main phase, there "
            "is an additional combat phase followed by an additional main phase."
        ),
    }
    # Over-fire guard: burn is not an extra-combat enabler.
    bolt = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
    }
    for key, scope in [
        ("combat_damage_matters", "opponents"),
        ("combat_damage_to_opp", "opponents"),
        ("voltron_matters", "you"),
    ]:
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))

        def covers(c, sp=sp):
            return sp.serve.matches(c) or any(
                (ex.serve or serve_from_dict(ex.search)).matches(c) for ex in sp.extras
            )

        assert covers(relentless), key
        assert not covers(bolt), key


def test_group_mana_serves_symmetric_mana():
    # A group-mana commander (Yurlok mana-burn, Shizuko group-ramp) wants symmetric
    # mana-makers/punishers — Mana Flare, Heartbeat of Spring, Manabarbs ("whenever a
    # player taps a land for mana"), Collective Voyage ("join forces"). The sweep serve
    # only credited "each player adds {".
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    mana_flare = {
        "name": "Mana Flare",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever a player taps a land for mana, that player adds an additional one "
            "mana of any type that land produced."
        ),
    }
    sp = spec_for(
        Signal(key="group_mana", scope="each", subject="", text="", source="")
    )

    def cov(c):
        return sp.serve.matches(c) or any(
            (ex.serve or serve_from_dict(ex.search)).matches(c) for ex in sp.extras
        )

    assert cov(mana_flare)
    # Over-fire guard: a one-sided mana dork is not symmetric group mana.
    llan = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
    }
    assert not cov(llan)


def test_discard_outlet_cross_opens_graveyard():
    # A discard-outlet commander fills the graveyard, so it wants GY payoffs (reanimate /
    # flashback / recur the discarded cards): cross-open graveyard_matters. Mishra loots
    # and discards artifacts; its GY misses (Trash for Treasure, Goblin Welder) were
    # unserved.
    # ADR-0027 (SIDECAR v26): discard_outlet migrated to the IR — it no longer rides the
    # pure-regex `extract_signals` path, so this test drives the HYBRID path (the IR cost
    # arm fires discard_outlet from Mishra's "Discard a card: …" ability) and the
    # graveyard_matters cross-open was re-keyed off the byte-identical _DISCARD_OUTLET_
    # SWEEP_RE per-clause, so it still fires.
    keys = {s.key for s in test_signals("Mishra, Excavation Prodigy")}
    assert "discard_outlet" in keys  # precondition (IR cost arm)
    assert "graveyard_matters" in keys  # cross-opened


def test_named_token_maker_opens_tribe_via_all_parts():
    # A creature token the commander makes (all_parts token component) reveals its
    # tribe even when the oracle uses the token's NAME: Enkira makes "Walker tokens"
    # (Token Creature — Zombie), so it's Zombie-tribal though the oracle never says
    # "Zombie" outside reminder text. The all_parts membership arm survives in
    # membership_floor; proven over the real record.
    assert ("type_matters", "you", "Zombie") in _ksub_real("Enkira, Hostile Scavenger")


def test_amass_cards_served_by_tokens_matter():
    # Amass creates or grows an Army CREATURE token (CR 701.47), so an amass card is a
    # token maker the tokens_matter serve must credit — Mouth of Sauron / Grishnákh want
    # their amass package. The serve keyed on "token enters" / "populate" and missed the
    # amass keyword (its token-making lives in stripped reminder text, like Mobilize).
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    crebain = {
        "name": "Dunland Crebain",
        "type_line": "Creature — Bird Horror",
        "oracle_text": (
            "Flying\nWhen this creature enters, amass Orcs 2. (Put two +1/+1 counters on "
            "an Army you control. It's also an Orc. If you don't control an Army, create "
            "a 0/0 black Orc Army creature token first.)"
        ),
    }
    sp = spec_for(
        Signal(key="tokens_matter", scope="you", subject="", text="", source="")
    )

    def cov(c):
        return sp.serve.matches(c) or any(
            (ex.serve or serve_from_dict(ex.search)).matches(c) for ex in sp.extras
        )

    assert cov(crebain)
    # Over-fire guard: a vanilla creature is not a token maker.
    bears = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert not cov(bears)


def test_play_from_top_cross_opens_topdeck_selection():
    # A "play cards from the top of your library" commander (Gwenom) curates its
    # top — it opens play_from_top and the sibling topdeck_selection lane (the
    # cross-open lives in extract_signals's post-merge reconciliation).
    ks = _ks_real("Gwenom, Remorseless")
    # The doer lane on this card's real parse is free_cast (cast-from-top); the
    # load-bearing pin is the post-merge cross-open pair.
    assert ("free_cast", "you") in ks
    assert ("topdeck_stack", "you") in ks
    assert ("topdeck_selection", "you") in ks
    # Over-fire guard: a commander that doesn't play from the top opens neither.
    assert ("topdeck_selection", "you") not in _ks_real("Grizzly Bears")


def test_sac_and_return_this_turn_does_not_over_fire_sacrifice():
    # ADR-0027: the old "sac-and-return-this-turn" floor regex fired
    # sacrifice_outlets on Garna / Gerrard — reanimation engines that name NO
    # sacrifice at all. That was an over-fire (a return-from-graveyard payoff is not
    # a sacrifice OUTLET); the production path correctly drops it. Real oracle.
    assert ("sacrifice_outlets", "you") not in _ks_real("Garna, the Bloodflame")
    assert ("sacrifice_outlets", "you") not in _ks_real("Gerrard, Weatherlight Hero")
    # Over-fire guard: a vanilla creature is not a sac-and-return engine.
    assert ("sacrifice_outlets", "you") not in _ks_real("Grizzly Bears")


def test_warp_granting_is_not_cheat_into_play():
    # Tannuk grants WARP ("Artifact cards and red creature cards in your hand have
    # warp {2}{R}"). ADR-0038 W6 endgame adjudicated this a legacy OVER-FIRE (the
    # deleted live-path detector's own comment called it "a thematic membership
    # hunch, not a mechanical match") and ADR-0039 W7 PROMOTED cheat_into_play off
    # residual with this exclusion CR-grounded: CR 702.185a — Warp is an
    # alternative CAST cost ("You may cast this card from your hand by paying
    # [cost] rather than its mana cost"), the card still goes on the stack and is
    # CAST, the opposite of CR 601.2/400.7's "put onto the battlefield WITHOUT
    # casting it." The crosswalk's structural read (a pure static AddKeyword
    # modification, no ChangeZone/RevealUntil/tutor node anywhere) correctly
    # declines. Real oracle.
    keys = _keys_real("Tannuk, Steadfast Second")
    assert "cheat_into_play" not in keys
    # Over-fire guard: a vanilla creature is not a cheat deck.
    assert "cheat_into_play" not in _keys_real("Grizzly Bears")


def test_creature_died_this_turn_payoff_opens_death():
    # A commander that rewards "a creature died ... this turn" (Faramir draws, Sméagol
    # tempts, Tobias makes Zombies, Ebondeath recasts) is an aristocrats payoff — it
    # wants sac fodder and sac outlets, which death_matters serves. The "died under your
    # control this turn" word order slipped past the existing died-this-turn detector.
    # ADR-0027: death_matters migrated to the Card IR; the morbid "died this turn"
    # family rides the byte-identical _DEATH_MATTERS_MIRROR (scope "any") on the IR path.
    assert ("death_matters", "any") in _ks_real("Faramir, Field Commander")
    assert ("death_matters", "any") in _ks_real("Tobias, Doomed Conqueror")
    # Over-fire guard: a vanilla creature has no death payoff.
    assert ("death_matters", "any") not in _ks_real("Grizzly Bears")


def test_self_dies_recursion_opens_self_death_payoff():
    # A commander whose OWN death trigger RETURNS/recurs itself (Lucius exiles-and-
    # returns, The Scorpion God returns to hand) wants sac outlets to loop it +
    # reanimation — the same package as a self-dies-VALUE commander. self_death_payoff
    # required a VALUE verb and missed the pure-recursion form. Real oracle.
    # ADR-0027: self_death_payoff migrated to the Card IR; the self-RECURSION death
    # branch ("return it"/"exile it") rides the name-aware kept mirror on the hybrid path.
    assert "self_death_payoff" in _keys_real("Lucius the Eternal")
    assert "self_death_payoff" in _keys_real("The Scorpion God")
    # Over-fire guard: a vanilla creature has no self-death trigger.
    assert "self_death_payoff" not in _keys_real("Grizzly Bears")


def test_treasure_care_opens_treasure_matters():
    # A commander that cares about Treasure without making it — "if the sacrificed
    # permanent was a Treasure" (Evereth), "sacrifice a Treasure" (Kain) — is a Treasure
    # deck wanting Treasure makers/doublers (Academy Manufactor, Xorn). The detector
    # keyed on "create ... Treasure" / "Treasures you control" and missed these.
    # ADR-0027: treasure_matters migrated to the Card IR — the "was a Treasure" care is
    # a `token_subtype_ref` marker (subtype in counter_kind) read via _TOKEN_SUBTYPE_KEYS
    # through the hybrid, not the deleted regex.
    assert ("treasure_matters", "you") in {
        (s.key, s.scope) for s in test_signals("Evereth, Viceroy of Plunder")
    }
    # Over-fire guard: a vanilla creature is not a Treasure commander.
    assert ("treasure_matters", "you") not in _ks_real("Grizzly Bears")


def test_mana_ability_payoff_opens_ramp():
    # A commander that rewards "creatures you control with a mana ability" (Raggadragga
    # buffs/untaps them) is a mana-dork deck — it wants mana-dork creatures (served by
    # ramp) and dork support (mana_amplifier). Niche (one commander) but precise.
    # ADR-0027 β: the dork-support mana_amplifier arm is migrated to the Card IR — phase
    # drops the "with a mana ability" subject, so it rides a byte-identical kept word
    # mirror (_MANA_DORK_SUPPORT_MIRROR). ADR-0027: ramp ALSO migrated — its
    # dork-support producer rode the SAME mirror, so both now fire from the hybrid path.
    assert ("ramp", "you") in _ks_real("Raggadragga, Goreguts Boss")
    assert ("mana_amplifier", "you") in _ks_real("Raggadragga, Goreguts Boss")
    # Over-fire guard: a vanilla beater is not a mana-dork payoff.
    assert ("ramp", "you") not in _ks_real("Grizzly Bears")


def test_charge_and_experience_counters_open_proliferate():
    # A commander that accumulates a BENEFICIAL resource counter — charge (Immard) or
    # experience (Ezuri, Mizzix) — wants proliferate (pure upside: more charge to spend,
    # more experience). Distinct from a PENALTY counter (Arixmethes' slumber), where
    # proliferate is anti-synergy, so the lane is gated to charge/experience only.
    # ADR-0027: proliferate_matters migrated to the Card IR; the charge/experience
    # counter sources now fire from the _IR_KEPT_DETECTORS mirror, so assert the
    # hybrid path.
    assert ("proliferate_matters", "you") in _ks_real("Immard, the Stormcleaver")
    assert ("proliferate_matters", "you") in _ks_real("Ezuri, Claw of Progress")
    # Over-fire guard: a PENALTY-counter commander (slumber) must NOT open proliferate —
    # proliferate would keep Arixmethes asleep (anti-synergy).
    assert ("proliferate_matters", "you") not in _ks_real("Arixmethes, Slumbering Isle")


def test_counter_payoff_with_a_counter_on_it_opens_counters():
    # A +1/+1-counters commander whose payoff REWARDS creatures that HAVE counters
    # ("each creature you control WITH A COUNTER ON IT ...", "unless he has a +1/+1
    # counter on him") is a counters deck. The per-clause counters detector missed it:
    # the payoff clause ("with a counter on it") and the +1/+1 reference ("put a +1/+1
    # counter on Baxter") sit in SEPARATE sentences, so neither clause alone has both.
    # Needs full-text. Real oracle.
    # ADR-0027 + _matters sweep (ADR-0034): Rishkar/Baxter project a place_counter(p1p1)
    # — the MAKER arm → plus_one_makers; Pipsqueak (a pure "has a +1/+1 counter" payoff)
    # recovers a counters_have_ref marker — the PAYOFF arm → plus_one_matters. Assert
    # via the hybrid (production) path.
    assert "plus_one_makers" in _keys_real("Rishkar, Peema Renegade")
    assert "plus_one_makers" in _keys_real("Baxter, Fly in the Ointment")
    assert "plus_one_matters" in _keys_real("Pipsqueak, Rebel Strongarm")


def test_artifact_dig_and_improvise_open_artifacts():
    # Commanders that DIG for artifact cards ("put an artifact card ... into your hand /
    # onto the battlefield" — Fifteenth Doctor, Jhoira) or grant IMPROVISE (an
    # artifact-tap mechanic like affinity) are artifact decks; artifacts_matter matched
    # "search for an artifact card" but not these forms. Real oracle.
    # ADR-0027: artifacts_matter migrated to the Card IR — the "put an artifact card …
    # into your hand / onto the battlefield" dig + \bimprovise\b ride the kept oracle
    # mirror on the hybrid path.
    assert "artifacts_matter" in _keys_real("The Fifteenth Doctor")
    assert "artifacts_matter" in _keys_real("Jhoira, Ageless Innovator")
    # Over-fire guard: a vanilla creature is not an artifact commander.
    assert "artifacts_matter" not in _keys_real("Grizzly Bears")


def test_power_greater_than_base_power_opens_counters():
    # A commander that rewards creatures whose "power [is] greater than its base power"
    # (Kutzil, Baird) — the ADR-0027 author read this as a pump / +1/+1-counters
    # payoff (those creatures got there via counters or pumps), but CR 208.4b: "power
    # greater than base power" is a LAYER-applied current-vs-base comparison true for
    # ANY power-increasing effect (a temporary pump, a static anthem, Evolve), not
    # specific to +1/+1 counters — the state carries no counter KIND at all, so it
    # isn't a counter reference of any kind (not even any_counter_matters). ADR-0039
    # W8: plus_one_matters PROMOTED — the crosswalk correctly does NOT fire it here,
    # an adjudicated shed (Ms. Marvel is the third corpus member; see
    # test_crosswalk.py's test_plus_one_matters_excludes_power_greater_than_base_
    # power_cda).
    kutzil = _keys_real("Kutzil, Malamet Exemplar")
    baird = _keys_real("Baird, Argivian Recruiter")
    assert "plus_one_matters" not in kutzil
    assert "plus_one_matters" not in baird


def test_forced_combat_and_any_player_attack_open_goad():
    # Goad cards (Disrupt Decorum) are top-synergy for two archetypes that never opened
    # goad_makers: commanders that FORCE OTHER creatures to attack (Basandra "Target
    # creature attacks this turn if able" — the goad mechanic itself, CR 701.39) and
    # commanders that reward ANY player attacking (Aurelia "Whenever a player attacks
    # with three or more creatures" — goad makes opponents attack into the payoff). Real
    # oracle.
    # ADR-0027: goad_makers migrated to the IR — the regex path no longer emits it;
    # the hybrid path serves it (Basandra via the goad-style single-target force_attack
    # effect; Aurelia via the _GOAD_REWARD_REF marker, mirrored as a goad_all effect).
    assert ("goad_makers", "opponents") in {
        (s.key, s.scope) for s in test_signals("Basandra, Battle Seraph")
    }
    assert ("goad_makers", "opponents") in {
        (s.key, s.scope) for s in test_signals("Aurelia, the Law Above")
    }
    # Over-fire guard: a SELF forced-attacker (Zurgo) is an aggressive beater, not a
    # goad commander — it forces only ITSELF to attack each combat. The goad-style
    # force lift requires a "target creature" force, which Zurgo's self-force lacks.
    assert ("goad_makers", "opponents") not in {
        (s.key, s.scope) for s in test_signals("Zurgo Helmsmasher")
    }


def test_gain_control_commander_also_opens_wants_theft():
    # A battlefield-steal commander (Dragonlord Silumgar "gain control of target
    # creature") is a facet of the stealing archetype — a steal deck WANTS the
    # borrow-and-cast package (ADR-0034 _matters sweep: the want-side cross-open is
    # wants_theft, re-opened by extract_signals's post-merge reconciliation
    # against the merged key set). Real snapshot card.
    ks = _ks_real("Dragonlord Silumgar")
    assert ("gain_control", "you") in ks
    assert ("wants_theft", "opponents") in ks
    # Over-fire guard: a commander with no steal/theft text opens neither.
    assert ("wants_theft", "opponents") not in _ks_real("Grizzly Bears")


def test_donate_via_that_player_opens_donate():
    # Blim gives his own permanents to opponents ("that player gains control of target
    # permanent you control") — a donate commander wanting donate enablers (Harmless
    # Offering, Bazaar Trader). ADR-0027: donate migrated to the IR — a `gain_control`
    # effect whose raw names an another-player RECIPIENT (phase drops the recipient to
    # scope='any', so the lane reads the effect raw). Real oracle.
    blim_keys = {(s.key, s.scope) for s in test_signals("Blim, Comedic Genius")}
    assert ("donate_makers", "you") in blim_keys
    # Over-fire guard: a commander where YOU gain control (the opposite of donate — its
    # raw names no other-player recipient) does not open the donate lane.
    donate_keys = {(s.key, s.scope) for s in test_signals("Dragonlord Silumgar")}
    assert ("donate_makers", "you") not in donate_keys


def test_dont_own_payoff_opens_wants_theft_and_gain_control():
    # A theft-PAYOFF commander that rewards permanents "you control but DON'T OWN"
    # (Don Andres, Arvinox) is built on stealing — it WANTS the whole theft package
    # (battlefield steals AND borrow-and-cast). Gonti, Canny Acquisitor's "Spells
    # you cast but don't own" pins the intervening-verb form. The don't-own tell is
    # extract_signals's post-merge reconciliation. Real oracle.
    for name in (
        "Don Andres, the Renegade",
        "Arvinox, the Mind Flail",
        "Gonti, Canny Acquisitor",
    ):
        ks = _ks_real(name)
        assert ("wants_theft", "opponents") in ks, name
        assert ("gain_control", "you") in ks, name
    # Over-fire guard: a plain commander opens neither.
    assert ("wants_theft", "opponents") not in _ks_real("Grizzly Bears")


def test_self_reference_resolves_any_scope_to_you_high_confidence():
    # A clause with no scope marker → baseline "any"; the self-reference to the card's
    # own name resolves it to "you" with high confidence (Krenko Tin Street). ADR-0027:
    # attack_matters migrated to the Card IR, so its emission no longer carries the
    # resolved scope — but `_resolve_scope` (which `_attack_matters_is_plan` and every
    # surviving baseline detector still use) is exercised directly here.
    clause = (
        "Whenever Krenko attacks, put a +1/+1 counter on it, then create a number "
        "of 1/1 red Goblin creature tokens equal to Krenko's power."
    )
    scope, conf = _resolve_scope(
        clause, clause.lower(), _scope(clause.lower()), "Krenko, Tin Street Kingpin"
    )
    assert scope == "you"
    assert conf == "high"


def test_self_reference_skips_leading_article():
    # "The" must not be treated as the card's self-reference name. ADR-0027: death_matters
    # migrated to the Card IR — its mirror emits scope "any" (the deleted _HAND_FLOOR
    # producer's forced scope, and the serve spec's scope), so "The Scorpion God"'s
    # "Whenever a creature … dies" never spuriously flips to a self-ref "you". Assert via
    # the hybrid path the migrated lane now lives on.
    s = next(s for s in test_signals("The Scorpion God") if s.key == "death_matters")
    assert s.scope == "any"  # not a spurious self-ref flip to "you"


def test_broad_possessive_scope_is_opponents_low_confidence():
    # Non-combat "that player's graveyard" → opponents, but LOW confidence (the broad
    # rule turned on behind the flag; not trusted blindly). ADR-0027 v29: graveyard_matters
    # migrated to the IR, so this exercises `_resolve_scope` (the scope-resolution
    # machinery still used by every surviving baseline detector + the *_has_plan mirrors)
    # directly on the broad-possessive clause.
    clause = "Exile target creature card from that player's graveyard."
    scope, conf = _resolve_scope(
        clause, clause.lower(), _scope(clause.lower()), "Graverobber"
    )
    assert scope == "opponents"
    assert conf == "low"


def test_narrow_tinybones_rule_is_high_confidence():
    # ADR-0027 v29: graveyard_matters migrated to the IR. The narrow Tinybones rule
    # (combat-damage-to-a-player + that-player's-zone → opponents, HIGH confidence) is
    # `_tinybones_scope`, applied per-clause; assert it directly + via the hybrid path.
    clause = (
        "Whenever Tinybones deals combat damage to a player, you may cast target "
        "nonland permanent card from that player's graveyard."
    )
    assert _tinybones_scope(clause) == "opponents"
    s = next(
        sig
        for sig in test_signals("Tinybones, the Pickpocket")
        if sig.key == "graveyard_matters"
    )
    assert s.scope == "opponents"


def test_granted_ability_marks_signal_low_confidence():
    # A baseline signal pulled from a GRANTED ability (have "...") is scope-uncertain
    # (outer "you control" vs inner effect), so it is marked low confidence. ADR-0027:
    # attack_matters migrated, so `_resolve_scope` (still used by `_attack_matters_is_plan`
    # and every surviving baseline detector) is exercised directly here.
    clause = 'Creatures you control have "Whenever this creature attacks, draw a card."'
    _, conf = _resolve_scope(clause, clause.lower(), _scope(clause.lower()), "Grantor")
    assert conf == "low"


def test_coverage_gate_flags_low_confidence_only():
    # The coverage gate flags a card whose every signal is LOW confidence (a scope guess
    # the agent must confirm). ADR-0027 v29: graveyard_matters migrated to the IR (whose
    # broad-possessive guess rides the byte mirror at high confidence), so this exercises
    # the gate logic directly with a constructed LOW-only signal list — a broad-possessive
    # graveyard guess is the canonical low-confidence shape.
    from mtg_utils._deck_forge.signals import Signal

    c = {
        "name": "Graverobber",
        "oracle_text": "You may play cards from that player's graveyard.",
    }
    sigs = [
        Signal(
            key="graveyard_matters",
            scope="opponents",
            subject="",
            text="you may play cards from that player's graveyard",
            source="Graverobber",
            confidence="low",
        )
    ]
    assert all(s.confidence == "low" for s in sigs)
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "low_confidence"


def test_populate_opens_token_copy_matters():
    # Populate (CR 702.95) IS "create a token that's a copy of a creature token you
    # control" — a token-copy mechanic — so a populate commander opens token_copy_makers
    # (the serve already credited populate; the detector missed the keyword).
    # ADR-0027 C5: populate (CR 701.36) projects to a make_token whose subject carries
    # the ("Token", "Copy") predicates (a copy of a creature token), which the structural
    # token_copy_makers arm reads — no regex mirror.
    assert "token_copy_makers" in _keys_real("Ghired, Conclave Exile")
    assert "token_copy_makers" in _keys_real("Trostani, Selesnya's Voice")


def test_self_death_payoff_opens_for_own_death_trigger():
    # A commander whose OWN "when ~ dies, <value>" is the engine opens self_death_payoff
    # (distinct from aristocrats death_matters — that keys on ANY creature dying). Real
    # cards, full oracle text.
    # ADR-0027: self_death_payoff migrated to the Card IR; a commander's OWN "when ~
    # dies, <value>" self-death engine rides the name-aware kept mirror on the hybrid
    # path (and the structural SelfRef `dies` arm when the IR carries the trigger).
    assert "self_death_payoff" in _keys_real("Kokusho, the Evening Star")
    assert "self_death_payoff" in _keys_real("Junji, the Midnight Sky")
    # Over-fire guard: aristocrats (OTHER creatures dying) is NOT a self-death payoff.
    assert "self_death_payoff" not in _keys_real("Blood Artist")


def test_creature_etb_opens_on_delayed_had_enter_payoff():
    # Ephara rewards creatures entering via a DELAYED check ("at the beginning of
    # upkeep, if you had a creature enter ... last turn, draw") — no "when/whenever"
    # trigger word, so the ETB detector's trigger-word gate missed it. It's an
    # ETB-payoff commander (wants ETB creatures / blink / token makers).
    # ADR-0027 β: this delayed "if you had a creature enter" payoff is exactly why
    # creature_etb rides a kept-mirror, not the structural etb-trigger arm — phase
    # models it as an upkeep trigger (no `etb` event), so it serves from the hybrid.
    assert "creature_etb" in _keys_real("Ephara, God of the Polis")


def test_creature_recursion_opens_and_self_sac_creatures_serve_it():
    # Creature-recursion commanders loop SELF-SACRIFICING creatures — the sac is the
    # activation (repeatable value) AND fuels the graveyard for re-recursion, no
    # separate outlet needed (Spore Frog). The extractor firing is pinned by
    # test_signal_keys_real_cards (creature_recursion); here the SERVE is checked.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    spore_frog = {
        "name": "Spore Frog",
        "type_line": "Creature — Frog",
        "oracle_text": "Sacrifice this creature: Prevent all combat damage that would be dealt this turn.",
    }
    assert lane_covers(spore_frog, "creature_recursion") is True
    # Over-fire guard: a vanilla creature is not loop fuel.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert lane_covers(bear, "creature_recursion") is False


def test_self_etb_value_matches_whenever_and_plural_enter():
    # ``_self_etb_value`` (production membership-floor input) must match "WHENEVER ~
    # enters" (Roxanne) — the old detector keyed on "\bwhen " only. Real oracle.
    roxanne_text = (
        "Whenever Roxanne enters or attacks, create a tapped colorless artifact "
        'token named Meteorite with "When this token enters, it deals 2 damage '
        'to any target" and "{T}: Add one mana of any color."'
    )
    assert _self_etb_value(roxanne_text, "Roxanne, Starfall Savant")


def test_self_etb_value_resolves_short_name_not_just_first_token():
    # The self-reference in oracle is the name BEFORE the comma (the short name),
    # which may be hyphenated, two-named, or multi-word — not the bare first token.
    # "When Spider-Byte enters" / "When Donnie & April enter" / "When Black Cat
    # enters" must all match ``_self_etb_value`` (production membership-floor
    # input). Real oracle text.
    assert _self_etb_value(
        "When Spider-Byte enters, return up to one target nonland permanent to "
        "its owner's hand.",
        "Spider-Byte, Web Warden",
    )
    assert _self_etb_value(
        "When Donnie & April enter, choose one or both. Each mode must target a "
        "different player.",
        "Donnie & April, Adorkable Duo",
    )
    assert _self_etb_value(
        "When Black Cat enters, look at the top nine cards of target opponent's "
        "library, exile two of them face down, then put the rest on the bottom of "
        "their library in a random order.",
        "Black Cat, Cunning Thief",
    )


def test_self_dies_value_resolves_short_name_for_clone():
    # A high-CMC commander with a self DIES trigger is worth cloning — a token copy
    # re-fires the trigger when the copy dies. The clone detector keyed on the first
    # name token before "dies", so "When The Scarab God dies" missed ("The" is an
    # article, "Scarab" is followed by " God", not " dies"). Real cards, cmc>=5, no ETB
    # (so the clone signal comes from the DIES path, not the ETB path).
    # ADR-0027 v30: wants_cloning migrated — the high-CMC self-dies clone-TARGET
    # membership cross-open is reproduced in the IR path, so assert via the hybrid.
    assert "wants_cloning" in _keys_real("The Scarab God")
    assert "wants_cloning" in _keys_real("The Locust God")


def test_self_counter_accumulator_opens_plus_one_makers():
    # A commander that puts +1/+1 counters on ITSELF and cares about its COUNT
    # (Sab-Sunen — "number of counters on it") is a +1/+1-counters commander; the
    # self-placement is the MAKER arm, so it opens plus_one_makers (counter sources).
    # ADR-0027 + _matters sweep (ADR-0034): the place_counter arm fires plus_one_makers
    # on ANY +1/+1 PLACEMENT (CR 122.1 / 122.6) — even a bare self-accumulator is a
    # source. Assert via the hybrid path.
    assert "plus_one_makers" in _keys_real("Sab-Sunen, Luxa Embodied")


def test_board_wide_counter_placement_opens_plus_one_makers():
    # Board-wide "+1/+1 counter on each <group>" placement is a counters ENGINE —
    # the commander repeatedly spreads counters across a board, so it wants counter
    # payoffs (proliferate, doublers, counter-matters creatures). The detector keyed
    # only on the exact phrase "on each creature you control", missing every other
    # group: "on each attacking creature", "on each <tribe> you control", "on each
    # of up to N target creatures", "on each other/legendary/artifact creature".
    # Generalize to the placement clause itself: "+1/+1 counter on each".
    # ADR-0027 + _matters sweep (ADR-0034): every board-wide +1/+1 placement projects a
    # place_counter(p1p1) — the MAKER arm → plus_one_makers. Assert via the hybrid path.
    # (The maker lane opens on any placement — a placement is a source whoever receives
    # it — so the old "self-grower stays out" precision guard is dropped.)
    assert "plus_one_makers" in _keys_real("Drana, Liberator of Malakir")
    # Activated board-wide placer (Steel Overseer-style) — same lane.
    assert "plus_one_makers" in _keys_real("Steel Overseer")


def test_voltron_override_opens_for_likely_voltron_commanders():
    # Voltron is surfaced (the equipment/aura + protection package) even when another
    # signal already fired, via three calibrated OVERRIDE criteria. Real oracle.
    from mtg_utils._deck_forge.signals import (
        _VOLTRON_EQUIP_RE,
        _voltron_self_pump,
        _voltron_self_unblockable,
    )

    # (D) Mirri grows herself on combat damage — opens voltron despite also opening
    # combat_damage_to_creature (the named bug: the old fallback was suppressed).
    # ADR-0027 (SIDECAR v41): combat_damage_to_creature reads the STRUCTURED recipient
    # (creature) on the IR's combat_damage trigger; the voltron self-pump override still
    # opens voltron.
    mk = {s.key for s in test_signals("Mirri the Cursed")}
    assert "voltron_matters" in mk
    assert "combat_damage_to_creature" in mk  # both — the override no longer suppresses
    # (C) Sram rewards casting Auras & Equipment (comma-list phrasing).
    assert "voltron_matters" in {s.key for s in test_signals("Sram, Senior Edificer")}
    # (F) Tromokratis (Kraken, 8/8) is self-unblockable — a fat evasive body.
    assert "voltron_matters" in {s.key for s in test_signals("Tromokratis")}
    # Self-scope unit guards (isolate the override from the power>=2 path-B fallback):
    # a counter on a NON-self target, and unblockable GRANTED to others, do not qualify.
    assert (
        _voltron_self_pump(
            "Whenever this attacks, put a +1/+1 counter on each creature you control.",
            "X",
        )
        is False
    )
    assert (
        _voltron_self_unblockable(
            "Whenever you cast a noncreature spell, target creature you control can't be "
            "blocked this turn.",
            "Bria, Riptide Rogue",
        )
        is False
    )
    # ...but the commander's OWN unblockability (real text, not stripped keyword
    # reminders) does — this is what isolates (F) from the power>=2 path-B fallback.
    assert (
        _voltron_self_unblockable(
            "Tromokratis can't be blocked unless all creatures defending player controls "
            "block it.",
            "Tromokratis",
        )
        is True
    )
    # (C) does not fire on a non-equipment commander (a pure token engine).
    assert (
        _VOLTRON_EQUIP_RE.search(
            "Whenever you cast a creature spell, create a 4/4 black Zombie Warrior token."
        )
        is None
    )


def test_voltron_orthogonal_signals_do_not_suppress_fallback():
    # A Background ("Choose a Background") is archetype-agnostic and conditional
    # self-protection is a resilient-beater tell — neither is a non-voltron PLAN, so
    # a commander whose ONLY signal is one of these reads as the vanilla voltron
    # body it is (Wilson is a trampling bear to suit up). A REAL engine still
    # suppresses the fallback (Mizzix is a spellslinger, not a suit-up body). Real
    # snapshot cards.
    assert "voltron_matters" in _keys_real("Wilson, Refined Grizzly")
    assert "voltron_matters" not in _keys_real("Mizzix of the Izmagnus")


def test_sea_monster_tribal_group_covers_all_four_types():
    # The sea-monster types (Kraken/Leviathan/Octopus/Serpent) share one tribal
    # identity — no card rewards any member alone (Quest for Ula's Temple / Whelming
    # Wave / Slinn Voda always name all four). So an Octopus commander's tribe spec
    # must cover the whole group + the group-naming payoffs.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    octo_sig = Signal(
        key="type_matters", scope="you", subject="Octopus", text="", source=""
    )
    sp = spec_for(octo_sig)

    def covers(card):
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    # other group members by type-line (no oracle tribal text)
    tromokratis = {
        "name": "Tromokratis",
        "type_line": "Legendary Creature — Kraken",
        "oracle_text": (
            "Tromokratis has hexproof unless it's attacking or blocking.\n"
            "Tromokratis can't be blocked unless all creatures defending player "
            "controls block it."
        ),
    }
    stormtide = {
        "name": "Stormtide Leviathan",
        "type_line": "Creature — Leviathan",
        "oracle_text": (
            "Islandwalk\nAll lands are Islands in addition to their other types.\n"
            "Creatures without flying or islandwalk can't attack."
        ),
    }
    whelming = {
        "name": "Whelming Wave",
        "type_line": "Sorcery",
        "oracle_text": (
            "Return all creatures to their owners' hands except for Krakens, "
            "Leviathans, Octopuses, and Serpents."
        ),
    }
    assert covers(tromokratis)  # Kraken body, no oracle tribal text
    assert covers(stormtide)  # Leviathan body
    assert covers(whelming)  # group-naming payoff (Sorcery, no creature type)
    # Over-fire guard: a STANDALONE tribe (Goblin) must NOT pick up a sea monster —
    # the group only applies to the four no-solo-identity types.
    gob = spec_for(
        Signal(key="type_matters", scope="you", subject="Goblin", text="", source="")
    )
    assert gob.serve.matches(tromokratis) is False
    assert not any(
        (ex.serve or serve_from_dict(ex.search)).matches(tromokratis)
        for ex in gob.extras
    )


def test_kazuul_defending_player_opens_goad_and_force_attack_serves():
    # Goad cards are top-synergy for commanders that reward opponents attacking —
    # the extractor firing (the _GOAD_REWARD_REF defending-player marker) is pinned
    # by test_crosswalk's goad_makers battery; here the lane's force-attack
    # sub-avenue must cover the force-ALL-attack cards (which carry no "goad"
    # keyword). Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    diplomats = {
        "name": "Goblin Diplomats",
        "type_line": "Creature — Goblin",
        "oracle_text": "{T}: Each creature attacks this turn if able.",
    }
    warstoll = {
        "name": "War's Toll",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever an opponent taps a land for mana, tap all lands that player "
            "controls.\n"
            "If a creature an opponent controls attacks, all creatures that opponent "
            "controls attack if able."
        ),
    }
    assert lane_covers(diplomats, "goad_makers", "opponents") is True
    assert lane_covers(warstoll, "goad_makers", "opponents") is True
    # Over-fire guard: a SELF forced-attack drawback (Juggernaut) is an aggressive
    # beater, not a force-the-table effect.
    juggernaut = {
        "name": "Juggernaut",
        "type_line": "Artifact Creature — Juggernaut",
        "oracle_text": (
            "This creature attacks each combat if able.\n"
            "This creature can't be blocked by Walls."
        ),
    }
    assert lane_covers(juggernaut, "goad_makers", "opponents") is False


def test_low_power_matters_opens_and_serves():
    # Subira rewards "creature you control with power 2 or less"; the lane surfaces
    # the small-creature payoffs (Raid Bombardment, Delney, Arabella). Anchored on
    # "you control with power N or less" so removal and the vanilla power<=2 pool
    # stay out. Real snapshot card (the structural PtComparison read is also pinned
    # by test_crosswalk).
    assert ("low_power_matters", "you") in _ks_real("Subira, Tulzidi Caravanner")

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    raid = {
        "name": "Raid Bombardment",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever a creature you control with power 2 or less attacks, this "
            "enchantment deals 1 damage to the player or planeswalker that creature "
            "is attacking."
        ),
    }
    assert lane_covers(raid, "low_power_matters") is True
    # Over-fire guard 1: removal targeting a small creature is not a payoff for YOUR
    # small creatures ("target", not "you control").
    removal = {
        "name": "Disfigure-like",
        "type_line": "Instant",
        "oracle_text": "Destroy target creature with power 2 or less.",
    }
    assert lane_covers(removal, "low_power_matters") is False
    # Over-fire guard 2: a vanilla small body is not on-theme fodder.
    bears = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert lane_covers(bears, "low_power_matters") is False


def test_gowide_package_creature_scoped_and_count_scaler_opens_it():
    # A creature-count-scaling commander is go-wide, so tokens_matter's go-wide
    # package serves MASS creature-token makers (create 2+/X) and team protection.
    # CREATURE-scoped: a Treasure/Clue maker (non-creature tokens) does NOT widen
    # the board and stays out. The extractor firing is pinned by
    # test_signal_keys_real_cards (tokens_matter) + test_crosswalk.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card):
        sp = spec_for(
            Signal(key="tokens_matter", scope="you", subject="", text="", source="")
        )
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    battle_screech = {
        "name": "Battle Screech",
        "type_line": "Sorcery",
        "oracle_text": "Create two 1/1 white Bird creature tokens with flying.",
    }
    rootborn = {
        "name": "Rootborn Defenses",
        "type_line": "Instant",
        "oracle_text": (
            "Populate. Creatures you control gain indestructible until end of turn."
        ),
    }
    assert lane_covers(battle_screech) is True  # mass creature-token maker
    assert lane_covers(rootborn) is True  # team protection
    # Creature-scoping guard: a Treasure maker makes NON-creature tokens — it
    # doesn't go wide and must NOT be in the go-wide package.
    tithe = {
        "name": "Smothering Tithe",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever an opponent draws a card, that player may pay {2}. If they don't, "
            "you create a Treasure token."
        ),
    }
    assert lane_covers(tithe) is False


def test_tokens_matter_serves_mobilize_swarm():
    # A Mobilize commander (Zurgo) opens tokens_matter, but the other Mobilize cards make
    # their Warrior tokens in stripped reminder text, so the serve missed them. Credit the
    # mobilize keyword (a bounded Warrior-swarm archetype) — Zurgo covers its package.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    packbeasts = {
        "name": "Dalkovan Packbeasts",
        "type_line": "Creature — Ox",
        "keywords": ["Mobilize", "Vigilance"],
        "oracle_text": (
            "Vigilance\n"
            "Mobilize 3 (Whenever this creature attacks, create three tapped and "
            "attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning "
            "of the next end step.)"
        ),
    }
    assert lane_covers(packbeasts, "tokens_matter", "you") is True
    # Over-fire guard: a plain creature with no token-making and no mobilize keyword is
    # not credited.
    bear = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "keywords": [],
        "oracle_text": "",
    }
    assert lane_covers(bear, "tokens_matter", "you") is False


def test_cost_reduction_serves_stacking_reducers():
    # A cost-reduction commander (Stenn makes its chosen type cost {1} less) wants
    # to STACK more category reducers to go off. The reducer sub-avenue serves
    # "<your/type> spells cost {N} less" (Cloud Key, Etherium Sculptor), excluding
    # the self-only "this spell costs {X} less" (Ghalta). The extractor firing is
    # pinned by test_signal_keys_real_cards (cost_reduction). Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    etherium = {
        "name": "Etherium Sculptor",
        "type_line": "Artifact Creature — Vedalken Artificer",
        "oracle_text": "Artifact spells you cast cost {1} less to cast.",
    }
    assert lane_covers(etherium, "cost_reduction", "you") is True
    # Over-fire guard (isolates the reducer extra): a SELF-only "this spell costs
    # {2} less" is not a stacking reducer — the plural "spells" anchor keeps it out.
    self_only = {
        "name": "Self Discounter",
        "type_line": "Creature — Beast",
        "oracle_text": "This spell costs {2} less to cast.",
    }
    assert lane_covers(self_only, "cost_reduction", "you") is False


def test_token_maker_serves_token_aristocrats_drain():
    # A token-flood commander (Endrek Sahr makes Thrulls) wants token-aristocrats
    # drain that fires on token CREATION (Mirkwood Bats) — it triggers just by going
    # wide, no sac outlet needed. Token-specific, so the generic "whenever a
    # creature dies" Blood Artist (served by the death lanes) does NOT match this
    # sub-avenue. The extractor firing is pinned by test_signal_keys_real_cards
    # (token_maker); the spec here carries the captured tribal subject.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    tm_sig = Signal(
        key="token_maker", scope="you", subject="Thrull", text="", source=""
    )
    sp = spec_for(tm_sig)

    def covers(card):
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    mirkwood = {
        "name": "Mirkwood Bats",
        "type_line": "Creature — Bat",
        "oracle_text": (
            "Flying\n"
            "Whenever you create or sacrifice a token, each opponent loses 1 life."
        ),
    }
    assert covers(mirkwood) is True
    # Over-fire guard: generic "whenever a creature dies" drain is NOT
    # token-specific — it belongs to the death/aristocrats lanes.
    blood_artist = {
        "name": "Blood Artist",
        "type_line": "Creature — Vampire",
        "oracle_text": (
            "Whenever this creature or another creature dies, target player loses 1 "
            "life and you gain 1 life."
        ),
    }
    assert covers(blood_artist) is False


def test_role_token_makers_open_enchantments_matter():
    # Role tokens are Aura ENCHANTMENTS (CR 303.7 / 111.10j), so a commander that
    # makes them (Gylwain) is an enchantment commander — it wants enchantment-count
    # payoffs (Sanctum Weaver) and Aura payoffs. Proven over the real record.
    assert ("enchantments_matter", "you") in _ks_real("Gylwain, Casting Director")


def test_celebration_archetype_opens_and_serves():
    # Celebration (WOE ability word) keys on the exact phrase "two or more nonland
    # permanents entered the battlefield under your control this turn". The
    # extractor firing (Ash, Party Crasher) is pinned by test_crosswalk's
    # celebration mirror test; here the lane serve must credit the other
    # Celebration payoffs and exclude generic go-wide payoffs.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    grand_ball_guest = {
        "name": "Grand Ball Guest",
        "type_line": "Creature — Human Peasant",
        "oracle_text": (
            "Celebration — This creature gets +1/+1 and has trample as long as two "
            "or more nonland permanents entered the battlefield under your control "
            "this turn."
        ),
    }
    assert lane_covers(grand_ball_guest, "celebration_matters") is True
    # Over-fire guard: a generic go-wide payoff that doesn't carry the Celebration
    # phrase is not a Celebration card.
    impact = {
        "name": "Impact Tremors",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever a creature you control enters, Impact Tremors deals 1 damage "
            "to each opponent."
        ),
    }
    assert lane_covers(impact, "celebration_matters") is False


def test_lands_matter_serves_creature_pump_by_basic():
    # A lands-matter commander whose own P/T scales with land count (Molimo) wants
    # the creature pump that scales the SAME way — "+N/+N for each Forest you
    # control" (Blanchwood Armor, Primal Bellow). The serve already takes "for each
    # LAND you control"; the per-basic-subtype form was the gap. The extractor
    # firing is pinned by test_signal_keys_real_cards (lands_matter).
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    primal_bellow = {
        "name": "Primal Bellow",
        "type_line": "Instant",
        "oracle_text": (
            "Target creature gets +1/+1 until end of turn for each Forest you control."
        ),
    }
    assert lane_covers(primal_bellow, "lands_matter") is True
    # Over-fire guard: pump that scales off your OPPONENTS' basics is not your
    # lands-matter payoff.
    crusading_knight = {
        "name": "Crusading Knight",
        "type_line": "Creature — Human Knight",
        "oracle_text": (
            "Protection from black\n"
            "Crusading Knight gets +1/+1 for each Swamp your opponents control."
        ),
    }
    assert lane_covers(crusading_knight, "lands_matter") is False


def test_tapped_creatures_matter_opens_and_serves():
    # tapped_matters: Masako's dropped "tapped creatures you control" grant is
    # recovered structurally (pinned by test_crosswalk's tapped_matters tests); the
    # serve pool stays oracle-defined (the hand spec). Distinct from
    # tap_untap_matters (becomes-tapped triggers) and convoke (taps UNtapped
    # creatures as a cost).
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    throne = {
        "name": "Throne of the God-Pharaoh",
        "type_line": "Legendary Artifact",
        "oracle_text": (
            "At the beginning of your end step, each opponent loses life equal to "
            "the number of tapped creatures you control."
        ),
    }
    assert lane_covers(throne, "tapped_matters") is True
    # Over-fire guard: a convoke / tap-as-cost card taps UNtapped creatures — the
    # word boundary on \btapped must keep it out of the lane.
    devout = {
        "name": "Devout Invocation",
        "type_line": "Sorcery",
        "oracle_text": (
            "Tap any number of untapped creatures you control. Create a 4/4 white "
            "Angel creature token for each creature tapped this way."
        ),
    }
    assert lane_covers(devout, "tapped_matters") is False


def test_tapped_threshold_and_count_open_and_serve():
    # The "if you control two or more tapped creatures, <payoff>" THRESHOLD (Sami
    # and the Edge of Eternities tap cluster) and the "for each tapped creature you
    # control" COUNT form are tapped-matters engines. The threshold-gate structural
    # read is pinned by test_crosswalk (Sami); here the serve must learn the
    # threshold + count so Sami covers its cluster. Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    dawnstrike = {
        "name": "Dawnstrike Vanguard",
        "type_line": "Creature — Human Knight",
        "oracle_text": (
            "Lifelink\n"
            "At the beginning of your end step, if you control two or more tapped "
            "creatures, put a +1/+1 counter on each creature you control other than "
            "this creature."
        ),
    }
    assert lane_covers(dawnstrike, "tapped_matters") is True


def test_your_graveyard_scope_not_stolen_by_incidental_opponent_mention():
    # A self-graveyard engine that merely MENTIONS opponents elsewhere (Araumi's encore
    # tokens "attack that opponent"; the cost counts "the number of opponents you have")
    # cares about YOUR graveyard — it must open graveyard_matters/you so self-mill
    # enablers (scoped you) serve, not be mis-scoped opponents by the "opponent"-
    # anywhere rule. Real card, full oracle.
    # ADR-0027 v29: graveyard_matters migrated to the IR — assert via the hybrid path
    # (the byte mirror's clause-resolved scope honors the "your graveyard"-first rule).
    assert ("graveyard_matters", "you") in _ks_real("Araumi of the Dead Tide")
    # Over-fire guard: a pure opponents'-graveyard-hate card (no "your graveyard", no
    # self-reference) stays opponents-scoped and does NOT acquire a "you" avenue — the
    # residual auto-scope is untouched by the fix.
    assert ("graveyard_matters", "opponents") in _ks_real("Leyline of the Void")
    assert ("graveyard_matters", "you") not in _ks_real("Leyline of the Void")


def test_multi_tribe_list_anthem_captures_every_named_type():
    # A menagerie anthem ("Other Spiders, Boars, ..., and Wolves you control get +1/+1")
    # lists many subtypes in one comma run — the multi-tribe head form ("creatures
    # that's a X, a Y") doesn't match it, and the single-tribe pattern grabbed only the
    # last type. Capture EVERY named subtype so each tribe's payoffs surface. Real card.
    # ADR-0027: type_matters migrated → hybrid path.
    subs = {
        subj
        for (key, scope, subj) in _ksub_real("Spider-Ham, Peter Porker")
        if key == "type_matters"
    }
    for t in ("Frog", "Squirrel", "Rabbit", "Raccoon", "Cat", "Bird"):
        assert t in subs, t
    # Over-fire guard: a plain anthem names no subtype, so no spurious tribe.
    glory_subs = {
        subj
        for (key, scope, subj) in _ksub_real("Glorious Anthem")
        if key == "type_matters"
    }
    assert glory_subs == set()


def test_divinity_indestructible_counter_wants_proliferate():
    # A permanent that "enters with a divinity/indestructible counter" (the Myojin
    # cycle, Arwen) has exactly ONE beneficial counter that gates indestructibility or
    # fuels a remove-a-counter ability — proliferate multiplies it. Unlike COUNTDOWN
    # counters (slumber, egg) you want to REMOVE, divinity/indestructible are always
    # good to multiply, so the lane is precise. Real card, full oracle.
    # ADR-0027: proliferate_matters migrated to the Card IR; the divinity /
    # indestructible enters-with cycle now fires from the _IR_KEPT_DETECTORS
    # mirror, so assert the hybrid path.
    assert "proliferate_matters" in _keys_real("Myojin of Cleansing Fire")
    # Over-fire guard: a COUNTDOWN counter you remove to wake a creature (slumber) is
    # anti-proliferate — you want fewer, not more.
    assert "proliferate_matters" not in _keys_real("Arixmethes, Slumbering Isle")


def test_ox_tribe_resolves_despite_two_letters_and_irregular_plural():
    # "Ox" is the only real two-letter creature subtype, so a len>=3 vocab-harvest
    # filter would drop it and "Oxen" (irregular plural) must singularize to it. An
    # Ox tribal lord (Bruse Tarl: "Oxen you control have double strike") must open
    # type_matters:Ox so its Oxen (Holy Cow, Makindi Ox) surface. Real snapshot card.
    assert ("type_matters", "you", "Ox") in _ksub_real("Bruse Tarl, Roving Rancher")


def test_discard_matters_payoff_opens_opponent_discard():
    # The opponent_discard lane's serve must credit the forced-discard package —
    # forcers (Bottomless Pit) and payoffs (Megrim) — while a SELF-discard loot
    # stays out. (The extractor side was re-adjudicated: test_crosswalk pins that
    # Tinybones, Trinket Thief's "an opponent discarded" END-STEP payoff does NOT
    # fire opponent_discard on the crosswalk path.)
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    megrim = {
        "name": "Megrim",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever an opponent discards a card, Megrim deals 2 damage to that player."
        ),
    }
    bottomless = {
        "name": "Bottomless Pit",
        "type_line": "Enchantment",
        "oracle_text": (
            "At the beginning of each player's upkeep, that player discards a card at "
            "random."
        ),
    }
    assert lane_covers(megrim, "opponent_discard", "opponents") is True
    assert lane_covers(bottomless, "opponent_discard", "opponents") is True


def test_symmetric_cast_punisher_is_not_opponent_cast_matters():
    # ADR-0027 #24k — opponent_cast_matters is the genuinely OPPONENT-scoped "whenever an
    # opponent casts" punisher/tax, read STRUCTURALLY off a cast_spell trigger
    # scope=='opp' (real IR, mirror DELETED). A SYMMETRIC "whenever a PLAYER casts"
    # punisher (Eidolon of the Great Revel, Ruric Thar "deals 6 damage to that player")
    # is NOT opponent-only — CR 102.1 "a player" INCLUDES its controller, so it punishes
    # EVERYONE (you too), a genuine NON-member of an opponent-scoped lane (CR 102.2/
    # 102.3). The deleted regex mirror over-swept these; they must no longer fire.
    assert "opponent_cast_matters" not in _keys_real("Eidolon of the Great Revel")
    assert "opponent_cast_matters" not in _keys_real("Ruric Thar, the Unbowed")
    # A GENUINELY opponent-scoped "whenever an opponent casts" punisher DOES fire
    # (phase scopes the direct trigger scope='opp' — Lavinia). CR 102.2.
    assert "opponent_cast_matters" in _keys_real("Lavinia, Azorius Renegade")
    # The QUOTED/granted/emblem forms phase folds into a non-trigger Effect are recovered
    # by supplement._recover_opponent_cast_scope (synth cast_spell scope='opp').
    assert "opponent_cast_matters" in _keys_real("Hunting Grounds")
    assert "opponent_cast_matters" in _keys_real("Jace, Unraveler of Secrets")
    assert "opponent_cast_matters" in _keys_real("Thundering Mightmare")


def test_tribe_damage_trigger_reads_recovered_source():
    # ADR-0027 #24k — tribe_damage_trigger reads the combat-/deals-damage trigger SOURCE
    # structurally (mirror DELETED). supplement._recover_tribe_damage_source refills the
    # source phase DROPS when the combat-damage trigger is QUOTED in a loyalty / emblem /
    # delayed ability; the arm broadens to read an AnyOf-outlaw source + a deals_damage
    # tribal source. Real IR.
    assert "tribe_damage_trigger" in _keys_real("Vraska, Golgari Queen")  # emblem
    assert "tribe_damage_trigger" in _keys_real(
        "Olivia, Opulent Outlaw"
    )  # AnyOf outlaw
    assert "tribe_damage_trigger" in _keys_real("Francisco, Fowl Marauder")  # deals_dmg
    # NON-members: a single-source "a commander you control" spread (Kediss) and a non-
    # creature "a source you control" payoff (Quest for Pure Flame) are NOT a go-wide
    # creature population, so the deleted regex's over-sweep of them drops. CR 510.1.
    assert "tribe_damage_trigger" not in _keys_real("Kediss, Emberclaw Familiar")
    assert "tribe_damage_trigger" not in _keys_real("Quest for Pure Flame")


def test_topdeck_stack_reads_recovered_self_controller():
    # ADR-0027 #24k — topdeck_stack reads a self top-stack STRUCTURALLY:
    # supplement._recover_topdeck_stack_self stamps subject=Filter(Card, you) on a
    # subject-None `topdeck_stack` Effect whose clause names "on top of your library", so
    # the controller==you arm fires (the controller phase DROPPED). Real IR — the 5
    # mirror-residue self-curators plus the broader self-top-stack set the narrow mirror
    # missed (graveyard→top recursion, look-then-stack). CR 401.
    assert "topdeck_stack" in _keys_real("Ancestral Knowledge")
    assert "topdeck_stack" in _keys_real("Orcish Librarian")
    assert "topdeck_stack" in _keys_real("Scroll Rack")
    assert "topdeck_stack" in _keys_real("Mortuary")
    assert "topdeck_stack" in _keys_real("Thassa's Oracle")
    # PARTIAL — a self-curation phase FOLDED to topdeck_select-to-hand with NO
    # topdeck_stack Effect (Diabolic Vision) is not structurally recoverable; the kept
    # mirror still serves it via the hybrid path.
    assert "topdeck_stack" in _keys_real("Diabolic Vision")


def test_opponent_reveal_mill_served_by_graveyard_opponents():
    # Old Dimir mill ("reveals cards from the top of their library until N lands, then
    # puts them into their graveyard" — Mind Funeral, Mind Grind) never uses the word
    # "mills", so the opponents'-graveyard serve (keyed on "mills") missed it though a
    # mill commander (Mirko Vosk, who mills the same way) opens the lane. Real cards.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    mind_funeral = {
        "name": "Mind Funeral",
        "type_line": "Sorcery",
        "oracle_text": (
            "Target opponent reveals cards from the top of their library until four "
            "land cards are revealed. That player puts all cards revealed this way "
            "into their graveyard."
        ),
    }
    assert lane_covers(mind_funeral, "graveyard_matters", "opponents") is True
    # Over-fire guard: a SELF-mill card reveals from YOUR library into YOUR graveyard —
    # the "their/that player's library" anchor must keep it out of the opponents lane.
    avenging = {
        "name": "Avenging Druid",
        "type_line": "Creature — Human Druid",
        "oracle_text": (
            "Whenever this creature deals damage to an opponent, you may reveal cards "
            "from the top of your library until you reveal a land card, put that card "
            "onto the battlefield, then put the rest into your graveyard."
        ),
    }
    assert lane_covers(avenging, "graveyard_matters", "opponents") is False


def test_land_sacrifice_matters_opens_and_serves():
    # Gitrog/Titania/Slogurk draw/grow when lands hit the graveyard, so repeatable
    # "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb) are their core engine.
    # sacrifice_outlets deliberately EXCLUDES "sacrifice a land" (fetchland guard), so
    # this land-sac archetype is its own lane. Real cards, full oracle.
    # ADR-0027 #24b: land_sacrifice_matters now reads STRUCTURE off the REAL IR — the
    # leaves/dies Trigger whose subject is a Land you control (Gitrog's "Whenever one
    # or more land cards are put into your graveyard") + the supplement-recovered
    # Land-subject sacrifice Effect (the "unless you sacrifice a land" cost). Asserted
    # over the real projected IR via ``test_signals`` (no synthetic-IR drift); the
    # serve-spec checks (lane_covers) are producer-independent.
    assert "land_sacrifice_matters" in {
        s.key for s in test_signals("The Gitrog Monster")
    }

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    zuran_orb = {
        "name": "Zuran Orb",
        "type_line": "Artifact",
        "oracle_text": "Sacrifice a land: You gain 2 life.",
    }
    assert lane_covers(zuran_orb, "land_sacrifice_matters") is True
    # Over-fire guard: a CREATURE-sacrifice outlet is aristocrats, not land sacrifice.
    viscera = {
        "name": "Viscera Seer",
        "type_line": "Creature — Vampire Wizard",
        "oracle_text": "Sacrifice a creature: Scry 1.",
    }
    assert lane_covers(viscera, "land_sacrifice_matters") is False


def test_land_sacrifice_matters_includes_symmetric_each_scope():
    # ADR-0027 #24f: a SYMMETRIC "each player sacrifices N lands" outlet makes YOU
    # sacrifice a land — your land hits your graveyard AS A SACRIFICE (CR 701.21), so
    # it FUELS the land-to-graveyard / "you sacrifice a land" payoffs (Gitrog, Titania,
    # Lord Windgrace). phase tags these structurally-identical wraths inconsistently
    # (`any` for Death Cloud, `each` for Destructive Force); the outlet arm reads the
    # land-only sacrifice Effect regardless of scope (gate is `scope != "opp"`), so the
    # twins are admitted consistently. Real cards, full oracle, real projected IR.
    # _matters sweep (ADR-0034): the card PERFORMS the land sac, so it is the MAKER
    # arm — land_sacrifice_makers, not the leaves/dies payoff land_sacrifice_matters.
    assert "land_sacrifice_makers" in {s.key for s in test_signals("Destructive Force")}
    assert "land_sacrifice_makers" in {s.key for s in test_signals("Tectonic Break")}
    # Boundary: an OPPONENT-ONLY land sac (scope=opp) never touches your lands, so it
    # is NOT a member — "Each opponent sacrifices a land of their choice."
    assert "land_sacrifice_makers" not in {
        s.key for s in test_signals("Yawning Fissure")
    }


def test_gain_control_serve_catches_that_them_those():
    # A theft commander (Zidane, Sauron the Lidless Eye) wants every steal payoff, but
    # the serve's pronoun list missed "gain control of that/them/those" — Treasure
    # Nabber ("that artifact"), Insurrection ("them") classify as gain_control yet
    # weren't served. Real cards, full oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    treasure_nabber = {
        "name": "Treasure Nabber",
        "type_line": "Creature — Goblin Rogue",
        "oracle_text": (
            "Whenever an opponent taps an artifact for mana, gain control of that "
            "artifact until the end of your next turn."
        ),
    }
    assert lane_covers(treasure_nabber, "gain_control") is True
    # Over-fire guard: DONATING control to an opponent is the opposite of theft and is
    # vetoed by serve_not.
    donate = {
        "name": "Generic Donate",
        "type_line": "Sorcery",
        "oracle_text": "Target opponent gains control of that creature.",
    }
    assert lane_covers(donate, "gain_control") is False


def test_debuff_serves_opponent_mass_shrink():
    # A -1/-1 debuff commander (Silumgar, the Drifting Death — "creatures defending
    # player controls get -1/-1") wants mass-shrink effects that set OPPONENTS'
    # creatures to a tiny base P/T (Mass Diminish, Flatline, Polymorphist's Jest).
    # Those classify as base_pt_set, not the -N/-N debuff form, so the serve missed
    # them. Real cards, full oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    mass_diminish = {
        "name": "Mass Diminish",
        "type_line": "Sorcery",
        "oracle_text": (
            "Until your next turn, creatures target player controls have base power "
            "and toughness 1/1."
        ),
    }
    assert lane_covers(mass_diminish, "debuff_makers", "any") is True
    # Over-fire guard: setting YOUR creatures' base P/T (Mirror Entity pump) is NOT a
    # debuff — the opponent-controls anchor must keep it out.
    mirror = {
        "name": "Mirror Entity",
        "type_line": "Creature — Shapeshifter",
        "oracle_text": (
            "Changeling\n"
            "{X}: Until end of turn, creatures you control have base power and "
            "toughness X/X and gain all creature types."
        ),
    }
    assert lane_covers(mirror, "debuff_makers", "any") is False


def test_lure_commander_cross_opens_blocked_matters():
    # Lure (force blocks) and blocked_matters (punish the blocker) are one archetype:
    # a commander that MUST be blocked / lures (Madame Vastra) wants the punish-when-
    # blocked payoffs (Engulfing Slagwurm, Tolarian Entrancer). Cross-open lure ->
    # blocked (one-directional — a bare "when blocked" trigger isn't a lure deck). Real
    # card, full oracle. ADR-0027: lure_makers migrated to the IR, so route through the
    # hybrid with the structural `lure` Effect; the regex path re-supplies the
    # blocked_matters cross-open from the byte-identical _LURE_MATTERS_PLAN_MIRROR
    # matching Vastra's "must be blocked if able".
    keys = _keys_real("Madame Vastra")
    assert "lure_makers" in keys
    assert "blocked_matters" in keys


def test_significant_bleed_opens_lifegain_but_negligible_rider_does_not():
    # A commander with SIGNIFICANT repeated self-life-loss (Deadpool loses 3 each upkeep;
    # cumulative-upkeep payers; "you lose life equal to" sac engines) bleeds out without
    # sustain, so it wants lifegain. Gated to meaningful bleed — a negligible "lose 1
    # life" rider on an attack/sac/value trigger won't deck you and must NOT open it
    # (that was the 79-commander over-broad lifeloss->lifegain trap). Real cards.
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the self-bleed-wants-
    # sustain block (ARM B) rides the byte-identical kept-mirror, served from the hybrid.
    assert "lifegain_matters" in _keys_real("Deadpool, Trading Card")
    # A passive, frequent, unavoidable death-triggered draw-and-bleed engine (Kothophed
    # loses 1 life per opponent permanent dying — fast with board wipes) also bleeds you
    # out, so it wants lifegain even though each event is only 1 life.
    assert "lifegain_matters" in _keys_real("Kothophed, Soul Hoarder")
    # Over-fire guard: losing 1 life per attack is a negligible rider, not a bleed engine.
    assert "lifegain_matters" not in _keys_real("Azula, On the Hunt")


def test_variable_self_bleed_opens_lifegain_sustain():
    # The significant-bleed -> lifegain cross-open fired on the fixed "you lose life
    # equal to" sac engines but missed the equivalent VARIABLE phrasings. Asmodeus
    # draws its whole library and "you lose that much life"; Be'lakor is the classic
    # "draw X / lose X" engine. Both are deck-defining scaling self-bleed that wants
    # lifegain sustain to not deck the controller. Real oracle, full text.
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the variable self-bleed
    # sustain (ARM B) rides the byte-identical kept-mirror, served from the hybrid.
    assert "lifegain_matters" in _keys_real("Asmodeus the Archfiend")
    assert "lifegain_matters" in _keys_real("Be'lakor, the Dark Master")
    # Boundary guard: OPTIONAL "you may pay life equal to" (Madame Null) is controlled,
    # affordable life payment, not an unavoidable bleed — it stays out (the over-broad
    # lifeloss trap). Forced "you lose …" opens; optional "you may pay …" does not.
    assert "lifegain_matters" not in _keys_real("Madame Null, Power Broker")


def test_variable_self_lifeloss_opens_life_as_resource_lane():
    # The lifeloss "you" lane (life-as-resource: pay/lose life on demand). Both fire
    # from the structural `lose_life` ("you lose X/that much life"). _matters sweep
    # (ADR-0034): a self life-loss DOER fires the MAKER arm lifeloss_makers (the card
    # performs the life loss); phase emits the lose_life Effect, the IR mirrors that
    # node (the supplement does not synthesize a bare-clause lose_life out of a trimmed
    # activated-ability raw).
    assert ("lifeloss_makers", "you") in {
        (s.key, s.scope) for s in test_signals("Asmodeus the Archfiend")
    }
    assert ("lifeloss_makers", "you") in {
        (s.key, s.scope) for s in test_signals("Be'lakor, the Dark Master")
    }
    # Over-fire guard: a "Ward—Pay life equal to" cost (Raubahn) is the OPPONENT paying,
    # not self life-loss — phase emits no lose_life, so neither lane fires on the IR.
    assert "lifeloss_makers" not in {
        s.key for s in test_signals("Raubahn, Bull of Ala Mhigo")
    }


def test_attacking_team_double_strike_opens_combat_damage():
    # A commander that grants double strike to your ATTACKING team (Raphael) makes them
    # deal combat damage to players twice — it wants the "whenever creatures you control
    # deal combat damage to a player" payoffs. Tight to "attacking creatures you control
    # have double strike" so go-wide/tribal/conditional double-strike granters (Kwende,
    # Jetmir) — which aren't combat-damage-payoff decks — stay out. Real cards.
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR, so the double-strike-
    # grant tail is served from the hybrid (IR) path via a LOW-confidence inline mirror.
    rsigs = {(s.key, s.scope) for s in test_signals("Raphael, the Nightwatcher")}
    assert ("combat_damage_to_opp", "opponents") in rsigs
    # Over-fire guard: a conditional/non-attacking double-strike grant is not this lane.
    ksigs = {(s.key, s.scope) for s in test_signals("Kwende, Pride of Femeref")}
    assert ("combat_damage_to_opp", "opponents") not in ksigs


def test_remove_counter_to_activate_opens_proliferate():
    # A commander that SPENDS a counter as an activation cost (remove a counter from a
    # permanent: <effect>) wants more counters — i.e. proliferate. Keyed on the MECHANIC
    # (colon = activation cost), not a counter-name list, so it future-proofs for new
    # counter types. COUNTDOWN counters (slumber/egg) use "may remove"/upkeep-remove with
    # NO colon-activation, so they're excluded by construction. Real cards, full oracle.
    # ADR-0027: proliferate_matters migrated to the Card IR; the remove-a-counter-
    # as-cost producer now fires from the LOW-confidence _PROLIFERATE_REMOVE_COST_RE
    # mirror arm, so assert the hybrid path.
    assert "proliferate_matters" in _keys_real("Tayam, Luminous Enigma")
    # Over-fire guard: a COUNTDOWN counter removed in upkeep (no colon-activation) — you
    # want FEWER, so it must NOT open proliferate.
    assert "proliferate_matters" not in _keys_real("Arixmethes, Slumbering Isle")


def test_keyword_soup_commander_opens_and_serves_multi_keyword_creatures():
    # A keyword-soup commander (Odric, Lunarch Marshal) SHARES many evergreen
    # keywords across the team, so it wants creatures stacked with keywords. Open on
    # >=5 distinct evergreen keywords in a team-grant context; serve creatures with
    # >=3 evergreen keywords. Real snapshot card.
    assert "keyword_soup_makers" in _keys_real("Odric, Lunarch Marshal")

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    aerial = {
        "name": "Aerial Responder",
        "type_line": "Creature — Dwarf Soldier",
        "oracle_text": "Flying, vigilance, lifelink",
        "keywords": ["Flying", "Lifelink", "Vigilance"],
    }
    assert lane_covers(aerial, "keyword_soup_makers") is True
    # Over-fire guard: a one-keyword creature is not a multi-keyword body.
    sprite = {
        "name": "Scryb Sprite",
        "type_line": "Creature — Faerie",
        "oracle_text": "Flying",
        "keywords": ["Flying"],
    }
    assert lane_covers(sprite, "keyword_soup_makers") is False


def test_combat_damage_serves_double_strike_granters():
    # A combat-damage-to-player commander wants double-strike GRANTERS — granting double
    # strike doubles the combat damage (and the combat-damage triggers) pushed through,
    # the same amplifier role as Gratuitous Violence. Duelist's Heritage grants it each
    # combat. Real cards, full oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    duelist = {
        "name": "Duelist's Heritage",
        "type_line": "Enchantment",
        "oracle_text": (
            "At the beginning of combat on your turn, choose target attacking "
            "creature. It gains double strike until end of turn."
        ),
    }
    assert lane_covers(duelist, "combat_damage_to_opp", "opponents") is True
    # Over-fire guard: a bare vanilla double-striker (the keyword on its own body, no
    # grant) is just a body, not an amplifier — it must NOT match the amplifier extra.
    vanilla_ds = {
        "name": "Vanilla Double Striker",
        "type_line": "Creature — Human Warrior",
        "oracle_text": "Double strike",
        "keywords": ["Double strike"],
    }
    assert lane_covers(vanilla_ds, "combat_damage_to_opp", "opponents") is False
    # Whole-table amplifier (Kediss): "deals that much damage to each other opponent"
    # copies your combat damage onto every opponent — also an amplifier. Real oracle.
    kediss = {
        "name": "Kediss, Emberclaw Familiar",
        "type_line": "Legendary Creature — Elemental Lizard",
        "oracle_text": (
            "Whenever a commander you control deals combat damage to an opponent, it "
            "deals that much damage to each other opponent.\n"
            "Partner (You can have two commanders if both have partner.)"
        ),
    }
    assert lane_covers(kediss, "combat_damage_to_opp", "opponents") is True
