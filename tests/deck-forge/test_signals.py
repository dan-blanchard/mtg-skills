"""Tests for deterministic signal extraction (the discovery-engine keystone).

The headline guard: a signal that concerns OPPONENTS' graveyards must be scoped
"opponents", never a generic graveyard signal that would justify self-mill (the
Tinybones overgeneralization the whole tool exists to prevent).
"""

from mtg_utils._deck_forge._signals_ir import extract_signals_ir
from mtg_utils._deck_forge.signals import (
    Signal,
    aggregate_signals,
    extract_signals,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face
from mtg_utils.testkit import test_card, test_signals


def _keys(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _real(name):
    """(key, scope) set from production over the REAL Scryfall record + REAL
    projected IR (``extract_signals_hybrid`` via the committed snapshot)."""
    return {(s.key, s.scope) for s in test_signals(name)}


# ADR-0039 task #80 step 6: these hand-built ``Card`` IR fixtures (no real
# ``oracle_id``) can never resolve a crosswalk tree — ``extract_signals_hybrid``
# (the production dispatcher) is now crosswalk-only and would silently return
# nothing for them. What these tests actually probe is the STRUCTURAL DETECTION
# LOGIC in ``extract_signals_ir`` (still a real, exercised module — task #80 step
# 6 leaves it as a stub pending step 7's decision on the legacy builder's own
# fate), so every synthetic-fixture call below goes straight to it instead of the
# hybrid facade. ``_real`` (testkit-backed) is unaffected — it already exercises
# the real production path.
def _ir_with(*abilities: Ability) -> Card:
    """A Card IR carrying the given abilities — the structural marker an ADR-0027-
    migrated effect-based key reads."""
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", abilities=tuple(abilities)),),
    )


# A minimal non-None IR for ADR-0027 keys whose IR source scans the record
# directly (kept word-detector mirror / keyword array) — any non-None Card routes
# to the IR path.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(card):
    return {(s.key, s.scope) for s in extract_signals_ir(card, _bare_ir())}


# ADR-0027 β: creature_etb migrated to the Card IR (a byte-identical kept-mirror over
# the reminder-stripped oracle), so it serves from the hybrid path, not pure regex.
def test_creature_etb_scoped_to_you():
    card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert ("creature_etb", "you") in _keys_hybrid(card)


def test_creature_etb_scoped_to_opponents():
    card = {
        "name": "Punisher",
        "oracle_text": "Whenever a creature an opponent controls enters, it deals 1 damage to them.",
    }
    assert ("creature_etb", "opponents") in _keys_hybrid(card)


def test_graveyard_signal_scoped_to_opponents_not_generic():
    # The Tinybones case: benefits from OPPONENTS' graveyards filling. Migrated to the
    # REAL record + REAL projected IR (snapshot) — production recovers the "that player's
    # graveyard" → 'opponents' Tinybones cast scope.
    sigs = test_signals("Tinybones, the Pickpocket")
    gy = [s for s in sigs if s.key == "graveyard_matters"]
    assert gy, "expected a graveyard signal"
    assert all(s.scope == "opponents" for s in gy)
    # It must NOT be scoped to 'you' — that would justify self-mill.
    assert ("graveyard_matters", "you") not in _real("Tinybones, the Pickpocket")


def test_graveyard_signal_scoped_to_you_for_reanimator():
    # ADR-0027 v29: graveyard_matters migrated to the Card IR. The "your graveyard"
    # reference rides the byte-identical mirror (scope 'you'); pure extract_signals no
    # longer emits it (the regex producers are deleted).
    card = {
        "name": "Reanimator",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("graveyard_matters", "you") in _keys_hybrid(card)


def test_lifegain_matters():
    # ADR-0027 β: lifegain_matters migrated to the Card IR (a `life_gained` trigger /
    # `gain_life` Effect structural arm + a byte-identical kept-mirror over the reminder-
    # stripped oracle), so it serves from the hybrid path.
    card = {
        "name": "Soul Warden's Friend",
        "oracle_text": "Whenever you gain life, put a +1/+1 counter on this creature.",
    }
    assert ("lifegain_matters", "you") in _keys_hybrid(card)


def test_vanilla_keyword_card_has_no_signals():
    # Logic probe (SYNTHETIC name): an evergreen-keyword-only body with no creature
    # type / no P/T mints no signal. NOT a real card — the real "Air Elemental" is a
    # 4/4 Elemental that fires type_matters(Elemental) + the voltron fallback, so a
    # real-card fixture here would mislead (the props matter, per the test-infra memory).
    card = {"name": "Keyword-Only Body", "oracle_text": "Flying"}
    assert extract_signals(card) == []


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


def test_signal_carries_source_and_quote():
    # ADR-0027 β: creature_etb is IR-served (a byte-identical kept-mirror), so it comes
    # through the hybrid path and carries the card name as its source (the structural
    # path emits no clause quote). A still-regex-served lane (graveyard_matters) proves
    # the source+quote contract holds end-to-end on the legacy path.
    etb_card = {
        "name": "ETB Boss",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    etb = next(
        s for s in extract_signals_ir(etb_card, _bare_ir()) if s.key == "creature_etb"
    )
    assert etb.source == "ETB Boss"
    # spellcast_matters (ADR-0027 signals-only, SIDECAR 50) is now IR-served, but its
    # byte-identical kept mirror (_detect_spellcast_matters) runs PER-CLAUSE and passes
    # the matched clause as the Signal's raw/text — so the source+quote contract still
    # holds end-to-end through the hybrid path.
    spell_card = {
        "name": "Spell Boss",
        "oracle_text": "Whenever you cast an instant spell, draw a card.",
    }
    quoting = next(
        s
        for s in extract_signals_ir(spell_card, _bare_ir())
        if s.key == "spellcast_matters"
    )
    assert quoting.source == "Spell Boss"
    assert "cast an instant spell" in quoting.text.lower()


def test_aggregate_dedupes_across_records():
    # aggregate_signals walks the legacy regex path (extract_signals). voltron_matters,
    # the last common non-migrated key, migrated in ADR-0027 (the cutover is complete),
    # so this uses a lane the regex still emits — type_matters (a tribal lord, scope you,
    # subject "Goblin"). Two distinct Goblin lords open the SAME (key, scope, subject),
    # which aggregate_signals must dedupe to one entry.
    a = {
        "name": "A",
        "type_line": "Creature — Goblin",
        "oracle_text": "Other Goblins you control get +1/+1.",
        "power": "2",
        "toughness": "2",
    }
    b = {
        "name": "B",
        "type_line": "Creature — Goblin",
        "oracle_text": "Other Goblin creatures you control get +1/+0.",
        "power": "2",
        "toughness": "2",
    }
    agg = aggregate_signals([a, b])
    sc = [
        s
        for s in agg
        if s.key == "type_matters" and s.scope == "you" and s.subject == "Goblin"
    ]
    assert len(sc) == 1  # deduped by (key, scope, subject)


def test_signal_is_hashable_frozen():
    s = Signal(key="x", scope="you", subject="", text="t", source="c")
    assert len({s, s}) == 1


# ── Reanimator payoff: "entered/cast from a graveyard" (Celes, Rune Knight) ──────
# The generic graveyard_matters lane is the FUEL (fill your yard / self-mill); a
# ADR-0027: reanimator migrated to the Card IR and its boundary was CORRECTED
# (rules-lawyer-verified, CR 702.34 / 603): the archetype is ACTIVE creature
# reanimation (a `reanimate` effect putting a CREATURE card from a graveyard onto the
# battlefield). The legacy regex conflated this with "entered/cast FROM a graveyard"
# (escape / disturb / flashback / recursion payoffs — Celes, River Kelpie), which is a
# SEPARATE graveyard-recursion axis. Celes is that recursion payoff, NOT reanimator.
def test_celes_is_not_reanimator_cast_from_graveyard_is_a_separate_axis():
    # The corrected boundary: an "entered/cast from a graveyard" PAYOFF is graveyard
    # recursion (escape/disturb/flashback), not the active-reanimation archetype.
    # Real Celes (snapshot) over real IR.
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


def test_reanimator_not_fired_by_plain_reanimation_spell():
    # A reanimation spell is an ENABLER (found by the avenue's search), not itself the
    # payoff trigger — its text says "to the battlefield", never "enters/cast from".
    card = {
        "name": "Animate Dead-like",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("reanimator", "you") not in _keys(card)


# ── Aristocrats: death-trigger doublers open the lane (the Teysa case) ───────────
# A commander that DOUBLES death triggers ("if a creature dying causes a triggered
# ability ... that ability triggers an additional time") is an aristocrats commander
# even though it never says "whenever ... dies". It must open the death lane so the
# drain payoffs (Blood Artist / Zulaport) surface.
def test_death_trigger_doubler_opens_aristocrats_lane():
    # Real Teysa Karlov (snapshot): the "dying"+"trigger" death-doubler opens the lane.
    assert any(k == "death_matters" for k, _ in _real("Teysa Karlov"))


def test_dies_in_passing_does_not_open_aristocrats():
    # A one-off non-death clause must NOT mint the aristocrats lane (no over-general).
    # ADR-0027: assert against the hybrid (IR) path the migrated lane now lives on.
    card = {
        "name": "Exiler",
        "oracle_text": "When this creature deals combat damage to a player, exile it.",
    }
    assert not any(k == "death_matters" for k, _ in _keys_hybrid(card))


# ── Cast-an-X-spell routes to the X lane, not Spellslinger (Sythis / Emry) ──────
def test_enchantment_cast_opens_enchantments_not_spellslinger():
    # "Whenever you cast an enchantment spell" is ENCHANTRESS, not spellslinger — the
    # greedy spellcast detector used to mis-route Sythis to instants/sorceries.
    # Real Sythis (snapshot): the enchantress "cast an enchantment spell" trigger.
    keys = _real("Sythis, Harvest's Hand")
    assert ("enchantments_matter", "you") in keys
    assert not any(k == "spellcast_matters" for k, _ in keys)


def test_affinity_and_artifact_cast_open_artifacts_lane():
    # Affinity (reminder text stripped) + casting artifacts from graveyard make Emry an
    # artifacts commander; she must open the Artifacts lane.
    # Real Emry (snapshot): affinity for artifacts + artifact graveyard recursion.
    assert ("artifacts_matter", "you") in _real("Emry, Lurker of the Loch")
    # Real Sai (snapshot): "cast an artifact spell" + artifact sac outlet.
    assert ("artifacts_matter", "you") in _real("Sai, Master Thopterist")


def test_token_doubler_opens_tokens_lane():
    # A token DOUBLER (Adrix) wants token-MAKERS to double — it must open the tokens
    # lane, not only "Doubling". ADR-0027: tokens_matter migrated to the Card IR via a
    # byte-identical kept-mirror, so assert against the hybrid path (the mirror reads
    # the oracle, so a bare IR routes the hybrid to the IR path).
    # Real Adrix and Nev (snapshot): the token doubler opens the tokens lane.
    assert ("tokens_matter", "you") in _real("Adrix and Nev, Twincasters")


# ── Landfall: a land-recursion commander opens the lands lane (the Windgrace case) ─
# A commander whose payoff replays lands from the graveyard ("return … land cards from
# your graveyard to the battlefield") is a lands-matter commander and must open the
# landfall lane so its payoffs (Lotus Cobra / Scute Swarm) surface, even with no literal
# "landfall" / "play an additional land". ADR-0027: landfall migrated to the Card IR —
# the land-recursion branch has no structural shape phase carries, so it fires from the
# _LANDFALL_MIRROR over the dict oracle via the hybrid (bare IR), NOT the regex producer.
def test_land_recursion_commander_opens_landfall_lane():
    # Real Lord Windgrace (snapshot): land recursion opens landfall on the IR path; the
    # regex path no longer emits the migrated key.
    assert ("landfall", "you") not in _keys(test_card("Lord Windgrace"))
    assert ("landfall", "you") in _real("Lord Windgrace")


# ── Lifegain payoffs that gate on HAVING gained life (Aerith / Celestine) ────────
# "if you gained life this turn" / "the amount of life you gained this turn" is a
# lifegain PAYOFF — it cares whether you gained life — but the detector only caught
# "whenever you gain life". These commanders showed ONLY an incidental graveyard
# signal; their real theme (lifegain) was invisible.
def test_lifegain_conditional_payoff_opens_lane():
    # Real Aerith (snapshot): the "if you gained life this turn" payoff opens lifegain.
    assert ("lifegain_matters", "you") in _real("Aerith, Last Ancient")


def test_lifegain_amount_gained_payoff_opens_lane():
    # Real Celestine (snapshot): "the amount of life you gained" opens lifegain.
    assert ("lifegain_matters", "you") in _real("Celestine, the Living Saint")


def test_combat_damage_to_player_does_not_open_lifegain():
    # Precision: a card that merely says "life" in passing (lose life) must not mint
    # the lifegain lane via the new past-tense branch.
    card = {
        "name": "Drainer",
        "oracle_text": "When this creature deals combat damage to a player, they lose 2 life.",
    }
    assert ("lifegain_matters", "you") not in _keys(card)


# ── Evasion keywords whose "can't be blocked" lives only in stripped reminder text ─
# Horsemanship / menace / fear / intimidate / shadow / skulk are all CR blocking
# restrictions (702.31 / .111 / .36 / .13 / .28 / .118). Their mechanic is in the
# parenthetical reminder, which extract_signals strips — so the bare keyword word is
# all that's left and the detector must recognize it (Guan Yu showed NO evasion lane).
def test_horsemanship_opens_evasion_lane():
    # Real Guan Yu (snapshot): Horsemanship opens the evasion lane.
    assert ("evasion_self", "you") in _real("Guan Yu, Sainted Warrior")


def test_menace_opens_evasion_lane():
    card = {
        "name": "Menacer",
        "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
    }
    # ADR-0027: hybrid path — the kept WORD MIRROR's "\bmenace\b" arm fires it.
    assert ("evasion_self", "you") in _keys_hybrid(card)


def test_plain_vigilance_creature_no_evasion_lane():
    # Precision: a non-evasion keyword must not open the evasion lane (hybrid path).
    card = {"name": "Watcher", "oracle_text": "Vigilance"}
    assert ("evasion_self", "you") not in _keys_hybrid(card)


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


def test_themeless_one_one_does_not_open_voltron():
    # Precision: a 1/1 themeless legend is too small to be a commander-damage plan.
    chump = {
        "name": "Tiny Legend",
        "type_line": "Legendary Creature — Human",
        "power": "1",
        "toughness": "1",
        "oracle_text": "",
    }
    assert ("voltron_matters", "you") not in _keys_hybrid(chump)


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


def test_artifact_removal_does_not_open_artifacts_lane():
    # Precision: destroying an opponent's artifact is removal, not an artifact theme.
    card = {
        "name": "Disenchanter",
        "oracle_text": "When this creature enters, destroy target artifact or enchantment.",
    }
    assert ("artifacts_matter", "you") not in _keys_hybrid(card)


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
    # ADR-0027 β: the doubler is the canonical reason creature_etb rides a kept-mirror,
    # not the structural etb-trigger arm — phase models "triggers an additional time" as
    # a static replacement effect (no `etb` event), so the lane serves from the hybrid.
    # Real Yarok (snapshot): the permanent-ETB trigger doubler opens creature_etb.
    assert ("creature_etb", "you") in _real("Yarok, the Desecrated")


# ── Artifact-token makers ARE artifact commanders (Food/Treasure/Clue are artifacts) ─
# A Treasure / Food / Clue / Blood maker should open the artifacts lane so artifact
# payoffs (Academy Manufactor, Foundry Inspector, artifact sac) surface — the serve
# already credits them; the detector missed the lane-opening (Korvold, Gyome).
def test_treasure_maker_opens_artifacts_lane():
    # Real Goldspan Dragon (snapshot): a Treasure maker opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Goldspan Dragon")


def test_food_maker_opens_artifacts_lane():
    # Real Gyome, Master Chef (snapshot): a Food maker opens the artifacts lane.
    assert ("artifacts_matter", "you") in _real("Gyome, Master Chef")


def test_creature_token_maker_does_not_open_artifacts_lane():
    # Precision: a Soldier-token maker is NOT an artifacts commander.
    card = {
        "name": "Soldier Boss",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "At the beginning of your end step, create two 1/1 white "
        "Soldier creature tokens.",
    }
    assert ("artifacts_matter", "you") not in _keys_hybrid(card)


# ── Activated-ability commanders want the untap / copy / cost-reduction package ──
# A commander whose engine is a {T}: activated ability (Arcum, Captain Sisay, Ertai,
# Kaho, Sanctum Weaver) wants Training Grounds / Thousand-Year Elixir / Rings of
# Brighthearth — none of which any existing lane surfaced.
# ── activated_ability (ADR-0027 β: migrated regex→Card IR) ──────────────────────
# The lane fires from the IR arm (an Ability kind=='activated', cost tap/untap/
# genericmana, >=1 NON-ramp/attach effect — the is_mana_ability + SIDECAR-v15
# genericmana discriminators kill the land/rock/dork flood the bare cost-shape regex
# matched). The regex path no longer emits it (the _DETECTORS row is deleted), so the
# positive cases assert via the hybrid (IR) path.
def test_tap_ability_commander_opens_activated_lane():
    # Real Arcum Dagsson (snapshot): the {T}: sacrifice/tutor activated ability opens
    # the lane on the IR path; the deleted regex no longer emits it.
    assert ("activated_ability", "you") in _real("Arcum Dagsson")
    assert ("activated_ability", "you") not in _keys(test_card("Arcum Dagsson"))


def test_non_tap_vanilla_no_activated_lane():
    # Precision: a creature with no activated ability must not open the lane.
    card = {
        "name": "Beater",
        "type_line": "Legendary Creature — Giant",
        "oracle_text": "Trample\nWhenever this creature attacks, it gets +1/+1.",
        "power": "6",
        "toughness": "6",
    }
    assert ("activated_ability", "you") not in _keys(card)


# ── Multi-tribe anthem: "each creature that's a Barbarian, a Warrior, or a Berserker
# gets +2/+2" (Lovisa) — emit type_matters per named type so each tribe's creatures
# surface. The single-type patterns required 'other'/'you control', missing this form.
def test_multi_tribe_anthem_emits_each_type():
    # Real Lovisa Coldeyes (snapshot): the multi-tribe anthem emits one type_matters
    # subject per named type.
    subjects = {
        s.subject for s in test_signals("Lovisa Coldeyes") if s.key == "type_matters"
    }
    assert {"Barbarian", "Warrior", "Berserker"} <= subjects


def test_multi_tribe_anthem_ignores_non_subtype_words():
    # Precision: "each creature that's attacking gets +1/+0" names no tribe.
    card = {
        "name": "Attack Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Each creature that's attacking gets +1/+0.",
    }
    subjects = {s.subject for s in extract_signals(card) if s.key == "type_matters"}
    assert subjects == set() or "attacking" not in {x.lower() for x in subjects}


# ── Mana-cost activated abilities also want the activated-ability package ─────────
# A commander whose engine is a generic-mana-cost activated ability (The Scarab God
# '{2}{U}{B}: reanimate', Kenrith, Varragoth). The IR arm's mana branch gates on the
# SIDECAR-v15 'genericmana' cost token, which excludes cheap colored-only firebreathing
# ({R}:) — the regex's generic branch ({(?:\d+|x)\}) did the same.
def test_mana_cost_activated_ability_opens_lane():
    # Real The Scarab God (snapshot): the {2}{U}{B}: generic-mana activated ability opens
    # the lane on the IR path; the deleted regex no longer emits it.
    assert ("activated_ability", "you") in _real("The Scarab God")
    assert ("activated_ability", "you") not in _keys(test_card("The Scarab God"))


def test_cheap_firebreathing_does_not_open_activated_lane():
    # Precision: a bare colored-only pump ({R}: +1/+0) is firebreathing, not an
    # activated-ability engine — no generic numeral in the cost, so phase projects
    # cost='mana' WITHOUT the genericmana token and the arm's mana branch stays shut.
    card = {
        "name": "Firebreather",
        "type_line": "Legendary Creature — Dragon",
        "oracle_text": "Flying\n{R}: This creature gets +1/+0 until end of turn.",
    }
    fb_ir = _ir_with(
        Ability(
            kind="activated",
            cost="mana",
            effects=(Effect(category="pump", scope="you", raw="gets +1/+0"),),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_ir(card, fb_ir)}
    assert ("activated_ability", "you") not in keys
    assert ("activated_ability", "you") not in _keys(card)


# ── Snow matters (Isu the Abominable) — a real niche archetype with a clean anchor ──
def test_snow_commander_opens_snow_lane():
    # Real Isu the Abominable (snapshot): snow_matters is IR-served, not pure regex.
    assert ("snow_matters", "you") in _real("Isu the Abominable")
    assert ("snow_matters", "you") not in _keys(test_card("Isu the Abominable"))


def test_non_snow_card_does_not_open_snow_lane():
    card = {"name": "Bear", "type_line": "Creature — Bear", "oracle_text": "Vigilance"}
    assert ("snow_matters", "you") not in _keys_hybrid(card)


# ── Missing race tribes: build-around-able races with deep pools but no lords were
# absent from the membership vocab (gated at >=8 tribal-SUPPORT cards). A Kraken /
# Wolf / Shade / Yeti commander builds a pile of its tribe (Brinelin, Anara, Ihsan, Isu).
def test_kraken_commander_opens_kraken_tribe():
    # Real Brinelin, the Moon Kraken (snapshot): the Kraken type-line opens the tribe.
    sigs = test_signals("Brinelin, the Moon Kraken")
    assert any(s.key == "type_matters" and s.subject == "Kraken" for s in sigs)


def test_shade_and_wolf_and_yeti_tribes_open():
    for tl, sub in [
        ("Legendary Creature — Shade Knight", "Shade"),
        ("Legendary Creature — Wolf Beast", "Wolf"),
        ("Legendary Snow Creature — Yeti", "Yeti"),
    ]:
        c = {"name": "X", "type_line": tl, "oracle_text": ""}
        subs = {s.subject for s in extract_signals(c) if s.key == "type_matters"}
        assert sub in subs, f"{sub} not in {subs}"


def test_class_type_commander_does_not_open_class_tribe():
    # Precision: class types (Human/Wizard/Warrior) stay OUT — they're near-ubiquitous.
    c = {
        "name": "Spellslinger",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": "Whenever you cast an instant or sorcery spell, draw a card.",
    }
    subs = {s.subject for s in extract_signals(c) if s.key == "type_matters"}
    assert "Human" not in subs
    assert "Wizard" not in subs


def test_vanilla_matters_opens_for_no_abilities_commander():
    # ADR-0027: vanilla_matters migrated to the Card IR (the HasNoAbilities subject-
    # Filter predicate). Ruxa pumps "creatures you control with no abilities" — phase
    # carries the predicate on the pump effect's subject Filter, so the hybrid (IR)
    # path opens the lane; the regex producer is deleted.
    # Real Ruxa, Patient Professor (snapshot): phase carries the HasNoAbilities subject
    # predicate on the pump effect, so the IR path opens the lane; the regex producer is
    # deleted.
    assert ("vanilla_matters", "you") in _real("Ruxa, Patient Professor")
    assert ("vanilla_matters", "you") not in _keys(test_card("Ruxa, Patient Professor"))


# ── Toughness payoffs beyond "assigns combat damage equal to toughness" (Geralf) ──
# ADR-0027 β: toughness_combat migrated to the Card IR (both regex producers deleted),
# so it no longer fires from the pure-regex _keys() path — assert via the hybrid, which
# serves it from the byte-identical _TOUGHNESS_COMBAT_MIRROR over the kept_oracle.
def test_toughness_value_payoff_opens_toughness_lane():
    # Real Geralf, Visionary Stitcher (snapshot): the toughness-as-value payoff opens the
    # lane on the IR path; the migrated key no longer rides the regex path.
    assert ("toughness_combat", "you") in _real("Geralf, Visionary Stitcher")
    assert ("toughness_combat", "you") not in _keys(
        test_card("Geralf, Visionary Stitcher")
    )


def test_set_base_pt_does_not_open_toughness_lane():
    # Precision: "power and toughness are each equal to the number of X" is set-base-P/T,
    # not a toughness-as-value payoff. The migrated mirror keeps the "(?! are each)" veto.
    # Real Abominable Treefolk (snapshot): set-base-P/T, not a toughness-as-value payoff.
    assert ("toughness_combat", "you") not in _real("Abominable Treefolk")


# ── Pariah combo: a commander that prevents/redirects damage to ITSELF (Cho-Manno,
# Anti-Venom) is the unkillable redirect target — it wants Pariah-style redirect + the
# indestructible grants that keep the target alive. ADR-0027 β migrated damage_redirect
# to the Card IR (ARM A — name-aware self-prevention), so the lane now fires from the
# HYBRID (IR) path; the regex path drops it (the migration invariant).
def test_self_damage_prevention_opens_redirect_lane():
    # Real Cho-Manno + Anti-Venom (snapshot): name-aware self-prevention (ARM A) opens
    # the redirect lane on the IR path; the regex path no longer does (migration invariant).
    assert ("damage_redirect", "you") in _real("Cho-Manno, Revolutionary")
    assert ("damage_redirect", "you") in _real("Anti-Venom, Horrifying Healer")
    assert ("damage_redirect", "you") not in _keys(
        test_card("Cho-Manno, Revolutionary")
    )
    assert ("damage_redirect", "you") not in _keys(
        test_card("Anti-Venom, Horrifying Healer")
    )


# ── ARM B (the redirect clause): "the next N damage … dealt to ~ instead" — en-Kor,
# Reflect Damage, Captain's Maneuver. Disjoint from ARM A (name-aware self-prevention);
# rides _DAMAGE_REDIRECT_MIRROR (the exact deleted SWEEP regex) over the IR path.
def test_redirect_clause_opens_redirect_lane():
    # Real Captain's Maneuver (snapshot): the ARM B redirect clause opens the lane on
    # the IR path; the regex path no longer does.
    assert ("damage_redirect", "you") in _real("Captain's Maneuver")
    assert ("damage_redirect", "you") not in _keys(test_card("Captain's Maneuver"))


def test_fog_does_not_open_redirect_lane():
    # Precision: a fog ("prevent all combat damage this turn") is not self-redirect.
    # Holds on BOTH the regex path (it never fired) and the hybrid path (neither IR arm
    # matches — the name-aware ARM A wants "to <self>", ARM B wants "dealt to … instead").
    # Real Fog (snapshot): damage_prevention only — never self-redirect, on either path.
    assert ("damage_redirect", "you") not in _keys(test_card("Fog"))
    assert ("damage_redirect", "you") not in _real("Fog")


def test_aura_recursion_opens_voltron_lane():
    # Hakim: "return target Aura card ... attached to Hakim" — aura voltron, but the
    # detector caught "attach an Aura", not the "Aura ... attached" recursion form.
    # _matters sweep (ADR-0034): the recursion PERFORMS the attaching, so Hakim is on
    # the MAKER arm voltron_makers now (it carries no payoff sub-tell).
    assert ("voltron_makers", "you") in _real("Hakim, Loreweaver")


def test_passive_combat_damage_opens_combat_lane():
    # Hope of Ghirapur: "target player who was dealt combat damage by Hope this turn" —
    # a voltron/combat commander that cares about HAVING dealt combat damage (passive
    # form). It wants gear to connect (combat_damage lane carries the gear extra).
    # Real Hope of Ghirapur (snapshot): the passive "player who was dealt combat damage
    # by ~" form is recovered as a player-recipient combat_damage trigger, so the matters
    # lane fires.
    assert any(k == "combat_damage_matters" for k, _ in _real("Hope of Ghirapur"))


def test_multi_counter_placement_opens_counters_lane():
    # Minsc & Boo: "+1: Put three +1/+1 counters on up to one target creature" — a
    # recurring counter engine. Plural 'counters' (multi-placement) distinguishes it
    # from bare 'put a +1/+1 counter on it' self-growth.
    # Real Minsc & Boo (snapshot): "+1: Put three +1/+1 counters" is a counter engine.
    assert any(k == "plus_one_makers" for k, _ in _real("Minsc & Boo, Timeless Heroes"))


def test_self_counter_now_opens_counters_in_production():
    # ADR-0027: plus_one_matters migrated to the IR and now fires on ANY +1/+1
    # PLACEMENT regardless of recipient (CR 122.1 / 122.6) — bare self-growth is a
    # source too. The legacy regex EXCLUDED it; the regex path no longer emits the
    # migrated key at all, and the production hybrid path opens the lane.
    card = {
        "name": "Lonely Grower",
        "oracle_text": "Whenever this creature attacks, put a +1/+1 counter on it.",
    }
    assert not any(k == "plus_one_makers" for k, _ in _keys(card))  # regex: migrated
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_ir(card, ir)}
    assert any(k == "plus_one_makers" for k, _ in keys)


def test_opponent_library_exile_opens_opponents_mill():
    # Circu: "exile the top card of target player's library" — exile-mill of opponents,
    # a mill variant the graveyard detector (keyed on "graveyard") missed. ADR-0027 v29:
    # graveyard_matters migrated to the IR — the _GY_EXILE_MILL_OPP_RE producer rides the
    # byte-identical _graveyard_matters_clauses mirror (scope 'opponents'), so assert via
    # the hybrid path.
    # Real Circu, Dimir Lobotomist (snapshot): exile-mill of opponents' libraries.
    assert ("graveyard_matters", "opponents") in _real("Circu, Dimir Lobotomist")


def test_self_library_exile_does_not_open_opponents_mill():
    # Precision: impulse-drawing off YOUR OWN library is not opponent mill (hybrid path —
    # graveyard_matters is IR-served, ADR-0027 v29).
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


def test_a_creature_you_control_does_not_capture_creature():
    card = {
        "name": "Generic",
        "oracle_text": "Whenever a creature you control dies, draw a card.",
    }
    subs = {s.subject for s in extract_signals(card) if s.key == "type_matters"}
    assert "creature" not in {x.lower() for x in subs}
    assert "Creature" not in subs


def test_more_race_tribes_open():
    for tl, sub in [
        ("Legendary Creature — Griffin", "Griffin"),
        ("Legendary Creature — Leviathan", "Leviathan"),
        ("Legendary Creature — Wall", "Wall"),
        ("Legendary Creature — Human Samurai", "Samurai"),
        ("Legendary Creature — Sphinx", "Sphinx"),
    ]:
        c = {"name": "X", "type_line": tl, "oracle_text": ""}
        subs = {s.subject for s in extract_signals(c) if s.key == "type_matters"}
        assert sub in subs, f"{sub} not in {subs}"


def test_generic_class_types_still_excluded_from_membership():
    # Warrior / Soldier / Wizard are too ubiquitous for membership tribal.
    for cls in ("Warrior", "Soldier", "Wizard"):
        c = {
            "name": "X",
            "type_line": f"Legendary Creature — Human {cls}",
            "oracle_text": "",
        }
        subs = {s.subject for s in extract_signals(c) if s.key == "type_matters"}
        assert cls not in subs


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


def test_cheap_etb_or_expensive_vanilla_does_not_open_clone():
    # Precision: copying a CHEAP ETB isn't worth a clone, and a big VANILLA has no ETB
    # to re-fire — both need a high CMC AND an ETB.
    cheap = {
        "name": "Elvish Visionary",
        "type_line": "Creature — Elf Shaman",
        "cmc": 2.0,
        "oracle_text": "When this creature enters, draw a card.",
    }
    vanilla = {
        "name": "Colossus",
        "type_line": "Creature — Golem",
        "cmc": 8.0,
        "oracle_text": "Trample",
    }
    # ADR-0027 v30: wants_cloning migrated — assert via the hybrid path (the membership
    # gate now lives in extract_signals_ir).
    assert ("wants_cloning", "you") not in _keys_hybrid(cheap)
    assert ("wants_cloning", "you") not in _keys_hybrid(vanilla)


def test_high_cmc_dies_trigger_commander_opens_clone():
    # A high-CMC commander with a strong DEATH trigger (Keiga, Kokusho) is also worth
    # copying — a clone/token-copy re-fires the death trigger when the copy dies
    # (sac-loop staple). Short name, like Scryfall prints it.
    # Real Keiga + Kokusho (snapshot): high-CMC death-trigger commanders worth cloning.
    assert ("wants_cloning", "you") in _real("Keiga, the Tide Star")
    assert ("wants_cloning", "you") in _real("Kokusho, the Evening Star")


def test_cheap_dies_trigger_does_not_open_clone():
    # Precision: a CHEAP death-trigger creature isn't worth a clone.
    # Real Doomed Dissenter (snapshot): a CHEAP death-trigger creature isn't worth a clone.
    assert ("wants_cloning", "you") not in _real("Doomed Dissenter")


def test_land_enter_punisher_opens_burn_lane():
    # Zo-Zu the Punisher: opponents-landfall PUNISH — "whenever a land enters, deal 2 to
    # that land's controller". The landfall lane is the YOU payoff; this is the missing
    # opponents-scoped punish side.
    # Real Zo-Zu the Punisher (snapshot): the landfall-punish burn fires direct_damage.
    assert ("direct_damage", "you") in _real("Zo-Zu the Punisher")


def test_source_deals_damage_opens_burn():
    # The Red Terror: "whenever a red source you control deals damage … put a +1/+1
    # counter on The Red Terror" — a damage-MATTERS trigger CONDITION (CR 603.2)
    # reading someone ELSE's damage, not a direct_damage EFFECT of its own (the same
    # doubler/matters/prevention shed the crosswalk lane's own docstring documents —
    # "Damage DOUBLERS are a separate lane"). ADR-0039 W7 endgame PROMOTED
    # direct_damage off the legacy hybrid fallback: the pre-promotion legacy
    # _DIRECT_DAMAGE_MIRROR's "whenever a source you control deals damage"
    # alternative was a GENUINE OVER-FIRE (already MANDATORY-SHED-pinned on the
    # crosswalk path — see test_crosswalk.py's
    # test_direct_damage_excludes_doubler_matters_prevention_shed). The real
    # payoff lanes fire regardless: its OWN +1/+1 counter growth
    # (self_counter_grow) and its counter-placement ability (plus_one_makers).
    idents = _real("The Red Terror")
    assert ("direct_damage", "you") not in idents
    assert ("self_counter_grow", "you") in idents


def test_self_power_scaling_opens_counters():
    # Mona Lisa: "{T}: Add X mana, where X is Mona Lisa's power" — her value scales with
    # her OWN power, so she wants to pump it with +1/+1 counters (Stony Strength).
    # ADR-0027 β: self_counter_grow migrated to the Card IR — this self-power-scaling
    # cross-open is now served from the narrowed _SELF_COUNTER_GROW_MIRROR (hybrid path).
    # Real Mona Lisa, Science Geek (snapshot): value scales with her own power, so she
    # wants +1/+1 counters.
    assert any(k == "self_counter_grow" for k, _ in _real("Mona Lisa, Science Geek"))


def test_fling_target_power_does_not_open_self_counters():
    # Precision: "X is TARGET creature's power" (fling) isn't self-scaling.
    # ADR-0027 β: served from the IR path now (hybrid), so check there.
    # Real Fling (snapshot): "X is TARGET creature's power" isn't self-scaling.
    assert not any(k == "self_counter_grow" for k, _ in _real("Fling"))


def test_punish_non_attackers_opens_forced_attack():
    # Kratos: "deals damage = creatures that didn't attack this turn" — a force-attack
    # incentive (attack or take damage), a goad/aggro commander. ADR-0027: forced_attack
    # migrated to the Card IR; the "didn't attack this turn" PUNISHER tail rides a byte-
    # identical DET kept mirror in signals._IR_KEPT_DETECTORS, so it serves from the
    # hybrid path, not pure regex.
    # Real Kratos, God of War (snapshot): the "didn't attack this turn" punisher tail
    # opens the forced-attack lane.
    assert any(k == "forced_attack" for k, _ in _real("Kratos, God of War"))


# ── Outlaw tribal (Outlaws of Thunder Junction): Assassin/Mercenary/Pirate/Rogue/
# Warlock are collectively "outlaws" (Vial Smasher). ──
def test_outlaw_commander_opens_outlaw_lane():
    # Real Vial Smasher (snapshot): "another outlaw you control" opens the outlaw lane
    # on the IR path, not pure regex.
    assert ("outlaw_matters", "you") in _real("Vial Smasher, Gleeful Grenadier")
    assert ("outlaw_matters", "you") not in _keys(
        test_card("Vial Smasher, Gleeful Grenadier")
    )


def test_pacify_control_commander_opens_pillowfort():
    # Gwafa Hazid neutralizes opponents' creatures ("can't attack or block") — a
    # control/pillowfort identity that wants Propaganda / Ghostly Prison / Windborn Muse.
    # ADR-0027: stax_taxes migrated to the Card IR, so the deleted _DETECTORS pacify
    # producer no longer fires in the pure regex path — the lane comes through the hybrid
    # (the byte-identical _STAX_TAXES_MIRROR over the "creatures … can't attack" clause).
    # Real Gwafa Hazid, Profiteer (snapshot): "creatures ... can't attack or block" is a
    # pillowfort/stax tell on the IR path; the deleted regex producer no longer fires.
    assert ("stax_taxes", "opponents") in _real("Gwafa Hazid, Profiteer")
    assert ("stax_taxes", "opponents") not in _keys(test_card("Gwafa Hazid, Profiteer"))


def test_banding_commander_opens_banding_lane():
    # Ayesha Tanaka has Banding — she wants other banding creatures to form bands.
    # ADR-0027: has_banding migrated to the Card IR (the byte-identical
    # _IR_KEYWORD_MAP['banding'] keyword-array route), so it serves from the hybrid
    # path, not pure regex — the regex extract_signals no longer emits the migrated key.
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
    # the structural gain_life Effect, read by the gain_life signals arm.
    # _matters sweep (ADR-0034): gaining life is the MAKER arm → lifegain_makers.
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
    # the digit-keyed branch missed (no literal number). ADR-0027: direct_damage
    # migrated to the Card IR; "each player" is scope='each' (reaches every player, so
    # it's player-reachable AND symmetric), served from the structural scope arm via the
    # bare-IR hybrid path's oracle-fed kept detectors / mirror.
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
    # ADR-0027: power_matters migrated to the Card IR — the aggregate "greatest power
    # among creatures you control" form phase folds into an empty-predicate board_count,
    # recovered by the byte-identical _POWER_MATTERS_MIRROR. The regex path no longer
    # emits it, so assert via the hybrid (IR) path.
    # Real Arni Brokenbrow (snapshot): "greatest power among other creatures you control"
    # folds into a board_count the IR path recovers; the regex path no longer emits it.
    assert ("power_matters", "you") in _real("Arni Brokenbrow")


def test_plural_death_trigger_opens_death_matters():
    # "one or more creatures YOU CONTROL die" — the plural death conjugation ("die" with
    # "you control" between the noun and the verb). The regex required the noun adjacent
    # to "die", so Vraan / Éomer / G'raha-style plural triggers read uncovered.
    for oracle in [
        "Whenever one or more other creatures you control die, each opponent loses 2 "
        "life and you gain 2 life.",
        "Whenever one or more other creatures and/or artifacts you control die, draw a "
        "card.",
    ]:
        card = {
            "name": "X",
            "type_line": "Legendary Creature — Test",
            "oracle_text": oracle,
        }
        # ADR-0027: the plural "creatures you control die" branch rides the byte-
        # identical _DEATH_MATTERS_MIRROR on the IR path.
        assert "death_matters" in {
            s.key for s in extract_signals_ir(card, _bare_ir())
        }, oracle


def test_artifact_type_commander_opens_artifacts():
    # A commander that IS an artifact (type line has the Artifact card type) is an
    # artifact deck — wants affinity / cost reducers / artifact synergy, just as a
    # creature is a member of its own tribe (the type-line membership insight).
    # Real ED-E (snapshot): a commander that IS an artifact (type line) opens the lane
    # via the type_line membership arm.
    assert ("artifacts_matter", "you") in _real("ED-E, Lonesome Eyebot")
    # A plain (non-artifact) creature commander does NOT open the artifacts lane
    # (synthetic negative — no real card needed for the absence probe).
    human = {
        "name": "Some Human",
        "type_line": "Legendary Creature — Human Noble",
        "oracle_text": "Vigilance",
    }
    assert ("artifacts_matter", "you") not in {
        (s.key, s.scope) for s in extract_signals_ir(human, _bare_ir())
    }
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
    # (stripped before detection), so match the KEYWORD (Dan's point). ADR-0027:
    # attack_matters migrated to the Card IR, so the lane fires from the Boast keyword in
    # _IR_KEYWORD_MAP via the hybrid path — NOT the deleted regex keyword row.
    # Real Varragoth, Bloodsky Sire (snapshot): the Boast keyword opens attack_matters on
    # the IR path (the keyword map), not the deleted regex keyword row.
    assert ("attack_matters", "you") not in _keys(test_card("Varragoth, Bloodsky Sire"))
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
    # creatures_matter MIGRATED to the Card IR (ADR-0027), so it fires from the
    # board_count marker the projection recovers, via the hybrid path — NOT the
    # deleted regex producer.
    # Real Shanna, Sisay's Legacy (snapshot): "+1/+1 for each creature you control" fires
    # from the board_count marker on the IR path; the regex producer is deleted.
    assert "creatures_matter" not in {
        s.key for s in extract_signals(test_card("Shanna, Sisay's Legacy"))
    }
    assert "creatures_matter" in {s.key for s in test_signals("Shanna, Sisay's Legacy")}


def test_ability_words_open_their_lane():
    # CR 207.2c ability-word audit: most ability words already open via their spelled-out
    # condition, but three didn't. The italic word itself prints in the oracle, so match
    # it (no rules meaning, but unambiguous): Metalcraft→artifacts, Heroic→targeting,
    # Formidable→power.
    cases = [
        (
            "metalcraft",
            "Metalcraft — This gets +2/+2 as long as you control three or "
            "more artifacts.",
            "artifacts_matter",
        ),
        (
            "heroic",
            "Heroic — Whenever you cast a spell that targets this creature, put a "
            "+1/+1 counter on it.",
            "targeting_matters",
        ),
        (
            "formidable",
            "Formidable — {2}: Draw a card. Activate this ability only if "
            "creatures you control have total power 8 or greater.",
            "power_matters",
        ),
    ]
    for aw, oracle, key in cases:
        card = {
            "name": f"{aw} Boss",
            "type_line": "Legendary Creature — Test",
            "oracle_text": oracle,
        }
        # ADR-0027 t2b5-C: targeting_matters (heroic) migrated to the Card IR (the kept
        # word mirror), so the regex path no longer emits it — assert via the hybrid (IR)
        # path, which serves migrated keys from the IR and non-migrated keys from regex.
        assert key in {s.key for s in extract_signals_ir(card, _bare_ir())}, aw


def test_triggered_counter_placement_opens_counters():
    # Leinore (Coven) / Shelinda: a recurring trigger that places a +1/+1 counter on a
    # CHOSEN creature is a counters engine. ADR-0027 + _matters sweep (ADR-0034): the
    # +1/+1 PLACEMENT arm is the MAKER side, so it fires plus_one_makers on ANY +1/+1
    # placement regardless of recipient (self / on-others / on-attacking — all are
    # sources, CR 122.1 / 122.6), so even bare self-growth ("put a +1/+1 counter on it")
    # opens the maker lane. Assert via the hybrid path.
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    for oracle in [
        "At the beginning of combat on your turn, put a +1/+1 counter on up to one "
        "target creature you control.",
        "Whenever another creature you control enters, put a +1/+1 counter on that "
        "creature if its power is less than this creature's power.",
        # Self-growth now also fires (a placement is a source whoever receives it).
        "Whenever this creature attacks, put a +1/+1 counter on it.",
    ]:
        card = {
            "name": "X",
            "type_line": "Legendary Creature — Test",
            "oracle_text": oracle,
        }
        keys = {s.key for s in extract_signals_ir(card, ir)}
        assert "plus_one_makers" in keys, oracle


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
    # the gain (no "gain life" oracle text), so open lifegain via the keyword. ADR-0027
    # β: lifelink→lifegain_matters MOVED to the IR-only _IR_KEYWORD_MAP, so it serves
    # from the hybrid via the IR's Lifelink keyword (the IR Face carries keywords[]).
    # Real Elenda, Saint of Dusk (snapshot): the Lifelink keyword opens lifegain via the
    # IR-only keyword map (the IR Face carries keywords[]).
    # _matters sweep (ADR-0034): a lifelink bearer is a lifegain SOURCE → the keyword
    # map emits the MAKER arm lifegain_makers.
    assert ("lifegain_makers", "you") in _real("Elenda, Saint of Dusk")


def test_counter_keyword_commander_opens_counters():
    # A commander whose own keyword is a +1/+1-counter mechanic (Exava=Unleash,
    # Cayth, Indoraptor=Bloodthirst) is a counters deck — open plus_one_makers.
    # ADR-0027 + _matters sweep (ADR-0034): these keywords are +1/+1 MAKERS — they
    # project a place_counter(p1p1) STRUCTURALLY (not via the keyword array), so assert
    # via the hybrid path with the structural IR phase produces for them.
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    for kw in ["Unleash", "Bloodthirst", "Graft", "Undying", "Riot"]:
        card = {
            "name": f"{kw} Lord",
            "type_line": "Legendary Creature — Test",
            "keywords": [kw],
            "oracle_text": "Some ability.",
        }
        keys = {s.key for s in extract_signals_ir(card, ir)}
        assert "plus_one_makers" in keys, kw


def test_archetype_keywords_open_their_lane():
    # CR-keyword audit (Dan): an archetype-defining keyword ability on the COMMANDER
    # opens that lane via the keyword (the mechanic is reminder text, stripped). Prowess
    # (spellcast_matters) is migrated (ADR-0027 SIDECAR 50), so it reads from the
    # _IR_KEYWORD_MAP via the hybrid path now (byte-identical Scryfall keyword array).
    card = {
        "name": "Prowess Lord",
        "type_line": "Legendary Creature — Test",
        "keywords": ["Prowess"],
        "oracle_text": "Some ability.",
    }
    assert ("spellcast_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_ir(card, _bare_ir())
    }
    # ADR-0027: Bushido / Annihilator (attack_matters) are migrated — their attack
    # condition is reminder text, so the lane fires from the keyword in _IR_KEYWORD_MAP
    # via the hybrid, NOT the deleted regex keyword row.
    for kw in ["Bushido", "Annihilator"]:
        card = {
            "name": f"{kw} Lord",
            "type_line": "Legendary Creature — Test",
            "keywords": [kw],
            "oracle_text": "Some ability.",
        }
        ir = Card(oracle_id="x", name="X", faces=(Face(name="X", keywords=(kw,)),))
        assert ("attack_matters", "you") not in {
            (s.key, s.scope) for s in extract_signals(card)
        }, kw
        assert ("attack_matters", "you") in {
            (s.key, s.scope) for s in extract_signals_ir(card, ir)
        }, kw
    # ADR-0027: Exploit (sacrifice_outlets) and Afflict (lifeloss_makers) are migrated
    # — phase models both as a STRUCTURAL effect (exploit's sacrifice, afflict's
    # lose_life), so they fire from the IR, not the regex keyword path. _matters sweep
    # (ADR-0034): afflict CAUSES opponents to lose life (a lose_life MAKER), so it fires
    # lifeloss_makers, not the lifeloss_matters payoff.
    afflict = {
        "name": "Afflict Lord",
        "type_line": "Legendary Creature — Test",
        "keywords": ["Afflict"],
        "oracle_text": "Afflict 2",
    }
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(Effect(category="lose_life", scope="any"),),
        )
    )
    assert ("lifeloss_makers", "opponents") in {
        (s.key, s.scope) for s in extract_signals_ir(afflict, ir)
    }


def test_attack_conditional_keywords_open_attack_matters():
    # Same class as Boast: keywords whose "as it attacks" / "attacked this turn"
    # condition lives in stripped reminder text — Exert (CR 702.107) and Myriad
    # (CR 702.116, attacking copies). ADR-0027: attack_matters migrated, so the lane
    # fires from the keyword in _IR_KEYWORD_MAP via the hybrid, NOT the regex keyword row.
    for kw in ["Exert", "Myriad"]:
        card = {
            "name": f"{kw} Boss",
            "type_line": "Legendary Creature — Test",
            "keywords": [kw],
            "oracle_text": "Some ability.",
        }
        ir = Card(oracle_id="x", name="X", faces=(Face(name="X", keywords=(kw,)),))
        assert ("attack_matters", "you") not in {
            (s.key, s.scope) for s in extract_signals(card)
        }, kw
        assert ("attack_matters", "you") in {
            (s.key, s.scope) for s in extract_signals_ir(card, ir)
        }, kw


def test_past_tense_count_payoffs_open_their_lane():
    # Tense audit (Dan): past-tense "this turn" COUNT payoffs are a class, like
    # "died this turn". Each rewards an accumulated count and should open the present-
    # tense lane. Verified real templating + commanders via bulk.
    # Gnostro / Rionya: "for each spell you've cast this turn" — spellcast_matters is
    # migrated (ADR-0027 SIDECAR 50), so the past-tense count payoff fires from the
    # byte-identical _detect_spellcast_matters kept mirror over the dict oracle via the
    # hybrid (bare IR), NOT the deleted regex producer.
    spellcast = {
        "name": "X",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Scry X, where X is the number of spells you've cast this turn.",
    }
    assert "spellcast_matters" in {
        s.key for s in extract_signals_ir(spellcast, _bare_ir())
    }
    # ADR-0027: attack_matters migrated — the combat-count "attacked this turn" payoff
    # (Varragoth / Relentless Assault) fires from the _ATTACK_MATTERS_MIRROR over the
    # dict oracle via the hybrid (empty IR), NOT the deleted regex producer.
    attack = {
        "name": "X",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Draw a card for each creature you control that attacked this turn.",
    }
    assert "attack_matters" not in {s.key for s in extract_signals(attack)}
    assert "attack_matters" in {s.key for s in extract_signals_ir(attack, _bare_ir())}
    # ADR-0027: lifeloss is migrated — Neheb / Rakdos "for each 1 life your opponents
    # have lost this turn" fires from the IR's _LOST_LIFE_TURN drain marker. _matters
    # sweep (ADR-0034): the marker folds into the structural lose_life MAKER arm, so it
    # fires lifeloss_makers (the whole lose_life arm is the maker side of the split).
    neheb = {
        "name": "Neheb",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Add {R} for each 1 life your opponents have lost this turn.",
    }
    from mtg_utils._card_ir.project import project_card

    neheb_ir = project_card([{**neheb, "card_type": {"core_types": ["Creature"]}}])
    assert "lifeloss_makers" in {s.key for s in extract_signals_ir(neheb, neheb_ir)}
    # ADR-0027 β: draw_matters is migrated — Proft / Kydele "for each card you've
    # drawn this turn" is a count-operand payoff with NO `drawn` trigger, so it fires
    # from the byte-identical draw_matters kept-mirror in the IR path (which scans the
    # reminder-stripped oracle), NOT the deleted regex producer.
    proft = {
        "name": "Proft",
        "type_line": "Legendary Creature — Test",
        "oracle_text": (
            "This creature gets +1/+1 for each card you've drawn this turn."
        ),
    }
    proft_ir = project_card([{**proft, "card_type": {"core_types": ["Creature"]}}])
    assert "draw_matters" in {s.key for s in extract_signals_ir(proft, proft_ir)}


def test_past_tense_death_count_opens_death_matters():
    # "create a Treasure for each creature that DIED this turn" — a past-tense death-COUNT
    # payoff (Mahadi, Gadrak, Shessra). The detector keyed on the present-tense trigger
    # "dies"/"die" and missed the morbid "died this turn" count (31 legendary creatures).
    for oracle in [
        "At the beginning of your end step, create a Treasure token for each creature "
        "that died this turn.",
        "At the beginning of your end step, if a creature died this turn, you may pay 2 "
        "life. If you do, draw a card.",
    ]:
        card = {
            "name": "X",
            "type_line": "Legendary Creature — Test",
            "oracle_text": oracle,
        }
        # ADR-0027: the morbid "died this turn" count payoff rides the byte-identical
        # _DEATH_MATTERS_MIRROR on the IR path.
        assert "death_matters" in {
            s.key for s in extract_signals_ir(card, _bare_ir())
        }, oracle


def test_plural_death_does_not_open_on_dice():
    # Precision: a dice "die" ("roll a six-sided die") must NOT read as a death trigger.
    # ADR-0027: the precision boundary now lives in the IR-path _DEATH_MATTERS_MIRROR
    # (its "creatures? … die" arm requires a creature/permanent/token subject, never the
    # bare dice "die"), so assert against the hybrid path.
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


def test_keyword_grant_lord_gain_opens_type_matters():
    # "Spirits you control GAIN …" — a keyword-grant tribal lord ("gain", which the
    # have/has pattern missed). 33 tribe-specific cards (Valiant Knight, Quintorius).
    # Isolated to the gain clause (no "get"/"have") so it actually exercises the fix.
    card = {
        "name": "Grant Lord",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Spirits you control gain flying and hexproof.",
    }
    # ADR-0027: type_matters migrated → hybrid path.
    subs = _subjects_hybrid(card, "type_matters")
    assert "Spirit" in subs


def test_singular_lord_has_opens_type_matters():
    # "Each Ally you control HAS …" — the singular lord conjugation ("has" not "have").
    # Real Great Divide Guide (snapshot): "Each Ally you control has …" — the singular
    # "has" lord conjugation opens the Ally tribe.
    subs = {
        s.subject for s in test_signals("Great Divide Guide") if s.key == "type_matters"
    }
    assert "Ally" in subs


def test_tribe_creatures_you_control_lord_opens_type_matters():
    # Canonical tribal-lord wording "Goblin creatures you control get +1/+1" — "you
    # control" sits between the tribe and the verb, which the lord patterns missed (the
    # "Xs you control get" form captures "creatures", the "X creatures get" form needs
    # adjacency). Use a NON-Goblin commander so this tests the oracle path, not the
    # type-line membership rule.
    card = {
        "name": "Goblin Buffer",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": "Goblin creatures you control get +1/+1.",
    }
    # ADR-0027: type_matters migrated → hybrid path.
    subs = _subjects_hybrid(card, "type_matters")
    assert "Goblin" in subs


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
    # one of your OTHER opponents — firing the reward (CR 701.38b). ADR-0027: migrated
    # to the IR — the regex path no longer emits it; the hybrid path serves it from the
    # _GOAD_REWARD_REF marker (here mirrored as a goad_all effect).
    # Real Gahiji, Honored One (snapshot): the "attacks one of your opponents" reward
    # opens goad on the IR path; the regex path no longer emits it.
    assert ("goad_makers", "opponents") not in _keys(test_card("Gahiji, Honored One"))
    assert ("goad_makers", "opponents") in _real("Gahiji, Honored One")


# ── Long-tail coverage clusters (workflow-diagnosed, verify-before-add) ────────


def _subjects(card, key):
    return {s.subject for s in extract_signals(card) if s.key == key}


def _subjects_hybrid(card, key):
    # ADR-0027: subjects from the HYBRID/IR path (for migrated subject-bearing keys
    # like keyword_tribe, whose kept mirror reads the record's oracle_text).
    return {s.subject for s in extract_signals_ir(card, _bare_ir()) if s.key == key}


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
    # impulse engine ("look at and" splits "you may"/"play"). ADR-0027 β: impulse_top_play
    # migrated to the Card IR, so the regex path no longer fires it; the hybrid serves it
    # (here via the per-clause kept mirror's "you may look at and play" arm — a bare IR
    # routes to the IR path, and the structural cast_from_zone arm also fires on the real
    # card's IR).
    # Real Headliner Scarlett (snapshot): "you may look at and play that card" is an
    # impulse engine on the IR path; the regex path no longer fires it.
    assert ("impulse_top_play", "you") not in _keys(test_card("Headliner Scarlett"))
    assert ("impulse_top_play", "you") in _real("Headliner Scarlett")


def test_extra_upkeep_lane_opens():
    # ADR-0027: extra_upkeep migrated to the Card IR — phase's `extra_upkeep` effect
    # category (Obeka, The Ninth Doctor — "additional upkeep step"), read via
    # _DOER_EFFECT_KEYS, so the lane opens through the hybrid IR path, not the regex.
    # Real Obeka, Splitter of Seconds + The Ninth Doctor (snapshot): both grant an
    # "additional upkeep step" via phase's extra_upkeep effect, opening the lane on the
    # IR path, not regex.
    assert ("extra_upkeep", "you") in _real("Obeka, Splitter of Seconds")
    assert ("extra_upkeep", "you") not in _keys(test_card("Obeka, Splitter of Seconds"))
    assert ("extra_upkeep", "you") in _real("The Ninth Doctor")
    assert ("extra_upkeep", "you") not in _keys(test_card("The Ninth Doctor"))


def test_extra_end_step_lane_opens():
    # Y'shtola Rhul grants an additional end step; the end-step payoff lane must open.
    # Real Y'shtola Rhul (snapshot): the "additional end step" grant is recovered by the
    # extra_end dropped-static face marker, opening the lane on the IR path, not regex.
    assert ("extra_end_step", "you") in _real("Y'shtola Rhul")
    assert ("extra_end_step", "you") not in _keys(test_card("Y'shtola Rhul"))


def test_extra_beginning_phase_decomposes_to_upkeep_and_draw():
    # CR 501.1: the beginning phase contains untap, upkeep, AND draw steps — so an
    # extra beginning phase (Sphinx of the Second Sun) re-triggers upkeep- and
    # draw-step payoffs. The untap step has no servable payoff, so no untap lane.
    # ADR-0027: phase mis-routes "additional beginning phase" to extra_combats, so the
    # grant is recovered by an `_EXTRA_BEGINNING_PHASE_GRANT` dropped-static face
    # marker emitting BOTH extra_upkeep + extra_draw, read through the hybrid IR path.
    # Real Sphinx of the Second Sun (snapshot): the "additional beginning phase" grant is
    # recovered as BOTH extra_upkeep + extra_draw, opening both lanes on the IR path.
    hybrid = _real("Sphinx of the Second Sun")
    assert ("extra_upkeep", "you") in hybrid
    assert ("extra_draw_step", "you") in hybrid
    keys = _keys(test_card("Sphinx of the Second Sun"))
    assert ("extra_upkeep", "you") not in keys
    assert ("extra_draw_step", "you") not in keys


def test_flying_from_top_opens_keyword_tribe():
    # Errant and Giada — "cast spells with flash or flying from the top" rewards
    # fliers; open the Flying keyword-tribe lane. ADR-0027: keyword_tribe migrated to
    # the Card IR (a subject-carrying kept mirror over the record's oracle_text), so
    # assert against the HYBRID path with a bare IR.
    # Real Errant and Giada (snapshot): "cast spells with flash or flying from the top"
    # rewards fliers — opens the Flying keyword-tribe lane.
    sigs = test_signals("Errant and Giada")
    assert ("keyword_tribe", "you") in {(s.key, s.scope) for s in sigs}
    assert "Flying" in {s.subject for s in sigs if s.key == "keyword_tribe"}


def test_yasharn_opens_stax_taxes():
    # Yasharn's cost-lock is a tax piece; the lane must OPEN so its hatebear
    # synergy package (Thalia, Archon of Emeria, …) is surfaced. ADR-0027: stax_taxes
    # migrated to the Card IR, so the lane is asserted through the hybrid path (the
    # byte-identical _STAX_TAXES_MIRROR reproduces the "players can't pay life or
    # sacrifice nonland permanents" firing the kept SWEEP row also carries).
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
    # trigger. spellcast_matters is migrated (ADR-0027 SIDECAR 50); the cost-reducer has
    # NO structural cast_spell trigger, so it rides the byte-identical
    # _detect_spellcast_matters kept mirror via the hybrid path.
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
    # ADR-0027: theft_matters migrated to the Card IR (a byte-identical THEFT_MATTERS_
    # REGEX kept mirror over the reminder-stripped oracle), so it serves from the hybrid
    # path, not pure regex. ADR-0034 _matters sweep: the steal-and-cast MAKER arm now
    # emits theft_makers (the LOW want-side cross-open is wants_theft).
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
    # ADR-0027: noncombat_damage_payoff is migrated to the Card IR (a byte-identical
    # NONCOMBAT_DAMAGE_PAYOFF_REGEX kept word mirror), so it surfaces only on the hybrid
    # path — the regex producer is deleted.
    # Real Kaervek the Merciless (snapshot): MV-scaling noncombat damage off opponents'
    # spells is a burn-engine payoff.
    assert ("noncombat_damage_payoff", "you") in _real("Kaervek the Merciless")


def test_opponent_lost_life_this_turn_opens_drain():
    # ADR-0039 W7: lifeloss_makers PROMOTED off the legacy _LOST_LIFE_TURN
    # marker — Sygg's "if an opponent lost 3 or more life this turn, you
    # may draw a card" is the condition_reference shed class (CR 603.4
    # intervening "if" / CR 603.2): a triggering CONDITION scaling a
    # DIFFERENT effect (the draw), never the card's OWN life-loss action.
    # The legacy marker's bare "lost...life" match fired regardless of
    # clause role; the crosswalk's structural read correctly finds no
    # LoseLife node to attribute to Sygg itself.
    # Real Sygg, River Cutthroat (snapshot).
    ident = ("lifeloss_makers", "opponents")
    idents = _real("Sygg, River Cutthroat")
    assert ident not in idents


def test_turn_target_face_up_opens_facedown():
    # Kaust turns a TARGET face-down creature face up + rewards "turned face up
    # this turn" — a morph/face-down payoff the detector missed (self-only form).
    # Real Kaust, Eyes of the Glade (snapshot): the turn-target-face-up + "turned face up
    # this turn" payoff opens facedown on the IR path, not pure regex.
    assert ("facedown_matters", "you") in _real("Kaust, Eyes of the Glade")
    assert ("facedown_matters", "you") not in _keys(
        test_card("Kaust, Eyes of the Glade")
    )


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
    # ETB distributes art stickers). The `\bstickers?\b` mirror matches any mention —
    # sticker is a dedicated mechanic, so "art sticker"/"distribute … stickers" is
    # on-theme. ADR-0027: stickers_matter migrated to the Card IR (a byte-identical
    # STICKERS_MATTER_REGEX kept word mirror), so it serves from the hybrid path.
    # Real Roxi, Publicist to the Stars (snapshot): art-sticker references open the
    # stickers lane.
    assert ("stickers_matter", "you") in _real("Roxi, Publicist to the Stars")
