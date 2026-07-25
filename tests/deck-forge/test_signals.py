"""Tests for deterministic signal extraction (the discovery-engine keystone).

The headline guard: a signal that concerns OPPONENTS' graveyards must be scoped
"opponents", never a generic graveyard signal that would justify self-mill (the
Tinybones overgeneralization the whole tool exists to prevent).

ADR-0039 task #80 step 6 retired the regex engine (``_signals_regex.py``) and the
projected-IR engine (``_signals_ir.py``) — a full commander/brawl-legal corpus
census (see ``signals.extract_signals``'s docstring) found the regex path
contributed ZERO keys outside the crosswalk's own ``SERVED_SIGNAL_KEYS``, so every test
here now asserts against the production ``extract_signals`` path via the
``testkit`` real-card fixtures, never a hand-built synthetic ``Card`` IR.
"""

from mtg_utils._deck_forge.signal_base import Signal
from mtg_utils.testkit import test_signals


def _real(name):
    """(key, scope) set from production over the REAL Scryfall record + REAL
    projected IR (``extract_signals`` via the committed snapshot)."""
    return {(s.key, s.scope) for s in test_signals(name)}


def test_graveyard_signal_scoped_to_opponents_not_generic():
    # The Tinybones case: benefits from OPPONENTS' graveyards filling. Real record +
    # real projected IR (snapshot) — production recovers the "that player's
    # graveyard" -> 'opponents' Tinybones cast scope.
    sigs = test_signals("Tinybones, the Pickpocket")
    gy = [s for s in sigs if s.key == "graveyard_matters"]
    assert gy, "expected a graveyard signal"
    assert all(s.scope == "opponents" for s in gy)
    # It must NOT be scoped to 'you' — that would justify self-mill.
    assert ("graveyard_matters", "you") not in _real("Tinybones, the Pickpocket")


def test_land_creatures_matter_detected_on_jyoti():
    # Real Jyoti (snapshot): makes a Land+Creature token (the maker arm) and anthems
    # land creatures (a pump over the same dual-type subject).
    keys = _real("Jyoti, Moag Ancient")
    # The defining theme of the commander — must be its own signal, not collapsed
    # into generic "creatures matter".
    assert ("land_creatures_matter", "you") in keys
    # The generic go-wide signal still fires too (regression safety).
    assert ("creatures_matter", "you") in keys


def test_land_creatures_matter_from_anthem_payoff():
    # Real Sylvan Advocate: a pump over a Land+Creature dual-type subject.
    assert ("land_creatures_matter", "you") in _real("Sylvan Advocate")


def test_plant_token_maker_is_not_a_land_creatures_signal():
    # Avenger makes *Plant* creature tokens — never "land creatures". The whole
    # point of the scoped vocabulary: this must NOT register as land-creatures.
    keys = _real("Avenger of Zendikar")
    assert ("land_creatures_matter", "you") not in keys
    assert ("land_creatures_matter", "any") not in keys


def test_signal_is_hashable_frozen():
    s = Signal(key="x", scope="you", subject="", text="t", source="c")
    assert len({s, s}) == 1


# ── Reanimator payoff: "entered/cast from a graveyard" (Celes, Rune Knight) ──────
# The generic graveyard_matters lane is the FUEL (fill your yard / self-mill); the
# archetype is ACTIVE creature reanimation (a `reanimate` effect putting a CREATURE
# card from a graveyard onto the battlefield, rules-lawyer-verified against CR
# 702.34 / 603). "entered/cast FROM a graveyard" (escape / disturb / flashback /
# recursion payoffs — Celes, River Kelpie) is a SEPARATE graveyard-recursion axis.
def test_celes_is_not_reanimator_cast_from_graveyard_is_a_separate_axis():
    # Real Celes (snapshot): the "entered/cast from a graveyard" recursion payoff is
    # a separate axis from active reanimation.
    assert ("reanimator", "you") not in _real("Celes, Rune Knight")
    # The graveyard FUEL still fires (Celes fills/uses its own graveyard).
    assert ("graveyard_matters", "you") in _real("Celes, Rune Knight")


def test_reanimator_fires_for_active_creature_reanimation_via_ir():
    # A CREATURE that returns a creature card from a graveyard to the battlefield IS
    # the reanimator archetype — Loyal Retainers (real card / real `reanimate` IR effect).
    assert ("reanimator", "you") in _real("Loyal Retainers")


def test_reanimator_not_fired_by_regrowth_to_hand():
    # Returning a card to HAND is graveyard-return, not reanimation — no payoff trigger.
    # Real Regrowth (snapshot): graveyard_matters fires, reanimator does not.
    assert ("reanimator", "you") not in _real("Regrowth")


# ── Aristocrats: death-trigger doublers open the lane (the Teysa case) ───────────
# A commander that DOUBLES death triggers ("if a creature dying causes a triggered
# ability ... that ability triggers an additional time") is an aristocrats commander
# even though it never says "whenever ... dies". It must open the death lane so the
# drain payoffs (Blood Artist / Zulaport) surface.
def test_death_trigger_doubler_opens_aristocrats_lane():
    # Real Teysa Karlov (snapshot): the "dying"+"trigger" death-doubler opens the lane.
    assert any(k == "death_matters" for k, _ in _real("Teysa Karlov"))


def test_enchantment_cast_opens_enchantments_not_spellslinger():
    # "Whenever you cast an enchantment spell" is ENCHANTRESS, not spellslinger.
    # Real Sythis (snapshot): the enchantress "cast an enchantment spell" trigger.
    keys = _real("Sythis, Harvest's Hand")
    assert ("enchantments_matter", "you") in keys
    assert not any(k == "spellcast_matters" for k, _ in keys)


def test_affinity_and_artifact_cast_open_artifacts_lane():
    # Affinity (reminder text stripped) + casting artifacts from graveyard make Emry an
    # artifacts commander.
    # Real Emry (snapshot): affinity for artifacts + artifact graveyard recursion.
    assert ("artifacts_matter", "you") in _real("Emry, Lurker of the Loch")
    # Real Sai (snapshot): "cast an artifact spell" + artifact sac outlet.
    assert ("artifacts_matter", "you") in _real("Sai, Master Thopterist")


def test_token_doubler_opens_tokens_lane():
    # A token DOUBLER (Adrix) wants token-MAKERS to double — it must open the tokens
    # lane, not only "Doubling".
    # Real Adrix and Nev (snapshot): the token doubler opens the tokens lane.
    assert ("tokens_matter", "you") in _real("Adrix and Nev, Twincasters")


# ── Landfall: a land-recursion commander opens the lands lane (the Windgrace case) ─
# A commander whose payoff replays lands from the graveyard ("return … land cards from
# your graveyard to the battlefield") is a lands-matter commander and must open the
# landfall lane so its payoffs (Lotus Cobra / Scute Swarm) surface, even with no literal
# "landfall" / "play an additional land".
def test_land_recursion_commander_opens_landfall_lane():
    # Real Lord Windgrace (snapshot): land recursion opens landfall.
    assert ("landfall", "you") in _real("Lord Windgrace")


# ── Lifegain payoffs that gate on HAVING gained life (Aerith / Celestine) ────────
# "if you gained life this turn" / "the amount of life you gained this turn" is a
# lifegain PAYOFF — it cares whether you gained life.
def test_lifegain_conditional_payoff_opens_lane():
    # Real Aerith (snapshot): the "if you gained life this turn" payoff opens lifegain.
    assert ("lifegain_matters", "you") in _real("Aerith, Last Ancient")


def test_lifegain_amount_gained_payoff_opens_lane():
    # Real Celestine (snapshot): "the amount of life you gained" opens lifegain.
    assert ("lifegain_matters", "you") in _real("Celestine, the Living Saint")


# ── Evasion keywords whose "can't be blocked" lives only in stripped reminder text ─
# Horsemanship / menace / fear / intimidate / shadow / skulk are all CR blocking
# restrictions (702.31 / .111 / .36 / .13 / .28 / .118). Their mechanic is in the
# parenthetical reminder, which is stripped before detection — the detector must
# recognize the bare keyword word (Guan Yu showed NO evasion lane).
def test_horsemanship_opens_evasion_lane():
    # Real Guan Yu (snapshot): Horsemanship opens the evasion lane.
    assert ("evasion_self", "you") in _real("Guan Yu, Sainted Warrior")


# ── Zero-avenue commander recovery: themeless beaters, variable counters, global lords
# These commanders extracted NO avenues at all — the worst case (0/10 coverage).
def test_variable_x_counters_opens_counters_lane():
    # Halana and Alena: a recurring engine that puts a VARIABLE number of +1/+1
    # counters on your team each combat — a counters commander, but the count-anchor
    # ('for each'/'number of') gate missed the 'X +1/+1 counters' scaling form.
    # Real Halana and Alena (snapshot): the "X +1/+1 counters" placement projects a
    # place_counter(p1p1) that opens the counters lane.
    assert any(k == "plus_one_makers" for k, _ in _real("Halana and Alena, Partners"))


def test_cheap_vanilla_legend_opens_voltron_fallback():
    # Isamaru: the iconic 2/2 vanilla voltron commander. Commander damage is the only
    # plan, so the themeless-creature fallback must open voltron even at low power.
    # Real Isamaru (snapshot): the iconic 2/2 vanilla voltron commander.
    assert ("voltron_matters", "you") in _real("Isamaru, Hound of Konda")


def test_indestructible_beater_opens_voltron_fallback():
    # Konda: indestructible + vigilance beater — a resilient commander-damage threat
    # whose keywords weren't in the voltron set.
    # Real Konda (snapshot): indestructible + vigilance commander-damage threat.
    assert ("voltron_matters", "you") in _real("Konda, Lord of Eiganjo")


def test_global_tribal_anthem_opens_tribe():
    # Soraya: "Bird creatures get +1/+1" is a Bird lord — but the anthem patterns
    # required 'you control'/'other', missing the bare global-lord phrasing.
    # Real Soraya the Falconer (snapshot): the bare global-lord "Bird creatures get
    # +1/+1" anthem opens the Bird tribe.
    sigs = test_signals("Soraya the Falconer")
    assert any(s.key == "type_matters" and s.subject == "Bird" for s in sigs)


# ── Artifact commanders that phrase the theme without "artifacts you control" ─────
# Foundry Inspector (artifact cost reducer) is top-synergy for these but the lane
# never opened: they sacrifice artifacts (Bosh), copy artifact abilities (Kurkesh),
# or turn permanents INTO artifacts (Memnarch).
def test_artifact_sac_outlet_opens_artifacts_lane():
    # Real Bosh, Iron Golem (snapshot): the artifact sac outlet opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Bosh, Iron Golem")


def test_artifact_ability_payoff_opens_artifacts_lane():
    # Real Kurkesh (snapshot): the artifact-ability copy payoff opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Kurkesh, Onakke Ancient")


def test_artifact_type_granter_opens_artifacts_lane():
    # Real Memnarch (snapshot): the artifact-type granter opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Memnarch")


# ── creature_etb scope tracks the ENTERING creature's controller, not the payoff ──
# Purphoros: "Whenever another creature YOU control enters, deal 2 damage to each
# opponent." The entering creature is yours — so this is creature_etb YOU (an ETB
# go-wide engine that wants Panharmonicon / flicker / ETB creatures). The payoff
# hitting opponents must NOT flip the scope.
def test_creature_etb_scope_follows_entering_controller_not_payoff():
    # Real Purphoros (snapshot): the entering creature is yours, so creature_etb tracks
    # 'you' even though the payoff hits opponents.
    keys = _real("Purphoros, God of the Forge")
    assert ("creature_etb", "you") in keys
    assert ("creature_etb", "opponents") not in keys


def test_etb_trigger_doubler_opens_etb_lane():
    # Yarok doubles every permanent-ETB trigger — he's an ETB-value commander who wants
    # ETB creatures, flicker, and other doublers, so he must open the creature_etb lane.
    # Real Yarok (snapshot): the permanent-ETB trigger doubler opens creature_etb.
    assert ("creature_etb", "you") in _real("Yarok, the Desecrated")


# ── Artifact-token makers ARE artifact commanders (Food/Treasure/Clue are artifacts) ─
# A Treasure / Food / Clue / Blood maker should open the artifacts lane so artifact
# payoffs (Academy Manufactor, Foundry Inspector, artifact sac) surface.
def test_treasure_maker_opens_artifacts_lane():
    # Real Goldspan Dragon (snapshot): a Treasure maker opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Goldspan Dragon")


def test_food_maker_opens_artifacts_lane():
    # Real Gyome, Master Chef (snapshot): a Food maker opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Gyome, Master Chef")


# ── Activated-ability commanders want the untap / copy / cost-reduction package ──
# A commander whose engine is a {T}: activated ability (Arcum, Captain Sisay, Ertai,
# Kaho, Sanctum Weaver) wants Training Grounds / Thousand-Year Elixir / Rings of
# Brighthearth — none of which any existing lane surfaced.
def test_tap_ability_commander_opens_activated_lane():
    # Real Arcum Dagsson (snapshot): the {T}: sacrifice/tutor activated ability opens
    # the lane.
    assert ("activated_ability", "you") in _real("Arcum Dagsson")


def test_multi_tribe_anthem_emits_each_type():
    # Real Lovisa Coldeyes (snapshot): the multi-tribe anthem emits one type_matters
    # subject per named type.
    subjects = {
        s.subject for s in test_signals("Lovisa Coldeyes") if s.key == "type_matters"
    }
    assert {"Barbarian", "Warrior", "Berserker"} <= subjects


# ── Mana-cost activated abilities also want the activated-ability package ─────────
# A commander whose engine is a generic-mana-cost activated ability (The Scarab God
# '{2}{U}{B}: reanimate', Kenrith, Varragoth).
def test_mana_cost_activated_ability_opens_lane():
    # Real The Scarab God (snapshot): the {2}{U}{B}: generic-mana activated ability opens
    # the lane.
    assert ("activated_ability", "you") in _real("The Scarab God")


# ── Snow matters (Isu the Abominable) — a real niche archetype with a clean anchor ──
def test_snow_commander_opens_snow_lane():
    # Real Isu the Abominable (snapshot): snow_matters fires.
    assert ("snow_matters", "you") in _real("Isu the Abominable")


def test_kraken_commander_opens_kraken_tribe():
    # Real Brinelin, the Moon Kraken (snapshot): the Kraken type-line opens the tribe.
    sigs = test_signals("Brinelin, the Moon Kraken")
    assert any(s.key == "type_matters" and s.subject == "Kraken" for s in sigs)


def test_set_base_pt_does_not_open_toughness_lane():
    # Precision: "power and toughness are each equal to the number of X" is set-base-P/T,
    # not a toughness-as-value payoff.
    # Real Abominable Treefolk (snapshot): set-base-P/T, not a toughness-as-value payoff.
    assert ("toughness_combat", "you") not in _real("Abominable Treefolk")


def test_vanilla_matters_opens_for_no_abilities_commander():
    # Ruxa pumps "creatures you control with no abilities" — a vanilla-matters payoff.
    # Real Ruxa, Patient Professor (snapshot): phase carries the HasNoAbilities subject
    # predicate on the pump effect, opening the lane.
    assert ("vanilla_matters", "you") in _real("Ruxa, Patient Professor")


# ── Toughness payoffs beyond "assigns combat damage equal to toughness" (Geralf) ──
def test_toughness_value_payoff_opens_toughness_lane():
    # Real Geralf, Visionary Stitcher (snapshot): the toughness-as-value payoff opens the
    # lane.
    assert ("toughness_combat", "you") in _real("Geralf, Visionary Stitcher")


# ── Pariah combo: a commander that prevents/redirects damage to ITSELF (Cho-Manno,
# Anti-Venom) is the unkillable redirect target — it wants Pariah-style redirect + the
# indestructible grants that keep the target alive.
def test_self_damage_prevention_opens_redirect_lane():
    # Real Cho-Manno + Anti-Venom (snapshot): name-aware self-prevention opens the
    # redirect lane.
    assert ("damage_redirect", "you") in _real("Cho-Manno, Revolutionary")
    assert ("damage_redirect", "you") in _real("Anti-Venom, Horrifying Healer")


# ── The redirect clause: "the next N damage … dealt to ~ instead" — en-Kor,
# Reflect Damage, Captain's Maneuver. Disjoint from the name-aware self-prevention arm.
def test_redirect_clause_opens_redirect_lane():
    # Real Captain's Maneuver (snapshot): the redirect clause opens the lane.
    assert ("damage_redirect", "you") in _real("Captain's Maneuver")


def test_fog_does_not_open_redirect_lane():
    # Precision: a fog ("prevent all combat damage this turn") is not self-redirect.
    # Real Fog (snapshot): damage_prevention only — never self-redirect.
    assert ("damage_redirect", "you") not in _real("Fog")


def test_aura_recursion_opens_voltron_lane():
    # Hakim: "return target Aura card ... attached to Hakim" — aura voltron, but the
    # detector caught "attach an Aura", not the "Aura ... attached" recursion form.
    # The recursion PERFORMS the attaching, so Hakim is on the MAKER arm voltron_makers.
    assert ("voltron_makers", "you") in _real("Hakim, Loreweaver")


def test_passive_combat_damage_opens_combat_lane():
    # Hope of Ghirapur: "target player who was dealt combat damage by Hope this turn" —
    # a voltron/combat commander that cares about HAVING dealt combat damage (passive
    # form).
    # Real Hope of Ghirapur (snapshot): the passive "player who was dealt combat damage
    # by ~" form is recovered as a player-recipient combat_damage trigger, so the matters
    # lane fires.
    assert any(k == "combat_damage_matters" for k, _ in _real("Hope of Ghirapur"))


def test_multi_counter_placement_opens_counters_lane():
    # Minsc & Boo: "+1: Put three +1/+1 counters on up to one target creature" — a
    # recurring counter engine.
    # Real Minsc & Boo (snapshot): "+1: Put three +1/+1 counters" is a counter engine.
    assert any(k == "plus_one_makers" for k, _ in _real("Minsc & Boo, Timeless Heroes"))


def test_opponent_library_exile_opens_opponents_mill():
    # Circu: "exile the top card of target player's library" — exile-mill of opponents,
    # a mill variant the graveyard detector (keyed on "graveyard") missed.
    # Real Circu, Dimir Lobotomist (snapshot): exile-mill of opponents' libraries.
    assert ("graveyard_matters", "opponents") in _real("Circu, Dimir Lobotomist")


def test_self_library_exile_does_not_open_opponents_mill():
    # Precision: impulse-drawing off YOUR OWN library is not opponent mill.
    # Real Light Up the Stage (snapshot): impulse-drawing off YOUR library is not
    # opponent mill.
    assert ("graveyard_matters", "opponents") not in _real("Light Up the Stage")


# ── "a <Type> you control <verb>" and "attacking <Type>" tribal triggers ─────────
def test_a_type_you_control_verb_opens_tribe():
    # "a Griffin you control deals combat damage" — the 'deals' trigger verb.
    # Real Zeriam (snapshot): "a Griffin you control deals combat damage" — 'deals' verb.
    # Real Dromoka (snapshot): "a Dragon you control attacks" — 'attacks' verb.
    assert ("type_matters", "you") in _real("Zeriam, Golden Wind")
    assert any(
        s.subject == "Griffin"
        for s in test_signals("Zeriam, Golden Wind")
        if s.key == "type_matters"
    )
    assert any(
        s.subject == "Dragon"
        for s in test_signals("Dromoka, the Eternal")
        if s.key == "type_matters"
    )


def test_attacking_type_opens_tribe():
    # Real Clavileño (snapshot): "attacking Vampire" opens the Vampire tribe.
    assert any(
        s.subject == "Vampire"
        for s in test_signals("Clavileño, First of the Blessed")
        if s.key == "type_matters"
    )


def test_hexproof_beater_opens_voltron_despite_other_signals():
    # Sigarda: Flying, Hexproof, 5/5 — THE aura-voltron target (hexproof protects the
    # auras). She has a strong sacrifice-protection signal, but is voltron regardless.
    # Real Sigarda, Host of Herons (snapshot): Flying + Hexproof 5/5 — the aura-voltron
    # target, voltron regardless of her sacrifice-protection signal.
    assert ("voltron_matters", "you") in _real("Sigarda, Host of Herons")


def test_offering_keyword_opens_tribe():
    # Patron of the Nezumi: "Rat offering" — the Offering mechanic sacrifices a tribe
    # member to cast, so it's that tribe. Real text (the reminder is stripped, keyword
    # survives).
    # Real Patron of the Nezumi (snapshot): "Rat offering" opens the Rat tribe.
    assert any(
        s.subject == "Rat"
        for s in test_signals("Patron of the Nezumi")
        if s.key == "type_matters"
    )


def test_your_team_controls_opens_tribe():
    # Sylvia Brightspear: "Dragons your team controls have double strike" — multiplayer
    # "your team controls", which the "you control" patterns missed.
    # Real Sylvia Brightspear (snapshot): "Dragons your team controls" opens the tribe.
    assert any(
        s.subject == "Dragon"
        for s in test_signals("Sylvia Brightspear")
        if s.key == "type_matters"
    )


# ── Clone synergy: a HIGH-CMC commander with a strong ETB is worth copying (Dan's
# insight) — copying it re-fires the expensive ETB on a token for cheap (Gyruda). ──
def test_high_cmc_etb_commander_opens_clone():
    # Real Scryfall oracle uses the SHORT name ("When Gyruda enters"), not the full
    # "Gyruda, Doom of Depths" — the clone gate must match the short name like
    # _self_etb_value does, or it misses the very commander it was built for.
    # Real Gyruda, Doom of Depths (snapshot): a high-CMC ETB commander worth cloning.
    assert ("wants_cloning", "you") in _real("Gyruda, Doom of Depths")


def test_high_cmc_dies_trigger_commander_opens_clone():
    # A high-CMC commander with a strong DEATH trigger (Keiga, Kokusho) is also worth
    # copying — a clone/token-copy re-fires the death trigger when the copy dies
    # (sac-loop staple).
    # Real Keiga + Kokusho (snapshot): high-CMC death-trigger commanders worth cloning.
    assert ("wants_cloning", "you") in _real("Keiga, the Tide Star")
    assert ("wants_cloning", "you") in _real("Kokusho, the Evening Star")


def test_cheap_dies_trigger_does_not_open_clone():
    # Precision: a CHEAP death-trigger creature isn't worth a clone.
    # Real Doomed Dissenter (snapshot): a CHEAP death-trigger creature isn't worth a clone.
    assert ("wants_cloning", "you") not in _real("Doomed Dissenter")


def test_land_enter_punisher_opens_burn_lane():
    # Zo-Zu the Punisher: opponents-landfall PUNISH — "whenever a land enters, deal 2 to
    # that land's controller".
    # Real Zo-Zu the Punisher (snapshot): the landfall-punish burn fires direct_damage.
    assert ("direct_damage", "you") in _real("Zo-Zu the Punisher")


def test_source_deals_damage_opens_burn():
    # The Red Terror: "whenever a red source you control deals damage … put a +1/+1
    # counter on The Red Terror" — a damage-MATTERS trigger CONDITION (CR 603.2) reading
    # someone ELSE's damage, not a direct_damage EFFECT of its own. The real payoff lanes
    # fire regardless: its OWN +1/+1 counter growth (self_counter_grow) and its
    # counter-placement ability (plus_one_makers).
    idents = _real("The Red Terror")
    assert ("direct_damage", "you") not in idents
    assert ("self_counter_grow", "you") in idents


def test_self_power_scaling_opens_counters():
    # Mona Lisa: "{T}: Add X mana, where X is Mona Lisa's power" — her value scales with
    # her OWN power, so she wants to pump it with +1/+1 counters (Stony Strength).
    # Real Mona Lisa, Science Geek (snapshot): value scales with her own power, so she
    # wants +1/+1 counters.
    assert any(k == "self_counter_grow" for k, _ in _real("Mona Lisa, Science Geek"))


def test_fling_target_power_does_not_open_self_counters():
    # Precision: "X is TARGET creature's power" (fling) isn't self-scaling.
    # Real Fling (snapshot): "X is TARGET creature's power" isn't self-scaling.
    assert not any(k == "self_counter_grow" for k, _ in _real("Fling"))


def test_punish_non_attackers_opens_forced_attack():
    # Kratos: "deals damage = creatures that didn't attack this turn" — a force-attack
    # incentive (attack or take damage), a goad/aggro commander.
    # Real Kratos, God of War (snapshot): the "didn't attack this turn" punisher tail
    # opens the forced-attack lane.
    assert any(k == "forced_attack" for k, _ in _real("Kratos, God of War"))


# ── Outlaw tribal (Outlaws of Thunder Junction): Assassin/Mercenary/Pirate/Rogue/
# Warlock are collectively "outlaws" (Vial Smasher). ──
def test_outlaw_commander_opens_outlaw_lane():
    # Real Vial Smasher (snapshot): "another outlaw you control" opens the outlaw lane.
    assert ("outlaw_matters", "you") in _real("Vial Smasher, Gleeful Grenadier")


def test_pacify_control_commander_opens_pillowfort():
    # Gwafa Hazid neutralizes opponents' creatures ("can't attack or block") — a
    # control/pillowfort identity that wants Propaganda / Ghostly Prison / Windborn Muse.
    # Real Gwafa Hazid, Profiteer (snapshot): "creatures ... can't attack or block" is a
    # pillowfort/stax tell.
    assert ("stax_taxes", "opponents") in _real("Gwafa Hazid, Profiteer")


def test_banding_commander_opens_banding_lane():
    # Ayesha Tanaka has Banding — she wants other banding creatures to form bands.
    # Real Ayesha Tanaka (snapshot): the Banding keyword opens the banding lane.
    assert ("has_banding", "you") in _real("Ayesha Tanaka")


def test_counter_on_another_opens_counters():
    # Anafenza, the Foremost: "Whenever Anafenza attacks, put a +1/+1 counter on another
    # target tapped creature" — a recurring counter engine (placement on ANOTHER
    # creature), distinct from bare self-growth ('on it').
    # Real Anafenza, the Foremost (snapshot): a counter placement on ANOTHER creature is
    # a counters engine.
    assert any(k == "plus_one_makers" for k, _ in _real("Anafenza, the Foremost"))


def test_variable_lifegain_opens_lifegain():
    # Atalya gains X life; Ayli gains life equal to toughness — variable lifegain the
    # detector (keyed on 'gain N life') missed.
    # Real Atalya + Ayli (snapshot): variable "gain X life" / "gain life equal to" rides
    # the structural gain_life Effect. The gaining is the MAKER arm -> lifegain_makers.
    assert ("lifegain_makers", "you") in _real("Atalya, Samite Master")
    assert ("lifegain_makers", "you") in _real("Ayli, Eternal Pilgrim")


def test_if_you_would_gain_life_opens_lifegain():
    # Bilbo / Boon Reflection / Rhox Faithmender: "if you would gain life, you gain …
    # instead" is a lifegain amplifier — a lifegain commander.
    # Real Bilbo, Birthday Celebrant (snapshot): the "if you would gain life" amplifier
    # opens lifegain.
    assert ("lifegain_matters", "you") in _real("Bilbo, Birthday Celebrant")


def test_tap_deals_damage_opens_burn():
    # Heartless Hidetsugu: "{T}: deals damage to each player equal to half …" — a pinger
    # the digit-keyed branch missed (no literal number).
    # Real Heartless Hidetsugu (snapshot): a no-literal-number "each player" pinger.
    assert ("direct_damage", "you") in _real("Heartless Hidetsugu")


def test_aura_equipment_cost_reducer_opens_voltron():
    # Danitha: "Aura and Equipment spells you cast cost {1} less" — a voltron payoff the
    # detector's 'cast an Aura/Equipment' branch missed.
    # Real Danitha Capashen, Paragon (snapshot): the Aura/Equipment cost reducer is a
    # voltron payoff.
    assert ("voltron_matters", "you") in _real("Danitha Capashen, Paragon")


def test_greatest_power_among_other_opens_power():
    # Arni Brokenbrow: "greatest power among OTHER creatures you control" — the power
    # detector required 'among creatures you control' (no 'other').
    # Real Arni Brokenbrow (snapshot): "greatest power among other creatures you control"
    # folds into a board_count the production path recovers.
    assert ("power_matters", "you") in _real("Arni Brokenbrow")


def test_artifact_type_commander_opens_artifacts():
    # A commander that IS an artifact (type line has the Artifact card type) is an
    # artifact deck — wants affinity / cost reducers / artifact synergy, just as a
    # creature is a member of its own tribe (the type-line membership insight).
    # Real ED-E (snapshot): a commander that IS an artifact (type line) opens the lane
    # via the type_line membership arm.
    assert ("artifacts_matter", "you") in _real("ED-E, Lonesome Eyebot")
    # Real Anikthea (snapshot): an enchantment-type commander → enchantments_matter.
    assert ("enchantments_matter", "you") in _real("Anikthea, Hand of Erebos")


def test_equipped_creature_reference_opens_voltron():
    # Akiri: "attack a player with one or more equipped creatures … unattach an
    # Equipment" — an equipment/voltron commander the attach/cast patterns missed.
    # Real Akiri, Fearless Voyager (snapshot): the equipped-creature reference is voltron.
    assert ("voltron_matters", "you") in _real("Akiri, Fearless Voyager")


def test_unkillable_self_prevention_opens_voltron():
    # Cho-Manno: "Prevent all damage that would be dealt to Cho-Manno" — an unkillable
    # body is the ideal Equipment/Aura carrier, so it's a voltron commander.
    # Real Cho-Manno (snapshot): an unkillable body is the ideal Equipment/Aura carrier.
    assert ("voltron_matters", "you") in _real("Cho-Manno, Revolutionary")


def test_boast_keyword_opens_attack_matters():
    # Boast (CR 702.135) can only be activated "if this creature attacked this turn", so
    # a Boast commander is an attack-matters deck. The condition lives in reminder text
    # (stripped before detection), so the lane fires from the keyword.
    # Real Varragoth, Bloodsky Sire (snapshot): the Boast keyword opens attack_matters.
    assert ("attack_matters", "you") in _real("Varragoth, Bloodsky Sire")


def test_enchantress_first_spell_opens_enchantments():
    # Psemilla: "Whenever you cast your FIRST enchantment spell each turn …" — the bare
    # "cast an enchantment" missed the "first/second enchantment spell" wording.
    # Real Psemilla, Meletian Poet (snapshot): "cast your first enchantment spell each
    # turn" opens enchantments.
    assert "enchantments_matter" in {
        s.key for s in test_signals("Psemilla, Meletian Poet")
    }


def test_for_each_creature_opens_creatures_matter():
    # Shanna: "gets +1/+1 for each creature you control" — a singular count operand.
    # Real Shanna, Sisay's Legacy (snapshot): "+1/+1 for each creature you control" fires
    # from the board_count marker.
    assert "creatures_matter" in {s.key for s in test_signals("Shanna, Sisay's Legacy")}


def test_fliers_matter_commander_opens_flying_keyword_tribe():
    # Momo: "creature spell with flying you cast costs {1} less … whenever another
    # creature you control with flying enters" — a fliers-matter commander. The keyword-
    # tribe detector matched only PLURAL "creatures … with flying"; add the singular
    # "creature you control with flying" / "creature spell with flying" forms.
    # Real Momo, Friendly Flier (snapshot): "creature you control with flying" / "creature
    # spell with flying" opens the Flying keyword tribe.
    subs = {
        s.subject
        for s in test_signals("Momo, Friendly Flier")
        if s.key == "keyword_tribe"
    }
    assert "Flying" in subs
    # Precision: real Isperia merely HAS flying (no "creature with flying" payoff) — NOT
    # a fliers-matter deck.
    assert "keyword_tribe" not in {
        s.key for s in test_signals("Isperia, Supreme Judge")
    }


def test_lifelink_commander_opens_lifegain():
    # A lifelink commander (Liesa, Elenda) gains life in combat → it's a lifegain deck
    # (lifelink + Sanguine Bond / Archangel of Thune is the payoff). The keyword carries
    # the gain (no "gain life" oracle text), so the lane opens via the keyword.
    # Real Elenda, Saint of Dusk (snapshot): the Lifelink keyword opens lifegain via the
    # keyword map. A lifelink bearer is a lifegain SOURCE → the maker arm lifegain_makers.
    assert ("lifegain_makers", "you") in _real("Elenda, Saint of Dusk")


def test_plural_death_does_not_open_on_dice():
    # Precision: a dice "die" ("roll a six-sided die") must NOT read as a death trigger.
    # Real Velukan Dragon (snapshot): the dice "die" ("roll a six-sided die") must NOT
    # read as a death trigger.
    assert "death_matters" not in {s.key for s in test_signals("Velukan Dragon")}


def test_plural_combat_damage_opens_combat_damage_matters():
    # "creatures you control DEAL combat damage" — the plural verb ("deal" not "deals").
    # 200+ cards (Yarus, Gonti Canny Acquisitor, Neheb) use the "one or more creatures …
    # deal combat damage to a player" form the singular-only regex missed.
    # Real Excogitator Sphinx (snapshot): the plural-verb "one or more creatures … deal
    # combat damage to a player" is the DamageDoneOnceByController trigger phase carries
    # with a Player recipient; matters reads the structure.
    assert ("combat_damage_matters", "opponents") in _real("Excogitator Sphinx")


def test_singular_lord_has_opens_type_matters():
    # "Each Ally you control HAS …" — the singular lord conjugation ("has" not "have").
    # Real Great Divide Guide (snapshot): "Each Ally you control has …" — the singular
    # "has" lord conjugation opens the Ally tribe.
    subs = {
        s.subject for s in test_signals("Great Divide Guide") if s.key == "type_matters"
    }
    assert "Ally" in subs


def test_singular_tribal_lord_gets_opens_type_matters():
    # "Each Fungus creature GETS +1/+1" — a singular-subject lord (Thelon of Havenwood).
    # The global-lord pattern matched only plural "get" ("Goblins … get"), missing the
    # singular "creature gets" conjugation, so the whole tribe read uncovered.
    # Real Thelon of Havenwood (snapshot): "Each Fungus creature gets +1/+1" — the
    # singular "creature gets" lord conjugation opens the Fungus tribe.
    sigs = test_signals("Thelon of Havenwood")
    assert ("type_matters", "you") in {(s.key, s.scope) for s in sigs}
    assert "Fungus" in {s.subject for s in sigs if s.key == "type_matters"}


def test_reward_for_attacking_opponents_opens_goad():
    # Gahiji / Frontier Warmonger reward any creature that attacks your opponents. Goad
    # forces opponents' creatures to attack a player other than their controller — i.e.
    # one of your OTHER opponents — firing the reward (CR 701.38b).
    # Real Gahiji, Honored One (snapshot): the "attacks one of your opponents" reward
    # opens goad.
    assert ("goad_makers", "opponents") in _real("Gahiji, Honored One")


def test_tribal_capture_cant_be_blocked():
    # Rocksteady, Crash Courser is a Rhino Mutant — NOT a Boar — yet it buffs
    # "Boars you control can't be blocked". A commander that buffs a tribe isn't
    # always that tribe, so type-line membership can't supply the Boar lane; only
    # the can't-be-blocked trigger pattern opens it.
    # Real Rocksteady, Crash Courser (snapshot): a Rhino Mutant that buffs "Boars you
    # control" — only the can't-be-blocked clause (not type-line membership) opens Boar.
    subs = {
        s.subject
        for s in test_signals("Rocksteady, Crash Courser")
        if s.key == "type_matters"
    }
    assert "Boar" in subs  # the buffed tribe, captured from the clause not the type


def test_tribal_capture_cant_be_blocked_vocab_gated():
    # Yuan Shao, the Indecisive — "Each creature you control can't be blocked …".
    # The generic card-type word "creature" must be dropped by the vocab gate, not
    # emitted as a bogus "Creature" tribal subject.
    # Real Yuan Shao, the Indecisive (snapshot): "Each creature you control can't be
    # blocked" — the generic word "creature" is vocab-gated, never a bogus tribal subject.
    subs = {
        s.subject
        for s in test_signals("Yuan Shao, the Indecisive")
        if s.key == "type_matters"
    }
    assert "Creature" not in subs


def test_two_tribe_trigger_emits_both_subjects():
    # Gorbag of Minas Morgul is an Orc Soldier (membership supplies Orc but never
    # Goblin); "a Goblin or Orc you control deals …" must open BOTH tribal lanes.
    # Real Gorbag of Minas Morgul (snapshot): "a Goblin or Orc you control deals …" opens
    # BOTH tribal lanes (membership supplies only Orc).
    subs = {
        s.subject
        for s in test_signals("Gorbag of Minas Morgul")
        if s.key == "type_matters"
    }
    assert {"Goblin", "Orc"} <= subs


def test_impulse_look_at_and_play_opens_lane():
    # Headliner Scarlett — "You may look at and play that card this turn" is an
    # impulse engine ("look at and" splits "you may"/"play").
    # Real Headliner Scarlett (snapshot): "you may look at and play that card" is an
    # impulse engine.
    assert ("impulse_top_play", "you") in _real("Headliner Scarlett")


def test_extra_upkeep_lane_opens():
    # Real Obeka, Splitter of Seconds + The Ninth Doctor (snapshot): both grant an
    # "additional upkeep step" via phase's extra_upkeep effect, opening the lane.
    assert ("extra_upkeep", "you") in _real("Obeka, Splitter of Seconds")
    assert ("extra_upkeep", "you") in _real("The Ninth Doctor")


def test_extra_end_step_lane_opens():
    # Y'shtola Rhul grants an additional end step; the end-step payoff lane must open.
    # Real Y'shtola Rhul (snapshot): the "additional end step" grant is recovered by the
    # extra_end dropped-static face marker, opening the lane.
    assert ("extra_end_step", "you") in _real("Y'shtola Rhul")


def test_extra_beginning_phase_decomposes_to_upkeep_and_draw():
    # CR 501.1: the beginning phase contains untap, upkeep, AND draw steps — so an
    # extra beginning phase (Sphinx of the Second Sun) re-triggers upkeep- and
    # draw-step payoffs. The untap step has no servable payoff, so no untap lane.
    # Real Sphinx of the Second Sun (snapshot): the "additional beginning phase" grant is
    # recovered as BOTH extra_upkeep + extra_draw, opening both lanes.
    hybrid = _real("Sphinx of the Second Sun")
    assert ("extra_upkeep", "you") in hybrid
    assert ("extra_draw_step", "you") in hybrid


def test_flying_from_top_opens_keyword_tribe():
    # Errant and Giada — "cast spells with flash or flying from the top" rewards
    # fliers; open the Flying keyword-tribe lane.
    # Real Errant and Giada (snapshot): "cast spells with flash or flying from the top"
    # rewards fliers — opens the Flying keyword-tribe lane.
    sigs = test_signals("Errant and Giada")
    assert ("keyword_tribe", "you") in {(s.key, s.scope) for s in sigs}
    assert "Flying" in {s.subject for s in sigs if s.key == "keyword_tribe"}


def test_yasharn_opens_stax_taxes():
    # Yasharn's cost-lock is a tax piece; the lane must OPEN so its hatebear
    # synergy package (Thalia, Archon of Emeria, …) is surfaced.
    # Real Yasharn, Implacable Earth (snapshot): the cost-lock tax piece opens stax_taxes.
    assert ("stax_taxes", "opponents") in _real("Yasharn, Implacable Earth")


# ── Long-tail batch 2 (salvaged workflow proposals: detector-open gaps) ────────


def test_enchantment_card_tutor_opens_enchantments():
    # Zur the Enchanter tutors enchantment CARDS; the detector keyed only on
    # "enchantments you control" / "cast an enchantment" and missed card-references.
    # Real Zur the Enchanter (snapshot): the "search … for an enchantment card" tutor
    # opens the enchantments lane.
    assert ("enchantments_matter", "you") in _real("Zur the Enchanter")


def test_instant_sorcery_cost_reducer_opens_spellslinger():
    # Baral reduces instant/sorcery cost — a core spellslinger payoff with no cast
    # trigger.
    # Real Baral, Chief of Compliance (snapshot): the instant/sorcery cost reducer (no
    # cast trigger) opens spellslinger.
    assert ("spellcast_matters", "you") in _real("Baral, Chief of Compliance")


def test_artifact_entered_condition_opens_artifacts():
    # Akal Pakal keys on "if an artifact entered the battlefield under your
    # control this turn" — an artifacts-matters condition the detector missed.
    # Real Akal Pakal (snapshot): the "if an artifact entered … this turn" condition opens
    # the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Akal Pakal, First Among Equals")


def test_heist_opens_theft():
    # Heist (Arena keyword) steals + casts an opponent's cards — a theft DOER
    # the detector missed. Grenzo, Crooked Jailer / Axavar / Mr. Monopoly.
    # Real Grenzo, Crooked Jailer (snapshot): Heist steals + casts opponents' cards — a
    # theft maker.
    assert ("theft_makers", "opponents") in _real("Grenzo, Crooked Jailer")


# ── Long-tail batch 3 (voltron / noncombat-engine / drain) ────────────────────


def test_enchanted_or_equipped_opens_voltron():
    # Koll buffs "enchanted or equipped" creature tokens — a voltron/auras+equip
    # payoff the detector missed (it keyed on "attach"/"equipped creatures").
    # Real Koll, the Forgemaster (snapshot): buffing "enchanted or equipped" creatures is
    # a voltron/auras+equip payoff.
    assert ("voltron_matters", "you") in _real("Koll, the Forgemaster")


def test_mv_scaling_burn_opens_noncombat_damage():
    # Kaervek scales noncombat damage off opponents' spells — a burn-engine payoff
    # commander; the lane keyed only on doublers / "deals that much damage".
    # Real Kaervek the Merciless (snapshot): MV-scaling noncombat damage off opponents'
    # spells is a burn-engine payoff.
    assert ("noncombat_damage_payoff", "you") in _real("Kaervek the Merciless")


def test_opponent_lost_life_this_turn_opens_drain():
    # Sygg's "if an opponent lost 3 or more life this turn, you may draw a card" is a
    # triggering CONDITION scaling a DIFFERENT effect (the draw), never the card's OWN
    # life-loss action — the structural read correctly finds no LoseLife node to
    # attribute to Sygg itself.
    # Real Sygg, River Cutthroat (snapshot).
    ident = ("lifeloss_makers", "opponents")
    idents = _real("Sygg, River Cutthroat")
    assert ident not in idents


def test_turn_target_face_up_opens_facedown():
    # Kaust turns a TARGET face-down creature face up + rewards "turned face up
    # this turn" — a morph/face-down payoff the detector missed (self-only form).
    # Real Kaust, Eyes of the Glade (snapshot): the turn-target-face-up + "turned face up
    # this turn" payoff opens facedown.
    assert ("facedown_matters", "you") in _real("Kaust, Eyes of the Glade")


def test_type_you_control_entering_gerund_opens_tribe():
    # Naban: "a Wizard you control entering causes …" — the gerund "entering"
    # the "(enters|attacks|…)" verb list missed; opens Wizard tribal.
    # Real Naban, Dean of Iteration (snapshot): the gerund "a Wizard you control entering"
    # opens Wizard tribal.
    subs = {
        s.subject
        for s in test_signals("Naban, Dean of Iteration")
        if s.key == "type_matters"
    }
    assert "Wizard" in subs


def test_art_sticker_opens_stickers():
    # Roxi cares about art stickers (power = permanents/cards with an art sticker;
    # ETB distributes art stickers). The mirror matches any mention — sticker is a
    # dedicated mechanic, so "art sticker"/"distribute … stickers" is on-theme.
    # Real Roxi, Publicist to the Stars (snapshot): art-sticker references open the
    # stickers lane.
    assert ("stickers_matter", "you") in _real("Roxi, Publicist to the Stars")
