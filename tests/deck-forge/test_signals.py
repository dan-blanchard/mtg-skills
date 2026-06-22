"""Tests for deterministic signal extraction (the discovery-engine keystone).

The headline guard: a signal that concerns OPPONENTS' graveyards must be scoped
"opponents", never a generic graveyard signal that would justify self-mill (the
Tinybones overgeneralization the whole tool exists to prevent).
"""

from mtg_utils._deck_forge.signals import (
    Signal,
    aggregate_signals,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter


def _keys(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


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
# the hybrid to the IR path.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _keys_hybrid(card):
    return {(s.key, s.scope) for s in extract_signals_hybrid(card, _bare_ir())}


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
    # The Tinybones case: benefits from OPPONENTS' graveyards filling.
    card = {
        "name": "Tinybones, the Pickpocket",
        "type_line": "Legendary Creature — Skeleton Rogue",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones deals combat damage to a player, you "
            "may cast target nonland permanent card from that player's graveyard, "
            "and mana of any type can be spent to cast that spell."
        ),
    }
    sigs = extract_signals(card)
    gy = [s for s in sigs if s.key == "graveyard_matters"]
    assert gy, "expected a graveyard signal"
    assert all(s.scope == "opponents" for s in gy)
    # It must NOT be scoped to 'you' — that would justify self-mill.
    assert ("graveyard_matters", "you") not in _keys(card)


def test_graveyard_signal_scoped_to_you_for_reanimator():
    card = {
        "name": "Reanimator",
        "oracle_text": "Return target creature card from your graveyard to the battlefield.",
    }
    assert ("graveyard_matters", "you") in _keys(card)


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
    card = {"name": "Air Elemental", "oracle_text": "Flying"}
    assert extract_signals(card) == []


JYOTI = {
    "name": "Jyoti, Moag Ancient",
    "oracle_text": (
        "When Jyoti enters, create a 1/1 green Forest Dryad land creature token "
        "for each time you've cast your commander from the command zone this game. "
        "(They're affected by summoning sickness.)\n"
        "At the beginning of each combat, land creatures you control get +X/+X "
        "until end of turn, where X is Jyoti's power."
    ),
}


def test_land_creatures_matter_detected_on_jyoti():
    # ADR-0027: land_creatures_matter migrated to the Card IR — assert via the hybrid
    # path. Jyoti makes a Land+Creature token (the maker arm) and anthems land
    # creatures (a pump over the same dual-type subject); the generic-creature anthem
    # below carries the creatures_matter regression guard.
    jyoti_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(card_types=("Creature", "Land"), controller="you"),
                    raw="create a 1/1 green Forest Dryad land creature token",
                ),
            ),
        ),
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(card_types=("Creature",), controller="you"),
                    raw="creatures you control get +X/+X",
                ),
            ),
        ),
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(JYOTI, jyoti_ir)}
    # The defining theme of the commander — must be its own signal, not collapsed
    # into generic "creatures matter".
    assert ("land_creatures_matter", "you") in keys
    # The generic go-wide signal still fires too (regression safety).
    assert ("creatures_matter", "you") in keys


def test_land_creatures_matter_from_anthem_payoff():
    # ADR-0027: served from a pump over a Land+Creature dual-type subject.
    sylvan = {
        "name": "Sylvan Advocate",
        "oracle_text": (
            "Vigilance\nAs long as you control six or more lands, this creature "
            "and land creatures you control get +2/+2."
        ),
    }
    sylvan_ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(card_types=("Creature", "Land"), controller="you"),
                    raw="~ and land creatures you control get +2/+2",
                ),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(sylvan, sylvan_ir)}
    assert ("land_creatures_matter", "you") in keys


def test_plant_token_maker_is_not_a_land_creatures_signal():
    # Avenger makes *Plant* creature tokens — never "land creatures". The whole
    # point of the scoped vocabulary: this must NOT register as land-creatures.
    # ADR-0027: assert via the hybrid path with a Plant (not Land) token subject —
    # neither the structural maker arm nor the kept oracle mirror fires.
    avenger = {
        "name": "Avenger of Zendikar",
        "oracle_text": (
            "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control."
        ),
    }
    avenger_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Plant",),
                        controller="you",
                    ),
                    raw="create a 0/1 green Plant creature token",
                ),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(avenger, avenger_ir)}
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
        s
        for s in extract_signals_hybrid(etb_card, _bare_ir())
        if s.key == "creature_etb"
    )
    assert etb.source == "ETB Boss"
    gy_card = {
        "name": "Yard Boss",
        "oracle_text": "Return a creature card from your graveyard to your hand.",
    }
    quoting = next(s for s in extract_signals(gy_card) if s.key == "graveyard_matters")
    assert quoting.source == "Yard Boss"
    assert "your graveyard" in quoting.text.lower()


def test_aggregate_dedupes_across_records():
    # ADR-0027 β: aggregate_signals walks the legacy regex path (extract_signals), so
    # the example uses a still-regex-served lane (graveyard_matters "your graveyard");
    # creature_etb has migrated to the IR and no longer rides the regex path.
    a = {
        "name": "A",
        "oracle_text": "Return a creature card from your graveyard to your hand.",
    }
    b = {
        "name": "B",
        "oracle_text": "Exile a creature card from your graveyard, then gain 1 life.",
    }
    agg = aggregate_signals([a, b])
    gy = [s for s in agg if s.key == "graveyard_matters" and s.scope == "you"]
    assert len(gy) == 1  # deduped by (key, scope, subject)


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
CELES = {
    "name": "Celes, Rune Knight",
    "type_line": "Legendary Creature — Human Wizard Knight",
    "oracle_text": (
        "When Celes enters, discard any number of cards, then draw that many cards "
        "plus one.\n"
        "Whenever one or more other creatures you control enter, if one or more of them "
        "entered from a graveyard or was cast from a graveyard, put a +1/+1 counter on "
        "each creature you control."
    ),
    "color_identity": ["B", "R", "W"],
}


def test_celes_is_not_reanimator_cast_from_graveyard_is_a_separate_axis():
    # The corrected boundary: an "entered/cast from a graveyard" PAYOFF is graveyard
    # recursion (escape/disturb/flashback), not the active-reanimation archetype.
    assert ("reanimator", "you") not in _keys_hybrid(CELES)
    # The graveyard FUEL still fires (Celes fills/uses its own graveyard).
    assert ("graveyard_matters", "you") in _keys_hybrid(CELES)


def test_reanimator_fires_for_active_creature_reanimation_via_ir():
    # A CREATURE that returns a creature card from a graveyard to the battlefield IS
    # the reanimator archetype — read from the structural `reanimate` IR effect.
    card = {
        "name": "Loyal Retainers",
        "type_line": "Creature — Human Advisor",
        "oracle_text": (
            "Sacrifice this creature: Return target legendary creature card "
            "from your graveyard to the battlefield."
        ),
    }
    ir = _ir_with(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="reanimate",
                    scope="you",
                    subject=Filter(card_types=("Creature",)),
                    raw="Return target legendary creature card from your graveyard to the battlefield.",
                ),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}
    assert ("reanimator", "you") in keys


def test_reanimator_not_fired_by_regrowth_to_hand():
    # Returning a card to HAND is graveyard-return, not reanimation — no payoff trigger.
    card = {
        "name": "Regrowth",
        "oracle_text": "Return target card from your graveyard to your hand.",
    }
    assert ("reanimator", "you") not in _keys_hybrid(card)


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
    teysa = {
        "name": "Teysa Karlov",
        "oracle_text": (
            "If a creature dying causes a triggered ability of a permanent you control "
            "to trigger, that ability triggers an additional time.\n"
            "Creature tokens you control have vigilance and lifelink."
        ),
    }
    # ADR-0027: death_matters migrated to the Card IR; the "dying"+"trigger" death-
    # doubler branch now rides the byte-identical _DEATH_MATTERS_MIRROR on the IR path.
    assert any(k == "death_matters" for k, _ in _keys_hybrid(teysa))


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
    sythis = {
        "name": "Sythis, Harvest's Hand",
        "type_line": "Legendary Enchantment Creature — Nymph",
        "oracle_text": "Whenever you cast an enchantment spell, you gain 1 life and draw a card.",
    }
    keys = _keys(sythis)
    assert ("enchantments_matter", "you") in keys
    assert not any(k == "spellcast_matters" for k, _ in keys)


def test_affinity_and_artifact_cast_open_artifacts_lane():
    # Affinity (reminder text stripped) + casting artifacts from graveyard make Emry an
    # artifacts commander; she must open the Artifacts lane.
    emry = {
        "name": "Emry, Lurker of the Loch",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "oracle_text": "Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nWhen Emry enters, mill four cards.\n{T}: Choose target artifact card in your graveyard. You may cast that card this turn. (You still pay its costs. Timing rules still apply.)",
    }
    assert ("artifacts_matter", "you") in _keys(emry)
    sai = {
        "name": "Sai, Master Thopterist",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": "Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.\n{1}{U}, Sacrifice two artifacts: Draw a card.",
    }
    assert ("artifacts_matter", "you") in _keys(sai)


def test_token_doubler_opens_tokens_lane():
    # A token DOUBLER (Adrix) wants token-MAKERS to double — it must open the tokens
    # lane, not only "Doubling".
    adrix = {
        "name": "Adrix and Nev, Twincasters",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "oracle_text": "Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.",
    }
    assert ("tokens_matter", "you") in _keys(adrix)


# ── Landfall: a land-recursion commander opens the lands lane (the Windgrace case) ─
# A commander whose payoff replays lands from the graveyard ("return … land cards from
# your graveyard to the battlefield") is a lands-matter commander and must open the
# landfall lane so its payoffs (Lotus Cobra / Scute Swarm) surface, even with no literal
# "landfall" / "play an additional land".
def test_land_recursion_commander_opens_landfall_lane():
    windgrace = {
        "name": "Lord Windgrace",
        "oracle_text": (
            "+2: Discard a card, then draw a card. If a land card is discarded this way, draw an additional card.\n−3: Return up to two target land cards from your graveyard to the battlefield.\n−11: Destroy up to six target nonland permanents, then create six 2/2 green Cat Warrior creature tokens with forestwalk.\nLord Windgrace can be your commander."
        ),
    }
    assert ("landfall", "you") in _keys(windgrace)


# ── Lifegain payoffs that gate on HAVING gained life (Aerith / Celestine) ────────
# "if you gained life this turn" / "the amount of life you gained this turn" is a
# lifegain PAYOFF — it cares whether you gained life — but the detector only caught
# "whenever you gain life". These commanders showed ONLY an incidental graveyard
# signal; their real theme (lifegain) was invisible.
def test_lifegain_conditional_payoff_opens_lane():
    aerith = {
        "name": "Aerith, Last Ancient",
        "oracle_text": (
            "Lifelink\nRaise — At the beginning of your end step, if you gained life "
            "this turn, return target creature card from your graveyard to your hand. "
            "If you gained 7 or more life this turn, return that card to the "
            "battlefield instead."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the "if you gained life
    # this turn" payoff rides the byte-identical kept-mirror, served from the hybrid.
    assert ("lifegain_matters", "you") in _keys_hybrid(aerith)


def test_lifegain_amount_gained_payoff_opens_lane():
    celestine = {
        "name": "Celestine, the Living Saint",
        "oracle_text": (
            "Flying, lifelink\nHealing Tears — At the beginning of your end step, "
            "return target creature card with mana value X or less from your graveyard "
            "to the battlefield, where X is the amount of life you gained this turn."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — "the amount of life you
    # gained" rides the kept-mirror, served from the hybrid path.
    assert ("lifegain_matters", "you") in _keys_hybrid(celestine)


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
    guan_yu = {
        "name": "Guan Yu, Sainted Warrior",
        "oracle_text": (
            "Horsemanship (This creature can't be blocked except by creatures with "
            "horsemanship.)\nWhen Guan Yu is put into your graveyard from the "
            "battlefield, you may shuffle Guan Yu into your library."
        ),
    }
    assert ("evasion_self", "you") in _keys(guan_yu)


def test_menace_opens_evasion_lane():
    card = {
        "name": "Menacer",
        "oracle_text": "Menace (This creature can't be blocked except by two or more creatures.)",
    }
    assert ("evasion_self", "you") in _keys(card)


def test_plain_vigilance_creature_no_evasion_lane():
    # Precision: a non-evasion keyword must not open the evasion lane.
    card = {"name": "Watcher", "oracle_text": "Vigilance"}
    assert ("evasion_self", "you") not in _keys(card)


# ── Zero-avenue commander recovery: themeless beaters, variable counters, global lords
# These commanders extracted NO avenues at all — the worst case (0/10 coverage).
def test_variable_x_counters_opens_counters_lane():
    # Halana and Alena: a recurring engine that puts a VARIABLE number of +1/+1
    # counters on your team each combat — a counters commander, but the count-anchor
    # ('for each'/'number of') gate missed the 'X +1/+1 counters' scaling form.
    halana = {
        "name": "Halana and Alena, Partners",
        "type_line": "Legendary Creature — Human Ranger",
        "oracle_text": (
            "First strike (This creature deals combat damage before creatures without first strike.)\nReach (This creature can block creatures with flying.)\nAt the beginning of combat on your turn, put X +1/+1 counters on another target creature you control, where X is Halana and Alena's power. That creature gains haste until end of turn."
        ),
    }
    # ADR-0027: counters_matter migrated to the IR — the +1/+1 placement projects a
    # place_counter(p1p1); assert via the hybrid (production) path.
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(halana, ir)}
    assert any(k == "counters_matter" for k, _ in keys)


def test_cheap_vanilla_legend_opens_voltron_fallback():
    # Isamaru: the iconic 2/2 vanilla voltron commander. Commander damage is the only
    # plan, so the themeless-creature fallback must open voltron even at low power.
    isamaru = {
        "name": "Isamaru, Hound of Konda",
        "type_line": "Legendary Creature — Dog",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    assert ("voltron_matters", "you") in _keys(isamaru)


def test_indestructible_beater_opens_voltron_fallback():
    # Konda: indestructible + vigilance beater — a resilient commander-damage threat
    # whose keywords weren't in the voltron set.
    konda = {
        "name": "Konda, Lord of Eiganjo",
        "type_line": "Legendary Creature — Human Samurai",
        "power": "3",
        "toughness": "3",
        "keywords": ["Vigilance", "Indestructible"],
        "oracle_text": "Vigilance, indestructible\nBushido 5 (Whenever this creature blocks or becomes blocked, it gets +5/+5 until end of turn.)",
    }
    assert ("voltron_matters", "you") in _keys(konda)


def test_themeless_one_one_does_not_open_voltron():
    # Precision: a 1/1 themeless legend is too small to be a commander-damage plan.
    chump = {
        "name": "Tiny Legend",
        "type_line": "Legendary Creature — Human",
        "power": "1",
        "toughness": "1",
        "oracle_text": "",
    }
    assert ("voltron_matters", "you") not in _keys(chump)


def test_global_tribal_anthem_opens_tribe():
    # Soraya: "Bird creatures get +1/+1" is a Bird lord — but the anthem patterns
    # required 'you control'/'other', missing the bare global-lord phrasing.
    soraya = {
        "name": "Soraya the Falconer",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "Bird creatures get +1/+1.\n{1}{W}: Target Bird creature gains banding until end of turn. (Any creatures with banding, and up to one without, can attack in a band. Bands are blocked as a group. If any creatures with banding a player controls are blocking or being blocked by a creature, that player divides that creature's combat damage, not its controller, among any of the creatures it's being blocked by or is blocking.)",
    }
    sigs = extract_signals(soraya)
    assert any(s.key == "type_matters" and s.subject == "Bird" for s in sigs)


# ── Artifact commanders that phrase the theme without "artifacts you control" ─────
# Foundry Inspector (artifact cost reducer) is top-synergy for these but the lane
# never opened: they sacrifice artifacts (Bosh), copy artifact abilities (Kurkesh),
# or turn permanents INTO artifacts (Memnarch).
def test_artifact_sac_outlet_opens_artifacts_lane():
    bosh = {
        "name": "Bosh, Iron Golem",
        "type_line": "Legendary Artifact Creature — Golem",
        "oracle_text": "Trample\n{3}{R}, Sacrifice an artifact: Bosh deals damage equal to the sacrificed artifact's mana value to any target.",
    }
    assert ("artifacts_matter", "you") in _keys(bosh)


def test_artifact_ability_payoff_opens_artifacts_lane():
    kurkesh = {
        "name": "Kurkesh, Onakke Ancient",
        "type_line": "Legendary Creature — Ogre Spirit",
        "oracle_text": "Whenever you activate an ability of an artifact, if it isn't a mana ability, you may pay {R}. If you do, copy that ability. You may choose new targets for the copy.",
    }
    assert ("artifacts_matter", "you") in _keys(kurkesh)


def test_artifact_type_granter_opens_artifacts_lane():
    memnarch = {
        "name": "Memnarch",
        "type_line": "Legendary Artifact Creature — Wizard",
        "oracle_text": "{1}{U}{U}: Target permanent becomes an artifact in addition to its other types. (This effect lasts indefinitely.)\n{3}{U}: Gain control of target artifact. (This effect lasts indefinitely.)",
    }
    assert ("artifacts_matter", "you") in _keys(memnarch)


def test_artifact_removal_does_not_open_artifacts_lane():
    # Precision: destroying an opponent's artifact is removal, not an artifact theme.
    card = {
        "name": "Disenchanter",
        "oracle_text": "When this creature enters, destroy target artifact or enchantment.",
    }
    assert ("artifacts_matter", "you") not in _keys(card)


# ── creature_etb scope tracks the ENTERING creature's controller, not the payoff ──
# Purphoros: "Whenever another creature YOU control enters, deal 2 damage to each
# opponent." The entering creature is yours — so this is creature_etb YOU (an ETB
# go-wide engine that wants Panharmonicon / flicker / ETB creatures). The payoff
# hitting opponents must NOT flip the scope.
def test_creature_etb_scope_follows_entering_controller_not_payoff():
    purphoros = {
        "name": "Purphoros, God of the Forge",
        "oracle_text": (
            "Indestructible\nAs long as your devotion to red is less than five, Purphoros isn't a creature.\nWhenever another creature you control enters, Purphoros deals 2 damage to each opponent.\n{2}{R}: Creatures you control get +1/+0 until end of turn."
        ),
    }
    # ADR-0027 β: creature_etb is IR-served (a byte-identical kept-mirror), so it comes
    # through the hybrid path — the scope-follows-entering-controller logic is preserved.
    keys = _keys_hybrid(purphoros)
    assert ("creature_etb", "you") in keys
    assert ("creature_etb", "opponents") not in keys


def test_etb_trigger_doubler_opens_etb_lane():
    # Yarok doubles every permanent-ETB trigger — he's an ETB-value commander who wants
    # ETB creatures, flicker, and other doublers, so he must open the creature_etb lane.
    # ADR-0027 β: the doubler is the canonical reason creature_etb rides a kept-mirror,
    # not the structural etb-trigger arm — phase models "triggers an additional time" as
    # a static replacement effect (no `etb` event), so the lane serves from the hybrid.
    yarok = {
        "name": "Yarok, the Desecrated",
        "oracle_text": (
            "Deathtouch, lifelink\nIf a permanent entering causes a triggered ability "
            "of a permanent you control to trigger, that ability triggers an "
            "additional time."
        ),
    }
    assert ("creature_etb", "you") in _keys_hybrid(yarok)


# ── Artifact-token makers ARE artifact commanders (Food/Treasure/Clue are artifacts) ─
# A Treasure / Food / Clue / Blood maker should open the artifacts lane so artifact
# payoffs (Academy Manufactor, Foundry Inspector, artifact sac) surface — the serve
# already credits them; the detector missed the lane-opening (Korvold, Gyome).
def test_treasure_maker_opens_artifacts_lane():
    goldspan = {
        "name": "Goldspan Dragon",
        "type_line": "Creature — Dragon",
        "oracle_text": 'Flying, haste\nWhenever this creature attacks or becomes the target of a spell, create a Treasure token.\nTreasures you control have "{T}, Sacrifice this artifact: Add two mana of any one color."',
    }
    assert ("artifacts_matter", "you") in _keys(goldspan)


def test_food_maker_opens_artifacts_lane():
    gyome = {
        "name": "Gyome, Master Chef",
        "type_line": "Legendary Creature — Troll Warlock",
        "oracle_text": "Trample\nAt the beginning of your end step, create a number of Food tokens equal to the number of nontoken creatures you had enter the battlefield under your control this turn.\n{1}, Sacrifice a Food: Target creature gains indestructible until end of turn. Tap it.",
    }
    assert ("artifacts_matter", "you") in _keys(gyome)


def test_creature_token_maker_does_not_open_artifacts_lane():
    # Precision: a Soldier-token maker is NOT an artifacts commander.
    card = {
        "name": "Soldier Boss",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "At the beginning of your end step, create two 1/1 white "
        "Soldier creature tokens.",
    }
    assert ("artifacts_matter", "you") not in _keys(card)


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
    arcum = {
        "name": "Arcum Dagsson",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": "{T}: Target artifact creature's controller sacrifices it. That "
        "player may search their library for a noncreature artifact card, put it onto "
        "the battlefield, then shuffle.",
    }
    # phase projects the {T}: ability with cost='tap' and a sacrifice/tutor effect.
    arcum_ir = _ir_with(
        Ability(
            kind="activated",
            cost="tap",
            effects=(
                Effect(category="sacrifice", scope="any", raw="sacrifices it"),
                Effect(category="tutor", scope="any", raw="search their library"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(arcum, arcum_ir)}
    assert ("activated_ability", "you") in keys
    # And the deleted regex no longer emits it.
    assert ("activated_ability", "you") not in _keys(arcum)


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
    lovisa = {
        "name": "Lovisa Coldeyes",
        "type_line": "Legendary Creature — Human",
        "oracle_text": "Each creature that's a Barbarian, a Warrior, or a Berserker "
        "gets +2/+2 and has haste.",
    }
    subjects = {s.subject for s in extract_signals(lovisa) if s.key == "type_matters"}
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
    scarab = {
        "name": "The Scarab God",
        "type_line": "Legendary Creature — God",
        "oracle_text": "At the beginning of your upkeep, each opponent loses X life and you scry X, where X is the number of Zombies you control.\n{2}{U}{B}: Exile target creature card from a graveyard. Create a token that's a copy of it, except it's a 4/4 black Zombie.\nWhen The Scarab God dies, return it to its owner's hand at the beginning of the next end step.",
    }
    # phase projects the {2}{U}{B}: ability with cost='genericmana,mana' and a
    # non-ramp exile/make_token effect.
    scarab_ir = _ir_with(
        Ability(
            kind="activated",
            cost="genericmana,mana",
            effects=(
                Effect(category="exile", scope="any", raw="exile target"),
                Effect(
                    category="make_token",
                    scope="you",
                    raw="create a token that's a copy",
                ),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(scarab, scarab_ir)}
    assert ("activated_ability", "you") in keys
    assert ("activated_ability", "you") not in _keys(scarab)


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
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(card, fb_ir)}
    assert ("activated_ability", "you") not in keys
    assert ("activated_ability", "you") not in _keys(card)


# ── Snow matters (Isu the Abominable) — a real niche archetype with a clean anchor ──
def test_snow_commander_opens_snow_lane():
    isu = {
        "name": "Isu the Abominable",
        "type_line": "Legendary Snow Creature — Yeti",
        "oracle_text": "You may look at the top card of your library any time.\nYou may play snow lands and cast snow spells from the top of your library.\nWhenever another snow permanent you control enters, you may pay {G}, {W}, or {U}. If you do, put a +1/+1 counter on Isu.",
    }
    # ADR-0027: snow_matters is IR-served from the kept word-detector mirror
    # (\bsnow\b), so it comes through the hybrid path, not pure regex.
    assert ("snow_matters", "you") in _keys_hybrid(isu)
    assert ("snow_matters", "you") not in _keys(isu)


def test_non_snow_card_does_not_open_snow_lane():
    card = {"name": "Bear", "type_line": "Creature — Bear", "oracle_text": "Vigilance"}
    assert ("snow_matters", "you") not in _keys_hybrid(card)


# ── Missing race tribes: build-around-able races with deep pools but no lords were
# absent from the membership vocab (gated at >=8 tribal-SUPPORT cards). A Kraken /
# Wolf / Shade / Yeti commander builds a pile of its tribe (Brinelin, Anara, Ihsan, Isu).
def test_kraken_commander_opens_kraken_tribe():
    brinelin = {
        "name": "Brinelin, the Moon Kraken",
        "type_line": "Legendary Creature — Kraken",
        "oracle_text": "When Brinelin enters and whenever you cast a spell with mana value 6 or greater, you may return target nonland permanent to its owner's hand.\nPartner (You can have two commanders if both have partner.)",
    }
    sigs = extract_signals(brinelin)
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
    ruxa = {
        "name": "Ruxa, Patient Professor",
        "type_line": "Legendary Creature — Bear Druid",
        "oracle_text": "Whenever Ruxa enters or attacks, return target creature card with no abilities from your graveyard to your hand.\nCreatures you control with no abilities get +1/+1.\nFor each creature you control with no abilities, you may have that creature assign its combat damage as though it weren't blocked.",
    }
    ruxa_ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        controller="you",
                        predicates=("HasNoAbilities",),
                    ),
                    raw="Creatures you control with no abilities get +1/+1.",
                ),
            ),
        )
    )
    assert ("vanilla_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(ruxa, ruxa_ir)
    }
    # The legacy regex path no longer emits the migrated key.
    assert ("vanilla_matters", "you") not in _keys(ruxa)


# ── Toughness payoffs beyond "assigns combat damage equal to toughness" (Geralf) ──
# ADR-0027 β: toughness_combat migrated to the Card IR (both regex producers deleted),
# so it no longer fires from the pure-regex _keys() path — assert via the hybrid, which
# serves it from the byte-identical _TOUGHNESS_COMBAT_MIRROR over the kept_oracle.
def test_toughness_value_payoff_opens_toughness_lane():
    geralf = {
        "name": "Geralf, Visionary Stitcher",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": "Zombies you control have flying.\n{U}, {T}, Sacrifice another "
        "nontoken creature: Create an X/X blue Zombie creature token, where X is the "
        "sacrificed creature's toughness.",
    }
    assert ("toughness_combat", "you") in _keys_hybrid(geralf)
    # The migrated key no longer rides the legacy regex path.
    assert ("toughness_combat", "you") not in _keys(geralf)


def test_set_base_pt_does_not_open_toughness_lane():
    # Precision: "power and toughness are each equal to the number of X" is set-base-P/T,
    # not a toughness-as-value payoff. The migrated mirror keeps the "(?! are each)" veto.
    card = {
        "name": "Abominable Treefolk",
        "type_line": "Snow Creature — Treefolk",
        "oracle_text": "Trample\nAbominable Treefolk's power and toughness are each equal to the number of snow permanents you control.\nWhen this creature enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step.",
    }
    assert ("toughness_combat", "you") not in _keys_hybrid(card)


# ── Pariah combo: a commander that prevents/redirects damage to ITSELF (Cho-Manno,
# Anti-Venom) is the unkillable redirect target — it wants Pariah-style redirect + the
# indestructible grants that keep the target alive. ADR-0027 β migrated damage_redirect
# to the Card IR (ARM A — name-aware self-prevention), so the lane now fires from the
# HYBRID (IR) path; the regex path drops it (the migration invariant).
def test_self_damage_prevention_opens_redirect_lane():
    cho = {
        "name": "Cho-Manno, Revolutionary",
        "type_line": "Legendary Creature — Human Rebel",
        "oracle_text": "Prevent all damage that would be dealt to Cho-Manno.",
    }
    anti = {
        "name": "Anti-Venom, Horrifying Healer",
        "type_line": "Legendary Creature — Symbiote Hero",
        "oracle_text": "When Anti-Venom enters, if he was cast, return target creature card from your graveyard to the battlefield.\nIf damage would be dealt to Anti-Venom, prevent that damage and put that many +1/+1 counters on him.",
    }
    # Hybrid (IR) path serves it; the regex path no longer does (migration invariant).
    assert ("damage_redirect", "you") in _keys_hybrid(cho)
    assert ("damage_redirect", "you") in _keys_hybrid(anti)
    assert ("damage_redirect", "you") not in _keys(cho)
    assert ("damage_redirect", "you") not in _keys(anti)


# ── ARM B (the redirect clause): "the next N damage … dealt to ~ instead" — en-Kor,
# Reflect Damage, Captain's Maneuver. Disjoint from ARM A (name-aware self-prevention);
# rides _DAMAGE_REDIRECT_MIRROR (the exact deleted SWEEP regex) over the IR path.
def test_redirect_clause_opens_redirect_lane():
    capt = {
        "name": "Captain's Maneuver",
        "type_line": "Instant",
        "oracle_text": (
            "The next X damage that would be dealt to target creature, planeswalker, "
            "or player this turn is dealt to another target creature, planeswalker, "
            "or player instead."
        ),
    }
    assert ("damage_redirect", "you") in _keys_hybrid(capt)
    assert ("damage_redirect", "you") not in _keys(capt)


def test_fog_does_not_open_redirect_lane():
    # Precision: a fog ("prevent all combat damage this turn") is not self-redirect.
    # Holds on BOTH the regex path (it never fired) and the hybrid path (neither IR arm
    # matches — the name-aware ARM A wants "to <self>", ARM B wants "dealt to … instead").
    card = {
        "name": "Fog",
        "type_line": "Instant",
        "oracle_text": "Prevent all combat damage that would be dealt this turn.",
    }
    assert ("damage_redirect", "you") not in _keys(card)
    assert ("damage_redirect", "you") not in _keys_hybrid(card)


def test_aura_recursion_opens_voltron_lane():
    # Hakim: "return target Aura card ... attached to Hakim" — aura voltron, but the
    # detector caught "attach an Aura", not the "Aura ... attached" recursion form.
    hakim = {
        "name": "Hakim, Loreweaver",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": "Flying\n{U}{U}: Return target Aura card from your graveyard to the battlefield attached to Hakim. Activate only during your upkeep and only if Hakim isn't enchanted.\n{U}{U}, {T}: Destroy all Auras attached to Hakim.",
    }
    assert ("voltron_matters", "you") in _keys(hakim)


def test_passive_combat_damage_opens_combat_lane():
    # Hope of Ghirapur: "target player who was dealt combat damage by Hope this turn" —
    # a voltron/combat commander that cares about HAVING dealt combat damage (passive
    # form). It wants gear to connect (combat_damage lane carries the gear extra).
    hope = {
        "name": "Hope of Ghirapur",
        "type_line": "Legendary Artifact Creature — Thopter",
        "oracle_text": "Flying\nSacrifice Hope of Ghirapur: Until your next turn, "
        "target player who was dealt combat damage by Hope of Ghirapur this turn can't "
        "cast noncreature spells.",
    }
    assert any(k == "combat_damage_matters" for k, _ in _keys(hope))


def test_multi_counter_placement_opens_counters_lane():
    # Minsc & Boo: "+1: Put three +1/+1 counters on up to one target creature" — a
    # recurring counter engine. Plural 'counters' (multi-placement) distinguishes it
    # from bare 'put a +1/+1 counter on it' self-growth.
    minsc = {
        "name": "Minsc & Boo, Timeless Heroes",
        "type_line": "Legendary Planeswalker — Minsc",
        "oracle_text": "When Minsc & Boo enters and at the beginning of your upkeep, you may create Boo, a legendary 1/1 red Hamster creature token with trample and haste.\n+1: Put three +1/+1 counters on up to one target creature with trample or haste.\n−2: Sacrifice a creature. When you do, Minsc & Boo deals X damage to any target, where X is that creature's power. If the sacrificed creature was a Hamster, draw X cards.\nMinsc & Boo, Timeless Heroes can be your commander.",
    }
    # ADR-0027: counters_matter migrated to the IR — assert via the hybrid path.
    ir = _ir_with(
        Ability(
            kind="activated",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(minsc, ir)}
    assert any(k == "counters_matter" for k, _ in keys)


def test_self_counter_now_opens_counters_in_production():
    # ADR-0027: counters_matter migrated to the IR and now fires on ANY +1/+1
    # PLACEMENT regardless of recipient (CR 122.1 / 122.6) — bare self-growth is a
    # source too. The legacy regex EXCLUDED it; the regex path no longer emits the
    # migrated key at all, and the production hybrid path opens the lane.
    card = {
        "name": "Lonely Grower",
        "oracle_text": "Whenever this creature attacks, put a +1/+1 counter on it.",
    }
    assert not any(k == "counters_matter" for k, _ in _keys(card))  # regex: migrated
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}
    assert any(k == "counters_matter" for k, _ in keys)


def test_opponent_library_exile_opens_opponents_mill():
    # Circu: "exile the top card of target player's library" — exile-mill of opponents,
    # a mill variant the graveyard detector (keyed on "graveyard") missed.
    circu = {
        "name": "Circu, Dimir Lobotomist",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": "Whenever you cast a blue spell, exile the top card of target player's library.\nWhenever you cast a black spell, exile the top card of target player's library.\nYour opponents can't cast spells with the same name as a card exiled with Circu.",
    }
    assert ("graveyard_matters", "opponents") in _keys(circu)


def test_self_library_exile_does_not_open_opponents_mill():
    # Precision: impulse-drawing off YOUR OWN library is not opponent mill.
    card = {
        "name": "Light Up the Stage",
        "oracle_text": "Spectacle {R} (You may cast this spell for its spectacle cost rather than its mana cost if an opponent lost life this turn.)\nExile the top two cards of your library. Until the end of your next turn, you may play those cards.",
    }
    assert ("graveyard_matters", "opponents") not in _keys(card)


# ── "a <Type> you control <verb>" and "attacking <Type>" tribal triggers ─────────
def test_a_type_you_control_verb_opens_tribe():
    # "a Griffin you control deals combat damage" — the 'deals' trigger verb.
    zeriam = {
        "name": "Zeriam, Golden Wind",
        "type_line": "Legendary Creature — Griffin",
        "oracle_text": "Flying\nWhenever a Griffin you control deals combat damage "
        "to a player, create a 2/2 white Griffin creature token with flying.",
    }
    # "a Dragon you control attacks" — the 'attacks' trigger verb.
    dromoka = {
        "name": "Dromoka, the Eternal",
        "type_line": "Legendary Creature — Dragon",
        "oracle_text": "Flying\nWhenever a Dragon you control attacks, bolster 2. "
        "(Choose a creature with the least toughness among creatures you control "
        "and put two +1/+1 counters on it.)",
    }
    assert ("type_matters", "you") in {(k, s) for k, s in _keys(zeriam)}
    assert any(
        s.subject == "Griffin"
        for s in extract_signals(zeriam)
        if s.key == "type_matters"
    )
    assert any(
        s.subject == "Dragon"
        for s in extract_signals(dromoka)
        if s.key == "type_matters"
    )


def test_attacking_type_opens_tribe():
    clavileno = {
        "name": "Clavileño, First of the Blessed",
        "type_line": "Legendary Creature — Vampire Cleric",
        "oracle_text": "Whenever you attack, target attacking Vampire that isn't a "
        'Demon becomes a Demon in addition to its other types. It gains "When this '
        "creature dies, draw a card and create a tapped 4/3 white and black Vampire "
        'Demon creature token with flying."',
    }
    assert any(
        s.subject == "Vampire"
        for s in extract_signals(clavileno)
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
    sigarda = {
        "name": "Sigarda, Host of Herons",
        "type_line": "Legendary Creature — Angel",
        "power": "5",
        "toughness": "5",
        "keywords": ["Flying", "Hexproof"],
        "oracle_text": "Flying, hexproof\nSpells and abilities your opponents control "
        "can't cause you to sacrifice permanents.",
    }
    assert ("voltron_matters", "you") in _keys(sigarda)


def test_offering_keyword_opens_tribe():
    # Patron of the Nezumi: "Rat offering" — the Offering mechanic sacrifices a tribe
    # member to cast, so it's that tribe. Real text (the reminder is stripped, keyword
    # survives).
    patron = {
        "name": "Patron of the Nezumi",
        "type_line": "Legendary Creature — Spirit",
        "oracle_text": "Rat offering (You may cast this spell any time you could cast an instant by sacrificing a Rat and paying the difference in mana costs between this and the sacrificed Rat. Mana cost includes color.)\nWhenever a permanent is put into an opponent's graveyard, that player loses 1 life.",
    }
    assert any(
        s.subject == "Rat" for s in extract_signals(patron) if s.key == "type_matters"
    )


def test_your_team_controls_opens_tribe():
    # Sylvia Brightspear: "Dragons your team controls have double strike" — multiplayer
    # "your team controls", which the "you control" patterns missed.
    sylvia = {
        "name": "Sylvia Brightspear",
        "type_line": "Legendary Creature — Human Knight",
        "oracle_text": "Partner with Khorvath Brightflame (When this creature enters, target player may put Khorvath into their hand from their library, then shuffle.)\nDouble strike\nDragons your team controls have double strike.",
    }
    assert any(
        s.subject == "Dragon"
        for s in extract_signals(sylvia)
        if s.key == "type_matters"
    )


# ── Clone synergy: a HIGH-CMC commander with a strong ETB is worth copying (Dan's
# insight) — copying it re-fires the expensive ETB on a token for cheap (Gyruda). ──
def test_high_cmc_etb_commander_opens_clone():
    # Real Scryfall oracle uses the SHORT name ("When Gyruda enters"), not the full
    # "Gyruda, Doom of Depths" — the clone gate must match the short name like
    # _self_etb_value does, or it misses the very commander it was built for.
    gyruda = {
        "name": "Gyruda, Doom of Depths",
        "type_line": "Legendary Creature — Demon Kraken",
        "cmc": 6.0,
        "oracle_text": "Companion — Your starting deck contains only cards with even mana values. (If this card is your chosen companion, you may put it into your hand from outside the game for {3} as a sorcery.)\nWhen Gyruda enters, each player mills four cards. Put a creature card with an even mana value from among the milled cards onto the battlefield under your control.",
    }
    assert ("clone_matters", "you") in _keys(gyruda)


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
    assert ("clone_matters", "you") not in _keys(cheap)
    assert ("clone_matters", "you") not in _keys(vanilla)


def test_high_cmc_dies_trigger_commander_opens_clone():
    # A high-CMC commander with a strong DEATH trigger (Keiga, Kokusho) is also worth
    # copying — a clone/token-copy re-fires the death trigger when the copy dies
    # (sac-loop staple). Short name, like Scryfall prints it.
    keiga = {
        "name": "Keiga, the Tide Star",
        "type_line": "Legendary Creature — Dragon Spirit",
        "cmc": 6.0,
        "oracle_text": "Flying\nWhen Keiga dies, gain control of target creature.",
    }
    kokusho = {
        "name": "Kokusho, the Evening Star",
        "type_line": "Legendary Creature — Dragon Spirit",
        "cmc": 6.0,
        "oracle_text": "Flying\nWhen Kokusho dies, each opponent loses 5 life. You "
        "gain life equal to the life lost this way.",
    }
    assert ("clone_matters", "you") in _keys(keiga)
    assert ("clone_matters", "you") in _keys(kokusho)


def test_cheap_dies_trigger_does_not_open_clone():
    # Precision: a CHEAP death-trigger creature isn't worth a clone.
    cheap = {
        "name": "Doomed Dissenter",
        "type_line": "Creature — Human",
        "cmc": 2.0,
        "oracle_text": "When this creature dies, create a 2/2 black Zombie creature token.",
    }
    assert ("clone_matters", "you") not in _keys(cheap)


def test_land_enter_punisher_opens_burn_lane():
    # Zo-Zu the Punisher: opponents-landfall PUNISH — "whenever a land enters, deal 2 to
    # that land's controller". The landfall lane is the YOU payoff; this is the missing
    # opponents-scoped punish side.
    zozu = {
        "name": "Zo-Zu the Punisher",
        "type_line": "Legendary Creature — Goblin Warrior",
        "oracle_text": "Whenever a land enters, Zo-Zu deals 2 damage to that land's controller.",
    }
    assert ("direct_damage", "you") in _keys(zozu)


def test_source_deals_damage_opens_burn():
    # The Red Terror: "whenever a red source you control deals damage …" — a damage-
    # matters commander who wants to deal lots of damage (burn).
    terror = {
        "name": "The Red Terror",
        "type_line": "Legendary Creature — Tyranid",
        "oracle_text": "Advanced Species — Whenever a red source you control deals damage to one or more permanents and/or players, put a +1/+1 counter on The Red Terror.",
    }
    assert ("direct_damage", "you") in _keys(terror)


def test_self_power_scaling_opens_counters():
    # Mona Lisa: "{T}: Add X mana, where X is Mona Lisa's power" — her value scales with
    # her OWN power, so she wants to pump it with +1/+1 counters (Stony Strength).
    # ADR-0027 β: self_counter_grow migrated to the Card IR — this self-power-scaling
    # cross-open is now served from the narrowed _SELF_COUNTER_GROW_MIRROR (hybrid path).
    mona = {
        "name": "Mona Lisa, Science Geek",
        "type_line": "Legendary Creature — Lizard Mutant",
        "oracle_text": "Reach\n{T}: Add X mana of any one color, where X is Mona Lisa's "
        "power.",
    }
    assert any(k == "self_counter_grow" for k, _ in _keys_hybrid(mona))


def test_fling_target_power_does_not_open_self_counters():
    # Precision: "X is TARGET creature's power" (fling) isn't self-scaling.
    # ADR-0027 β: served from the IR path now (hybrid), so check there.
    card = {
        "name": "Fling",
        "oracle_text": "As an additional cost to cast this spell, sacrifice a creature.\nFling deals damage equal to the sacrificed creature's power to any target.",
    }
    assert not any(k == "self_counter_grow" for k, _ in _keys_hybrid(card))


def test_punish_non_attackers_opens_forced_attack():
    # Kratos: "deals damage = creatures that didn't attack this turn" — a force-attack
    # incentive (attack or take damage), a goad/aggro commander.
    kratos = {
        "name": "Kratos, God of War",
        "type_line": "Legendary Creature — God Warrior",
        "oracle_text": "Double strike\nAll creatures have haste.\nAt the beginning of "
        "each player's end step, Kratos deals damage to that player equal to the number "
        "of creatures that player controls that didn't attack this turn.",
    }
    assert any(k == "forced_attack" for k, _ in _keys(kratos))


# ── Outlaw tribal (Outlaws of Thunder Junction): Assassin/Mercenary/Pirate/Rogue/
# Warlock are collectively "outlaws" (Vial Smasher). ──
def test_outlaw_commander_opens_outlaw_lane():
    vial = {
        "name": "Vial Smasher, Gleeful Grenadier",
        "type_line": "Legendary Creature — Goblin Mercenary",
        "oracle_text": "Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
    }
    # ADR-0027: outlaw_matters is IR-served from the kept word-detector mirror
    # (\boutlaws?\b), so it comes through the hybrid path, not pure regex.
    assert ("outlaw_matters", "you") in _keys_hybrid(vial)
    assert ("outlaw_matters", "you") not in _keys(vial)


def test_pacify_control_commander_opens_pillowfort():
    # Gwafa Hazid neutralizes opponents' creatures ("can't attack or block") — a
    # control/pillowfort identity that wants Propaganda / Ghostly Prison / Windborn Muse.
    gwafa = {
        "name": "Gwafa Hazid, Profiteer",
        "type_line": "Legendary Creature — Human Rogue",
        "oracle_text": "{W}{U}, {T}: Put a bribery counter on target creature you don't "
        "control. Its controller draws a card.\nCreatures with bribery counters on them "
        "can't attack or block.",
    }
    assert ("stax_taxes", "opponents") in _keys(gwafa)


def test_banding_commander_opens_banding_lane():
    # Ayesha Tanaka has Banding — she wants other banding creatures to form bands.
    ayesha = {
        "name": "Ayesha Tanaka",
        "type_line": "Legendary Creature — Human Artificer",
        "keywords": ["Banding"],
        "oracle_text": "Banding (Any creatures with banding, and up to one without, can attack in a band. Bands are blocked as a group. If any creatures with banding you control are blocking or being blocked by a creature, you divide that creature's combat damage, not its controller, among any of the creatures it's being blocked by or is blocking.)\n{T}: Counter target activated ability from an artifact source unless that ability's controller pays {W}. (Mana abilities can't be targeted.)",
    }
    assert ("banding_matters", "you") in _keys(ayesha)


def test_counter_on_another_opens_counters():
    # Anafenza, the Foremost: "Whenever Anafenza attacks, put a +1/+1 counter on another
    # target tapped creature" — a recurring counter engine (placement on ANOTHER
    # creature), distinct from bare self-growth ('on it').
    anafenza = {
        "name": "Anafenza, the Foremost",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": "Whenever Anafenza attacks, put a +1/+1 counter on another target tapped creature you control.\nIf a nontoken creature an opponent owns would die or a creature card not on the battlefield would be put into an opponent's graveyard, exile that card instead.",
    }
    # ADR-0027: counters_matter migrated to the IR — assert via the hybrid path.
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(category="place_counter", scope="you", counter_kind="p1p1"),
            ),
        )
    )
    keys = {(s.key, s.scope) for s in extract_signals_hybrid(anafenza, ir)}
    assert any(k == "counters_matter" for k, _ in keys)


def test_variable_lifegain_opens_lifegain():
    # Atalya gains X life; Ayli gains life equal to toughness — variable lifegain the
    # detector (keyed on 'gain N life') missed.
    atalya = {
        "name": "Atalya, Samite Master",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": "{X}, {T}: Choose one —\n• Prevent the next X damage that would be dealt to target creature this turn. Spend only white mana on X.\n• You gain X life. Spend only white mana on X.",
    }
    ayli = {
        "name": "Ayli, Eternal Pilgrim",
        "type_line": "Legendary Creature — Kor Cleric",
        "oracle_text": "Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\n{1}, Sacrifice another creature: You gain life equal to the sacrificed creature's toughness.\n{1}{W}{B}, Sacrifice another creature: Exile target nonland permanent. Activate only if you have at least 10 life more than your starting life total.",
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — variable "gain X life" /
    # "gain life equal to" rides the byte-identical kept-mirror, served from the hybrid.
    assert ("lifegain_matters", "you") in _keys_hybrid(atalya)
    assert ("lifegain_matters", "you") in _keys_hybrid(ayli)


def test_if_you_would_gain_life_opens_lifegain():
    # Bilbo / Boon Reflection / Rhox Faithmender: "if you would gain life, you gain …
    # instead" is a lifegain amplifier — a lifegain commander.
    bilbo = {
        "name": "Bilbo, Birthday Celebrant",
        "type_line": "Legendary Creature — Halfling Rogue",
        "oracle_text": "If you would gain life, you gain that much life plus 1 instead.\n{2}{W}{B}{G}, {T}, Exile Bilbo: Search your library for any number of creature cards, put them onto the battlefield, then shuffle. Activate only if you have 111 or more life.",
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the "if you would gain
    # life" amplifier rides the byte-identical kept-mirror, served from the hybrid.
    assert ("lifegain_matters", "you") in _keys_hybrid(bilbo)


def test_tap_deals_damage_opens_burn():
    # Heartless Hidetsugu: "{T}: deals damage to each player equal to half …" — a pinger
    # the digit-keyed branch missed (no literal number).
    hidetsugu = {
        "name": "Heartless Hidetsugu",
        "type_line": "Legendary Creature — Ogre Shaman",
        "oracle_text": "{T}: Heartless Hidetsugu deals damage to each player equal to "
        "half that player's life total, rounded down.",
    }
    assert ("direct_damage", "you") in _keys(hidetsugu)


def test_aura_equipment_cost_reducer_opens_voltron():
    # Danitha: "Aura and Equipment spells you cast cost {1} less" — a voltron payoff the
    # detector's 'cast an Aura/Equipment' branch missed.
    danitha = {
        "name": "Danitha Capashen, Paragon",
        "type_line": "Legendary Creature — Human Knight",
        "oracle_text": "First strike, vigilance, lifelink\nAura and Equipment spells you "
        "cast cost {1} less to cast.",
    }
    assert ("voltron_matters", "you") in _keys(danitha)


def test_greatest_power_among_other_opens_power():
    # Arni Brokenbrow: "greatest power among OTHER creatures you control" — the power
    # detector required 'among creatures you control' (no 'other').
    arni = {
        "name": "Arni Brokenbrow",
        "type_line": "Legendary Creature — Human Berserker",
        "oracle_text": "Haste\nBoast — {1}: You may change Arni's base power to 1 plus the greatest power among other creatures you control until end of turn. (Activate only if this creature attacked this turn and only once each turn.)",
    }
    assert ("power_matters", "you") in _keys(arni)


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
            s.key for s in extract_signals_hybrid(card, _bare_ir())
        }, oracle


def test_artifact_type_commander_opens_artifacts():
    # A commander that IS an artifact (type line has the Artifact card type) is an
    # artifact deck — wants affinity / cost reducers / artifact synergy, just as a
    # creature is a member of its own tribe (the type-line membership insight).
    ede = {
        "name": "ED-E, Lonesome Eyebot",
        "type_line": "Legendary Artifact Creature — Robot",
        "oracle_text": "Flying\nED-E My Love — Whenever you attack, if the number of attacking creatures is greater than the number of quest counters on ED-E, put a quest counter on it.\n{2}, Sacrifice ED-E: Draw a card, then draw an additional card for each quest counter on ED-E.",
    }
    assert ("artifacts_matter", "you") in {
        (s.key, s.scope) for s in extract_signals(ede)
    }
    # A plain (non-artifact) creature commander does NOT open the artifacts lane.
    human = {
        "name": "Some Human",
        "type_line": "Legendary Creature — Human Noble",
        "oracle_text": "Vigilance",
    }
    assert ("artifacts_matter", "you") not in {
        (s.key, s.scope) for s in extract_signals(human)
    }
    # Same for enchantment-type commanders (Anikthea, Arasta) → enchantments_matter.
    anikthea = {
        "name": "Anikthea, Hand of Erebos",
        "type_line": "Legendary Enchantment Creature — Demigod",
        "oracle_text": "Menace\nOther enchantment creatures you control have menace.\nWhenever Anikthea enters or attacks, exile up to one target non-Aura enchantment card from your graveyard. Create a token that's a copy of that card, except it's a 3/3 black Zombie creature in addition to its other types.",
    }
    assert ("enchantments_matter", "you") in {
        (s.key, s.scope) for s in extract_signals(anikthea)
    }


def test_equipped_creature_reference_opens_voltron():
    # Akiri: "attack a player with one or more equipped creatures … unattach an
    # Equipment" — an equipment/voltron commander the attach/cast patterns missed.
    akiri = {
        "name": "Akiri, Fearless Voyager",
        "type_line": "Legendary Creature — Kor Warrior",
        "oracle_text": "Whenever you attack a player with one or more equipped creatures, draw a card.\n{W}: You may unattach an Equipment from a creature you control. If you do, tap that creature and it gains indestructible until end of turn.",
    }
    assert ("voltron_matters", "you") in {
        (s.key, s.scope) for s in extract_signals(akiri)
    }


def test_unkillable_self_prevention_opens_voltron():
    # Cho-Manno: "Prevent all damage that would be dealt to Cho-Manno" — an unkillable
    # body is the ideal Equipment/Aura carrier, so it's a voltron commander.
    cho = {
        "name": "Cho-Manno, Revolutionary",
        "type_line": "Legendary Creature — Human Rebel",
        "oracle_text": "Prevent all damage that would be dealt to Cho-Manno.",
    }
    assert ("voltron_matters", "you") in {
        (s.key, s.scope) for s in extract_signals(cho)
    }


def test_boast_keyword_opens_attack_matters():
    # Boast (CR 702.135) can only be activated "if this creature attacked this turn", so
    # a Boast commander is an attack-matters deck. The condition lives in reminder text
    # (stripped before detection), so match the KEYWORD (Dan's point).
    card = {
        "name": "Varragoth, Bloodsky Sire",
        "type_line": "Legendary Creature — Demon Rogue",
        "keywords": ["Boast", "Deathtouch"],
        "oracle_text": "Deathtouch\nBoast — {1}{B}: Target player searches their library for a card, then shuffles and puts that card on top. (Activate only if this creature attacked this turn and only once each turn.)",
    }
    assert ("attack_matters", "you") in {
        (s.key, s.scope) for s in extract_signals(card)
    }


def test_enchantress_first_spell_opens_enchantments():
    # Psemilla: "Whenever you cast your FIRST enchantment spell each turn …" — the bare
    # "cast an enchantment" missed the "first/second enchantment spell" wording.
    card = {
        "name": "Psemilla, Meletian Poet",
        "type_line": "Legendary Creature — Human Bard",
        "oracle_text": "Whenever you cast your first enchantment spell each turn, create a 2/2 white Nymph enchantment creature token.\nAt the beginning of each combat, if you control five or more enchantments, Psemilla gets +4/+4 and gains lifelink until end of turn. (Damage dealt by this creature also causes you to gain that much life.)",
    }
    assert "enchantments_matter" in {s.key for s in extract_signals(card)}


def test_for_each_creature_opens_creatures_matter():
    # Shanna: "gets +1/+1 for each creature you control" — a singular count operand.
    # creatures_matter MIGRATED to the Card IR (ADR-0027), so it fires from the
    # board_count marker the projection recovers, via the hybrid path — NOT the
    # deleted regex producer.
    from mtg_utils._card_ir.project import project_card

    card = {
        "name": "Shanna, Sisay's Legacy",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": "Shanna can't be the target of abilities your opponents control.\nShanna gets +1/+1 for each creature you control.",
    }
    ir = project_card([{**card, "scryfall_oracle_id": "shanna"}])
    assert "creatures_matter" not in {s.key for s in extract_signals(card)}
    assert "creatures_matter" in {s.key for s in extract_signals_hybrid(card, ir)}


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
        assert key in {s.key for s in extract_signals_hybrid(card, _bare_ir())}, aw


def test_triggered_counter_placement_opens_counters():
    # Leinore (Coven) / Shelinda: a recurring trigger that places a +1/+1 counter on a
    # CHOSEN creature is a counters engine. ADR-0027: counters_matter migrated to the
    # IR and now fires on ANY +1/+1 PLACEMENT regardless of recipient (self / on-
    # others / on-attacking — all are sources, CR 122.1 / 122.6), so even bare self-
    # growth ("put a +1/+1 counter on it") opens the lane. Assert via the hybrid path.
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
        keys = {s.key for s in extract_signals_hybrid(card, ir)}
        assert "counters_matter" in keys, oracle


def test_fliers_matter_commander_opens_flying_keyword_tribe():
    # Momo: "creature spell with flying you cast costs {1} less … whenever another
    # creature you control with flying enters" — a fliers-matter commander. The keyword-
    # tribe detector matched only PLURAL "creatures … with flying"; add the singular
    # "creature you control with flying" / "creature spell with flying" forms.
    momo = {
        "name": "Momo, Friendly Flier",
        "type_line": "Legendary Creature — Lemur Bat Ally",
        "oracle_text": "Flying\nThe first non-Lemur creature spell with flying you cast during each of your turns costs {1} less to cast.\nWhenever another creature you control with flying enters, Momo gets +1/+1 until end of turn.",
    }
    subs = {s.subject for s in extract_signals(momo) if s.key == "keyword_tribe"}
    assert "Flying" in subs
    # Precision: a commander that merely HAS flying (no "creature with flying" payoff)
    # is NOT a fliers-matter deck.
    isperia = {
        "name": "Isperia, Supreme Judge",
        "type_line": "Legendary Creature — Sphinx",
        "keywords": ["Flying"],
        "oracle_text": "Flying\nWhenever a creature attacks you or a planeswalker you control, you may draw a card.",
    }
    assert "keyword_tribe" not in {s.key for s in extract_signals(isperia)}


def test_lifelink_commander_opens_lifegain():
    # A lifelink commander (Liesa, Elenda) gains life in combat → it's a lifegain deck
    # (lifelink + Sanguine Bond / Archangel of Thune is the payoff). The keyword carries
    # the gain (no "gain life" oracle text), so open lifegain via the keyword. ADR-0027
    # β: lifelink→lifegain_matters MOVED to the IR-only _IR_KEYWORD_MAP, so it serves
    # from the hybrid via the IR's Lifelink keyword (the IR Face carries keywords[]).
    card = {
        "name": "Elenda, Saint of Dusk",
        "type_line": "Legendary Creature — Vampire Knight",
        "keywords": ["Lifelink", "Deathtouch"],
        "oracle_text": "Lifelink, hexproof from instants\nAs long as your life total is greater than your starting life total, Elenda gets +1/+1 and has menace. Elenda gets an additional +5/+5 as long as your life total is at least 10 greater than your starting life total.",
    }
    ir = Card(
        oracle_id="x",
        name="Elenda, Saint of Dusk",
        faces=(Face(name="Elenda", keywords=("Lifelink", "Deathtouch")),),
    )
    assert ("lifegain_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(card, ir)
    }


def test_counter_keyword_commander_opens_counters():
    # A commander whose own keyword is a +1/+1-counter mechanic (Exava=Unleash,
    # Cayth, Indoraptor=Bloodthirst) is a counters deck — open counters_matter.
    # ADR-0027: counters_matter migrated to the IR — these keywords project a
    # place_counter(p1p1) STRUCTURALLY (not via the keyword array), so assert via the
    # hybrid path with the structural IR phase produces for them.
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
        keys = {s.key for s in extract_signals_hybrid(card, ir)}
        assert "counters_matter" in keys, kw


def test_archetype_keywords_open_their_lane():
    # CR-keyword audit (Dan): an archetype-defining keyword ability on the COMMANDER
    # opens that lane via the keyword (the mechanic is reminder text, stripped). The
    # non-migrated keywords still read from the regex keyword path.
    cases = [
        ("Prowess", ("spellcast_matters", "you")),
        ("Bushido", ("attack_matters", "you")),
        ("Annihilator", ("attack_matters", "you")),
    ]
    for kw, expect in cases:
        card = {
            "name": f"{kw} Lord",
            "type_line": "Legendary Creature — Test",
            "keywords": [kw],
            "oracle_text": "Some ability.",
        }
        assert expect in {(s.key, s.scope) for s in extract_signals(card)}, kw
    # ADR-0027: Exploit (sacrifice_matters) and Afflict (lifeloss_matters) are migrated
    # — phase models both as a STRUCTURAL effect (exploit's sacrifice, afflict's
    # lose_life), so they fire from the IR, not the regex keyword path.
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
    assert ("lifeloss_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(afflict, ir)
    }


def test_attack_conditional_keywords_open_attack_matters():
    # Same class as Boast: keywords whose "as it attacks" / "attacked this turn"
    # condition lives in stripped reminder text — Exert (CR 702.107) and Myriad
    # (CR 702.116, attacking copies). Match the keyword.
    for kw in ["Exert", "Myriad"]:
        card = {
            "name": f"{kw} Boss",
            "type_line": "Legendary Creature — Test",
            "keywords": [kw],
            "oracle_text": "Some ability.",
        }
        assert ("attack_matters", "you") in {
            (s.key, s.scope) for s in extract_signals(card)
        }, kw


def test_past_tense_count_payoffs_open_their_lane():
    # Tense audit (Dan): past-tense "this turn" COUNT payoffs are a class, like
    # "died this turn". Each rewards an accumulated count and should open the present-
    # tense lane. Verified real templating + commanders via bulk.
    cases = [
        # Varragoth / Relentless Assault: combat-count payoff
        (
            "attack_matters",
            "Draw a card for each creature you control that attacked this turn.",
        ),
        # Gnostro / Rionya: "for each spell you've cast this turn"
        (
            "spellcast_matters",
            "Scry X, where X is the number of spells you've cast this turn.",
        ),
    ]
    for key, oracle in cases:
        card = {
            "name": "X",
            "type_line": "Legendary Creature — Test",
            "oracle_text": oracle,
        }
        assert key in {s.key for s in extract_signals(card)}, (key, oracle)
    # ADR-0027: lifeloss_matters is migrated — Neheb / Rakdos "for each 1 life your
    # opponents have lost this turn" fires from the IR's _LOST_LIFE_TURN drain marker.
    neheb = {
        "name": "Neheb",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Add {R} for each 1 life your opponents have lost this turn.",
    }
    from mtg_utils._card_ir.project import project_card

    neheb_ir = project_card([{**neheb, "card_type": {"core_types": ["Creature"]}}])
    assert "lifeloss_matters" in {
        s.key for s in extract_signals_hybrid(neheb, neheb_ir)
    }
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
    assert "draw_matters" in {s.key for s in extract_signals_hybrid(proft, proft_ir)}


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
            s.key for s in extract_signals_hybrid(card, _bare_ir())
        }, oracle


def test_plural_death_does_not_open_on_dice():
    # Precision: a dice "die" ("roll a six-sided die") must NOT read as a death trigger.
    # ADR-0027: the precision boundary now lives in the IR-path _DEATH_MATTERS_MIRROR
    # (its "creatures? … die" arm requires a creature/permanent/token subject, never the
    # bare dice "die"), so assert against the hybrid path.
    card = {
        "name": "Velukan Dragon",
        "type_line": "Creature — Dragon",
        "oracle_text": "Flying\nWhenever this creature attacks or blocks, roll a six-sided die. This creature gets +X/+0 until end of turn, where X is the result minus 1.",
    }
    assert "death_matters" not in {
        s.key for s in extract_signals_hybrid(card, _bare_ir())
    }


def test_plural_combat_damage_opens_combat_damage_matters():
    # "creatures you control DEAL combat damage" — the plural verb ("deal" not "deals").
    # 200+ cards (Yarus, Gonti Canny Acquisitor, Neheb) use the "one or more creatures …
    # deal combat damage to a player" form the singular-only regex missed.
    card = {
        "name": "Excogitator Sphinx",
        "type_line": "Creature — Sphinx Detective",
        "oracle_text": "Flying\nWhenever one or more creatures you control deal combat damage to a player, investigate.\n{1}, Sacrifice a Clue: Seek an instant or sorcery card.",
    }
    assert ("combat_damage_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals(card)
    }


def test_keyword_grant_lord_gain_opens_type_matters():
    # "Spirits you control GAIN …" — a keyword-grant tribal lord ("gain", which the
    # have/has pattern missed). 33 tribe-specific cards (Valiant Knight, Quintorius).
    # Isolated to the gain clause (no "get"/"have") so it actually exercises the fix.
    card = {
        "name": "Grant Lord",
        "type_line": "Legendary Creature — Test",
        "oracle_text": "Spirits you control gain flying and hexproof.",
    }
    subs = {s.subject for s in extract_signals(card) if s.key == "type_matters"}
    assert "Spirit" in subs


def test_singular_lord_has_opens_type_matters():
    # "Each Ally you control HAS …" — the singular lord conjugation ("has" not "have").
    card = {
        "name": "Great Divide Guide",
        "type_line": "Creature — Human Scout Ally",
        "oracle_text": 'Each land and Ally you control has "{T}: Add one mana of any color."',
    }
    subs = {s.subject for s in extract_signals(card) if s.key == "type_matters"}
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
    subs = {s.subject for s in extract_signals(card) if s.key == "type_matters"}
    assert "Goblin" in subs


def test_singular_tribal_lord_gets_opens_type_matters():
    # "Each Fungus creature GETS +1/+1" — a singular-subject lord (Thelon of Havenwood).
    # The global-lord pattern matched only plural "get" ("Goblins … get"), missing the
    # singular "creature gets" conjugation, so the whole tribe read uncovered.
    thelon = {
        "name": "Thelon of Havenwood",
        "type_line": "Legendary Creature — Elf Druid",
        "oracle_text": "Each Fungus creature gets +1/+1 for each spore counter on it.\n{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus on the battlefield.",
    }
    assert ("type_matters", "you") in _keys(thelon)
    subs = {s.subject for s in extract_signals(thelon) if s.key == "type_matters"}
    assert "Fungus" in subs


def test_reward_for_attacking_opponents_opens_goad():
    # Gahiji / Frontier Warmonger reward any creature that attacks your opponents. Goad
    # forces opponents' creatures to attack a player other than their controller — i.e.
    # one of your OTHER opponents — firing the reward (CR 701.38b). ADR-0027: migrated
    # to the IR — the regex path no longer emits it; the hybrid path serves it from the
    # _GOAD_REWARD_REF marker (here mirrored as a goad_all effect).
    gahiji = {
        "name": "Gahiji, Honored One",
        "type_line": "Legendary Creature — Beast",
        "oracle_text": "Whenever a creature attacks one of your opponents or a "
        "planeswalker an opponent controls, that creature gets +2/+0 until end of turn.",
    }
    assert ("goad_matters", "opponents") not in _keys(gahiji)
    ir = _ir_with(
        Ability(
            kind="spell",
            effects=(
                Effect(
                    category="goad_all",
                    scope="opp",
                    raw="attacks one of your opponents",
                ),
            ),
        )
    )
    assert ("goad_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(gahiji, ir)
    }


# ── Long-tail coverage clusters (workflow-diagnosed, verify-before-add) ────────


def _subjects(card, key):
    return {s.subject for s in extract_signals(card) if s.key == key}


def test_tribal_capture_cant_be_blocked():
    # Rocksteady, Crash Courser is a Rhino Mutant — NOT a Boar — yet it buffs
    # "Boars you control can't be blocked". A commander that buffs a tribe isn't
    # always that tribe, so type-line membership can't supply the Boar lane; only
    # the can't-be-blocked trigger pattern opens it.
    card = {
        "name": "Rocksteady, Crash Courser",
        "type_line": "Legendary Creature — Rhino Mutant",
        "oracle_text": (
            "Rocksteady can't be blocked by more than one creature.\n"
            "Boars you control can't be blocked by more than one creature.\n"
            "Forestcycling {2} ({2}, Discard this card: Search your library for a "
            "Forest card, reveal it, put it into your hand, then shuffle.)"
        ),
    }
    subs = _subjects(card, "type_matters")
    assert "Boar" in subs  # the buffed tribe, captured from the clause not the type


def test_tribal_capture_cant_be_blocked_vocab_gated():
    # Yuan Shao, the Indecisive — "Each creature you control can't be blocked …".
    # The generic card-type word "creature" must be dropped by the vocab gate, not
    # emitted as a bogus "Creature" tribal subject.
    card = {
        "name": "Yuan Shao, the Indecisive",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Horsemanship (This creature can't be blocked except by creatures "
            "with horsemanship.)\n"
            "Each creature you control can't be blocked by more than one creature."
        ),
    }
    assert "Creature" not in _subjects(card, "type_matters")


def test_two_tribe_trigger_emits_both_subjects():
    # Gorbag of Minas Morgul is an Orc Soldier (membership supplies Orc but never
    # Goblin); "a Goblin or Orc you control deals …" must open BOTH tribal lanes.
    card = {
        "name": "Gorbag of Minas Morgul",
        "type_line": "Legendary Creature — Orc Soldier",
        "oracle_text": (
            "Whenever a Goblin or Orc you control deals combat damage to a "
            "player, you may sacrifice it. When you do, choose one —\n"
            "• Draw a card.\n"
            "• Create a Treasure token. (It's an artifact with \"{T}, Sacrifice "
            'this token: Add one mana of any color.")'
        ),
    }
    subs = _subjects(card, "type_matters")
    assert {"Goblin", "Orc"} <= subs


def test_impulse_look_at_and_play_opens_lane():
    # Headliner Scarlett — "You may look at and play that card this turn" is an
    # impulse engine ("look at and" splits "you may"/"play"). ADR-0027 β: impulse_top_play
    # migrated to the Card IR, so the regex path no longer fires it; the hybrid serves it
    # (here via the per-clause kept mirror's "you may look at and play" arm — a bare IR
    # routes to the IR path, and the structural cast_from_zone arm also fires on the real
    # card's IR).
    card = {
        "name": "Headliner Scarlett",
        "type_line": "Legendary Creature — Human Warlock",
        "oracle_text": (
            "Haste\n"
            "When Headliner Scarlett enters, creatures target player controls "
            "can't block this turn.\n"
            "At the beginning of your upkeep, exile the top card of your library "
            "face down. You may look at and play that card this turn."
        ),
    }
    assert ("impulse_top_play", "you") not in _keys(card)
    assert ("impulse_top_play", "you") in _keys_hybrid(card)


def test_extra_upkeep_lane_opens():
    # ADR-0027: extra_upkeep migrated to the Card IR — phase's `extra_upkeep` effect
    # category (Obeka, The Ninth Doctor — "additional upkeep step"), read via
    # _DOER_EFFECT_KEYS, so the lane opens through the hybrid IR path, not the regex.
    obeka = {
        "name": "Obeka, Splitter of Seconds",
        "type_line": "Legendary Creature — Ogre Warlock",
        "oracle_text": (
            "Menace\n"
            "Whenever Obeka deals combat damage to a player, you get that many "
            "additional upkeep steps after this phase."
        ),
    }
    ninth = {
        "name": "The Ninth Doctor",
        "type_line": "Legendary Creature — Time Lord Doctor",
        "oracle_text": (
            "Haste\n"
            "Into the TARDIS — Whenever The Ninth Doctor becomes untapped during "
            "your untap step, you get an additional upkeep step after this step."
        ),
    }
    ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="extra_upkeep",
                    scope="you",
                    raw="additional upkeep step",
                ),
            ),
        )
    )
    for card in (obeka, ninth):
        hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}
        assert ("extra_upkeep", "you") in hybrid
        assert ("extra_upkeep", "you") not in _keys(card)


def test_extra_end_step_lane_opens():
    # Y'shtola Rhul grants an additional end step; the end-step payoff lane must open.
    card = {
        "name": "Y'shtola Rhul",
        "type_line": "Legendary Creature — Cat Druid",
        "oracle_text": (
            "At the beginning of your end step, exile target creature you control, "
            "then return it to the battlefield under its owner's control. Then if "
            "it's the first end step of the turn, there is an additional end step "
            "after this step."
        ),
    }
    # ADR-0027: extra_end_step migrated to the Card IR — phase drops the "additional
    # end step" clause, recovered by an `extra_end` dropped-static face marker
    # (read via _DOER_EFFECT_KEYS), so the lane opens through the hybrid IR path.
    ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(category="extra_end", scope="you", raw="additional end step"),
            ),
        )
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}
    assert ("extra_end_step", "you") in hybrid
    assert ("extra_end_step", "you") not in _keys(card)


def test_extra_beginning_phase_decomposes_to_upkeep_and_draw():
    # CR 501.1: the beginning phase contains untap, upkeep, AND draw steps — so an
    # extra beginning phase (Sphinx of the Second Sun) re-triggers upkeep- and
    # draw-step payoffs. The untap step has no servable payoff, so no untap lane.
    # ADR-0027: phase mis-routes "additional beginning phase" to extra_combats, so the
    # grant is recovered by an `_EXTRA_BEGINNING_PHASE_GRANT` dropped-static face
    # marker emitting BOTH extra_upkeep + extra_draw, read through the hybrid IR path.
    card = {
        "name": "Sphinx of the Second Sun",
        "type_line": "Creature — Sphinx",
        "oracle_text": (
            "Flying\n"
            "At the beginning of each of your postcombat main phases, there is an "
            "additional beginning phase after this phase. (The beginning phase "
            "includes the untap, upkeep, and draw steps.)"
        ),
    }
    ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="extra_upkeep",
                    scope="you",
                    raw="additional beginning phase",
                ),
                Effect(
                    category="extra_draw",
                    scope="you",
                    raw="additional beginning phase",
                ),
            ),
        )
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}
    assert ("extra_upkeep", "you") in hybrid
    assert ("extra_draw_step", "you") in hybrid
    keys = _keys(card)
    assert ("extra_upkeep", "you") not in keys
    assert ("extra_draw_step", "you") not in keys


def test_flying_from_top_opens_keyword_tribe():
    # Errant and Giada — "cast spells with flash or flying from the top" rewards
    # fliers; open the Flying keyword-tribe lane.
    card = {
        "name": "Errant and Giada",
        "type_line": "Legendary Creature — Human Angel",
        "oracle_text": (
            "Flash\nFlying\n"
            "You may look at the top card of your library any time.\n"
            "You may cast spells with flash or flying from the top of your library."
        ),
    }
    assert ("keyword_tribe", "you") in _keys(card)
    assert "Flying" in _subjects(card, "keyword_tribe")


def test_yasharn_opens_stax_taxes():
    # Yasharn's cost-lock is a tax piece; the lane must OPEN so its hatebear
    # synergy package (Thalia, Archon of Emeria, …) is surfaced.
    card = {
        "name": "Yasharn, Implacable Earth",
        "type_line": "Legendary Creature — Elemental Boar",
        "oracle_text": (
            "When Yasharn enters, search your library for a basic Forest card and "
            "a basic Plains card, reveal those cards, put them into your hand, "
            "then shuffle.\n"
            "Players can't pay life or sacrifice nonland permanents to cast "
            "spells or activate abilities."
        ),
    }
    assert ("stax_taxes", "opponents") in _keys(card)


# ── Long-tail batch 2 (salvaged workflow proposals: detector-open gaps) ────────


def test_enchantment_card_tutor_opens_enchantments():
    # Zur the Enchanter tutors enchantment CARDS; the detector keyed only on
    # "enchantments you control" / "cast an enchantment" and missed card-references.
    card = {
        "name": "Zur the Enchanter",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Flying\nWhenever Zur attacks, you may search your library for an "
            "enchantment card with mana value 3 or less, put it onto the "
            "battlefield, then shuffle."
        ),
    }
    assert ("enchantments_matter", "you") in _keys(card)


def test_instant_sorcery_cost_reducer_opens_spellslinger():
    # Baral reduces instant/sorcery cost — a core spellslinger payoff the
    # "whenever you cast" lambda missed (no cast trigger).
    card = {
        "name": "Baral, Chief of Compliance",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Instant and sorcery spells you cast cost {1} less to cast.\n"
            "Whenever a spell or ability you control counters a spell, you may "
            "draw a card. If you do, discard a card."
        ),
    }
    assert ("spellcast_matters", "you") in _keys(card)


def test_artifact_entered_condition_opens_artifacts():
    # Akal Pakal keys on "if an artifact entered the battlefield under your
    # control this turn" — an artifacts-matters condition the detector missed.
    card = {
        "name": "Akal Pakal, First Among Equals",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": (
            "At the beginning of each player's end step, if an artifact entered "
            "the battlefield under your control this turn, look at the top two "
            "cards of your library. Put one of them into your hand and the other "
            "into your graveyard."
        ),
    }
    assert ("artifacts_matter", "you") in _keys(card)


def test_heist_opens_theft():
    # Heist (Arena keyword) steals + casts an opponent's cards — a theft payoff
    # the detector missed. Grenzo, Crooked Jailer / Axavar / Mr. Monopoly.
    card = {
        "name": "Grenzo, Crooked Jailer",
        "type_line": "Legendary Creature — Goblin Rogue",
        "oracle_text": (
            "When Grenzo enters and at the beginning of your upkeep, heist target "
            "opponent's library.\nOnce each turn, you may pay {0} rather than pay "
            "the mana cost for a spell you cast that you don't own with mana value "
            "3 or less."
        ),
    }
    assert ("theft_matters", "opponents") in _keys(card)


# ── Long-tail batch 3 (voltron / noncombat-engine / drain) ────────────────────


def test_enchanted_or_equipped_opens_voltron():
    # Koll buffs "enchanted or equipped" creature tokens — a voltron/auras+equip
    # payoff the detector missed (it keyed on "attach"/"equipped creatures").
    card = {
        "name": "Koll, the Forgemaster",
        "type_line": "Legendary Creature — Dwarf Warrior",
        "oracle_text": (
            "Whenever another nontoken creature you control dies, if it was "
            "enchanted or equipped, return it to its owner's hand.\nCreature "
            "tokens you control that are enchanted or equipped get +1/+1."
        ),
    }
    assert ("voltron_matters", "you") in _keys(card)


def test_mv_scaling_burn_opens_noncombat_damage():
    # Kaervek scales noncombat damage off opponents' spells — a burn-engine payoff
    # commander; the lane keyed only on doublers / "deals that much damage".
    card = {
        "name": "Kaervek the Merciless",
        "type_line": "Legendary Creature — Human Shaman",
        "oracle_text": (
            "Whenever an opponent casts a spell, Kaervek deals damage equal to "
            "that spell's mana value to any target."
        ),
    }
    assert ("noncombat_damage_payoff", "you") in _keys(card)


def test_opponent_lost_life_this_turn_opens_drain():
    # Sygg pays off "an opponent lost 3 or more life this turn" — a drain/lifeloss
    # payoff. ADR-0027: lifeloss_matters is migrated, served from the IR's
    # _LOST_LIFE_TURN drain marker.
    card = {
        "name": "Sygg, River Cutthroat",
        "type_line": "Legendary Creature — Merfolk Rogue",
        "oracle_text": (
            "At the beginning of each end step, if an opponent lost 3 or more "
            "life this turn, you may draw a card. (Damage causes loss of life.)"
        ),
    }
    from mtg_utils._card_ir.project import project_card

    ir = project_card([{**card, "card_type": {"core_types": ["Creature"]}}])
    assert ("lifeloss_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(card, ir)
    }


def test_turn_target_face_up_opens_facedown():
    # Kaust turns a TARGET face-down creature face up + rewards "turned face up
    # this turn" — a morph/face-down payoff the detector missed (self-only form).
    card = {
        "name": "Kaust, Eyes of the Glade",
        "type_line": "Legendary Creature — Dryad Druid",
        "oracle_text": (
            "Whenever a creature you control that was turned face up this turn "
            "deals combat damage to a player, draw a card.\n{T}: Turn target "
            "face-down attacking creature you control face up."
        ),
    }
    # ADR-0027: facedown_matters is IR-served from the kept word-detector mirror
    # (the face-down / turn-face-up payoff text), so it comes through the hybrid
    # path, not pure regex.
    assert ("facedown_matters", "you") in _keys_hybrid(card)
    assert ("facedown_matters", "you") not in _keys(card)


def test_type_you_control_entering_gerund_opens_tribe():
    # Naban: "a Wizard you control entering causes …" — the gerund "entering"
    # the "(enters|attacks|…)" verb list missed; opens Wizard tribal.
    card = {
        "name": "Naban, Dean of Iteration",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "If a Wizard you control entering causes a triggered ability of a "
            "permanent you control to trigger, that ability triggers an "
            "additional time."
        ),
    }
    assert "Wizard" in _subjects(card, "type_matters")


def test_art_sticker_opens_stickers():
    # Roxi cares about art stickers (power = permanents/cards with an art sticker;
    # ETB distributes art stickers) — the detector keyed on "put a sticker"/"stickers
    # on" and missed "art sticker"/"distribute … stickers". Sticker is a dedicated
    # mechanic, so any mention is on-theme.
    card = {
        "name": "Roxi, Publicist to the Stars",
        "type_line": "Legendary Creature — Human Employee",
        "oracle_text": (
            "Flying\nRoxi's power is equal to the number of permanents you control "
            "with an art sticker plus the number of cards in your graveyard with "
            "an art sticker.\nWhen Roxi enters, distribute up to two art stickers "
            "among one or two nonland permanents you own."
        ),
    }
    assert ("stickers_matter", "you") in _keys(card)
