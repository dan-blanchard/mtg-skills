"""Tests for the generalized signal extractor (covers all commanders, not just
hand-coded cases).

The headline goals: capture the SUBJECT noun (populate the long-dead Signal.subject)
so tribes/types stop collapsing into one generic signal; recognize whole archetypes
the 12-detector baseline was blind to (treasure / artifacts / tokens / stax / blink /
mill / goad / proliferate); and do it precisely — every false-positive class the
design review flagged (clones, "Plant"/"nonland creature", instant/sorcery spell-type
leakage, stax self-restrictions) must stay clean.
"""

from mtg_utils._deck_forge._signals_regex import _resolve_scope, _scope
from mtg_utils._deck_forge.signals import (
    _voltron_double_strike_beater,
    _voltron_land_scaler,
    _voltron_self_heroic,
    _voltron_self_recurs,
    coverage_gate,
    extract_signals,
    extract_signals_hybrid,
)
from mtg_utils.card_ir import (
    Ability,
    Card,
    Condition,
    Effect,
    Face,
    Filter,
    Trigger,
)


def _ksub(card):
    return {(s.key, s.scope, s.subject) for s in extract_signals(card)}


def _ksub_hybrid(card, ir):
    return {(s.key, s.scope, s.subject) for s in extract_signals_hybrid(card, ir)}


def _ks(card):
    return {(s.key, s.scope) for s in extract_signals(card)}


def _keys(card):
    return {s.key for s in extract_signals(card)}


# A minimal non-None IR for ADR-0027 migrated keys whose IR source reads a
# structured field (keyword array) or the kept word-detector mirror — both scan
# the record directly, so any non-None Card routes the hybrid to the IR path.
def _bare_ir() -> Card:
    return Card(oracle_id="x", name="X", faces=(Face(name="X", abilities=()),))


def _ir_with(*abilities: Ability) -> Card:
    """A Card IR carrying the given abilities — the structural marker an ADR-0027-
    migrated effect-based key reads."""
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", abilities=tuple(abilities)),),
    )


def _ks_hybrid(card):
    return {(s.key, s.scope) for s in extract_signals_hybrid(card, _bare_ir())}


def _keys_hybrid(card):
    return {s.key for s in extract_signals_hybrid(card, _bare_ir())}


def _keys_hybrid_ir(card, ir):
    return {s.key for s in extract_signals_hybrid(card, ir)}


def _ks_hybrid_ir(card, ir):
    return {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}


# --- parametric subject capture (the core generalization) ----------------------


def test_type_matters_captures_kindred_subject():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    assert ("type_matters", "you", "Goblin") in _ksub(c)


def test_type_matters_from_count_clause_and_token_maker_together():
    c = {
        "name": "Krenko, Mob Boss",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number "
            "of Goblins you control."
        ),
    }
    s = _ksub(c)
    assert ("type_matters", "you", "Goblin") in s
    assert ("token_maker", "you", "Goblin") in s


def test_type_matters_rejects_generic_creatures_word():
    # "Creatures you control get" must NOT become a junk type_matters subject — it is
    # the generic go-wide lane. creatures_matter MIGRATED to the Card IR (ADR-0027), so
    # it fires from the team-anthem pump arm via the hybrid path, never type_matters.
    c = {"name": "Anthem", "oracle_text": "Creatures you control get +1/+1."}
    ir = Card(
        oracle_id="x",
        name="Anthem",
        faces=(
            Face(
                name="Anthem",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="pump",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature",), controller="you"
                                ),
                                raw="Creatures you control get +1/+1.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.subject) for s in extract_signals_hybrid(c, ir)}
    assert ("creatures_matter", "") in hybrid
    assert "type_matters" not in {s.key for s in extract_signals_hybrid(c, ir)}


def test_type_matters_irregular_plural_resolves():
    c = {"name": "Magda-like", "oracle_text": "Other Dwarves you control get +1/+0."}
    assert ("type_matters", "you", "Dwarf") in _ksub(c)


def test_type_matters_count_clause_tolerates_state_adjective():
    # "the number of tapped Assassins you control" (Lydia Frye) — a state adjective
    # ("tapped") sits between "number of" and the tribe, so the bare
    # "number of <tribe> you control" anchor captured "tapped" (vocab-dropped) and lost
    # the Assassin tribe. Lydia thus never opened Assassin kindred and missed her whole
    # tribal package (Assassin Initiate / Rooftop Bypass). Real oracle.
    lydia = {
        "name": "Lydia Frye",
        "type_line": "Legendary Creature — Human Assassin",
        "mana_cost": "{2}{U/B}",
        "power": "3",
        "toughness": "2",
        "oracle_text": (
            "Lydia Frye can't be blocked by creatures with power 3 or greater.\n"
            "At the beginning of your end step, surveil X, where X is the number of "
            "tapped Assassins you control. (Look at the top X cards of your library, "
            "then put any number of them into your graveyard and the rest on top of "
            "your library in any order.)"
        ),
    }
    assert ("type_matters", "you", "Assassin") in _ksub(lydia)
    # The vocab gate still drops the generic card-type word in the same adjective form:
    # Foul-Tongue Shriek's "for each attacking creature you control" captures "creature"
    # (dropped). A noncreature, so no own-subtype membership tribal confounds the guard.
    foul_tongue_shriek = {
        "name": "Foul-Tongue Shriek",
        "type_line": "Instant",
        "mana_cost": "{B}",
        "oracle_text": (
            "Target opponent loses 1 life for each attacking creature you control. "
            "You gain that much life."
        ),
    }
    assert "type_matters" not in _keys(foul_tongue_shriek)


def test_keyword_tribe_opens_on_flier_tutor():
    # Isperia tutors "a creature card with flying" — a fliers-matter (keyword-tribe)
    # payoff (CR 109.3 groups by the keyword characteristic). The keyword-tribe patterns
    # matched "creatures you control with flying" / "creature spell with flying" but not
    # the tutor's "creature CARD with flying", so a flying-tribal commander whose only
    # hook is the fetch stayed blind. Real oracle.
    isperia = {
        "name": "Isperia the Inscrutable",
        "type_line": "Legendary Creature — Sphinx",
        "mana_cost": "{1}{W}{W}{U}{U}",
        "power": "3",
        "toughness": "6",
        "oracle_text": (
            "Flying\nWhenever Isperia deals combat damage to a player, choose a card "
            "name. That player reveals their hand. If a card with the chosen name is "
            "revealed this way, search your library for a creature card with flying, "
            "reveal it, put it into your hand, then shuffle."
        ),
    }
    assert ("keyword_tribe", "you", "Flying") in _ksub(isperia)
    # The fetch verb is REQUIRED: a card that merely GAINS flying while "a creature card
    # with flying is in a graveyard" (Cairn Wanderer) is not a fliers-matter payoff — it
    # buffs itself off any graveyard, yours or not — so it must NOT open the tribe. Real
    # oracle.
    cairn = {
        "name": "Cairn Wanderer",
        "type_line": "Creature — Shapeshifter",
        "mana_cost": "{4}{B}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Changeling (This card is every creature type.)\nAs long as a creature card "
            "with flying is in a graveyard, this creature has flying. The same is true "
            "for fear, first strike, double strike, deathtouch, haste, landwalk, "
            "lifelink, protection, reach, trample, shroud, and vigilance."
        ),
    }
    assert ("keyword_tribe", "you", "Flying") not in _ksub(cairn)


def test_direct_damage_opens_on_damage_to_a_creatures_controller():
    # Shocker deals "2 damage to target creature and 2 damage to that creature's
    # controller" — the second clause burns a PLAYER, but the direct_damage player-anchor
    # list lacked "that creature's controller", so a burn pinger never opened the lane and
    # lost its damage doublers (Furnace of Rath / Dictate / Repercussion). Real oracle.
    shocker = {
        "name": "Shocker, Unshakable",
        "type_line": "Legendary Creature — Human Rogue Villain",
        "mana_cost": "{4}{R}{R}",
        "power": "5",
        "toughness": "5",
        "oracle_text": (
            "During your turn, Shocker has first strike.\n"
            "Vibro-Shock Gauntlets — When Shocker enters, he deals 2 damage to target "
            "creature and 2 damage to that creature's controller."
        ),
    }
    assert "direct_damage" in _keys(shocker)
    # A pure creature-only removal ping (no player/controller damage) stays out.
    flame_slash = {
        "name": "Flame Slash",
        "type_line": "Sorcery",
        "mana_cost": "{R}",
        "oracle_text": "Flame Slash deals 4 damage to target creature.",
    }
    assert "direct_damage" not in _keys(flame_slash)


def test_direct_damage_opens_on_target_first_variable_damage():
    # "deals damage to target player equal to N" (target-first) — the variable-damage
    # branch was amount-first ("deals damage equal to N to <target>"), missing this word
    # order. 84 burn cards (Anathemancer, Fanatic of Mogis, Corrupt). phase_crosscheck-
    # surfaced. Real oracle.
    anathemancer = {
        "name": "Anathemancer",
        "type_line": "Creature — Zombie Wizard",
        "mana_cost": "{1}{B}{R}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "When this creature enters, it deals damage to target player equal to the "
            "number of nonbasic lands that player controls.\nUnearth {5}{B}{R} "
            "({5}{B}{R}: Return this card from your graveyard to the battlefield. It "
            "gains haste. Exile it at the beginning of the next end step or if it would "
            "leave the battlefield. Unearth only as a sorcery.)"
        ),
    }
    fanatic_of_mogis = {
        "name": "Fanatic of Mogis",
        "type_line": "Creature — Minotaur Shaman",
        "mana_cost": "{3}{R}",
        "power": "4",
        "toughness": "2",
        "oracle_text": (
            "When this creature enters, it deals damage to each opponent equal to your "
            "devotion to red. (Each {R} in the mana costs of permanents you control "
            "counts toward your devotion to red.)"
        ),
    }
    assert "direct_damage" in _keys(anathemancer)  # to target player equal to N
    assert "direct_damage" in _keys(fanatic_of_mogis)  # to each opponent equal to N
    # creature-only variable damage (to target CREATURE) must stay out — not player burn.
    rockslide_ambush = {
        "name": "Rockslide Ambush",
        "type_line": "Sorcery",
        "mana_cost": "{1}{R}",
        "oracle_text": (
            "Rockslide Ambush deals damage to target creature equal to the number of "
            "Mountains you control."
        ),
    }
    assert "direct_damage" not in _keys(rockslide_ambush)


def test_free_creature_payoff_opens_on_no_mana_spent_to_cast():
    # Satoru draws when creatures enter with "no mana was spent to cast them" — the
    # 0-cost creatures (Ornithopter / Memnite / Phyrexian Walker). ADR-0027 tranche2-C:
    # migrated to the Card IR — an ETB trigger whose condition tree carries a
    # manaspentcondition (phase nests it under an 'or' alongside 'not'>'wascast').
    satoru = {
        "name": "Satoru, the Infiltrator",
        "type_line": "Legendary Creature — Human Ninja Rogue",
        "mana_cost": "{U}{B}",
        "power": "2",
        "toughness": "3",
        "oracle_text": (
            "Menace\nWhenever Satoru and/or one or more other nontoken creatures you "
            "control enter, if none of them were cast or no mana was spent to cast "
            "them, draw a card."
        ),
    }
    satoru_ir = Card(
        oracle_id="x",
        name="Satoru, the Infiltrator",
        faces=(
            Face(
                name="Satoru, the Infiltrator",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="etb", scope="you"),
                        condition=Condition(
                            kind="or",
                            nested=(
                                Condition(
                                    kind="not",
                                    nested=(Condition(kind="wascast"),),
                                ),
                                Condition(kind="manaspentcondition"),
                            ),
                        ),
                        effects=(Effect(category="draw", scope="you"),),
                    ),
                ),
            ),
        ),
    )
    assert "free_creature_payoff" in _keys_hybrid_ir(satoru, satoru_ir)
    # The 4 cast_spell-triggered manaspentcondition cards (Lavinia / Boromir / Roiling
    # Vortex / Vexing Bauble) TAX or COUNTER opponents' free spells — the etb-trigger
    # gate excludes them. Same manaspentcondition, wrong trigger event → no fire.
    boromir = {"name": "Boromir, Warden of the Tower", "oracle_text": ""}
    boromir_ir = Card(
        oracle_id="y",
        name="Boromir, Warden of the Tower",
        faces=(
            Face(
                name="Boromir, Warden of the Tower",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="cast_spell", scope="opp"),
                        condition=Condition(kind="manaspentcondition"),
                        effects=(Effect(category="counter_spell", scope="opp"),),
                    ),
                ),
            ),
        ),
    )
    assert "free_creature_payoff" not in _keys_hybrid_ir(boromir, boromir_ir)
    # "wasn't cast" alone (Preston's blink/token payoff) is NOT the 0-cost "no mana
    # spent" hook — an ETB trigger gated on a bare wascast (no manaspentcondition) wants
    # reanimate/blink, not free creatures.
    preston = {"name": "Preston, the Vanisher", "oracle_text": ""}
    preston_ir = Card(
        oracle_id="z",
        name="Preston, the Vanisher",
        faces=(
            Face(
                name="Preston, the Vanisher",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="etb", scope="you"),
                        condition=Condition(
                            kind="not", nested=(Condition(kind="wascast"),)
                        ),
                        effects=(Effect(category="make_token", scope="you"),),
                    ),
                ),
            ),
        ),
    )
    assert "free_creature_payoff" not in _keys_hybrid_ir(preston, preston_ir)


def test_mass_death_payoff_opens_on_aggregate_death_count():
    # Tobias rewards creatures dying EN MASSE: "for each nontoken creature you controlled
    # that died this turn, create a 2/2 Zombie." A payoff that SCALES with the number of
    # deaths this turn wants board wipes (to force the big turn) + mass-reanimation (to
    # refill after). Nevinyrral / Gadrak / Mahadi share the "for each ... died this turn"
    # shape. Real oracle.
    tobias = {
        "name": "Tobias, Doomed Conqueror",
        "type_line": "Legendary Creature — Human Soldier",
        "mana_cost": "{2}{W}{U}",
        "power": "3",
        "toughness": "2",
        "oracle_text": (
            "Flash\nWhen Tobias dies, for each nontoken creature you controlled that "
            "died this turn, create a 2/2 black Zombie creature token."
        ),
    }
    # ADR-0027: mass_death_payoff migrated to the Card IR — the aggregate "for each …
    # creature … died this turn" count operand is recovered as a `mass_death` marker
    # (read via _DOER_EFFECT_KEYS); the regex path no longer produces it.
    tobias_ir = Card(
        oracle_id="x",
        name="Tobias, Doomed Conqueror",
        faces=(
            Face(
                name="Tobias, Doomed Conqueror",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="mass_death",
                                scope="you",
                                raw="for each nontoken creature you controlled "
                                "that died this turn",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("mass_death_payoff", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(tobias, tobias_ir)
    }
    assert ("mass_death_payoff", "you") not in _ks(tobias)
    # Precision guard: a SINGLE-death conditional with a FIXED reward ("if a creature
    # died this turn, create a Food token") does NOT scale with mass death — Old
    # Flitterfang makes one Food whether 1 or 10 died, so a board wipe buys it nothing.
    # It must NOT open this lane (it's plain death_matters, not a wipe payoff). Real oracle.
    old_flitterfang = {
        "name": "Old Flitterfang",
        "type_line": "Legendary Creature — Rat Faerie",
        "mana_cost": "{4}{B}",
        "power": "3",
        "toughness": "4",
        "oracle_text": (
            "Flying\nAt the beginning of each end step, if a creature died this turn, "
            "create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this "
            'token: You gain 3 life.")\n{2}{B}, Sacrifice another creature or artifact: '
            "Old Flitterfang gets +2/+2 until end of turn."
        ),
    }
    assert "mass_death_payoff" not in _keys(old_flitterfang)


def test_per_target_payoff_opens_on_cost_less_per_target():
    # Hinata's "Spells you cast cost {1} less to cast for each target" makes MULTI-target
    # spells (Aurelia's Fury, Distorting Wake) wildly cheap — the more targets, the bigger
    # the discount. A unique mechanic; it opens a payoff lane that wants variable-target
    # spells. Real oracle.
    hinata = {
        "name": "Hinata, Dawn-Crowned",
        "type_line": "Legendary Creature — Kirin Spirit",
        "mana_cost": "{1}{U}{R}{W}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Flying, trample\nSpells you cast cost {1} less to cast for each target.\n"
            "Spells your opponents cast cost {1} more to cast for each target."
        ),
    }
    # ADR-0027 t2b5-B: migrated to the Card IR (kept_detector) — assert on the
    # production hybrid path (the regex path no longer emits it).
    assert ("per_target_payoff", "you") in _ks_hybrid(hinata)
    # Flat cost reduction (Goblin Electromancer: "cost {1} less to cast", no per-target
    # scaling) is NOT this — it doesn't reward casting one spell at many targets. Real
    # oracle.
    electromancer = {
        "name": "Goblin Electromancer",
        "type_line": "Creature — Goblin Wizard",
        "mana_cost": "{U}{R}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "Instant and sorcery spells you cast cost {1} less to cast.",
    }
    assert "per_target_payoff" not in _keys_hybrid(electromancer)


def test_ability_strip_payoff_opens_on_strip_and_buff():
    # Abigale strips a creature's abilities and KEEPS it as a beater (adds keyword
    # counters), so she wants big cheap creatures whose DRAWBACK she neutralizes — strip
    # Rotting Regisaur's upkeep-discard, keep the 7/6. CR 613.1f (ability-removing +
    # keyword counters share layer 6); CR 122.1b (the counters grant flying/first
    # strike/lifelink). Gated on strip+counter so it's Abigale-specific. Real oracle.
    abigale = {
        "name": "Abigale, Eloquent First-Year",
        "type_line": "Legendary Creature — Bird Bard",
        "mana_cost": "{W/B}{W/B}",
        "power": "1",
        "toughness": "1",
        "oracle_text": (
            "Flying, first strike, lifelink\nWhen Abigale enters, up to one other target "
            "creature loses all abilities. Put a flying counter, a first strike counter, "
            "and a lifelink counter on that creature."
        ),
    }
    assert ("ability_strip_payoff", "you") in _ks(abigale)
    # Lizard ALSO says "loses all abilities" but SETS base power/toughness to 4/4 (CR
    # 613 layer 7b) — it shrinks the target rather than keeping a big body, so it is NOT
    # a drawback-beater payoff and must not open this lane. Real oracle.
    lizard = {
        "name": "Lizard, Connors's Curse",
        "type_line": "Legendary Creature — Lizard Villain",
        "mana_cost": "{2}{G}{G}",
        "power": "5",
        "toughness": "5",
        "oracle_text": (
            "Trample\nLizard Formula — When Lizard, Connors's Curse enters, up to one "
            "other target creature loses all abilities and becomes a green Lizard "
            "creature with base power and toughness 4/4."
        ),
    }
    assert "ability_strip_payoff" not in _keys(lizard)


def test_arcane_matters_opens_on_arcane_payoff():
    # The Unspeakable returns Arcane cards; the Kamigawa Kirins reward casting Arcane
    # spells. Either way the commander wants Arcane-subtype spells (CR 205.3k). Real
    # oracle.
    unspeakable = {
        "name": "The Unspeakable",
        "type_line": "Legendary Creature — Spirit",
        "mana_cost": "{6}{U}{U}{U}",
        "power": "6",
        "toughness": "7",
        "oracle_text": (
            "Flying, trample\nWhenever The Unspeakable deals combat damage to a player, "
            "you may return target Arcane card from your graveyard to your hand."
        ),
    }
    assert ("arcane_matters", "you") in _ks(unspeakable)
    # A commander with no Arcane care does not open it.
    krenko = {
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    assert "arcane_matters" not in _keys(krenko)


def test_enlist_matters_opens_on_enlist():
    # Aradesh has enlist and rewards enlisting, so he wants other enlist creatures plus
    # high-power tap fodder. ADR-0027: enlist_matters is IR-served from the Scryfall
    # `enlist` keyword array, so it comes through the hybrid path, not pure regex.
    aradesh = {
        "name": "Aradesh, the Founder",
        "type_line": "Legendary Creature — Human Soldier",
        "mana_cost": "{2}{W}",
        "power": "1",
        "toughness": "4",
        "keywords": ["Enlist"],
        "oracle_text": (
            "Enlist (As this creature attacks, you may tap a nonattacking creature you "
            "control without summoning sickness. When you do, add its power to this "
            "creature's until end of turn.)\nWhenever a creature you control attacks, if "
            "it enlisted a creature this combat, the creature that attacked gains double "
            "strike until end of turn. If that creature's power is 4 or greater, draw a "
            "card."
        ),
    }
    assert ("enlist_matters", "you") in _ks_hybrid(aradesh)
    assert ("enlist_matters", "you") not in _ks(aradesh)


def test_power_tap_engine_opens_on_tap_ability_scaling_with_power():
    # Mona Lisa's "{T}: Add X mana, where X is Mona Lisa's power" wants UNTAP effects
    # (re-tap for more mana) and power pumps. A {T} ability that scales with a creature's
    # power is the tell; Krenko's {T} scales with Goblin count, not power. Real oracle.
    # ADR-0027: power_tap_engine migrated to the Card IR (an ACTIVATED ability cost~'tap'
    # + a power-scaling effect raw), so it is served via the hybrid path, not pure regex.
    mona_lisa = {
        "name": "Mona Lisa, Science Geek",
        "type_line": "Legendary Creature — Lizard Mutant",
        "mana_cost": "{2}{G}",
        "power": "1",
        "toughness": "3",
        "oracle_text": (
            "Reach\n{T}: Add X mana of any one color, where X is Mona Lisa's power."
        ),
    }
    mona_ir = Card(
        oracle_id="x",
        name="Mona Lisa, Science Geek",
        faces=(
            Face(
                name="Mona Lisa, Science Geek",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="tap",
                        effects=(
                            Effect(
                                category="ramp",
                                scope="any",
                                raw="{T}: Add X mana, where X is ~'s power.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("power_tap_engine", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(mona_lisa, mona_ir)
    }
    assert "power_tap_engine" not in {s.key for s in extract_signals(mona_lisa)}
    krenko = {
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    krenko_ir = Card(
        oracle_id="y",
        name="Krenko, Mob Boss",
        faces=(
            Face(
                name="Krenko, Mob Boss",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="tap",
                        effects=(
                            Effect(
                                category="make_token",
                                scope="you",
                                raw=(
                                    "{T}: Create X 1/1 red Goblin creature tokens, "
                                    "where X is the number of Goblins you control."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "power_tap_engine" not in {
        s.key for s in extract_signals_hybrid(krenko, krenko_ir)
    }


def test_recast_etb_opens_on_sneak():
    # Oroku Saki's Sneak (return an unblocked attacker, recast cheaply) replays a
    # creature's ETB, so he wants cheap aggressive-ETB creatures (recast = repeat the
    # bleed). ADR-0027: recast_etb migrated to the Card IR — the regex path no longer
    # emits it; the hybrid serves it from the Scryfall `Sneak` keyword. Real oracle.
    oroku_saki = {
        "name": "Oroku Saki, Shredder Rising",
        "type_line": "Legendary Creature — Human Ninja",
        "mana_cost": "{2}{B}",
        "power": "3",
        "toughness": "1",
        "keywords": ["Sneak"],
        "oracle_text": (
            "Sneak {1}{B} (You may cast this spell for {1}{B} if you also return an "
            "unblocked attacker you control to hand during the declare blockers step. He "
            "enters tapped and attacking.)\nWhenever Oroku Saki deals combat damage to a "
            "player, you draw a card and lose 1 life."
        ),
    }
    assert "recast_etb" not in _keys(oroku_saki)
    assert ("recast_etb", "you") in _ks_hybrid_card(oroku_saki, _bare_ir())
    krenko = {
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    assert "recast_etb" not in _keys_hybrid(krenko)


def test_type_change_opens_on_creature_type_hoser():
    # Gor Muldrak has "protection from Salamanders" and seeds opponents with Salamander
    # tokens — so he wants creature-type CHANGERS to turn the rest of their board into
    # Salamanders, which his protection then blanks (creature type is continuously
    # checked, CR 205.3 / 702.16). Real oracle.
    # ADR-0027 t2b4-C: type_change migrated to the Card IR — the regex path no longer
    # emits it; it fires from the _type_hoser_clause subtype-gated mirror (bare IR).
    gor_muldrak = {
        "name": "Gor Muldrak, Amphinologist",
        "type_line": "Legendary Creature — Human Scout",
        "mana_cost": "{1}{G}{U}",
        "power": "3",
        "toughness": "2",
        "oracle_text": (
            "You and permanents you control have protection from Salamanders.\nAt the "
            "beginning of your end step, each player who controls the fewest creatures "
            "creates a 4/3 blue Salamander Warrior creature token."
        ),
    }
    assert "type_change" not in _keys(gor_muldrak)
    assert ("type_change", "you") in _ks_hybrid(gor_muldrak)
    # The captured word is validated against the subtype vocab, so a plain
    # "protection from black" (a color, not a creature type) is not a type hoser.
    krenko = {
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    assert "type_change" not in _keys_hybrid(krenko)


def test_exert_matters_opens_on_pseudo_vigilance():
    # Johan grants "attacking doesn't cause creatures you control to tap", which makes an
    # exert creature's "won't untap next turn" cost free — so he wants exert creatures.
    # ADR-0027: exert_matters migrated to the Card IR — the regex path no longer emits
    # it; the Johan namesake is served by a kept word mirror (oracle scan → bare IR).
    # Real oracle.
    johan = {
        "name": "Johan",
        "type_line": "Legendary Creature — Human Wizard",
        "mana_cost": "{3}{R}{G}{W}",
        "power": "5",
        "toughness": "4",
        "oracle_text": (
            'At the beginning of combat on your turn, you may have Johan gain "Johan '
            "can't attack\" until end of combat. If you do, attacking doesn't cause "
            "creatures you control to tap this combat if Johan is untapped."
        ),
    }
    assert "exert_matters" not in _keys(johan)
    assert ("exert_matters", "you") in _ks_hybrid(johan)
    krenko = {
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    assert "exert_matters" not in _keys_hybrid(krenko)


def test_tap_down_blockers_opens_on_unblockable_unless_all():
    # Tromokratis connects only if the defender can't field enough blockers, so it wants
    # to tap their creatures down. Real oracle.
    # ADR-0027 t2b4-C: tap_down_blockers migrated to the Card IR — the regex path no
    # longer emits it; it fires from a kept word mirror (bare IR routes to the IR path).
    tromokratis = {
        "name": "Tromokratis",
        "type_line": "Legendary Creature — Kraken",
        "mana_cost": "{5}{U}{U}",
        "power": "8",
        "toughness": "8",
        "oracle_text": (
            "Tromokratis has hexproof unless it's attacking or blocking.\nTromokratis "
            "can't be blocked unless all creatures defending player controls block it. "
            "(If any creature that player controls doesn't block this creature, it can't "
            "be blocked.)"
        ),
    }
    assert "tap_down_blockers" not in _keys(tromokratis)
    assert ("tap_down_blockers", "you") in _ks_hybrid(tromokratis)


def test_island_matters_opens_on_island_attack_restriction():
    # Zhou Yu can only attack if the defender controls an Island, so he wants to turn
    # opponents' lands into Islands. Real oracle.
    zhou_yu = {
        "name": "Zhou Yu, Chief Commander",
        "type_line": "Legendary Creature — Human Soldier",
        "mana_cost": "{5}{U}{U}",
        "power": "8",
        "toughness": "8",
        "oracle_text": "Zhou Yu can't attack unless defending player controls an Island.",
    }
    assert ("island_matters", "you") in _ks(zhou_yu)


def test_entered_attacker_opens_on_entered_this_turn_combat():
    # Samut rewards a creature that ENTERED this turn dealing combat damage, so she wants
    # haste + ETB-pump to let fresh creatures swing at once. Real oracle.
    samut = {
        "name": "Samut, Vizier of Naktamun",
        "type_line": "Legendary Creature — Human Warrior Cleric",
        "mana_cost": "{1}{R}{G}",
        "power": "2",
        "toughness": "3",
        "oracle_text": (
            "First strike, vigilance, haste\nWhenever a creature you control deals "
            "combat damage to a player, if that creature entered this turn, draw a card."
        ),
    }
    # ADR-0027 β: entered_attacker migrated to the Card IR (a byte-identical kept-mirror
    # over the reminder-stripped oracle), so it serves from the hybrid path.
    assert ("entered_attacker", "you") in _ks_hybrid(samut)


def test_land_protection_opens_on_land_animation():
    # Noyan Dar turns lands into creatures, which die to removal and wraths, so he wants
    # land protection. Real oracle.
    noyan_dar = {
        "name": "Noyan Dar, Roil Shaper",
        "type_line": "Legendary Creature — Merfolk Ally",
        "mana_cost": "{3}{W}{U}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Whenever you cast an instant or sorcery spell, you may put three +1/+1 "
            "counters on target land you control. If you do, that land becomes a 0/0 "
            "Elemental creature with haste that's still a land."
        ),
    }
    # ADR-0027: land_protection migrated to the Card IR — the land-animator predicate
    # (a base_pt_set with subject=None whose ability-level raw says "land … becomes a
    # creature"). Assert via the hybrid path.
    noyan_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="place_counter",
                    counter_kind="p1p1",
                    scope="you",
                    subject=Filter(card_types=("Land",), controller="you"),
                    raw="put three +1/+1 counters on target land you control",
                ),
                Effect(
                    category="base_pt_set",
                    scope="you",
                    raw="that land becomes a 0/0 Elemental creature that's still a land",
                ),
            ),
        )
    )
    assert ("land_protection", "you") in _ks_hybrid_ir(noyan_dar, noyan_ir)


def test_lose_unless_hand_opens_on_cast_from_hand_drawback():
    # Phage loses you the game if not cast from hand, so she wants to negate that. Real
    # oracle. ADR-0027: lose_unless_hand migrated to the Card IR (an ETB trigger scoped
    # YOU + a lose_game effect), so it is served via the hybrid path, not pure regex.
    phage = {
        "name": "Phage the Untouchable",
        "type_line": "Legendary Creature — Avatar Minion",
        "mana_cost": "{3}{B}{B}{B}{B}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "When Phage enters, if you didn't cast it from your hand, you lose the "
            "game.\nWhenever Phage deals combat damage to a creature, destroy that "
            "creature. It can't be regenerated.\nWhenever Phage deals combat damage to "
            "a player, that player loses the game."
        ),
    }
    phage_ir = Card(
        oracle_id="x",
        name="Phage the Untouchable",
        faces=(
            Face(
                name="Phage the Untouchable",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="etb", scope="you"),
                        effects=(
                            Effect(
                                category="lose_game",
                                scope="you",
                                raw=(
                                    "When ~ enters, if you didn't cast it from your "
                                    "hand, you lose the game."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("lose_unless_hand", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(phage, phage_ir)
    }
    assert "lose_unless_hand" not in {s.key for s in extract_signals(phage)}


def test_land_denial_opens_on_phasing_lands():
    # Taniwha's lands phase back each turn, so symmetric land-denial stax hits opponents
    # permanently while it recovers. Real oracle.
    taniwha = {
        "name": "Taniwha",
        "type_line": "Legendary Creature — Serpent",
        "mana_cost": "{3}{U}{U}",
        "power": "7",
        "toughness": "7",
        "oracle_text": (
            "Trample\nPhasing (This phases in or out before you untap during each of "
            "your untap steps. While it's phased out, it's treated as though it doesn't "
            "exist.)\nAt the beginning of your upkeep, all lands you control phase out. "
            "(They phase in before you untap during your next untap step.)"
        ),
    }
    # ADR-0027: land_denial migrated to the Card IR — a `phasing` Effect on a Land
    # subject with controller=='you'. Assert via the hybrid path.
    taniwha_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="phasing",
                    scope="you",
                    subject=Filter(card_types=("Land",), controller="you"),
                    raw="all lands you control phase out",
                ),
            ),
        )
    )
    assert ("land_denial", "you") in _ks_hybrid_ir(taniwha, taniwha_ir)


def test_multicolor_matters_opens_on_color_pair_payoff():
    # Niv-Mizzet Reborn draws cards by exact color pair, so it's a gold-cards deck that
    # wants the multicolored payoffs. Real oracle. ADR-0027: multicolor_matters migrated
    # to the Card IR (the "for each color pair" / "exactly those colors" kept word
    # mirror), so it comes through the hybrid path, not pure regex.
    niv = {
        "name": "Niv-Mizzet Reborn",
        "type_line": "Legendary Creature — Dragon Avatar",
        "mana_cost": "{W}{U}{B}{R}{G}",
        "power": "6",
        "toughness": "6",
        "oracle_text": (
            "Flying\nWhen Niv-Mizzet enters, reveal the top ten cards of your library. "
            "For each color pair, choose a card that's exactly those colors from among "
            "them. Put the chosen cards into your hand and the rest on the bottom of "
            "your library in a random order."
        ),
    }
    assert ("multicolor_matters", "you") in _ks_hybrid(niv)
    assert ("multicolor_matters", "you") not in _ks(niv)


def test_target_own_payoff_opens_on_targeted_your_creature():
    # Monk Gyatso airbends a creature you control whenever it becomes the target, so he
    # wants free ways to target your own creatures. Real oracle.
    gyatso = {
        "name": "Monk Gyatso",
        "type_line": "Legendary Creature — Human Monk",
        "mana_cost": "{3}{W}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "Whenever another creature you control becomes the target of a spell or "
            "ability, you may airbend that creature. (Exile it. While it's exiled, its "
            "owner may cast it for {2} rather than its mana cost.)"
        ),
    }
    # ADR-0027 t2b5-B: migrated to the Card IR (kept_detector) — assert on hybrid.
    assert ("target_own_payoff", "you") in _ks_hybrid(gyatso)


def test_life_payment_insurance_opens_on_repeatable_pay_life():
    # ADR-0027: life_payment_insurance migrated to the Card IR — Selenia's "Pay 2 life:"
    # is a repeatable activation COST ("paylife" in Ability.cost), read through the
    # hybrid IR path, not the regex.
    selenia = {
        "name": "Selenia, Dark Angel",
        "type_line": "Legendary Creature — Phyrexian Angel",
        "oracle_text": "Flying\nPay 2 life: Return Selenia to its owner's hand.",
    }
    selenia_ir = Card(
        oracle_id="x",
        name="Selenia, Dark Angel",
        faces=(
            Face(
                name="Selenia, Dark Angel",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="paylife",
                        effects=(
                            Effect(
                                category="bounce",
                                scope="you",
                                raw="Return Selenia to its owner's hand",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("life_payment_insurance", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(selenia, selenia_ir)
    }
    assert ("life_payment_insurance", "you") not in _ks(selenia)


def test_land_exchange_opens_on_land_control():
    # ADR-0027: land_exchange migrated to the Card IR — phase parses "exchange control
    # of target X and target Y" as a gain_control effect with subject=None, read by
    # the _LAND_EXCHANGE_RAW fallback. Political Trickery is the genuine swap. Sharkey
    # (which copies/taxes land abilities, never EXCHANGES control) was the regex's lone
    # false positive — it emits no gain_control effect, so the IR correctly drops it.
    trickery = {
        "name": "Political Trickery",
        "type_line": "Sorcery",
        "oracle_text": (
            "Exchange control of target land you control and target land an "
            "opponent controls. (This effect lasts indefinitely.)"
        ),
    }
    ir = Card(
        oracle_id="x",
        name="Political Trickery",
        faces=(
            Face(
                name="Political Trickery",
                abilities=(
                    Ability(
                        kind="spell",
                        effects=(
                            Effect(
                                category="gain_control",
                                scope="any",
                                subject=None,
                                raw=(
                                    "Exchange control of target land you control "
                                    "and target land an opponent controls."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("land_exchange", "you") in _ks_hybrid_card(trickery, ir)
    sharkey = {
        "name": "Sharkey, Tyrant of the Shire",
        "type_line": "Legendary Creature — Avatar Rogue",
        "oracle_text": (
            "Activated abilities of lands your opponents control can't be activated "
            "unless they're mana abilities.\nSharkey has all activated abilities of "
            "lands your opponents control except mana abilities.\nMana of any type can "
            "be spent to activate Sharkey's abilities."
        ),
    }
    assert ("land_exchange", "you") not in _ks(sharkey)


def _ks_hybrid_card(card, ir):
    return {(s.key, s.scope) for s in extract_signals_hybrid(card, ir)}


def test_scavenge_fuel_opens_on_scavenge():
    # Varolz gives graveyard creatures scavenge (counters = the card's power), so he
    # wants high-power creatures as the biggest payloads. Real oracle.
    varolz = {
        "name": "Varolz, the Scar-Striped",
        "type_line": "Legendary Creature — Troll Warrior",
        "mana_cost": "{1}{B}{G}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "Each creature card in your graveyard has scavenge. The scavenge cost is "
            "equal to its mana cost. (Exile a creature card from your graveyard and pay "
            "its mana cost: Put a number of +1/+1 counters equal to that card's power "
            "on target creature. Scavenge only as a sorcery.)\nSacrifice another "
            "creature: Regenerate Varolz."
        ),
    }
    # ADR-0027: scavenge_fuel migrated to the Card IR — Varolz is a keyword-less
    # graveyard-wide GRANTER, recovered by a `scavenge` dropped-static face marker
    # (read via _DOER_EFFECT_KEYS), so the lane opens through the hybrid IR path.
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="scavenge", scope="you", raw="has scavenge"
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(varolz, ir)}
    assert ("scavenge_fuel", "you") in hybrid
    assert ("scavenge_fuel", "you") not in _ks(varolz)


def test_free_spell_storm_opens_on_cost_less_per_spell():
    # Thrasta's cost drops {3} per other spell cast this turn, so it wants free spells to
    # chain. Real oracle.
    thrasta = {
        "name": "Thrasta, Tempest's Roar",
        "type_line": "Legendary Creature — Dinosaur",
        "mana_cost": "{10}{G}{G}",
        "power": "7",
        "toughness": "7",
        "oracle_text": (
            "This spell costs {3} less to cast for each other spell cast this turn.\n"
            "Trample, haste\nTrample over planeswalkers (This creature can deal excess "
            "combat damage to the controller of the planeswalker it's attacking.)\n"
            "Thrasta has hexproof as long as it entered this turn."
        ),
    }
    # ADR-0027 β: free_spell_storm migrated to the Card IR — phase's SelfRef
    # ModifyCost{Reduce} static is dropped by project (a self-discount is excluded from
    # the build-around cost_reduction lane), so project._free_spell_storm_marker
    # re-surfaces it as a dedicated `free_spell_storm` STATIC Effect the hybrid reads.
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="free_spell_storm",
                                scope="you",
                                raw=(
                                    "This spell costs {3} less to cast for each other "
                                    "spell cast this turn."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    hybrid = {(s.key, s.scope) for s in extract_signals_hybrid(thrasta, ir)}
    assert ("free_spell_storm", "you") in hybrid
    assert ("free_spell_storm", "you") not in _ks(thrasta)


def test_target_redirect_opens_on_draw_when_targeted():
    # Rayne draws when an opponent targets your stuff, so it wants target-redirect to
    # shunt the spell onto a cheap permanent. Real oracle.
    rayne = {
        "name": "Rayne, Academy Chancellor",
        "type_line": "Legendary Creature — Human Wizard",
        "mana_cost": "{2}{U}",
        "power": "1",
        "toughness": "1",
        "oracle_text": (
            "Whenever you or a permanent you control becomes the target of a spell or "
            "ability an opponent controls, you may draw a card. You may draw an "
            "additional card if Rayne is enchanted."
        ),
    }
    # ADR-0027 t2b5-B: migrated to the Card IR (kept_detector) — assert on hybrid.
    assert ("target_redirect", "you") in _ks_hybrid(rayne)


def test_artifacts_matter_opens_on_investigate():
    # "Investigate" creates a Clue token — an artifact (keyword action) — so an
    # investigate commander (Sophina) is an artifact deck whose Clues trigger artifact
    # payoffs (Reckless Fireweaver / Ingenious Artillerist). "create a Clue token"
    # already opened the lane; the keyword action "investigate" must too. Real oracle.
    sophina = {
        "name": "Sophina, Spearsage Deserter",
        "type_line": "Legendary Creature — Human Soldier",
        "mana_cost": "{2}{R}{W}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "Menace\nWhenever Sophina, Spearsage Deserter attacks, investigate once for "
            "each nontoken attacking creature. (To investigate, create a Clue token. "
            'It\'s an artifact with "{2}, Sacrifice this artifact: Draw a card.")\n'
            "Partner—Friends forever (You can have two commanders if both have this "
            "ability.)"
        ),
    }
    # ADR-0027: artifacts_matter migrated to the Card IR (the kept oracle mirror catches
    # \binvestigate\b); clue_matters is NOT migrated. The hybrid path emits both.
    keys = _keys_hybrid(sophina)
    assert "artifacts_matter" in keys  # Clue tokens are artifacts
    assert "clue_matters" in keys  # still a Clue commander too


def test_token_copy_matters_opens_on_token_doubling():
    # A token DOUBLER ("twice that many tokens are created" — Adrix and Nev, Mondrak)
    # wants token-COPY effects: Rite of Replication / Esix make token copies, which the
    # doubler then doubles. So it IS a token-copy commander. The detector only knew
    # "token that's a copy" / populate, so token-doublers never opened the lane and lost
    # their copy spells. Real oracle.
    adrix = {
        "name": "Adrix and Nev, Twincasters",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "mana_cost": "{2}{G}{U}",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "Ward {2} (Whenever this creature becomes the target of a spell or ability "
            "an opponent controls, counter it unless that player pays {2}.)\nIf one or "
            "more tokens would be created under your control, twice that many of those "
            "tokens are created instead."
        ),
    }
    mondrak = {
        "name": "Mondrak, Glory Dominus",
        "type_line": "Legendary Creature — Phyrexian Horror",
        "mana_cost": "{2}{W}{W}",
        "power": "4",
        "toughness": "4",
        "oracle_text": (
            "If one or more tokens would be created under your control, twice that many "
            "of those tokens are created instead.\n{1}{W/P}{W/P}, Sacrifice two other "
            "artifacts and/or creatures: Put an indestructible counter on Mondrak. "
            "({W/P} can be paid with either {W} or 2 life.)"
        ),
    }
    krenko = {  # a plain token MAKER (not a copier/doubler) must NOT open the lane
        "name": "Krenko, Mob Boss",
        "type_line": "Legendary Creature — Goblin Warrior",
        "mana_cost": "{2}{R}{R}",
        "power": "3",
        "toughness": "3",
        "oracle_text": (
            "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of "
            "Goblins you control."
        ),
    }
    # ADR-0027 β: token_copy_matters migrated to the Card IR (a byte-identical kept-
    # mirror over the reminder-stripped oracle), so it serves from the hybrid path.
    assert "token_copy_matters" in _keys_hybrid(adrix)
    assert "token_copy_matters" in _keys_hybrid(mondrak)
    assert "token_copy_matters" not in _keys_hybrid(krenko)


def test_clone_matters_opens_for_recurring_value_legendary():
    # "Clone your engine" is legitimate for a recurring-value LEGENDARY: copying it forks
    # the per-turn engine and the copy dodges the legend rule. Obeka ("{T}: end the turn")
    # and Koma (per-upkeep token engine) are clone targets; a vanilla legendary (Isamaru)
    # is not. Commander-level (membership), so it must NOT fire for the 99. Real oracle.
    obeka = {
        "name": "Obeka, Brute Chronologist",
        "type_line": "Legendary Creature — Ogre Wizard",
        "mana_cost": "{1}{U}{B}{R}",
        "power": "3",
        "toughness": "4",
        "oracle_text": (
            "{T}: The player whose turn it is may end the turn. (Exile all spells and "
            "abilities from the stack. The player whose turn it is discards down to "
            'their maximum hand size. Damage wears off, and "this turn" and "until end '
            'of turn" effects end.)'
        ),
    }
    koma = {
        "name": "Koma, Cosmos Serpent",
        "type_line": "Legendary Creature — Serpent",
        "mana_cost": "{3}{G}{G}{U}{U}",
        "power": "6",
        "toughness": "6",
        "oracle_text": (
            "This spell can't be countered.\nAt the beginning of each upkeep, create a "
            "3/3 blue Serpent creature token named Koma's Coil.\nSacrifice another "
            "Serpent: Choose one —\n• Tap target permanent. Its activated abilities "
            "can't be activated this turn.\n• Koma gains indestructible until end of "
            "turn."
        ),
    }
    isamaru = {  # vanilla legendary — no repeatable engine
        "name": "Isamaru, Hound of Konda",
        "type_line": "Legendary Creature — Dog",
        "mana_cost": "{W}",
        "power": "2",
        "toughness": "2",
        "oracle_text": "",
    }
    # Obeka, Splitter of Seconds — the extra-PHASE engine (combat damage -> additional
    # upkeep steps). Dan clones THIS Obeka; extra-turn/phase generators are premium
    # clone targets (cloning multiplies the extra phases). Real oracle.
    obeka_splitter = {
        "name": "Obeka, Splitter of Seconds",
        "type_line": "Legendary Creature — Ogre Warlock",
        "mana_cost": "{1}{U}{B}{R}",
        "power": "2",
        "toughness": "5",
        "oracle_text": (
            "Menace\nWhenever Obeka deals combat damage to a player, you get that many "
            "additional upkeep steps after this phase."
        ),
    }
    assert "clone_matters" in _keys(obeka)  # {T} engine
    assert "clone_matters" in _keys(koma)  # per-upkeep engine
    assert "clone_matters" in _keys(obeka_splitter)  # extra-upkeep engine
    assert "clone_matters" not in _keys(isamaru)  # vanilla legendary
    # Commander-level: must NOT fire when aggregating the 99 (include_membership=False).
    assert "clone_matters" not in {
        s.key for s in extract_signals(obeka, include_membership=False)
    }


def test_clone_engine_fires_for_legendary_with_intervening_card_type():
    # The engine-clone suggestion gated on the contiguous substring "legendary creature",
    # so a "Legendary ENCHANTMENT Creature" (Go-Shintai) or "Legendary ARTIFACT Creature"
    # was wrongly excluded — yet a Shrine whose mill SCALES per-Shrine is a textbook
    # clone-your-engine target: fork the end-step engine, dodge the legend rule. Real
    # oracle.
    go_shintai = {
        "name": "Go-Shintai of Lost Wisdom",
        "type_line": "Legendary Enchantment Creature — Shrine",
        "mana_cost": "{1}{U}",
        "power": "0",
        "toughness": "4",
        "oracle_text": (
            "Flying\nAt the beginning of your end step, you may pay {1}. When you do, "
            "target player mills X cards, where X is the number of Shrines you control. "
            "(To mill a card, a player puts the top card of their library into their "
            "graveyard.)"
        ),
    }
    assert ("clone_matters", "you", "") in _ksub(go_shintai)
    # Precision: broadening the type gate must not bypass the ENGINE gate. A legendary
    # enchantment creature with only static abilities and a non-tap activated ability
    # (Heliod, Sun-Crowned — no per-turn trigger, no {T} ability) is not a clone-your-
    # engine target. Real oracle.
    heliod = {
        "name": "Heliod, Sun-Crowned",
        "type_line": "Legendary Enchantment Creature — God",
        "mana_cost": "{2}{W}",
        "power": "5",
        "toughness": "5",
        "oracle_text": (
            "Indestructible\nAs long as your devotion to white is less than five, Heliod "
            "isn't a creature.\nWhenever you gain life, put a +1/+1 counter on target "
            "creature or enchantment you control.\n{1}{W}: Another target creature gains "
            "lifelink until end of turn."
        ),
    }
    assert ("clone_matters", "you", "") not in _ksub(heliod)


def test_token_maker_prefers_creature_subtype_over_artifact_word():
    c = {
        "name": "Urza, Lord High Artificer",
        "oracle_text": 'When Urza enters, create a 0/0 colorless Construct artifact creature token with "This token gets +1/+1 for each artifact you control."\nTap an untapped artifact you control: Add {U}.\n{5}: Shuffle your library, then exile the top card. Until end of turn, you may play that card without paying its mana cost.',
    }
    assert ("token_maker", "you", "Construct") in _ksub(c)


def test_typed_spellcast_captures_tribe():
    c = {
        "name": "The First Sliver",
        "oracle_text": "Cascade (When you cast this spell, exile cards from the top of your library until you exile a nonland card that costs less. You may cast it without paying its mana cost. Put the exiled cards on the bottom in a random order.)\nSliver spells you cast have cascade.",
    }
    assert ("typed_spellcast", "you", "Sliver") in _ksub(c)


def test_typed_spellcast_rejects_instant_and_sorcery():
    # "Instant and sorcery spells you cast" is spellslinger, NOT a tribe.
    c = {
        "name": "Mizzix of the Izmagnus",
        "oracle_text": "Whenever you cast an instant or sorcery spell with mana value greater than the number of experience counters you have, you get an experience counter.\nInstant and sorcery spells you cast cost {1} less to cast for each experience counter you have.",
    }
    assert "typed_spellcast" not in _keys(c)


# --- false-positive guards -----------------------------------------------------


def test_clone_yields_no_subject_signal():
    c = {
        "name": "Silent Hallcreeper",
        "oracle_text": "This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
    }
    assert _keys(c).isdisjoint({"type_matters", "token_maker", "typed_spellcast"})


def test_plant_token_maker_keeps_subject_but_not_land_creatures():
    # Avenger makes Plant tokens — token_maker/Plant is CORRECT; it must not be
    # mistaken for the land-creatures theme. ADR-0027: both token_maker and
    # land_creatures_matter are IR-served, so assert via the hybrid path with a
    # Plant (not Land) token subject.
    c = {
        "name": "Avenger of Zendikar",
        "oracle_text": "When this creature enters, create a 0/1 green Plant creature token for each land you control.\nLandfall — Whenever a land you control enters, you may put a +1/+1 counter on each Plant creature you control.",
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
    s = _ksub_hybrid(c, avenger_ir)
    assert ("token_maker", "you", "Plant") in s
    assert not any(k == "land_creatures_matter" for k, _, _ in s)


def test_yedora_forest_land_maker_opens_land_creatures():
    # Yedora returns dead creatures as face-down Forest LANDS ("It's a Forest
    # land."). Those lands are exactly what animate-your-lands payoffs (Life and
    # Limb, Living Plane) turn into a creature army, so she belongs in the
    # existing land-creatures lane, reached via her "It's a Forest land" tell.
    c = {
        "name": "Yedora, Grave Gardener",
        "type_line": "Legendary Creature — Treefolk Druid",
        "mana_cost": "{4}{G}",
        "power": "5",
        "toughness": "5",
        "keywords": [],
        "oracle_text": "Whenever another nontoken creature you control dies, you may return it to the battlefield face down under its owner's control. It's a Forest land. (It has no other types or abilities.)",
    }
    # ADR-0027: the "(it's|becomes) a forest land" maker tail rides the kept oracle
    # mirror (phase parses Yedora as a reanimate, dropping the Forest-land tell), so
    # assert via the hybrid path — any non-None IR routes to the mirror-bearing path.
    assert any(k == "land_creatures_matter" for k, _, _ in _ksub_hybrid(c, _bare_ir()))


def test_repeatable_aoe_ping_opens_for_deathtouch_combo():
    # Tibor's recurring "deals 1 damage to each creature" is a REPEATABLE board
    # ping (whenever you cast a red spell) — with deathtouch on the source it's a
    # recurring board wipe (CR 702.2b). Pestilence is the same via an activated
    # ability. A one-shot ETB sweep (Chaos Maw) must NOT open it: deathtouch gear
    # can't be attached when the ETB resolves, so it's not the combo.
    tibor = {
        "name": "Tibor and Lumia",
        "type_line": "Legendary Creature — Human Wizard",
        "mana_cost": "{2}{U}{R}",
        "power": "2",
        "toughness": "2",
        "keywords": [],
        "oracle_text": "Whenever you cast a blue spell, target creature gains flying until end of turn.\nWhenever you cast a red spell, Tibor and Lumia deals 1 damage to each creature without flying.",
    }
    pestilence = {
        "name": "Pestilence",
        "type_line": "Enchantment",
        "mana_cost": "{2}{B}{B}",
        "keywords": [],
        "oracle_text": "At the beginning of the end step, if no creatures are on the battlefield, sacrifice this enchantment.\n{B}: This enchantment deals 1 damage to each creature and each player.",
    }
    chaos_maw = {
        "name": "Chaos Maw",
        "type_line": "Creature — Hellion",
        "mana_cost": "{5}{R}{R}",
        "power": "6",
        "toughness": "6",
        "keywords": [],
        "oracle_text": "When this creature enters, it deals 3 damage to each other creature.",
    }
    # ADR-0027 tranche2-A: aoe_ping migrated to the Card IR — a counter_kind="all"
    # damage Effect over a Creature subject on a REPEATABLE-FRAME ability (a cast-trigger
    # for Tibor, an activated mana cost for Pestilence). A one-shot ETB sweep (Chaos Maw,
    # event="etb") is NOT repeatable and must stay out. Asserted via the hybrid.
    tibor_ir = Card(
        oracle_id="tibor",
        name="Tibor and Lumia",
        faces=(
            Face(
                name="Tibor and Lumia",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="cast_spell", scope="you"),
                        effects=(
                            Effect(
                                category="damage",
                                counter_kind="all",
                                subject=Filter(card_types=("Creature",)),
                                raw="~ deals 1 damage to each creature without flying.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    pestilence_ir = Card(
        oracle_id="pestilence",
        name="Pestilence",
        faces=(
            Face(
                name="Pestilence",
                abilities=(
                    Ability(
                        kind="activated",
                        cost="mana",
                        effects=(
                            Effect(
                                category="damage",
                                counter_kind="all",
                                subject=Filter(card_types=("Creature",)),
                                raw="~ deals 1 damage to each creature and each player.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    chaos_maw_ir = Card(
        oracle_id="chaos_maw",
        name="Chaos Maw",
        faces=(
            Face(
                name="Chaos Maw",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="etb", scope="you"),
                        effects=(
                            Effect(
                                category="damage",
                                counter_kind="all",
                                subject=Filter(card_types=("Creature",)),
                                raw="it deals 3 damage to each other creature.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert any(k == "aoe_ping" for k, _, _ in _ksub_hybrid(tibor, tibor_ir))
    assert any(k == "aoe_ping" for k, _, _ in _ksub_hybrid(pestilence, pestilence_ir))
    assert not any(k == "aoe_ping" for k, _, _ in _ksub_hybrid(chaos_maw, chaos_maw_ir))
    # And the regex path no longer fires it (the _HAND_FLOOR producer is deleted).
    assert not any(k == "aoe_ping" for k, _, _ in _ksub(tibor))


def test_numot_repeatable_land_destruction_opens_lane():
    # Numot destroys lands every time she connects — a repeatable land-destruction
    # ENGINE (the commander herself), so she wants the LD support package (land
    # recursion to survive symmetric LD, land-loss punishers). Membership + creature
    # gated: a one-shot LD SPELL (Stone Rain) is not an LD commander, so it stays out.
    # ADR-0027: land_destruction migrated to the Card IR (the membership-gated
    # _LAND_DESTRUCTION_MIRROR arm, reproducing the deleted regex cross-open byte-
    # identically), so this asserts on the HYBRID path. A bare non-None IR routes the
    # hybrid to the IR path; the mirror reads type_line + oracle_text off the record.
    numot = {
        "name": "Numot, the Devastator",
        "type_line": "Legendary Creature — Dragon",
        "mana_cost": "{3}{U}{R}{W}",
        "power": "6",
        "toughness": "6",
        "keywords": ["Flying"],
        "oracle_text": "Flying\nWhenever Numot deals combat damage to a player, you may pay {2}{R}. If you do, destroy up to two target lands.",
    }
    stone_rain = {
        "name": "Stone Rain",
        "type_line": "Sorcery",
        "mana_cost": "{2}{R}",
        "keywords": [],
        "oracle_text": "Destroy target land.",
    }
    assert any(k == "land_destruction" for k, _, _ in _ksub_hybrid(numot, _bare_ir()))
    assert not any(
        k == "land_destruction" for k, _, _ in _ksub_hybrid(stone_rain, _bare_ir())
    )


def test_cheat_from_top_commander_opens_lane():
    # Vaevictis / Hans reveal the top card and cheat a permanent onto the battlefield,
    # so they want to STACK their top with a bomb (graveyard-to-top). Requires BOTH the
    # reveal-top tell AND the puts-onto-battlefield tell: a plain reanimation spell
    # (Reanimate) puts a creature onto the battlefield but never reveals the top, so it
    # is not a top-cheater and stays out.
    vaevictis = {
        "name": "Vaevictis Asmadi, the Dire",
        "type_line": "Legendary Creature — Elder Dragon",
        "mana_cost": "{3}{B}{R}{G}",
        "power": "6",
        "toughness": "6",
        "keywords": ["Flying"],
        "oracle_text": "Flying\nWhenever Vaevictis Asmadi attacks, for each player, choose target permanent that player controls. Those players sacrifice those permanents. Each player who sacrificed a permanent this way reveals the top card of their library, then puts it onto the battlefield if it's a permanent card.",
    }
    hans = {
        "name": "Hans Eriksson",
        "type_line": "Legendary Creature — Human Scout",
        "mana_cost": "{2}{R}{G}",
        "power": "1",
        "toughness": "4",
        "keywords": ["Fight"],
        "oracle_text": "Whenever Hans Eriksson attacks, reveal the top card of your library. If it's a creature card, put it onto the battlefield tapped and attacking defending player or a planeswalker they control. Otherwise, put that card into your hand. When you put a creature card onto the battlefield this way, it fights Hans Eriksson.",
    }
    reanimate = {
        "name": "Reanimate",
        "type_line": "Sorcery",
        "mana_cost": "{B}",
        "keywords": [],
        "oracle_text": "Put target creature card from a graveyard onto the battlefield under your control. You lose life equal to that card's mana value.",
    }
    assert any(k == "cheat_from_top" for k, _, _ in _ksub(vaevictis))
    assert any(k == "cheat_from_top" for k, _, _ in _ksub(hans))
    assert not any(k == "cheat_from_top" for k, _, _ in _ksub(reanimate))


def test_repeatable_creature_kill_opens_kill_engine():
    # A commander that destroys creatures EVERY turn (Diaochan's {T}, Visara's {T})
    # is a reliable death-engine: each kill triggers death payoffs (Blood Artist,
    # Vicious Shadows). Requires a REPEATABLE frame (activated/triggered): a one-shot
    # removal spell (Murder) is not an engine and stays out.
    diaochan = {
        "name": "Diaochan, Artful Beauty",
        "type_line": "Legendary Creature — Human Advisor",
        "mana_cost": "{2}{B}",
        "power": "1",
        "toughness": "1",
        "keywords": [],
        "oracle_text": "{T}: Destroy target creature of your choice, then destroy target creature of an opponent's choice. Activate only during your turn, before attackers are declared.",
    }
    visara = {
        "name": "Visara the Dreadful",
        "type_line": "Legendary Creature — Gorgon",
        "mana_cost": "{3}{B}{B}{B}",
        "power": "5",
        "toughness": "5",
        "keywords": ["Flying"],
        "oracle_text": "Flying\n{T}: Destroy target creature. It can't be regenerated.",
    }
    murder = {
        "name": "Murder",
        "type_line": "Instant",
        "mana_cost": "{1}{B}{B}",
        "keywords": [],
        "oracle_text": "Destroy target creature.",
    }
    assert any(k == "kill_engine" for k, _, _ in _ksub(diaochan))
    assert any(k == "kill_engine" for k, _, _ in _ksub(visara))
    assert not any(k == "kill_engine" for k, _, _ in _ksub(murder))


def test_one_punch_efficient_beater_opens_lane():
    # An extreme power-for-cost beater (Lord 10/4, Yargle 18/6) wins by connecting once
    # for lethal, so it wants damage amplification (grant infect / double strike). Gated
    # power >= 8 AND power >= 2*cmc: an EXPENSIVE fatty (Emrakul 15/15 for 15) wins by
    # being huge rather than by amplification, and a small creature never qualifies.
    lord = {
        "name": "Lord of Tresserhorn",
        "type_line": "Legendary Creature — Zombie",
        "mana_cost": "{2}{B}{B}",
        "power": "10",
        "toughness": "4",
        "cmc": 4.0,
        "keywords": [],
        "oracle_text": "When Lord of Tresserhorn enters, you lose 2 life, you sacrifice two creatures, and target opponent draws two cards.\n{B}: Regenerate Lord of Tresserhorn.",
    }
    yargle = {
        "name": "Yargle and Multani",
        "type_line": "Legendary Creature — Frog Spirit Elemental",
        "mana_cost": "{3}{B}{B}{G}",
        "power": "18",
        "toughness": "6",
        "cmc": 6.0,
        "keywords": [],
        "oracle_text": "",
    }
    emrakul = {
        "name": "Emrakul, the Aeons Torn",
        "type_line": "Legendary Creature — Eldrazi",
        "mana_cost": "{15}",
        "power": "15",
        "toughness": "15",
        "cmc": 15.0,
        "keywords": ["Flying", "Annihilator", "Protection"],
        "oracle_text": "This spell can't be countered.\nWhen you cast this spell, take an extra turn after this one.\nFlying, protection from spells that are one or more colors, annihilator 6\nWhen Emrakul is put into a graveyard from anywhere, its owner shuffles their graveyard into their library.",
    }
    llanowar = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "cmc": 1.0,
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    }
    assert any(k == "one_punch" for k, _, _ in _ksub(lord))
    assert any(k == "one_punch" for k, _, _ in _ksub(yargle))
    assert not any(k == "one_punch" for k, _, _ in _ksub(emrakul))  # expensive fatty
    assert not any(k == "one_punch" for k, _, _ in _ksub(llanowar))  # low power


def test_nonhuman_attack_engine_opens_evasive_attackers():
    # Winota triggers when a non-Human creature attacks, so she wants evasive (flying)
    # attackers that reliably connect to fire her engine — fliers are a useful narrowing
    # (~a quarter of the pool), unlike "all non-Humans" (96%). A creature with no such
    # attack trigger never opens it.
    winota = {
        "name": "Winota, Joiner of Forces",
        "type_line": "Legendary Creature — Human Warrior",
        "mana_cost": "{2}{R}{W}",
        "power": "4",
        "toughness": "4",
        "cmc": 4.0,
        "keywords": [],
        "oracle_text": "Whenever a non-Human creature you control attacks, look at the top six cards of your library. You may put a Human creature card from among them onto the battlefield tapped and attacking. It gains indestructible until end of turn. Put the rest of the cards on the bottom of your library in a random order.",
    }
    elf = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "cmc": 1.0,
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    }
    # ADR-0027: nonhuman_attackers is IR-served from the structural attacks-trigger
    # shape (NotSubtype:Human subject, you-controller), so it comes through the
    # hybrid path with the matching IR, not pure regex.
    winota_ir = Card(
        oracle_id="x",
        name="Winota",
        faces=(
            Face(
                name="Winota",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(
                            event="attacks",
                            subject=Filter(
                                card_types=("Creature",),
                                controller="you",
                                predicates=("NotSubtype:Human",),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    elf_ir = Card(oracle_id="y", name="Elf", faces=(Face(name="Elf", abilities=()),))
    assert any(k == "nonhuman_attackers" for k, _, _ in _ksub_hybrid(winota, winota_ir))
    assert not any(k == "nonhuman_attackers" for k, _, _ in _ksub(winota))
    assert not any(k == "nonhuman_attackers" for k, _, _ in _ksub_hybrid(elf, elf_ir))


def test_reclaim_owned_commander_opens_control_exchange():
    # Meneldor / The Neutrinos exile a creature YOU OWN and return it under your control,
    # so you can donate a dud via control-EXCHANGE (Puca's Mischief), keep their bomb,
    # then reclaim your own dud. A standard blink that exiles a creature you CONTROL
    # (Restoration Angel) can't reclaim a donated creature, so it stays out.
    meneldor = {
        "name": "Meneldor, Swift Savior",
        "type_line": "Legendary Creature — Bird Soldier",
        "mana_cost": "{3}{U}",
        "power": "3",
        "toughness": "3",
        "keywords": ["Flying"],
        "oracle_text": "Flying\nWhenever Meneldor deals combat damage to a player, exile up to one target creature you own, then return it to the battlefield under your control.",
    }
    neutrinos = {
        "name": "The Neutrinos",
        "type_line": "Legendary Creature — Elf Rebel",
        "mana_cost": "{2}{R}{W}",
        "power": "2",
        "toughness": "4",
        "keywords": ["Flying"],
        "oracle_text": "Flying\nAlliance — Whenever another creature you control enters, The Neutrinos get +1/+0 until end of turn.\nWhenever The Neutrinos attack, exile up to one target creature you own, then return it to the battlefield under your control tapped and attacking.",
    }
    resto = {
        "name": "Restoration Angel",
        "type_line": "Creature — Angel",
        "mana_cost": "{3}{W}",
        "power": "3",
        "toughness": "4",
        "keywords": ["Flying", "Flash"],
        "oracle_text": "Flash\nFlying\nWhen this creature enters, you may exile target non-Angel creature you control, then return that card to the battlefield under your control.",
    }

    # ADR-0027 (t2b2-A): control_exchange migrated to the Card IR, so it no longer
    # fires from the regex path — assert via the hybrid (IR) path. The IR mirror is an
    # `exile` Effect whose subject carries the `Owned` predicate ("you OWN") PAIRED with
    # a to:battlefield return; Restoration Angel exiles a creature you CONTROL (no Owned
    # predicate), so it stays out.
    def _exchange_ir() -> Card:
        return Card(
            oracle_id="x",
            name="X",
            faces=(
                Face(
                    name="X",
                    abilities=(
                        Ability(
                            kind="triggered",
                            trigger=Trigger(event="attacks", scope="you"),
                            effects=(
                                Effect(
                                    category="exile",
                                    scope="any",
                                    zones=("to:exile",),
                                    subject=Filter(
                                        card_types=("Creature",),
                                        controller="any",
                                        predicates=("Owned",),
                                    ),
                                    raw="exile up to one target creature you own",
                                ),
                                Effect(
                                    category="exile",
                                    scope="any",
                                    zones=("to:battlefield",),
                                    subject=None,
                                    raw="return it to the battlefield",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )

    def _blink_control_ir() -> Card:
        return Card(
            oracle_id="x",
            name="X",
            faces=(
                Face(
                    name="X",
                    abilities=(
                        Ability(
                            kind="triggered",
                            trigger=Trigger(event="etb", scope="you"),
                            effects=(
                                Effect(
                                    category="exile",
                                    scope="any",
                                    zones=("to:exile",),
                                    subject=Filter(
                                        card_types=("Creature",),
                                        controller="you",
                                    ),
                                    raw="exile target creature you control",
                                ),
                                Effect(
                                    category="exile",
                                    scope="any",
                                    zones=("to:battlefield",),
                                    subject=None,
                                    raw="return that card to the battlefield",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )

    assert any(
        k == "control_exchange" for k, _, _ in _ksub_hybrid(meneldor, _exchange_ir())
    )
    assert any(
        k == "control_exchange" for k, _, _ in _ksub_hybrid(neutrinos, _exchange_ir())
    )
    assert not any(
        k == "control_exchange" for k, _, _ in _ksub_hybrid(resto, _blink_control_ir())
    )


def test_kira_targeting_shield_opens_protected_theft():
    # Kira grants your creatures "counter the FIRST spell/ability targeting them each
    # turn" — so a contingent steal (Sower: lost if the thief dies) can't be undone, and
    # a theft engine (Empress Galina) survives. That's the sticky-theft lock. WARD
    # ("counter it unless that player pays") is a different, single-creature shield and
    # must NOT open it (Spider-Rex).
    kira = {
        "name": "Kira, Great Glass-Spinner",
        "type_line": "Legendary Creature — Spirit",
        "mana_cost": "{1}{U}{U}",
        "power": "2",
        "toughness": "2",
        "keywords": ["Flying"],
        "oracle_text": 'Flying\nCreatures you control have "Whenever this creature becomes the target of a spell or ability for the first time each turn, counter that spell or ability."',
    }
    spider_rex = {
        "name": "Spider-Rex, Daring Dino",
        "type_line": "Legendary Creature — Spider Dinosaur Hero",
        "mana_cost": "{4}{G}{G}",
        "power": "6",
        "toughness": "6",
        "keywords": ["Reach", "Trample", "Ward"],
        "oracle_text": "Reach, trample\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
    }
    # ADR-0027 t2b5-C: theft_protection migrated to the Card IR (the kept word mirror),
    # so the regex path no longer emits it — assert via the hybrid (IR) path.
    assert any(k == "theft_protection" for k, _, _ in _ksub_hybrid(kira, _bare_ir()))
    assert not any(
        k == "theft_protection" for k, _, _ in _ksub_hybrid(spider_rex, _bare_ir())
    )


def test_big_mana_generator_opens_x_spell_sink():
    # A commander that GENERATES big mana (Neheb: "add {R} for each life lost"; Sunastian:
    # "{T}: Add {C}{C}") wants X-spell mana sinks to dump it into. (Dan's clarification:
    # big-mana-GENERATING cards -> X-spells, not "high-cmc cards -> X".) A single-mana dork
    # (Llanowar Elves) is not a big-mana generator and stays out.
    neheb = {
        "name": "Neheb, the Eternal",
        "type_line": "Legendary Creature — Zombie Minotaur Warrior",
        "mana_cost": "{3}{R}{R}",
        "power": "4",
        "toughness": "6",
        "keywords": ["Afflict"],
        "oracle_text": "Afflict 3 (Whenever this creature becomes blocked, defending player loses 3 life.)\nAt the beginning of each of your postcombat main phases, add {R} for each 1 life your opponents have lost this turn.",
    }
    sunastian = {
        "name": "Sunastian Falconer",
        "type_line": "Legendary Creature — Human Shaman",
        "mana_cost": "{3}{R}{G}",
        "power": "4",
        "toughness": "4",
        "keywords": [],
        "oracle_text": "{T}: Add {C}{C}.",
    }
    elf = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    }
    assert any(k == "big_mana" for k, _, _ in _ksub(neheb))
    assert any(k == "big_mana" for k, _, _ in _ksub(sunastian))
    assert not any(k == "big_mana" for k, _, _ in _ksub(elf))  # single mana, not big


def test_opp_top_exile_opens_for_library_predators():
    # Circu (and Ragavan, Grenzo) exile/take the top card of a TARGET player's library,
    # so seeing opponents' tops (Field of Dreams) lets them exile/steal the BEST card and
    # target the right player. A commander with no opponent-library-top interaction
    # (Llanowar Elves) never opens it. ADR-0027 q2-D2: opp_top_exile is now IR-served —
    # Circu's exile scope phase reads as 'any' (no structural arm), so it fires from the
    # _IR_KEPT_DETECTORS word mirror (oracle scan → a bare IR routes to the IR path).
    circu = {
        "name": "Circu, Dimir Lobotomist",
        "type_line": "Legendary Creature — Human Wizard",
        "mana_cost": "{2}{U}{B}",
        "power": "2",
        "toughness": "3",
        "keywords": [],
        "oracle_text": "Whenever you cast a blue spell, exile the top card of target player's library.\nWhenever you cast a black spell, exile the top card of target player's library.\nYour opponents can't cast spells with the same name as a card exiled with Circu.",
    }
    elf = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    }
    assert any(k == "opp_top_exile" for k, _, _ in _ksub_hybrid(circu, _bare_ir()))
    assert not any(k == "opp_top_exile" for k, _, _ in _ksub_hybrid(elf, _bare_ir()))


def test_fblthp_free_plot_opens_for_zero_cost():
    # Fblthp makes the top card's plot cost EQUAL its mana cost, so 0-cost cards are FREE
    # to plot — the artifact-combo / storm engine (Hullbreaker + two 0-cost permanents =
    # infinite; Sai / Displacer chains). So he wants 0-cost cards. A commander without the
    # free-plot ability never opens it.
    fblthp = {
        "name": "Fblthp, Lost on the Range",
        "type_line": "Legendary Creature — Homunculus",
        "mana_cost": "{1}{U}{U}",
        "power": "1",
        "toughness": "1",
        "keywords": ["Plot", "Ward"],
        "oracle_text": "Ward {2}\nYou may look at the top card of your library any time.\nThe top card of your library has plot. The plot cost is equal to its mana cost.\nYou may plot nonland cards from the top of your library.",
    }
    elf = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "keywords": [],
        "oracle_text": "{T}: Add {G}.",
    }
    # ADR-0027 t2b5-A: free_plot migrated to the Card IR (a kept word mirror), so it now
    # fires from the hybrid path, not the deleted _HAND_FLOOR producer.
    assert any(k == "free_plot" for k, _, _ in _ksub_hybrid(fblthp, _bare_ir()))
    assert not any(k == "free_plot" for k, _, _ in _ksub_hybrid(elf, _bare_ir()))


# --- structural-anchored floor detectors (whole archetypes the baseline missed) -


def test_treasure_matters():
    # ADR-0027: treasure_matters migrated to the Card IR — a Treasure-subtype make_token
    # opens the lane via _TOKEN_SUBTYPE_KEYS through the hybrid, not the deleted regex.
    c = {
        "name": "Goldspan-like",
        "oracle_text": "Whenever this creature attacks, create a Treasure token.",
    }
    ir = Card(
        oracle_id="x",
        name="Goldspan-like",
        faces=(
            Face(
                name="Goldspan-like",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="attacks"),
                        effects=(
                            Effect(
                                category="make_token",
                                scope="you",
                                subject=Filter(
                                    card_types=("Artifact",), subtypes=("Treasure",)
                                ),
                                raw="create a Treasure token",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("treasure_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(c, ir)
    }
    assert ("treasure_matters", "you") not in _ks(c)


def test_artifacts_matter():
    # ADR-0027: artifacts_matter migrated to the Card IR — "Artifacts you control have
    # ward" rides the kept oracle mirror on the hybrid path.
    c = {"name": "Artificer", "oracle_text": "Artifacts you control have ward {2}."}
    assert ("artifacts_matter", "you") in _ks_hybrid(c)


def test_bargain_symmetric_sac_does_not_open_type_lanes():
    # ADR-0027 (CR 702.166a): Bargain ("sacrifice an artifact, ENCHANTMENT, or token")
    # projects a sacrifice Effect whose subject carries the catch-all 'Permanent' type
    # (the 'token' option) alongside Artifact/Enchantment. That is a GENERIC alt-cost,
    # NOT an artifacts/enchantments build-around (Torch the Tower / Beseech the Mirror
    # are burn / a generic tutor). The symmetric-list gate must keep BOTH type lanes
    # shut. Regression: the sidecar projection structures this sac, so it over-fired
    # both lanes in production until the gate landed.
    bargain = {"name": "Torch the Tower", "oracle_text": "Bargain ..."}
    bargain_ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="sacrifice",
                    scope="you",
                    subject=Filter(
                        card_types=("Artifact", "Enchantment", "Permanent"),
                        controller="any",
                    ),
                ),
            ),
        )
    )
    keys = _keys_hybrid_ir(bargain, bargain_ir)
    assert "artifacts_matter" not in keys
    assert "enchantments_matter" not in keys
    # Positive control: a SINGLE-type artifact sac outlet (Atog-style) DOES open the
    # lane — the gate is narrow to the Permanent-containing symmetric list.
    atog = {"name": "Atog", "oracle_text": "Sacrifice an artifact: ..."}
    atog_ir = _ir_with(
        Ability(
            kind="activated",
            effects=(
                Effect(
                    category="sacrifice",
                    scope="you",
                    subject=Filter(card_types=("Artifact",), controller="you"),
                ),
            ),
        )
    )
    assert "artifacts_matter" in _keys_hybrid_ir(atog, atog_ir)


def test_tokens_matter_payoff():
    # ADR-0027: tokens_matter migrated to the Card IR via a byte-identical kept-mirror,
    # so assert against the hybrid path (the mirror reads the oracle).
    c = {"name": "Token Payoff", "oracle_text": "Tokens you control have haste."}
    assert ("tokens_matter", "you") in _ks_hybrid(c)


def test_stax_taxes_scoped_to_opponents():
    c = {
        "name": "Grand Arbiter Augustin IV",
        "oracle_text": "White spells you cast cost {1} less to cast.\nBlue spells you cast cost {1} less to cast.\nSpells your opponents cast cost {1} more to cast.",
    }
    assert ("stax_taxes", "opponents") in _ks(c)


def test_stax_self_restriction_does_not_fire():
    # "This creature can't attack unless..." is a self-restriction, NOT stax.
    c = {
        "name": "Kefnet-like",
        "oracle_text": "This creature can't attack or block unless you control an Island.",
    }
    assert "stax_taxes" not in _keys(c)


# --- theme_presets reuse -------------------------------------------------------


def test_blink_flicker_via_preset_regex():
    c = {
        "name": "Brago-like",
        "oracle_text": "Exile target creature you control, then return it to the battlefield under your control.",
    }
    assert ("blink_flicker", "you") in _ks(c)


def test_blink_flicker_exile_other_target_then_return():
    # "exile up to one OTHER target [permanent] ... return it/that card to the
    # battlefield" is a blink engine (CR — leaves then re-enters); the cross-sentence
    # detector's optional group only had "another/one", so "one other" slipped past
    # and these read as plain exile_removal. Real cards, full oracle text.
    ennis = {
        "name": "Ennis, Debate Moderator",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": (
            "When Ennis enters, exile up to one other target creature you control. "
            "Return that card to the battlefield under its owner's control at the "
            "beginning of the next end step.\n"
            "At the beginning of your end step, if one or more cards were put into "
            "exile this turn, put a +1/+1 counter on Ennis."
        ),
    }
    koya = {
        "name": "Koya, Death from Above",
        "type_line": "Legendary Creature — Mutant Ninja Bird",
        "oracle_text": (
            "Flying\n"
            "When Koya enters, exile up to one other target creature. At the "
            "beginning of the next end step, you may pay {3}{B}. If you don't, "
            "return that card to the battlefield under its owner's control."
        ),
    }
    phelia = {
        "name": "Phelia, Exuberant Shepherd",
        "type_line": "Legendary Creature — Dog",
        "oracle_text": (
            "Flash\n"
            "Whenever Phelia attacks, exile up to one other target nonland "
            "permanent. At the beginning of the next end step, return that card to "
            "the battlefield under its owner's control. If it entered under your "
            "control, put a +1/+1 counter on Phelia."
        ),
    }
    assert "blink_flicker" in _keys(ennis)
    assert "blink_flicker" in _keys(koya)
    assert "blink_flicker" in _keys(phelia)


def test_self_etb_variable_damage_opens_flicker_and_clone():
    # A commander whose own ETB deals VARIABLE damage ("deals damage equal to its
    # power", "deals X damage") is a Flametongue-Kavu-style value ETB: flicker re-fires
    # it, and (CMC >= 5) a clone re-fires it on a cheap body. The self-ETB payoff list
    # matched numeric "deals N damage" but not the variable forms, so Dong Zhou opened
    # no ETB-reuse avenue and missed Panharmonicon/Splinter Twin/Strionic Resonator.
    # Membership-gated (commander-only); real oracle.
    dong_zhou = {
        "name": "Dong Zhou, the Tyrant",
        "type_line": "Legendary Creature — Human Soldier",
        "cmc": 5.0,
        "oracle_text": (
            "When Dong Zhou enters, target creature an opponent controls deals "
            "damage equal to its power to that player."
        ),
    }
    keys = {s.key for s in extract_signals(dong_zhou, include_membership=True)}
    assert "blink_flicker" in keys
    assert "clone_matters" in keys  # cmc 5 >= 5 -> worth copying
    # Over-fire guard: an exile-removal ETB (Banisher Priest) is NOT a flicker payoff —
    # damage/value verbs qualify, "exile target" does not (O-Ring rule). Real oracle.
    banisher = {
        "name": "Banisher Priest",
        "type_line": "Creature — Human Cleric",
        "cmc": 3.0,
        "oracle_text": (
            "When this creature enters, exile target creature an opponent controls "
            "until this creature leaves the battlefield."
        ),
    }
    assert "blink_flicker" not in {
        s.key for s in extract_signals(banisher, include_membership=True)
    }


def test_self_etb_modal_choose_requires_enters_not_dies():
    # The self-ETB payoff list includes the modal marker "choose one/two/three" — but it
    # MUST stay anchored to "when ~ enters". A DEATH-modal trigger ("When ~ dies, choose
    # one —") is re-used by sacrifice/reanimation, NOT by blink, so it must not open the
    # Blink avenue. Regression guard: the modal alternative was ungrouped, so it floated
    # to the top of the pattern and matched ANY "choose one" (Atsushi's death modal).
    # Real oracle.
    atsushi = {
        "name": "Atsushi, the Blazing Sky",
        "type_line": "Legendary Creature — Dragon Spirit",
        "oracle_text": (
            "Flying, trample\nWhen Atsushi dies, choose one —\n• Exile the top two "
            "cards of your library. Until the end of your next turn, you may play "
            "those cards.\n• Create three Treasure tokens."
        ),
    }
    assert "blink_flicker" not in _keys(atsushi)
    # A genuine ETB modal ("When ~ enters, choose one —") still opens Blink: flicker
    # re-fires the enter trigger (CR 603.6). Real oracle.
    charming_prince = {
        "name": "Charming Prince",
        "type_line": "Creature — Human Noble",
        "oracle_text": (
            "When this creature enters, choose one —\n• Scry 2.\n• You gain 3 life.\n"
            "• Exile another target creature you own. Return it to the battlefield "
            "under your control at the beginning of the next end step."
        ),
    }
    assert "blink_flicker" in _keys(charming_prince)


def test_xspell_matters_detects_x_cost_payoffs_not_hoser():
    # A commander that rewards/enables casting spells whose PRINTED mana cost contains
    # {X} (CR 107.3 / 202.1) opens xspell_matters — it wants the universe of X-spells +
    # X-doublers. ADR-0027 t2b4a-B: IR-served — the HasXInManaCost predicate on a
    # cast_spell trigger subject (Zaxara) + a kept effect-raw hook mirror minus the
    # "can't be cast" veto (Rosheen's mana-enabler) so an X-spell HOSER never reads as
    # wanting them. Real oracle; the regex path no longer fires it.
    zaxara = {
        "name": "Zaxara, the Exemplary",
        "type_line": "Legendary Creature — Nightmare Hydra",
        "oracle_text": (
            "Deathtouch\n{T}: Add two mana of any one color.\nWhenever you cast a "
            "spell with {X} in its mana cost, create a 0/0 green Hydra creature "
            "token, then put X +1/+1 counters on it."
        ),
    }
    zaxara_ir = _ir_with(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                scope="you",
                subject=Filter(predicates=("HasXInManaCost",)),
            ),
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    raw="create a 0/0 green Hydra creature token",
                ),
            ),
        )
    )
    assert "xspell_matters" in _keys_hybrid_ir(zaxara, zaxara_ir)
    assert "xspell_matters" not in _keys(zaxara)
    rosheen = {
        "name": "Rosheen Meanderer",
        "type_line": "Legendary Creature — Giant Shaman",
        "oracle_text": (
            "{T}: Add {C}{C}{C}{C}. Spend this mana only on costs that contain {X}."
        ),
    }
    # phase drops the {X}-in-cost predicate here (folds to a bare ramp effect); the
    # kept effect-raw hook mirror recovers it.
    rosheen_ir = _ir_with(
        Ability(
            kind="activated",
            cost="{T}",
            effects=(
                Effect(
                    category="ramp",
                    scope="you",
                    raw="Add {C}{C}{C}{C}. Spend this mana only on costs that "
                    "contain {X}.",
                ),
            ),
        )
    )
    assert "xspell_matters" in _keys_hybrid_ir(rosheen, rosheen_ir)
    # Hoser: Gaddock Teeg BANS X-spells ("can't be cast") — it does NOT want them. The
    # ban is a restriction effect (no payoff trigger predicate), and the kept hook
    # mirror's veto keeps the avenue closed even on the effect raw.
    gaddock = {
        "name": "Gaddock Teeg",
        "type_line": "Legendary Creature — Kithkin Advisor",
        "oracle_text": (
            "Noncreature spells with mana value 4 or greater can't be cast.\n"
            "Noncreature spells with {X} in their mana costs can't be cast."
        ),
    }
    gaddock_ir = _ir_with(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="restriction",
                    scope="any",
                    subject=Filter(predicates=("Cmc:4", "NotType:Creature")),
                    raw="Noncreature spells with {X} in their mana costs can't be "
                    "cast.",
                ),
            ),
        )
    )
    assert "xspell_matters" not in _keys_hybrid_ir(gaddock, gaddock_ir)
    assert "xspell_matters" not in _keys(gaddock)


def test_self_heroic_commander_opens_voltron():
    # A commander with a SELF-targeting heroic trigger ("whenever you cast a spell that
    # targets [itself]", CR 702.86) is a suit-up-one-creature voltron deck: casting an
    # Aura/pump spell on it both fires heroic AND buffs it, so it wants the equipment /
    # pump-aura / protection package voltron_matters serves. Opens even with another
    # engine present (Brigone also has a counter sub-theme). Real oracle.
    brigone = {
        "name": "Brigone, Soldier of Meletis",
        "type_line": "Legendary Creature — Human Soldier",
        "power": "2",
        "toughness": "2",
        "oracle_text": (
            "Vigilance\nHeroic — Whenever you cast a spell that targets Brigone, put "
            "a +1/+1 counter on Brigone.\n{T}, Remove a +1/+1 counter from Brigone: "
            "Draw a card."
        ),
    }
    assert "voltron_matters" in _keys(brigone)
    # The "targets only <name>" form (Feather).
    feather = {
        "name": "Feather, Radiant Arbiter",
        "type_line": "Legendary Creature — Angel",
        "power": "4",
        "toughness": "3",
        "oracle_text": (
            "Flying, lifelink\nWhenever you cast a noncreature spell that targets only "
            "Feather, you may choose any number of other creatures that spell could "
            "target and pay {2} for each of those creatures. If you do, for each of "
            "those creatures, copy that spell. The copy targets that creature. (Copies "
            "of permanent spells become tokens.)"
        ),
    }
    assert "voltron_matters" in _keys(feather)
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
    sima_yi = {
        "name": "Sima Yi, Wei Field Marshal",
        "type_line": "Legendary Creature — Human Soldier",
        "power": "*",
        "toughness": "3",
        "oracle_text": "Sima Yi's power is equal to the number of Swamps you control.",
    }
    assert "voltron_matters" in _keys(sima_yi)
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
    akuta = {
        "name": "Akuta, Born of Ash",
        "type_line": "Legendary Creature — Spirit",
        "power": "3",
        "toughness": "2",
        "oracle_text": (
            "Haste\nAt the beginning of your upkeep, if you have more cards in hand "
            "than each opponent, you may sacrifice a Swamp. If you do, return Akuta "
            "from your graveyard to the battlefield."
        ),
    }
    assert "voltron_matters" in _keys(akuta)
    # Self-scoped: a reanimation spell returning ANOTHER creature is not the resilience
    # tell — the helper must not match it.
    assert (
        _voltron_self_recurs(
            "Return target creature card from your graveyard to the battlefield.",
            "Reanimator",
        )
        is False
    )


def test_creatures_are_lands_opens_untap_engine():
    # Ashaya's nontoken creatures ARE Forest lands, so untap-lands effects (Quirion
    # Ranger, Argothian Elder, Ley Weaver) untap its creature-lands for mana and re-use.
    # Opens untap_engine. Real oracle. ADR-0027 β: untap_engine migrated to the Card IR,
    # so the creatures-are-lands marker now fires from the IR kept mirror (the hybrid
    # path with any non-None IR — the mirror scans the card's oracle text), not the
    # deleted regex producer.
    ashaya = {
        "name": "Ashaya, Soul of the Wild",
        "type_line": "Legendary Creature — Elemental",
        "oracle_text": (
            "Ashaya's power and toughness are each equal to the number of lands you "
            "control.\nNontoken creatures you control are Forest lands in addition to "
            "their other types. (They're still affected by summoning sickness.)"
        ),
    }
    assert "untap_engine" not in _keys(ashaya)
    assert "untap_engine" in _keys_hybrid(ashaya)


def test_rampage_keyword_opens_blocked_matters():
    # Rampage's "whenever this creature becomes blocked" trigger lives in stripped
    # reminder text, so blocked_matters (which keys on "becomes blocked") missed it. A
    # Rampage commander (Marhault) wants the blocked-matters payoffs (Varchild's
    # War-Riders, Craw Giant, Retaliation). Map the keyword. Real oracle.
    marhault = {
        "name": "Marhault Elsdragon",
        "type_line": "Legendary Creature — Elf Warrior",
        "keywords": ["Rampage"],
        "oracle_text": (
            "Rampage 1 (Whenever this creature becomes blocked, it gets +1/+1 until "
            "end of turn for each creature blocking it beyond the first.)"
        ),
    }
    assert "blocked_matters" in _keys(marhault)


def test_permanents_with_counters_opens_counters():
    # Xolatoyac untaps "each permanent you control with a counter on it" — a counters-
    # matters commander (it wants counters on its permanents to untap them), but the
    # +1/+1-specific detector missed it (flood counters; "with a counter on it"). So it
    # missed counter producers (Forgotten Ancient, Master Biomancer, Vorel). Real oracle.
    xolatoyac = {
        "name": "Xolatoyac, the Smiling Flood",
        "type_line": "Legendary Creature — Salamander Turtle",
        "oracle_text": (
            "Whenever Xolatoyac enters or attacks, put a flood counter on target land. "
            "That land is an Island in addition to its other types for as long as it "
            "has a flood counter on it.\nAt the beginning of your end step, untap each "
            "permanent you control with a counter on it."
        ),
    }
    # ADR-0027: counters_matter migrated to the IR — the "you control with a counter
    # on it" payoff recovers a counters_have_ref marker (project._narrow_counter_refs
    # / _counter_face_marker). Assert via the hybrid (production) path.
    ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="counters_have_ref",
                                scope="you",
                                raw="untap each permanent you control with a counter on it",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "counters_matter" in _keys_hybrid_ir(xolatoyac, ir)


def test_planeswalker_type_opens_superfriends():
    # Leori cares about planeswalkers as a GROUP ("choose a planeswalker type ... activate
    # an ability of a planeswalker of that type, copy it") — a superfriends commander, but
    # the detector keyed only on "planeswalkers you control" / "loyalty counter" / "activate
    # a loyalty", missing the "planeswalker type" / "ability of a planeswalker" phrasing,
    # so it missed The Chain Veil / Ichormoon Gauntlet / Onakke Oathkeeper. Real oracle.
    leori = {
        "name": "Leori, Sparktouched Hunter",
        "type_line": "Legendary Creature — Elemental Cat",
        "oracle_text": (
            "Flying, vigilance\nWhenever Leori deals combat damage to a player, choose "
            "a planeswalker type. Until end of turn, whenever you activate an ability "
            "of a planeswalker of that type, copy that ability. You may choose new "
            "targets for the copies."
        ),
    }
    assert "superfriends_matters" in _keys(leori)
    # Over-fire guard: activating a CREATURE's ability is not a superfriends tell.
    assert "superfriends_matters" not in _keys(
        {
            "name": "X",
            "oracle_text": "Whenever you activate an ability of a creature, draw a card.",
        }
    )


def test_three_zone_opponent_search_opens_theft():
    # Kotose rifles all THREE of an opponent's zones ("Search that player's graveyard,
    # hand, and library ... and exile them ... you may play one of the exiled cards") —
    # unambiguous steal-and-cast theft, but the detector keyed only on top-of-library
    # forms, so Kotose missed the theft payoffs (Gonti, Praetor's Grasp). Real oracle.
    kotose = {
        "name": "Kotose, the Silent Spider",
        "type_line": "Legendary Creature — Human Ninja",
        "oracle_text": (
            "When Kotose enters, exile target card other than a basic land card from "
            "an opponent's graveyard. Search that player's graveyard, hand, and "
            "library for any number of cards with the same name as that card and "
            "exile them. Then that player shuffles. For as long as you control "
            "Kotose, you may play one of the exiled cards, and you may spend mana as "
            "though it were mana of any color to cast it."
        ),
    }
    assert "theft_matters" in _keys(kotose)
    # Over-fire guard: searching YOUR OWN library is not theft.
    assert "theft_matters" not in _keys(
        {"name": "X", "oracle_text": "Search your library for a card."}
    )


def test_self_double_strike_beater_opens_voltron():
    # A commander that ITSELF has double strike and a real body (power >= 4) is a single
    # beater that doubles every equipment/aura bonus -> voltron. Sabin's only signal is a
    # spurious graveyard_matters (from its blitz discard cost), which suppressed the
    # voltron fallback; the override surfaces its equipment package. Real oracle.
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
    assert "voltron_matters" in _keys(sabin)
    # Gate (helper-level, no other voltron path interfering): a double-strike TOKEN
    # go-wide engine (Oketra: makes Warriors, power 3) is excluded by BOTH the power>=4
    # and no-token gates — the documented over-fire class stays out.
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
    # re-firing — a clone re-fires it when the copy dies (CMC >= 5), and it's a
    # self_death_payoff. Both death regexes matched numeric "deals N damage" but not
    # the variable form, so Orca opened neither. Real oracle.
    orca = {
        "name": "Orca, Siege Demon",
        "type_line": "Legendary Creature — Demon",
        "cmc": 7.0,
        "oracle_text": (
            "Trample\n"
            "Whenever another creature dies, put a +1/+1 counter on Orca.\n"
            "When Orca dies, it deals damage equal to its power divided as you choose "
            "among any number of targets."
        ),
    }
    # ADR-0027: self_death_payoff migrated to the Card IR; the "deals damage equal to"
    # self-death VALUE branch rides the name-aware kept mirror on the hybrid path.
    keys = {
        s.key for s in extract_signals_hybrid(orca, _bare_ir(), include_membership=True)
    }
    assert "self_death_payoff" in keys
    assert "clone_matters" in keys  # cmc 7 >= 5
    # Over-fire guard: a "deals damage equal to" clause NOT on a death trigger (a combat
    # trigger) must not open the death payoff. Real oracle (Inferno Titan-style is
    # numeric, so use a variable-combat case).
    combat = {
        "name": "Variable Combat Burner",
        "type_line": "Legendary Creature — Beast",
        "cmc": 6.0,
        "oracle_text": (
            "Whenever this creature attacks, it deals damage equal to its power to "
            "any target."
        ),
    }
    assert "self_death_payoff" not in {
        s.key
        for s in extract_signals_hybrid(combat, _bare_ir(), include_membership=True)
    }


def test_goad_via_keyword_array_scoped_opponents():
    c = {
        "name": "Marisi-like",
        "oracle_text": "Goad target creature.",
        "keywords": ["Goad"],
    }
    assert ("goad_matters", "opponents") in _ks(c)


def test_proliferate_via_keyword_array():
    # ADR-0027: proliferate_matters migrated to the Card IR; the proliferate
    # keyword now opens the lane via _IR_KEYWORD_MAP (the IR-only keyword path,
    # reading the record's Scryfall keyword array), so this asserts the hybrid.
    c = {
        "name": "Atraxa, Praetors' Voice",
        "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)",
        "keywords": ["Proliferate"],
    }
    assert ("proliferate_matters", "you") in _ks_hybrid(c)


# --- narrow Tinybones scope fix (ADR-0009) ------------------------------------


def test_tinybones_combat_damage_zone_scoped_opponents():
    c = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell."
        ),
    }
    sigs = extract_signals(c)
    assert any(s.key == "graveyard_matters" and s.scope == "opponents" for s in sigs)
    assert not any(s.key == "graveyard_matters" and s.scope == "you" for s in sigs)


def test_self_graveyard_recursion_stays_you():
    # The narrow rule must NOT flip a self-graveyard effect to opponents.
    c = {
        "name": "Greasefang-like",
        "oracle_text": "Return target Vehicle card from your graveyard to the battlefield.",
    }
    assert not any(
        s.key == "graveyard_matters" and s.scope == "opponents"
        for s in extract_signals(c)
    )


# --- dedup + aggregate ---------------------------------------------------------


def test_subject_field_is_actually_populated():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    assert any(s.subject == "Goblin" for s in extract_signals(c))


# --- coverage gate (the agent-augmentation hook) -------------------------------


def test_coverage_gate_flags_zero_signal():
    c = {"name": "Vanilla", "oracle_text": "Flying"}
    needs, reason = coverage_gate(c, extract_signals(c))
    assert needs is True
    assert reason == "zero_signal"


def test_coverage_gate_passes_when_subject_present():
    c = {"name": "Lord", "oracle_text": "Other Goblins you control get +1/+1."}
    needs, _reason = coverage_gate(c, extract_signals(c))
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


# --- regression: baseline still fires -----------------------------------------


def test_reminder_text_does_not_produce_signals():
    # Ba Sing Se's earthbend REMINDER text (parenthetical) mentions exile+return;
    # it must not register as a blink/flicker engine (reminder text restates a
    # keyword and should never generate a signal).
    c = {
        "name": "Ba Sing Se",
        "oracle_text": (
            "This land enters tapped unless you control a basic land.\n{T}: Add {G}.\n{2}{G}, {T}: Earthbend 2. Activate only as a sorcery. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)"
        ),
    }
    assert "blink_flicker" not in _keys(c)


def test_instant_sorcery_recaster_opens_spellcast():
    # A commander that casts or copies instants/sorceries (Mavinda recasts from the yard,
    # Velomachus casts off the top, Naru Meha copies) is a spellslinger — it wants
    # prowess/magecraft payoffs (Monastery Mentor, Leonin Lightscribe). The spellcast
    # detector keyed on the "whenever you cast an instant/sorcery" PAYOFF form, missing
    # these enabler/copier forms. Real oracle.
    mavinda = {
        "name": "Mavinda, Students' Advocate",
        "type_line": "Legendary Creature — Bird Advisor",
        "oracle_text": (
            "Flying\n{0}: You may cast target instant or sorcery card from your "
            "graveyard this turn. If that spell doesn't target a creature you control, "
            "it costs {8} more to cast this way."
        ),
    }
    velomachus = {
        "name": "Velomachus Lorehold",
        "type_line": "Legendary Creature — Dragon Cleric",
        "oracle_text": (
            "Flying, vigilance, haste\nWhenever Velomachus Lorehold attacks, look at "
            "the top seven cards of your library. You may cast an instant or sorcery "
            "spell with mana value less than or equal to Velomachus Lorehold's power "
            "from among them without paying its mana cost."
        ),
    }
    naru_meha = {
        "name": "Naru Meha, Master Wizard",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Flash\nWhen Naru Meha, Master Wizard enters, copy target instant or "
            "sorcery spell you control. You may choose new targets for the copy.\n"
            "Other Wizards you control get +1/+1."
        ),
    }
    for cmd in (mavinda, velomachus, naru_meha):
        assert ("spellcast_matters", "you") in _ks(cmd), cmd["name"]
    # Over-fire guard: a vanilla creature is not a spellslinger.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("spellcast_matters", "you") not in _ks(bear)


def test_enchantment_token_maker_opens_enchantments():
    # A commander that creates enchantment/Aura tokens (Scriv "create a white Aura
    # enchantment token", The Rani, Preston Garvey) is an enchantment deck — it wants
    # enchantment payoffs (Eriette, Sphere of Safety). Real oracle.
    scriv = {
        "name": "Scriv, the Obligator",
        "type_line": "Legendary Creature — Phyrexian Praetor",
        "oracle_text": (
            "Flying, deathtouch\nWhenever Scriv enters or attacks, create a white Aura "
            "enchantment token named Contract attached to target creature an opponent "
            "controls."
        ),
    }
    # ADR-0027: enchantments_matter migrated to the Card IR — the make_token DOER fires
    # off the Enchantment-typed token subject (the Aura token), so this serves from the
    # hybrid path against the structured make_token Effect.
    scriv_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(
                        card_types=("Enchantment",),
                        subtypes=("Aura",),
                        controller="any",
                    ),
                ),
            ),
        )
    )
    assert ("enchantments_matter", "you") in _ks_hybrid_ir(scriv, scriv_ir)
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("enchantments_matter", "you") not in _ks_hybrid(bear)


def test_legendary_permanent_trigger_opens_legends():
    # A commander with a legendary-permanent trigger (Yomiji "whenever a legendary
    # permanent ... is put into a graveyard, return it", Cleopatra) is a legends-matter
    # deck — it wants legendary payoffs (Yoshimaru, Search for Glory). Real oracle.
    # ADR-0027: legends_matter migrated to the Card IR, so the textual refs phase
    # leaves unstructured fire via the kept word mirror in the hybrid path, not regex.
    yomiji = {
        "name": "Yomiji, Who Bars the Way",
        "type_line": "Legendary Creature — Spirit",
        "oracle_text": (
            "Whenever a legendary permanent other than Yomiji, Who Bars the Way is put "
            "into a graveyard from the battlefield, return that card to its owner's "
            "hand."
        ),
    }
    assert ("legends_matter", "you") in _ks_hybrid(yomiji)
    # Also the TUTOR form (Captain Sisay) and BUFF form.
    sisay = {
        "name": "Captain Sisay",
        "type_line": "Legendary Creature — Legend",
        "oracle_text": (
            "{T}: Search your library for a legendary card, reveal that card, put it "
            "into your hand, then shuffle."
        ),
    }
    assert ("legends_matter", "you") in _ks_hybrid(sisay)
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("legends_matter", "you") not in _ks_hybrid(bear)


def test_double_damage_of_counter_creatures_opens_counters():
    # "Double all damage that creatures you control WITH COUNTERS ON THEM would deal"
    # (Raphael, Tidus) is a +1/+1-counters DAMAGE payoff — the damage-doubling context
    # implies POSITIVE counters (you wouldn't double the damage of -1/-1 creatures), so
    # no literal "+1/+1" is needed. Real oracle.
    # ADR-0027: counters_matter migrated to the IR — "creatures you control with
    # counters on them" recovers a counters_have_ref marker; assert via the hybrid
    # (production) path.
    raphael = {
        "name": "Raphael, the Muscle",
        "type_line": "Legendary Creature — Mutant Turtle Warrior",
        "oracle_text": (
            "Double all damage that creatures you control with counters on them would "
            "deal.\nWhen Raphael, the Muscle enters, create a Mutagen token."
        ),
    }
    raphael_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="counters_have_ref",
                                scope="you",
                                raw="creatures you control with counters on them",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "counters_matter" in _keys_hybrid_ir(raphael, raphael_ir)


def test_two_tribe_tutor():
    # "search ... for a <X> or <Y> card": Lo and Li tutors "a Lesson or Noble card" and
    # anthems Nobles, so it's Noble-tribal (its top-synergy cards are legendary Nobles).
    lo_and_li = {
        "name": "Lo and Li, Twin Tutors",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": (
            "When Lo and Li enter, search your library for a Lesson or Noble card, "
            "reveal it, put it into your hand, then shuffle.\nNoble creatures you control "
            "and Lesson spells you control have lifelink."
        ),
    }
    assert ("type_matters", "you", "Noble") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(lo_and_li, include_membership=True)
    }


def test_two_tribe_creature_spell():
    # "(a) <X> or <Y> creature spell": Tawnos copies "a Beast or Bird creature spell", so
    # it's a Beast AND Bird commander. Scoped to "creature spell" (not bare card/spell) so
    # an opponent-cast hoser ("an opponent casts a Spirit or Arcane spell") is excluded.
    tawnos = {
        "name": "Tawnos, the Toymaker",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "Whenever you cast a Beast or Bird creature spell, you may copy it, except "
            "the copy is an artifact in addition to its other types."
        ),
    }
    trips = {
        (s.key, s.subject) for s in extract_signals(tawnos, include_membership=True)
    }
    assert ("type_matters", "Beast") in trips
    assert ("type_matters", "Bird") in trips


def test_tribe_comma_list_refs():
    # "(a) <X>, <Y>, or <Z> spell/card": Kiora casts "a Kraken, Leviathan, Octopus, or
    # Serpent spell" (sea-monster group), Dr. Eggman puts "a Construct, Robot, or Vehicle
    # card". Every listed tribe is captured.
    kiora = {
        "name": "Kiora, Sovereign of the Deep",
        "type_line": "Legendary Creature — Merfolk Noble",
        "oracle_text": (
            "Vigilance, ward {3}\nWhenever you cast a Kraken, Leviathan, Octopus, or "
            "Serpent spell from your hand, look at the top X cards of your library, where "
            "X is that spell's mana value."
        ),
    }
    trips = {
        (s.key, s.subject) for s in extract_signals(kiora, include_membership=True)
    }
    for t in ("Kraken", "Leviathan", "Serpent"):
        assert ("type_matters", t) in trips, t


def test_tribal_card_spell_list_refs():
    # Multi-tribe "(a/an) <Tribe> card/spell" lists the single-capture patterns miss:
    # Kaalia reveals "an Angel card, a Demon card, and/or a Dragon card" (all three),
    # Disa returns "a Lhurgoyf permanent card", Eivor puts "a Saga card".
    kaalia = {
        "name": "Kaalia, Zenith Seeker",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": (
            "Flying, vigilance\nWhen Kaalia enters, look at the top six cards of your "
            "library. You may reveal an Angel card, a Demon card, and/or a Dragon card "
            "from among them and put them into your hand. Put the rest on the bottom."
        ),
    }
    trips = {
        (s.key, s.subject) for s in extract_signals(kaalia, include_membership=True)
    }
    for tribe in ("Angel", "Demon", "Dragon"):
        assert ("type_matters", tribe) in trips, tribe
    disa = {
        "name": "Disa the Restless",
        "type_line": "Legendary Creature — Human Scout",
        "oracle_text": (
            "Whenever a Lhurgoyf permanent card is put into your graveyard from anywhere "
            "other than the battlefield, put it onto the battlefield."
        ),
    }
    assert ("type_matters", "Lhurgoyf") in {
        (s.key, s.subject) for s in extract_signals(disa, include_membership=True)
    }


def test_tribal_creature_spell_and_target_tribe():
    # Tribal references the standard patterns miss: "<Tribe> creature spell" (Gisa casts
    # Zombie creature spells, Rivaz casts Dragon creature spells) and "target <Tribe>
    # can't be blocked" (Splinter is Ninja-tribal).
    gisa = {
        "name": "Gisa and Geralf",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "When Gisa and Geralf enters, mill four cards.\nOnce during each of your "
            "turns, you may cast a Zombie creature spell from your graveyard."
        ),
    }
    assert ("type_matters", "you", "Zombie") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(gisa, include_membership=True)
    }
    splinter = {
        "name": "Splinter, Radical Rat",
        "type_line": "Legendary Creature — Mutant Ninja Rat",
        "oracle_text": (
            "If a triggered ability of a Ninja creature you control triggers, that "
            "ability triggers an additional time.\n{1}{U}: Target Ninja can't be blocked "
            "this turn."
        ),
    }
    assert ("type_matters", "you", "Ninja") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(splinter, include_membership=True)
    }
    # Over-fire guard: a generic "creature spell" / "target creature can't be blocked"
    # captures no tribe (vocab gate drops the card-type word).
    generic = {
        "name": "Generic",
        "type_line": "Instant",
        "oracle_text": (
            "Whenever you cast a creature spell, draw a card. Target creature can't be "
            "blocked this turn."
        ),
    }
    assert not any(
        s.key == "type_matters" and s.subject == "Creature"
        for s in extract_signals(generic, include_membership=True)
    )


def test_tribal_tutor_with_intervening_type_word():
    # The tribal-tutor pattern must capture the tribe when a card-type word sits between
    # the tribe and "card": Zirilan tutors "a Dragon PERMANENT card", so it's a Dragon
    # commander (wants Utvara Hellkite, Balefire Dragon). The bare "for a X card" regex
    # broke on "Dragon permanent card".
    zirilan = {
        "name": "Zirilan of the Claw",
        "type_line": "Legendary Creature — Lizard Shaman",
        "oracle_text": (
            "{1}{R}{R}, {T}: Search your library for a Dragon permanent card, put that "
            "card onto the battlefield, then shuffle. That Dragon gains haste until end "
            "of turn. Sacrifice it at the beginning of the next end step."
        ),
    }
    assert ("type_matters", "you", "Dragon") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(zirilan, include_membership=True)
    }
    # Over-fire guard: "search for a basic land card" captures no tribe (vocab gate).
    fetch = {
        "name": "Generic Fetch",
        "type_line": "Sorcery",
        "oracle_text": "Search your library for a basic land card, put it onto the battlefield tapped.",
    }
    assert not any(
        s.key == "type_matters" and s.subject in ("Basic", "Land")
        for s in extract_signals(fetch, include_membership=True)
    )


def test_type_grant_opens_tribal():
    # A commander that CONVERTS its creatures to a tribe — "it's a Zombie in addition to
    # its other creature types" (Lim-Dûl reanimates as Zombies), Chainer (Nightmare) —
    # makes its board that tribe, so it wants that tribe's lords (Death Baron, Undead
    # Warchief). The tribal detector keyed on "Xs you control", not the type-GRANT form.
    lim_dul = {
        "name": "Lim-Dûl the Necromancer",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Whenever a creature an opponent controls dies, you may pay {1}{B}. If you "
            "do, return that card to the battlefield under your control. If it's a "
            "creature, it's a Zombie in addition to its other creature types.\n"
            "{1}{B}: Regenerate target Zombie."
        ),
    }
    assert ("type_matters", "you", "Zombie") in {
        (s.key, s.scope, s.subject) for s in extract_signals(lim_dul)
    }
    # Over-fire guard: a vanilla creature grants no type.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert not any(
        s.key == "type_matters" and s.subject == "Zombie" for s in extract_signals(bear)
    )


def test_class_tribe_membership_opens_when_go_wide():
    # A class-typed legend (Soldier/Cleric/Ninja/…) is its OWN tribe only when it also
    # rewards a board of creatures (go-wide / anthem / attack). Odric is a Human SOLDIER
    # whose ability rewards attacking with many creatures, so it wants Soldier lords
    # (Field Marshal, Daru Warchief) though the oracle never says "Soldier". Class types
    # stay gated (unlike race tribes) because they're near-ubiquitous.
    odric = {
        "name": "Odric, Master Tactician",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "First strike (This creature deals combat damage before creatures without "
            "first strike.)\nWhenever Odric and at least three other creatures attack, "
            "you choose which creatures block this combat and how those creatures block."
        ),
    }
    trips = {
        (s.key, s.scope, s.subject)
        for s in extract_signals(odric, include_membership=True)
    }
    assert ("type_matters", "you", "Soldier") in trips
    # Human is excluded even gated — too ubiquitous to be a build-around.
    assert ("type_matters", "you", "Human") not in trips

    # Anthem path: Ravos is a Human CLERIC with "Other creatures you control get +1/+1".
    ravos = {
        "name": "Ravos, Soultender",
        "type_line": "Legendary Creature — Human Cleric",
        "oracle_text": (
            "Flying\nOther creatures you control get +1/+1.\nAt the beginning of your "
            "upkeep, you may return target creature card from your graveyard to your "
            "hand.\nPartner (You can have two commanders if both have partner.)"
        ),
    }
    assert ("type_matters", "you", "Cleric") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(ravos, include_membership=True)
    }

    # Ninja: Taeko (Turtle Ninja) opens Turtle (race membership) AND attacks; the class-
    # tribe rule adds Ninja so its ninjutsu pile (Silver-Fur Master, Satoru) is served.
    taeko = {
        "name": "Taeko, the Patient Avalanche",
        "type_line": "Legendary Creature — Turtle Ninja",
        "oracle_text": (
            "Taeko enters tapped.\nWhenever another creature you control leaves the "
            "battlefield, if it didn't die, scry 1 and put a +1/+1 counter on Taeko.\n"
            "Whenever Taeko attacks, you may pay {U/B}. When you do, target attacking "
            "creature can't be blocked this turn."
        ),
    }
    assert ("type_matters", "you", "Ninja") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(taeko, include_membership=True)
    }


def test_universes_beyond_faction_tribes_open_by_membership():
    # UB faction-tribes with their own commanders + tribal support (the samurai flavor-
    # tribe precedent): a Villain legend (Rhino) wants Villains, a Doctor legend (The
    # Fourteenth Doctor) wants Doctors — opened by membership though the oracle names no
    # tribe. Strong build-around identity, so ungated like a race/flavor tribe.
    rhino = {
        "name": "Rhino, Barreling Brute",
        "type_line": "Legendary Creature — Human Villain",
        "oracle_text": (
            "Vigilance, trample, haste\nWhenever Rhino attacks, if you've cast a spell "
            "with mana value 4 or greater this turn, draw a card."
        ),
    }
    assert ("type_matters", "you", "Villain") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(rhino, include_membership=True)
    }
    doctor = {
        "name": "The Fourteenth Doctor",
        "type_line": "Legendary Creature — Time Lord Doctor",
        "oracle_text": (
            "When you cast this spell, reveal the top fourteen cards of your library. "
            "Put all Doctor cards revealed this way into your graveyard and the rest on "
            "the bottom of your library in a random order.\nYou may have The Fourteenth "
            "Doctor enter as a copy of a Doctor card in your graveyard that was put there "
            "from your library this turn. If you do, it gains haste until end of turn."
        ),
    }
    assert ("type_matters", "you", "Doctor") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(doctor, include_membership=True)
    }


def test_class_tribe_membership_gated_off_without_creature_signal():
    # Over-fire guard: a class-typed legend that DOESN'T reward a board (a pure control
    # Wizard) must NOT open its class tribe. Hisoka is a Human Wizard whose only ability
    # is a counterspell — no go-wide/anthem/attack signal — so "Wizard" stays closed.
    hisoka = {
        "name": "Hisoka, Minamo Sensei",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "{2}{U}, Discard a card: Counter target spell if it has the same mana value "
            "as the discarded card."
        ),
    }
    assert not any(
        s.key == "type_matters" and s.subject == "Wizard"
        for s in extract_signals(hisoka, include_membership=True)
    )


def test_instant_sorcery_buildaround_opens_spellcast():
    # A commander that builds around instants/sorceries WITHOUT a "whenever you cast"
    # trigger — Lier grants every instant/sorcery in the graveyard flashback — is a
    # spellslinger deck; the cast-trigger-only detector misses it, so its instant/sorcery
    # density goes unserved. Open spellcast_matters off the flashback-grant / recursion /
    # cost-reduction build-around.
    lier = {
        "name": "Lier, Disciple of the Drowned",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Spells can't be countered.\nEach instant and sorcery card in your graveyard "
            "has flashback. The flashback cost is equal to that card's mana cost."
        ),
    }
    assert "spellcast_matters" in {
        s.key for s in extract_signals(lier, include_membership=True)
    }
    # Over-fire guard: a bare counterspell mentions an instant but isn't an instant/
    # sorcery build-around — it must NOT read as spellslinger.
    dispel = {
        "name": "Dispel",
        "type_line": "Instant",
        "oracle_text": "Counter target instant spell.",
    }
    assert "spellcast_matters" not in {
        s.key for s in extract_signals(dispel, include_membership=True)
    }


def test_color_hoser_opens_and_serves_color_change_toolbox():
    # A color-HOSER commander (punishes/restricts/bounces a named COLOR) wants the
    # color-changing "Painter" toolbox to force its color payoff onto every permanent:
    # Llawan (opponents' blue creatures bounce + can't be cast), Dromar (choose a color,
    # bounce all of it). They open color_hoser; the serve is the color-change toolbox.
    from mtg_utils._deck_forge.signal_specs import spec_for

    llawan = {
        "name": "Llawan, Cephalid Empress",
        "type_line": "Legendary Creature — Octopus Noble",
        "oracle_text": (
            "When Llawan enters, return all blue creatures your opponents control to "
            "their owners' hands.\nYour opponents can't cast blue creature spells."
        ),
    }
    dromar = {
        "name": "Dromar, the Banisher",
        "type_line": "Legendary Creature — Dragon",
        "oracle_text": (
            "Flying\nWhenever Dromar deals combat damage to a player, you may pay "
            "{2}{U}. If you do, choose a color, then return all creatures of that color "
            "to their owners' hands."
        ),
    }
    assert any(s.key == "color_hoser" for s in extract_signals(llawan))
    assert any(s.key == "color_hoser" for s in extract_signals(dromar))
    # Over-fire guard: a plain color anthem (Bad Moon, "Black creatures get +1/+1") is
    # NOT a hoser — it doesn't punish/restrict/bounce a color.
    bad_moon = {
        "name": "Bad Moon",
        "type_line": "Enchantment",
        "oracle_text": "Black creatures get +1/+1.",
    }
    assert not any(s.key == "color_hoser" for s in extract_signals(bad_moon))

    # Serve = the color-change toolbox (Painter's Servant, Sleight of Mind), not a
    # protection-from-color trick or a mana fixer.
    sig = next(s for s in extract_signals(llawan) if s.key == "color_hoser")
    sp = spec_for(sig)
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
    mishra = {
        "name": "Mishra, Excavation Prodigy",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "Haste\n{1}, {T}, Discard a card: Draw a card.\nWhenever you discard one or "
            "more artifact cards, add {R}{R}. This ability triggers only once each turn."
        ),
    }
    keys = {s.key for s in extract_signals(mishra, include_membership=True)}
    assert "discard_outlet" in keys  # precondition
    assert "graveyard_matters" in keys  # cross-opened


def test_spell_copy_cross_opens_spellcast():
    # A spell-copy commander copies the instants/sorceries you cast (Zevlor, Rassilon,
    # Veyran), so it is a spellslinger wanting a dense spell base — cross-open
    # spellcast_matters so its instant/sorcery package is served.
    zevlor = {
        "name": "Zevlor, Elturel Exile",
        "type_line": "Legendary Creature — Tiefling Warrior",
        "oracle_text": (
            "Haste\n{2}, {T}: When you next cast an instant or sorcery spell that targets "
            "only a single opponent or a single permanent an opponent controls this turn, "
            "for each other opponent, choose that player or a permanent they control, copy "
            "that spell, and the copy targets the chosen player or permanent."
        ),
    }
    # ADR-0027: spell_copy_matters migrated to the IR, so the cross-open is
    # reconciled in the hybrid (the regex path no longer emits spell_copy_matters).
    spell_copy_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="activated",
                        effects=(
                            Effect(
                                category="spell_copy",
                                scope="you",
                                raw="copy that spell",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    keys = {
        s.key
        for s in extract_signals_hybrid(zevlor, spell_copy_ir, include_membership=True)
    }
    assert "spell_copy_matters" in keys  # precondition
    assert "spellcast_matters" in keys  # cross-opened


def test_named_token_maker_opens_tribe_via_all_parts():
    # A creature token the commander makes (all_parts token component) reveals its tribe
    # even when the oracle uses the token's NAME: Enkira makes "Walker tokens" (Token
    # Creature — Zombie), so it's Zombie-tribal (Death Baron, Gravecrawler) though the
    # oracle never says "Zombie" outside reminder text.
    enkira = {
        "name": "Enkira, Hostile Scavenger",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "When Enkira, Hostile Scavenger enters, create two Walker tokens. (They're "
            "2/2 black Zombie creatures.)"
        ),
        "all_parts": [
            {
                "component": "combo_piece",
                "name": "Enkira, Hostile Scavenger",
                "type_line": "Legendary Creature — Human Warrior",
            },
            {
                "component": "token",
                "name": "Walker",
                "type_line": "Token Creature — Zombie",
            },
        ],
    }
    assert ("type_matters", "you", "Zombie") in {
        (s.key, s.scope, s.subject)
        for s in extract_signals(enkira, include_membership=True)
    }


def test_token_maker_cross_opens_its_tribe_kindred():
    # A commander that MAKES tribe-X creature tokens wants tribe-X lords/support — its
    # token board IS that kindred. Grist makes Insect tokens but is a Planeswalker, so
    # membership (which needs a creature type-line) misses it; cross-open type_matters
    # from the token's captured subtype.
    grist = {
        "name": "Grist, the Hunger Tide",
        "type_line": "Legendary Planeswalker — Grist",
        "oracle_text": (
            "As long as Grist isn't on the battlefield, it's a 1/1 Insect creature in "
            "addition to its other types.\n+1: Create a 1/1 black and green Insect "
            "creature token, then mill a card. If an Insect card was milled this way, put "
            "a loyalty counter on Grist and repeat this process.\n−2: You may sacrifice a "
            "creature. When you do, destroy target creature or planeswalker.\n−5: Each "
            "opponent loses life equal to the number of creature cards in your graveyard."
        ),
    }
    trips = {
        (s.key, s.subject) for s in extract_signals(grist, include_membership=True)
    }
    assert ("type_matters", "Insect") in trips


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


def test_creature_token_maker_cross_opens_creatures_matter():
    # A token_maker that makes CREATURE tokens (Darien -> Soldiers) is a go-wide creatures
    # deck: it wants anthems + per-creature-ETB payoffs (Soul Warden, Impact Tremors) +
    # Cathars' Crusade, all served by creatures_matter. The bare token_maker lane doesn't
    # serve those, so cross-open creatures_matter (low confidence).
    darien = {
        "name": "Darien, King of Kjeldor",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Whenever you're dealt damage, you may create that many 1/1 white Soldier "
            "creature tokens."
        ),
    }
    keys = {s.key for s in extract_signals(darien, include_membership=True)}
    assert "creatures_matter" in keys
    # Over-fire guard: a NON-creature (Treasure) token maker is not a go-wide creatures
    # deck — token_maker never captures a creature subject, so creatures_matter stays shut.
    tithe = {
        "name": "Smothering Tithe",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever an opponent draws a card, that player may pay {2}. If the player "
            "doesn't, you create a Treasure token."
        ),
    }
    assert "creatures_matter" not in {
        s.key for s in extract_signals(tithe, include_membership=True)
    }


def test_play_from_top_cross_opens_topdeck_selection():
    # A "play cards from the top of your library" commander (Gwenom, Glarb) curates its
    # top — it wants surveil/scry and top-stacking (Doom Whisperer, Sensei's Top). It
    # opens play_from_top and the sibling topdeck_selection/stack lanes. Real oracle.
    # ADR-0027 β: play_from_top migrated to the Card IR, so the hybrid serves it (here
    # via the per-clause kept mirror — Gwenom's permission is a TRIGGERED/temporary form
    # phase doesn't model as a cast-permission static). The topdeck_selection cross-open
    # now keys off the byte-identical _PLAY_FROM_TOP_MIRROR in the regex path, so it
    # fires on both the regex and hybrid paths.
    gwenom = {
        "name": "Gwenom, Remorseless",
        "type_line": "Legendary Creature — Symbiote Villain",
        "oracle_text": (
            "Deathtouch, lifelink\nWhenever Gwenom attacks, until end of turn, you may "
            "look at the top card of your library any time and you may play cards from "
            "the top of your library."
        ),
    }
    ks = _ks_hybrid(gwenom)
    assert ("play_from_top", "you") in ks
    assert ("topdeck_selection", "you") in ks
    # Over-fire guard: a commander that doesn't play from the top opens neither.
    plain = {
        "name": "Plain Beater",
        "type_line": "Legendary Creature — Bear",
        "oracle_text": "Trample",
    }
    assert ("topdeck_selection", "you") not in _ks_hybrid(plain)


def test_sac_and_return_this_turn_does_not_over_fire_sacrifice():
    # ADR-0027: the old "sac-and-return-this-turn" floor regex fired sacrifice_matters
    # on Garna / Gerrard — reanimation engines that name NO sacrifice at all. That was
    # an over-fire (a return-from-graveyard payoff is not a sacrifice OUTLET); the
    # migrated IR path correctly drops it, and the floor regex is deleted. Real oracle.
    garna = {
        "name": "Garna, the Bloodflame",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "Flash\nWhen Garna, the Bloodflame enters, return to your hand all creature "
            "cards in your graveyard that were put there from anywhere this turn.\n"
            "Other creatures you control have haste."
        ),
    }
    gerrard = {
        "name": "Gerrard, Weatherlight Hero",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "When Gerrard, Weatherlight Hero dies, return to the battlefield all "
            "permanent cards in your graveyard that were put there from the "
            "battlefield this turn."
        ),
    }
    assert ("sacrifice_matters", "you") not in _ks(garna)
    assert ("sacrifice_matters", "you") not in _ks(gerrard)
    # Over-fire guard: a vanilla creature is not a sac-and-return engine.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("sacrifice_matters", "you") not in _ks(bear)


def test_warp_granting_opens_cheat_into_play():
    # Tannuk grants WARP ("cards in your hand have warp" — cast from hand for the warp
    # cost, a temporary cheat-into-play). It's a cheat deck: it wants fat creatures and
    # cheat enablers (Ilharg, Maelstrom Colossus), served by cheat_into_play. It opened
    # void_warp/team_buff but not cheat. Real oracle.
    tannuk = {
        "name": "Tannuk, Steadfast Second",
        "type_line": "Legendary Creature — Phyrexian Warrior",
        "oracle_text": (
            "Other creatures you control have haste.\n"
            "Artifact cards and red creature cards in your hand have warp {2}{R}. (You "
            "may cast a card from your hand for its warp cost. Exile that permanent at "
            "the beginning of the next end step, then you may cast it from exile on a "
            "later turn.)"
        ),
    }
    assert "cheat_into_play" in _keys(tannuk)
    # Over-fire guard: a vanilla creature is not a cheat deck.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert "cheat_into_play" not in _keys(bear)


def test_active_reanimation_opens_reanimator():
    # A CREATURE whose OWN ability actively reanimates — "return/put target creature
    # card from a graveyard onto/to the battlefield" (Alesha, Olivia Crimson Bride,
    # Sauron) — is a reanimator deck wanting reanimation spells + fat targets. ADR-0027:
    # reanimator migrated to the IR; the lane reads a structural `reanimate` effect that
    # returns CREATURE cards (the archetype), NOT the regex's conflated "entered/cast
    # FROM a graveyard" recursion form (a separate axis — CR 702.34 / 603). Real oracle.
    alesha = {
        "name": "Alesha, Who Smiles at Death",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "First strike\nWhenever Alesha, Who Smiles at Death attacks, you may pay "
            "{W/B}{W/B}. If you do, return target creature card with power 2 or less "
            "from your graveyard to the battlefield tapped and attacking."
        ),
    }
    olivia = {
        "name": "Olivia, Crimson Bride",
        "type_line": "Legendary Creature — Vampire Noble",
        "oracle_text": (
            "Flying, haste\nWhenever Olivia, Crimson Bride attacks, return target "
            "creature card from your graveyard to the battlefield tapped and attacking."
        ),
    }
    reanimate_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="reanimate",
                                scope="you",
                                subject=Filter(card_types=("Creature",)),
                                raw="return target creature card from your graveyard to the battlefield",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "reanimator" in _keys_hybrid_ir(alesha, reanimate_ir)
    assert "reanimator" in _keys_hybrid_ir(olivia, reanimate_ir)
    # Over-fire guard: a self-mill spell (fills the yard, doesn't reanimate) is not a
    # reanimator commander.
    selfmill = {
        "name": "Mill Self",
        "type_line": "Legendary Creature — Wizard",
        "oracle_text": "Put the top four cards of your library into your graveyard.",
    }
    assert "reanimator" not in _keys_hybrid(selfmill)


def test_creature_died_this_turn_payoff_opens_death():
    # A commander that rewards "a creature died ... this turn" (Faramir draws, Sméagol
    # tempts, Tobias makes Zombies, Ebondeath recasts) is an aristocrats payoff — it
    # wants sac fodder and sac outlets, which death_matters serves. The "died under your
    # control this turn" word order slipped past the existing died-this-turn detector.
    faramir = {
        "name": "Faramir, Field Commander",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "At the beginning of your end step, if a creature died under your control "
            "this turn, draw a card."
        ),
    }
    tobias = {
        "name": "Tobias, Doomed Conqueror",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Flash\nWhen Tobias dies, for each nontoken creature you controlled that "
            "died this turn, create a 2/2 black Zombie creature token."
        ),
    }
    # ADR-0027: death_matters migrated to the Card IR; the morbid "died this turn"
    # family rides the byte-identical _DEATH_MATTERS_MIRROR (scope "any") on the IR path.
    assert ("death_matters", "any") in _ks_hybrid(faramir)
    assert ("death_matters", "any") in _ks_hybrid(tobias)
    # Over-fire guard: a vanilla creature has no death payoff.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("death_matters", "any") not in _ks_hybrid(bear)


def test_self_dies_recursion_opens_self_death_payoff():
    # A commander whose OWN death trigger RETURNS/recurs itself (Lucius exiles-and-
    # returns, The Scorpion God returns to hand) wants sac outlets to loop it +
    # reanimation — the same package as a self-dies-VALUE commander. self_death_payoff
    # required a VALUE verb and missed the pure-recursion form. Real oracle.
    lucius = {
        "name": "Lucius the Eternal",
        "type_line": "Legendary Creature — Phyrexian Noble",
        "oracle_text": (
            "Haste\nArmour of Shrieking Souls — When Lucius the Eternal dies, exile it "
            "and choose target creature an opponent controls. When that creature "
            "leaves the battlefield, return this card from exile to the battlefield "
            "under its owner's control."
        ),
    }
    scorpion = {
        "name": "The Scorpion God",
        "type_line": "Legendary Creature — God",
        "oracle_text": (
            "The Scorpion God can't be blocked by creatures with power 2 or less.\n"
            "Whenever a creature with a -1/-1 counter on it dies, draw a card.\n"
            "When The Scorpion God dies, return it to its owner's hand at the "
            "beginning of the next end step."
        ),
    }
    # ADR-0027: self_death_payoff migrated to the Card IR; the self-RECURSION death
    # branch ("return it"/"exile it") rides the name-aware kept mirror on the hybrid path.
    assert "self_death_payoff" in _keys_hybrid(lucius)
    assert "self_death_payoff" in _keys_hybrid(scorpion)
    # Over-fire guard: a vanilla creature has no self-death trigger.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert "self_death_payoff" not in _keys_hybrid(bear)


def test_opponent_shrink_opens_debuff():
    # Maha shrinks opponents' creatures ("Creatures your opponents control have base
    # toughness 1") — it combos with -1/-1 effects (toughness 1 + any -1/-1 = dead), so
    # it's a debuff commander wanting -1/-1 anthems/wipes (Kaervek the Spiteful, Black
    # Sun's Zenith). It opened base_pt_set/stax but not debuff_matters. Real oracle.
    maha = {
        "name": "Maha, Its Feathers Night",
        "type_line": "Legendary Creature — Elemental Bird",
        "oracle_text": (
            "Flying, trample\nWard—Discard a card.\n"
            "Creatures your opponents control have base toughness 1."
        ),
    }
    # ADR-0027 β: debuff_matters is IR-served. The Maha opponent-shrink fires via the
    # DEBUFF_MAHA_REGEX kept-mirror (scope "you"), which scans the oracle directly, so a
    # bare non-None IR routes the hybrid to the IR path. The legacy regex path no longer
    # emits it.
    assert ("debuff_matters", "you") not in _ks(maha)
    assert ("debuff_matters", "you") in _ks_hybrid(maha)
    # Over-fire guard: a commander that buffs YOUR creatures is not a debuff commander.
    buffer_cmd = {
        "name": "Team Buffer",
        "type_line": "Legendary Creature — Soldier",
        "oracle_text": "Creatures you control get +1/+1.",
    }
    assert ("debuff_matters", "you") not in _ks_hybrid(buffer_cmd)


def test_treasure_care_opens_treasure_matters():
    # A commander that cares about Treasure without making it — "if the sacrificed
    # permanent was a Treasure" (Evereth), "sacrifice a Treasure" (Kain) — is a Treasure
    # deck wanting Treasure makers/doublers (Academy Manufactor, Xorn). The detector
    # keyed on "create ... Treasure" / "Treasures you control" and missed these.
    # ADR-0027: treasure_matters migrated to the Card IR — the "was a Treasure" care is
    # a `token_subtype_ref` marker (subtype in counter_kind) read via _TOKEN_SUBTYPE_KEYS
    # through the hybrid, not the deleted regex.
    evereth = {
        "name": "Evereth, Viceroy of Plunder",
        "type_line": "Legendary Creature — Human Pirate",
        "oracle_text": (
            "Flying\nSacrifice another creature or artifact: Put a +1/+1 counter on "
            "Evereth. If the sacrificed permanent was a Treasure, Evereth gains "
            "lifelink until end of turn. Activate only as a sorcery."
        ),
    }
    evereth_ir = Card(
        oracle_id="x",
        name="Evereth, Viceroy of Plunder",
        faces=(
            Face(
                name="Evereth, Viceroy of Plunder",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="token_subtype_ref",
                                scope="you",
                                counter_kind="treasure",
                                raw="was a Treasure",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("treasure_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(evereth, evereth_ir)
    }
    assert ("treasure_matters", "you") not in _ks(evereth)
    # Over-fire guard: a vanilla creature is not a Treasure commander.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("treasure_matters", "you") not in _ks(bear)
    assert ("treasure_matters", "you") not in _ks_hybrid(bear)


def test_mana_ability_payoff_opens_ramp():
    # A commander that rewards "creatures you control with a mana ability" (Raggadragga
    # buffs/untaps them) is a mana-dork deck — it wants mana-dork creatures (served by
    # ramp_matters) and dork support (mana_amplifier). Niche (one commander) but precise.
    # ADR-0027 β: the dork-support mana_amplifier arm is migrated to the Card IR — phase
    # drops the "with a mana ability" subject, so it rides a byte-identical kept word
    # mirror (_MANA_DORK_SUPPORT_MIRROR). ADR-0027: ramp_matters ALSO migrated — its
    # dork-support producer rode the SAME mirror, so both now fire from the hybrid path.
    raggadragga = {
        "name": "Raggadragga, Goreguts Boss",
        "type_line": "Legendary Creature — Frog Warrior",
        "oracle_text": (
            "Each creature you control with a mana ability gets +2/+2.\n"
            "Whenever a creature you control with a mana ability attacks, untap it.\n"
            "Whenever you cast a spell, if at least seven mana was spent to cast it, "
            "untap target creature. It gets +7/+7 and gains trample until end of turn."
        ),
    }
    assert ("ramp_matters", "you") not in _ks(raggadragga)
    assert ("ramp_matters", "you") in _ks_hybrid(raggadragga)
    assert "mana_amplifier" not in _keys(raggadragga)
    assert ("mana_amplifier", "you") in _ks_hybrid(raggadragga)
    # Over-fire guard: a vanilla beater is not a mana-dork payoff.
    bear = {"name": "Grizzly Bears", "type_line": "Creature — Bear", "oracle_text": ""}
    assert ("ramp_matters", "you") not in _ks(bear)
    assert ("ramp_matters", "you") not in _ks_hybrid(bear)


def test_charge_and_experience_counters_open_proliferate():
    # A commander that accumulates a BENEFICIAL resource counter — charge (Immard) or
    # experience (Ezuri, Mizzix) — wants proliferate (pure upside: more charge to spend,
    # more experience). Distinct from a PENALTY counter (Arixmethes' slumber), where
    # proliferate is anti-synergy, so the lane is gated to charge/experience only.
    immard = {
        "name": "Immard, the Stormcleaver",
        "type_line": "Legendary Creature — Giant Berserker",
        "oracle_text": (
            "Whenever Immard, the Stormcleaver enters or attacks, put a charge counter "
            "on it or remove one from it. When you remove a counter this way, choose "
            "one —\n• Immard deals 4 damage to any target.\n• Immard gains lifelink."
        ),
    }
    ezuri = {
        "name": "Ezuri, Claw of Progress",
        "type_line": "Legendary Creature — Phyrexian Elf",
        "oracle_text": (
            "Whenever a creature you control with power 2 or less enters, you get an "
            "experience counter.\nAt the beginning of combat on your turn, put X +1/+1 "
            "counters on another target creature you control, where X is the number of "
            "experience counters you have."
        ),
    }
    # ADR-0027: proliferate_matters migrated to the Card IR; the charge/experience
    # counter sources now fire from the _IR_KEPT_DETECTORS mirror, so assert the
    # hybrid path.
    assert ("proliferate_matters", "you") in _ks_hybrid(immard)
    assert ("proliferate_matters", "you") in _ks_hybrid(ezuri)
    # Over-fire guard: a PENALTY-counter commander (slumber) must NOT open proliferate —
    # proliferate would keep Arixmethes asleep (anti-synergy).
    arixmethes = {
        "name": "Arixmethes, Slumbering Isle",
        "type_line": "Legendary Creature — Kraken",
        "oracle_text": (
            "Arixmethes, Slumbering Isle enters tapped with five slumber counters on "
            "it.\nAs long as Arixmethes has a slumber counter on it, it's a land.\n"
            "Whenever you cast a spell, you may remove a slumber counter from Arixmethes."
        ),
    }
    assert ("proliferate_matters", "you") not in _ks_hybrid(arixmethes)


def test_polymorph_cheat_opens_cheat_into_play():
    # Polymorph/cheat commanders dig until a creature card and PUT IT ONTO THE
    # BATTLEFIELD (Jalira, Atla Palani, Eladamri) — they want big fatties to cheat in.
    # The per-clause cheat detector missed them: "reveal … a creature card." and "Put
    # that card onto the battlefield" split across a period, and "that card" isn't
    # "creature card". Full-text. Real oracle.
    jalira = {
        "name": "Jalira, Master Polymorphist",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "{2}{U}, {T}, Sacrifice another creature: Reveal cards from the top of "
            "your library until you reveal a nonlegendary creature card. Put that card "
            "onto the battlefield and the rest on the bottom of your library in a "
            "random order."
        ),
    }
    atla = {
        "name": "Atla Palani, Nest Tender",
        "type_line": "Legendary Creature — Bird Shaman",
        "oracle_text": (
            "{2}, {T}: Create a 0/1 green Egg creature token with defender.\n"
            "Whenever an Egg you control dies, reveal cards from the top of your "
            "library until you reveal a creature card. Put that card onto the "
            "battlefield and the rest on the bottom of your library in a random order."
        ),
    }
    eladamri = {
        "name": "Eladamri, Korvecdal",
        "type_line": "Legendary Creature — Elf",
        "oracle_text": (
            "You may look at the top card of your library any time.\n"
            "You may cast creature spells from the top of your library.\n"
            "{G}, {T}, Tap two untapped creatures you control: Reveal a card from your "
            "hand or the top card of your library. If you reveal a creature card this "
            "way, put it onto the battlefield. Activate only during your turn."
        ),
    }
    assert "cheat_into_play" in _keys(jalira)
    assert "cheat_into_play" in _keys(atla)
    assert "cheat_into_play" in _keys(eladamri)
    # Over-fire guard: a graveyard reanimator is not a library/hand cheat.
    reanimator = {
        "name": "Reanimator",
        "type_line": "Sorcery",
        "oracle_text": (
            "Return target creature card from your graveyard to the battlefield."
        ),
    }
    assert "cheat_into_play" not in _keys(reanimator)


def test_counter_payoff_with_a_counter_on_it_opens_counters():
    # A +1/+1-counters commander whose payoff REWARDS creatures that HAVE counters
    # ("each creature you control WITH A COUNTER ON IT ...", "unless he has a +1/+1
    # counter on him") is a counters deck. The per-clause counters detector missed it:
    # the payoff clause ("with a counter on it") and the +1/+1 reference ("put a +1/+1
    # counter on Baxter") sit in SEPARATE sentences, so neither clause alone has both.
    # Needs full-text. Real oracle.
    rishkar = {
        "name": "Rishkar, Peema Renegade",
        "type_line": "Legendary Creature — Elf Druid",
        "oracle_text": (
            "When Rishkar, Peema Renegade enters, put a +1/+1 counter on each of up to "
            "two target creatures.\nEach creature you control with a counter on it has "
            '"{T}: Add {G}."'
        ),
    }
    baxter = {
        "name": "Baxter, Fly in the Ointment",
        "type_line": "Legendary Creature — Insect",
        "oracle_text": (
            "Whenever Baxter enters or attacks, each creature you control with a "
            "counter on it gains flying until end of turn.\nWhenever you draw a card, "
            "put a +1/+1 counter on Baxter."
        ),
    }
    pipsqueak = {
        "name": "Pipsqueak, Rebel Strongarm",
        "type_line": "Legendary Creature — Rabbit Soldier",
        "oracle_text": "Pipsqueak can't attack alone unless he has a +1/+1 counter on him.",
    }
    # ADR-0027: counters_matter migrated to the IR. Rishkar/Baxter project a
    # place_counter(p1p1); Pipsqueak (a pure "has a +1/+1 counter" payoff) recovers a
    # counters_have_ref marker. Assert via the hybrid (production) path.
    place_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="place_counter",
                                scope="you",
                                counter_kind="p1p1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    have_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="counters_have_ref",
                                scope="you",
                                raw="has a +1/+1 counter on him",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "counters_matter" in _keys_hybrid_ir(rishkar, place_ir)
    assert "counters_matter" in _keys_hybrid_ir(baxter, place_ir)
    assert "counters_matter" in _keys_hybrid_ir(pipsqueak, have_ir)


def test_artifact_dig_and_improvise_open_artifacts():
    # Commanders that DIG for artifact cards ("put an artifact card ... into your hand /
    # onto the battlefield" — Fifteenth Doctor, Jhoira) or grant IMPROVISE (an
    # artifact-tap mechanic like affinity) are artifact decks; artifacts_matter matched
    # "search for an artifact card" but not these forms. Real oracle.
    doctor = {
        "name": "The Fifteenth Doctor",
        "type_line": "Legendary Creature — Time Lord Doctor",
        "oracle_text": (
            "Whenever The Fifteenth Doctor enters or attacks, mill three cards. You "
            "may put an artifact card with mana value 2 or 3 from among them into your "
            "hand.\nThe first nonartifact spell you cast each turn has improvise."
        ),
    }
    jhoira = {
        "name": "Jhoira, Ageless Innovator",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "{T}: Put two ingenuity counters on Jhoira, then you may put an artifact "
            "card with mana value X or less from your hand onto the battlefield, where "
            "X is the number of ingenuity counters on Jhoira."
        ),
    }
    # ADR-0027: artifacts_matter migrated to the Card IR — the "put an artifact card …
    # into your hand / onto the battlefield" dig + \bimprovise\b ride the kept oracle
    # mirror on the hybrid path.
    assert "artifacts_matter" in _keys_hybrid(doctor)
    assert "artifacts_matter" in _keys_hybrid(jhoira)
    # Over-fire guard: a vanilla creature is not an artifact commander.
    bear = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert "artifacts_matter" not in _keys_hybrid(bear)


def test_power_greater_than_base_power_opens_counters():
    # A commander that rewards creatures whose "power [is] greater than its base power"
    # (Kutzil, Baird) is a pump / +1/+1-counters payoff — those creatures got there via
    # counters or pumps. It should open counters_matter so +1/+1 counter sources
    # (Forgotten Ancient, Hardened Scales) surface. Niche but precise — only two
    # commander-legal cards carry the phrase. Real oracle.
    kutzil = {
        "name": "Kutzil, Malamet Exemplar",
        "type_line": "Legendary Creature — Cat Warrior",
        "oracle_text": (
            "Your opponents can't cast spells during your turn.\nWhenever one or more "
            "creatures you control each with power greater than its base power deals "
            "combat damage to a player, draw a card."
        ),
    }
    baird = {
        "name": "Baird, Argivian Recruiter",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "At the beginning of your end step, if you control a creature with power "
            "greater than its base power, create a 1/1 white Soldier creature token."
        ),
    }
    # ADR-0027: counters_matter migrated to the IR — "power greater than its base
    # power" recovers a counters_have_ref marker; assert via the hybrid path.
    have_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="counters_have_ref",
                                scope="you",
                                raw="power greater than its base power",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "counters_matter" in _keys_hybrid_ir(kutzil, have_ir)
    assert "counters_matter" in _keys_hybrid_ir(baird, have_ir)


def test_forced_combat_and_any_player_attack_open_goad():
    # Goad cards (Disrupt Decorum) are top-synergy for two archetypes that never opened
    # goad_matters: commanders that FORCE OTHER creatures to attack (Basandra "Target
    # creature attacks this turn if able" — the goad mechanic itself, CR 701.39) and
    # commanders that reward ANY player attacking (Aurelia "Whenever a player attacks
    # with three or more creatures" — goad makes opponents attack into the payoff). Real
    # oracle.
    basandra = {
        "name": "Basandra, Battle Seraph",
        "type_line": "Legendary Creature — Angel",
        "oracle_text": (
            "Flying\nPlayers can't cast spells during combat.\n"
            "{R}: Target creature attacks this turn if able."
        ),
    }
    aurelia = {
        "name": "Aurelia, the Law Above",
        "type_line": "Legendary Creature — Angel",
        "oracle_text": (
            "Flying, vigilance, haste\nWhenever a player attacks with three or more "
            "creatures, you draw a card. This ability triggers only once each turn."
        ),
    }
    # ADR-0027: goad_matters migrated to the IR — the regex path no longer emits it;
    # the hybrid path serves it (Basandra via the goad-style single-target force_attack
    # effect; Aurelia via the _GOAD_REWARD_REF marker, mirrored as a goad_all effect).
    assert ("goad_matters", "opponents") not in _ks(basandra)
    assert ("goad_matters", "opponents") not in _ks(aurelia)
    basandra_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="activated",
                        effects=(
                            Effect(
                                category="force_attack",
                                scope="any",
                                raw="Target creature attacks this turn if able.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    aurelia_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="spell",
                        effects=(
                            Effect(
                                category="goad_all",
                                scope="opp",
                                raw="Whenever a player attacks",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("goad_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(basandra, basandra_ir)
    }
    assert ("goad_matters", "opponents") in {
        (s.key, s.scope) for s in extract_signals_hybrid(aurelia, aurelia_ir)
    }
    # Over-fire guard: a SELF forced-attacker (Zurgo) is an aggressive beater, not a
    # goad commander — it forces only ITSELF to attack each combat. The goad-style
    # force lift requires a "target creature" force, which Zurgo's self-force lacks.
    zurgo = {
        "name": "Zurgo Helmsmasher",
        "type_line": "Legendary Creature — Orc Warrior",
        "oracle_text": (
            "Haste\nZurgo Helmsmasher attacks each combat if able.\nZurgo Helmsmasher "
            "gets +3/+3 as long as it's your turn."
        ),
    }
    zurgo_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="force_attack",
                                scope="any",
                                raw="~ attacks each combat if able.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("goad_matters", "opponents") not in _ks(zurgo)
    assert ("goad_matters", "opponents") not in {
        (s.key, s.scope) for s in extract_signals_hybrid(zurgo, zurgo_ir)
    }


def test_gain_control_commander_also_opens_theft_matters():
    # A battlefield-steal commander (Dragonlord Silumgar "gain control of target
    # creature") and a borrow-and-cast theft commander are facets of the SAME stealing
    # archetype — a steal deck runs the borrow-and-cast package (Gonti, Hostage Taker,
    # Thief of Sanity), which lives in theft_matters. The card classification stays
    # split (battlefield control change vs play-what-you-don't-own); only the COMMANDER
    # cross-opens both sibling lanes. ADR-0027 β: gain_control migrated to the Card IR
    # (the gated cat=='gain_control' arm), so it now fires from the hybrid IR path, and
    # the facade re-opens the theft_matters sibling against the merged key set. Real
    # oracle; the IR mirrors phase's ETB gain_control Effect.
    silumgar = {
        "name": "Dragonlord Silumgar",
        "type_line": "Legendary Creature — Elder Dragon",
        "oracle_text": (
            "Flying, deathtouch\nWhen Dragonlord Silumgar enters, gain control of "
            "target creature or planeswalker for as long as you control Dragonlord "
            "Silumgar."
        ),
    }
    silumgar_ir = _ir_with(
        Ability(
            kind="triggered",
            effects=(
                Effect(
                    category="gain_control",
                    scope="you",
                    subject=Filter(card_types=("Creature", "Planeswalker")),
                    raw="gain control of target creature or planeswalker",
                ),
            ),
        )
    )
    ks = _ks_hybrid_ir(silumgar, silumgar_ir)
    assert ("gain_control", "you") in ks
    assert ("theft_matters", "opponents") in ks
    # Over-fire guard: a commander with no steal/theft text opens neither.
    plain = {
        "name": "Plain Beater",
        "type_line": "Legendary Creature — Bear",
        "oracle_text": "Trample\nWhenever this creature attacks, it gets +1/+1.",
    }
    assert ("theft_matters", "opponents") not in _ks_hybrid(plain)


def test_player_burn_source_opens_direct_damage():
    # A commander that deals N/X damage to a PLAYER/opponent as a source (Syr Konrad,
    # Mogis, Go-Shintai) is a burn deck — it wants burn payoffs and damage doublers
    # (served by direct_damage). The damage_to_opp lane keys on a "whenever ~ deals
    # combat damage" TRIGGER, so these source-burners opened no damage lane. Real oracle.
    syr_konrad = {
        "name": "Syr Konrad, the Grim",
        "type_line": "Legendary Creature — Human Knight",
        "oracle_text": (
            "Whenever another creature dies, or a creature card is put into a graveyard "
            "from anywhere other than the battlefield, or a creature card leaves your "
            "graveyard, Syr Konrad, the Grim deals 1 damage to each opponent.\n"
            "{1}{B}: Each player mills a card."
        ),
    }
    mogis = {
        "name": "Mogis, God of Slaughter",
        "type_line": "Legendary Enchantment Creature — God",
        "oracle_text": (
            "Indestructible\nAs long as your devotion to black and red is less than "
            "seven, Mogis isn't a creature.\nAt the beginning of each opponent's "
            "upkeep, Mogis deals 2 damage to that player unless they sacrifice a "
            "creature of their choice."
        ),
    }
    go_shintai = {
        "name": "Go-Shintai of Ancient Wars",
        "type_line": "Legendary Enchantment Creature — Shrine",
        "oracle_text": (
            "First strike\nAt the beginning of your end step, you may pay {1}. When you "
            "do, Go-Shintai of Ancient Wars deals X damage to target player or "
            "planeswalker, where X is the number of Shrines you control."
        ),
    }
    assert ("direct_damage", "you") in _ks(syr_konrad)
    assert ("direct_damage", "you") in _ks(mogis)
    assert ("direct_damage", "you") in _ks(go_shintai)
    # Over-fire guard: a commander that deals no damage at all does not open the lane.
    healer = {
        "name": "Healer Commander",
        "type_line": "Legendary Creature — Cleric",
        "oracle_text": "Whenever you gain life, draw a card.",
    }
    assert ("direct_damage", "you") not in _ks(healer)


def test_donate_via_that_player_opens_donate():
    # Blim gives his own permanents to opponents ("that player gains control of target
    # permanent you control") — a donate commander wanting donate enablers (Harmless
    # Offering, Bazaar Trader). ADR-0027: donate migrated to the IR — a `gain_control`
    # effect whose raw names an another-player RECIPIENT (phase drops the recipient to
    # scope='any', so the lane reads the effect raw). Real oracle.
    blim = {
        "name": "Blim, Comedic Genius",
        "type_line": "Legendary Creature — Zombie Spirit",
        "oracle_text": (
            "Flying\nWhenever Blim deals combat damage to a player, that player gains "
            "control of target permanent you control. Then each player loses life and "
            "discards cards equal to the number of permanents they control."
        ),
    }
    blim_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="gain_control",
                                scope="any",
                                subject=Filter(
                                    card_types=("Permanent",), controller="you"
                                ),
                                raw="that player gains control of target permanent you control",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    blim_keys = {(s.key, s.scope) for s in extract_signals_hybrid(blim, blim_ir)}
    assert ("donate_matters", "you") in blim_keys
    # Over-fire guard: a commander where YOU gain control (the opposite of donate — its
    # raw names no other-player recipient) does not open the donate lane.
    silumgar = {
        "name": "Dragonlord Silumgar",
        "type_line": "Legendary Creature — Elder Dragon",
        "oracle_text": (
            "Flying, deathtouch\nWhen Dragonlord Silumgar enters, gain control of "
            "target creature or planeswalker for as long as you control Silumgar."
        ),
    }
    silumgar_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="gain_control",
                                scope="you",
                                subject=Filter(card_types=("Creature", "Planeswalker")),
                                raw="gain control of target creature or planeswalker",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    donate_keys = {
        (s.key, s.scope) for s in extract_signals_hybrid(silumgar, silumgar_ir)
    }
    assert ("donate_matters", "you") not in donate_keys


def test_dont_own_payoff_opens_theft_and_gain_control():
    # A theft-PAYOFF commander that rewards permanents "you control but DON'T OWN"
    # (Don Andres, Arvinox) is built on stealing — it wants the whole theft package
    # (battlefield steals AND borrow-and-cast). Open both sibling lanes. Real oracle.
    don_andres = {
        "name": "Don Andres, the Renegade",
        "type_line": "Legendary Creature — Vampire Pirate",
        "oracle_text": (
            "Each creature you control but don't own gets +2/+2, has menace and "
            "deathtouch, and is a Pirate in addition to its other types.\nWhenever you "
            "gain control of one or more permanents you don't own, draw a card."
        ),
    }
    arvinox = {
        "name": "Arvinox, the Mind Flail",
        "type_line": "Legendary Artifact Creature — Phyrexian Horror",
        "oracle_text": (
            "Arvinox isn't a creature unless you control three or more permanents you "
            "don't own.\nAt the beginning of your end step, exile the bottom card of "
            "each opponent's library face down."
        ),
    }
    # Gonti, Canny Acquisitor: "Spells you cast but don't own ..." — the intervening
    # verb ("cast") must not slip past the don't-own detector.
    gonti_canny = {
        "name": "Gonti, Canny Acquisitor",
        "type_line": "Legendary Creature — Aetherborn Rogue",
        "oracle_text": (
            "Spells you cast but don't own cost {1} less to cast.\nWhenever one or more "
            "creatures you control deal combat damage to a player, exile the top card "
            "of that player's library face down. You may look at and play that card."
        ),
    }
    for cmd in (don_andres, arvinox, gonti_canny):
        ks = _ks(cmd)
        assert ("theft_matters", "opponents") in ks, cmd["name"]
        assert ("gain_control", "you") in ks, cmd["name"]
    # Over-fire guard: a plain commander opens neither.
    plain = {
        "name": "Plain Beater",
        "type_line": "Legendary Creature — Bear",
        "oracle_text": "Trample",
    }
    assert ("theft_matters", "opponents") not in _ks(plain)


def test_baseline_creature_etb_unchanged():
    # ADR-0027 β: creature_etb migrated to the Card IR (a byte-identical kept-mirror),
    # so it serves from the hybrid path, not pure regex.
    c = {
        "name": "ETB",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert ("creature_etb", "you") in _ks_hybrid(c)


# --- Phase B: confidence flag + nested-scope / self-reference resolvers ---------


def _by_key(card, key):
    return next(s for s in extract_signals(card) if s.key == key)


def test_confidence_defaults_high():
    c = {
        "name": "ETB",
        "oracle_text": "Whenever a creature you control enters, draw a card.",
    }
    assert all(s.confidence == "high" for s in extract_signals(c))


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
    c = {
        "name": "The Scorpion God",
        "oracle_text": "Whenever a creature with a -1/-1 counter on it dies, draw a card.\n{1}{B}{R}: Put a -1/-1 counter on another target creature.\nWhen The Scorpion God dies, return it to its owner's hand at the beginning of the next end step.",
    }
    s = next(
        s for s in extract_signals_hybrid(c, _bare_ir()) if s.key == "death_matters"
    )
    assert s.scope == "any"  # not a spurious self-ref flip to "you"


def test_broad_possessive_scope_is_opponents_low_confidence():
    # Non-combat "that player's graveyard" → opponents, but LOW confidence (the
    # broad rule turned on behind the flag; not trusted blindly).
    c = {
        "name": "Graverobber",
        "oracle_text": "Exile target creature card from that player's graveyard.",
    }
    gy = [s for s in extract_signals(c) if s.key == "graveyard_matters"]
    assert gy
    assert gy[0].scope == "opponents"
    assert gy[0].confidence == "low"


def test_narrow_tinybones_rule_is_high_confidence():
    c = {
        "name": "Tinybones, the Pickpocket",
        "oracle_text": (
            "Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell."
        ),
    }
    s = _by_key(c, "graveyard_matters")
    assert s.scope == "opponents"
    assert s.confidence == "high"


def test_granted_ability_marks_signal_low_confidence():
    # A baseline signal pulled from a GRANTED ability (have "...") is scope-uncertain
    # (outer "you control" vs inner effect), so it is marked low confidence. ADR-0027:
    # attack_matters migrated, so `_resolve_scope` (still used by `_attack_matters_is_plan`
    # and every surviving baseline detector) is exercised directly here.
    clause = 'Creatures you control have "Whenever this creature attacks, draw a card."'
    _, conf = _resolve_scope(clause, clause.lower(), _scope(clause.lower()), "Grantor")
    assert conf == "low"


def test_coverage_gate_flags_low_confidence_only():
    # Only signal is a broad-possessive graveyard guess (no other detectable axis).
    c = {
        "name": "Graverobber",
        "oracle_text": "You may play cards from that player's graveyard.",
    }
    sigs = extract_signals(c)
    assert sigs
    assert all(s.confidence == "low" for s in sigs)
    needs, reason = coverage_gate(c, sigs)
    assert needs is True
    assert reason == "low_confidence"


def test_populate_opens_token_copy_matters():
    # Populate (CR 702.95) IS "create a token that's a copy of a creature token you
    # control" — a token-copy mechanic — so a populate commander opens token_copy_matters
    # (the serve already credited populate; the detector missed the keyword).
    ghired = {
        "name": "Ghired, Conclave Exile",
        "type_line": "Legendary Creature — Human Shaman",
        "oracle_text": (
            "When Ghired enters, create a 4/4 green Rhino creature token with "
            "trample.\nWhenever Ghired attacks, populate. The token enters tapped "
            "and attacking. (To populate, create a token that's a copy of a creature "
            "token you control.)"
        ),
    }
    trostani = {
        "name": "Trostani, Selesnya's Voice",
        "type_line": "Legendary Creature — Dryad",
        "oracle_text": (
            "Whenever another creature you control enters, you gain life equal to "
            "that creature's toughness.\n"
            "{1}{G}{W}, {T}: Populate. (Create a token that's a copy of a creature "
            "token you control.)"
        ),
    }
    # ADR-0027 β: token_copy_matters serves from the hybrid path (the kept-mirror fires
    # on the reminder-STRIPPED oracle, where `Populate.` survives outside the parens).
    assert "token_copy_matters" in _keys_hybrid(ghired)
    assert "token_copy_matters" in _keys_hybrid(trostani)


def test_self_death_payoff_opens_for_own_death_trigger():
    # A commander whose OWN "when ~ dies, <value>" is the engine opens self_death_payoff
    # (distinct from aristocrats death_matters — that keys on ANY creature dying). Real
    # cards, full oracle text.
    kokusho = {
        "name": "Kokusho, the Evening Star",
        "type_line": "Legendary Creature — Dragon Spirit",
        "oracle_text": (
            "Flying\n"
            "When Kokusho dies, each opponent loses 5 life. You gain life equal to "
            "the life lost this way."
        ),
    }
    junji = {
        "name": "Junji, the Midnight Sky",
        "type_line": "Legendary Creature — Dragon Spirit",
        "oracle_text": (
            "Flying, menace\n"
            "When Junji dies, choose one —\n"
            "• Each opponent discards two cards and loses 2 life.\n"
            "• Put target non-Dragon creature card from a graveyard onto the "
            "battlefield under your control. You lose 2 life."
        ),
    }
    # ADR-0027: self_death_payoff migrated to the Card IR; a commander's OWN "when ~
    # dies, <value>" self-death engine rides the name-aware kept mirror on the hybrid
    # path (and the structural SelfRef `dies` arm when the IR carries the trigger).
    assert "self_death_payoff" in _keys_hybrid(kokusho)
    assert "self_death_payoff" in _keys_hybrid(junji)
    # Over-fire guard: aristocrats (OTHER creatures dying) is NOT a self-death payoff.
    blood_artist = {
        "name": "Blood Artist",
        "type_line": "Creature — Vampire",
        "oracle_text": (
            "Whenever Blood Artist or another creature dies, target player loses 1 "
            "life and you gain 1 life."
        ),
    }
    assert "self_death_payoff" not in _keys_hybrid(blood_artist)


def test_creature_etb_opens_on_delayed_had_enter_payoff():
    # Ephara rewards creatures entering via a DELAYED check ("at the beginning of
    # upkeep, if you had a creature enter ... last turn, draw") — no "when/whenever"
    # trigger word, so the ETB detector's trigger-word gate missed it. It's an
    # ETB-payoff commander (wants ETB creatures / blink / token makers).
    # ADR-0027 β: this delayed "if you had a creature enter" payoff is exactly why
    # creature_etb rides a kept-mirror, not the structural etb-trigger arm — phase
    # models it as an upkeep trigger (no `etb` event), so it serves from the hybrid.
    ephara = {
        "name": "Ephara, God of the Polis",
        "type_line": "Legendary Enchantment Creature — God",
        "oracle_text": (
            "Indestructible\n"
            "As long as your devotion to white and blue is less than seven, Ephara "
            "isn't a creature.\n"
            "At the beginning of each upkeep, if you had another creature enter the "
            "battlefield under your control last turn, draw a card."
        ),
    }
    assert "creature_etb" in _keys_hybrid(ephara)


def test_artifacts_matter_opens_for_artifact_tutor():
    # Arcum Dagsson tutors artifacts ("search ... for a noncreature artifact card, put
    # it onto the battlefield") and sacs artifact creatures — an artifact commander —
    # but the detector wanted the "artifacts you control" possessive, so it missed him.
    # artifacts_matter already serves artifacts by type, so opening it covers his fodder.
    arcum = {
        "name": "Arcum Dagsson",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "{T}: Target artifact creature's controller sacrifices it. That player "
            "may search their library for a noncreature artifact card, put it onto "
            "the battlefield, then shuffle."
        ),
    }
    # ADR-0027: artifacts_matter migrated to the Card IR — the "search … for a
    # noncreature artifact card" tutor rides the kept oracle mirror on the hybrid path.
    assert "artifacts_matter" in _keys_hybrid(arcum)
    # Over-fire guard: a generic creature-tutor is not an artifact commander.
    diabolic_tutor = {
        "name": "Tutor Test",
        "type_line": "Legendary Creature — Wizard",
        "oracle_text": "When this creature enters, search your library for a creature card, reveal it, put it into your hand, then shuffle.",
    }
    assert "artifacts_matter" not in _keys_hybrid(diabolic_tutor)


def test_creature_recursion_opens_and_self_sac_creatures_serve_it():
    # Creature-recursion commanders (return/put a creature card from your graveyard:
    # Hua Tuo, Adun, Othelm) loop SELF-SACRIFICING creatures — the sac is the
    # activation (repeatable value) AND fuels the graveyard for re-recursion, no
    # separate outlet needed (Spore Frog). Real cards, full oracle.
    # ADR-0027: creature_recursion is IR-served (MIGRATED_KEYS); Hua Tuo's GY→library
    # recursion rides the byte-identical _CREATURE_RECURSION_MIRROR (which scans the
    # oracle text), so it surfaces on the hybrid path with any non-None IR.
    hua_tuo = {
        "name": "Hua Tuo, Honored Physician",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": (
            "{T}: Put target creature card from your graveyard on top of your "
            "library. Activate only during your turn, before attackers are declared."
        ),
    }
    assert "creature_recursion" in _keys_hybrid(hua_tuo)
    # Serve: self-sacrificing creatures are the loop fuel.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    # A self-ETB-value commander wants blink + ETB-trigger doublers (Panharmonicon).
    # The detector used "\bwhen " (missing "WHENEVER ~ enters" — Roxanne) and "enters"
    # (missing plural "enter"). Real card, full oracle.
    roxanne = {
        "name": "Roxanne, Starfall Savant",
        "type_line": "Legendary Creature — Cat Druid",
        "oracle_text": (
            "Whenever Roxanne enters or attacks, create a tapped colorless artifact "
            'token named Meteorite with "When this token enters, it deals 2 damage '
            'to any target" and "{T}: Add one mana of any color."\n'
            "Whenever you tap an artifact token for mana, add one mana of any type "
            "that artifact token produced."
        ),
    }
    assert "blink_flicker" in _keys(roxanne)


def test_self_etb_value_resolves_short_name_not_just_first_token():
    # The self-reference in oracle is the name BEFORE the comma (the short name), which
    # may be hyphenated, two-named, or multi-word — not the bare first token. The
    # detector keyed only on the first token immediately before "enters", so
    # "When Spider-Byte enters" / "When Donnie & April enter" / "When Black Cat enters"
    # all missed (the first token is followed by more name, not " enters"). A self-ETB
    # commander wants blink + ETB-trigger doublers (Panharmonicon). Real cards.
    spider_byte = {
        "name": "Spider-Byte, Web Warden",
        "type_line": "Legendary Creature — Spider",
        "oracle_text": (
            "When Spider-Byte enters, return up to one target nonland permanent to "
            "its owner's hand."
        ),
    }
    donnie_april = {
        "name": "Donnie & April, Adorkable Duo",
        "type_line": "Legendary Creature — Mutant Turtle",
        "oracle_text": (
            "When Donnie & April enter, choose one or both. Each mode must target a "
            "different player.\n• Target player draws two cards.\n• Target player "
            "returns an artifact, instant, or sorcery card from their graveyard to "
            "their hand."
        ),
    }
    black_cat = {
        "name": "Black Cat, Cunning Thief",
        "type_line": "Legendary Creature — Cat",
        "oracle_text": (
            "When Black Cat enters, look at the top nine cards of target opponent's "
            "library, exile two of them face down, then put the rest on the bottom of "
            "their library in a random order."
        ),
    }
    assert "blink_flicker" in _keys(spider_byte)
    assert "blink_flicker" in _keys(donnie_april)
    assert "blink_flicker" in _keys(black_cat)


def test_self_dies_value_resolves_short_name_for_clone():
    # A high-CMC commander with a self DIES trigger is worth cloning — a token copy
    # re-fires the trigger when the copy dies. The clone detector keyed on the first
    # name token before "dies", so "When The Scarab God dies" missed ("The" is an
    # article, "Scarab" is followed by " God", not " dies"). Real cards, cmc>=5, no ETB
    # (so the clone signal comes from the DIES path, not the ETB path).
    scarab = {
        "name": "The Scarab God",
        "type_line": "Legendary Creature — God",
        "cmc": 5.0,
        "oracle_text": (
            "At the beginning of your upkeep, each opponent loses X life and you scry "
            "X, where X is the number of Zombies you control.\n"
            "{2}{U}{B}: Exile target creature card from a graveyard. Create a token "
            "that's a copy of it, except it's a 4/4 black Zombie.\n"
            "When The Scarab God dies, return it to its owner's hand at the beginning "
            "of the next end step."
        ),
    }
    locust = {
        "name": "The Locust God",
        "type_line": "Legendary Creature — God",
        "cmc": 6.0,
        "oracle_text": (
            "Flying\nWhenever you draw a card, create a 1/1 blue and red Insect "
            "creature token with flying and haste.\n{2}{U}{R}: Draw a card, then "
            "discard a card.\nWhen The Locust God dies, return it to its owner's hand "
            "at the beginning of the next end step."
        ),
    }
    assert "clone_matters" in _keys(scarab)
    assert "clone_matters" in _keys(locust)


def test_self_counter_accumulator_opens_counters_matter():
    # A commander that puts +1/+1 counters on ITSELF and cares about its COUNT
    # (Sab-Sunen — "number of counters on it") is a +1/+1-counters commander; it should
    # open counters_matter (counter sources/proliferate). The 2-condition check
    # (accumulates AND cares about count) excludes incidental self-counter creatures
    # (Thraximundar gets a counter but doesn't care about the count).
    sab_sunen = {
        "name": "Sab-Sunen, Luxa Embodied",
        "type_line": "Legendary Creature — God",
        "oracle_text": (
            "Reach, trample, indestructible\n"
            "Sab-Sunen can't attack or block unless it has an even number of counters "
            "on it. (Zero is even.)\n"
            "At the beginning of your first main phase, put a +1/+1 counter on "
            "Sab-Sunen. Then if it has an odd number of counters on it, draw two cards."
        ),
    }
    # ADR-0027: counters_matter migrated to the IR and now fires on ANY +1/+1
    # PLACEMENT (CR 122.1 / 122.6) — even a bare self-accumulator is a source. Assert
    # via the hybrid path; the old "must also care about the count" precision guard is
    # superseded by the broadened lane (the IR fires on the place_counter alone).
    place_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="place_counter",
                                scope="you",
                                counter_kind="p1p1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "counters_matter" in _keys_hybrid_ir(sab_sunen, place_ir)


def test_board_wide_counter_placement_opens_counters_matter():
    # Board-wide "+1/+1 counter on each <group>" placement is a counters ENGINE —
    # the commander repeatedly spreads counters across a board, so it wants counter
    # payoffs (proliferate, doublers, counter-matters creatures). The detector keyed
    # only on the exact phrase "on each creature you control", missing every other
    # group: "on each attacking creature", "on each <tribe> you control", "on each
    # of up to N target creatures", "on each other/legendary/artifact creature".
    # Generalize to the placement clause itself: "+1/+1 counter on each".
    # ADR-0027: counters_matter migrated to the IR — every board-wide +1/+1 placement
    # projects a place_counter(p1p1). Assert via the hybrid path. (The broadened lane
    # also opens on a bare self-growth placement — a placement is a source whoever
    # receives it — so the old "self-grower stays out" precision guard is dropped.)
    place_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="place_counter",
                                scope="you",
                                counter_kind="p1p1",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    drana = {
        "name": "Drana, Liberator of Malakir",
        "type_line": "Legendary Creature — Vampire Ally",
        "oracle_text": (
            "Flying, first strike\n"
            "Whenever Drana deals combat damage to a player, put a +1/+1 counter on "
            "each attacking creature you control."
        ),
    }
    assert "counters_matter" in _keys_hybrid_ir(drana, place_ir)
    # Activated board-wide placer (Steel Overseer-style) — same lane.
    overseer = {
        "name": "Steel Overseer",
        "type_line": "Artifact Creature — Construct",
        "oracle_text": "{T}: Put a +1/+1 counter on each artifact creature you control.",
    }
    assert "counters_matter" in _keys_hybrid_ir(overseer, place_ir)


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
    # ADR-0027 β: combat_damage_to_creature migrated to the Card IR, so it is served
    # from the hybrid (IR) path; the voltron self-pump override still opens voltron.
    mirri = {
        "name": "Mirri the Cursed",
        "type_line": "Legendary Creature — Vampire Cat",
        "power": "3",
        "oracle_text": (
            "Flying, first strike, haste\n"
            "Whenever Mirri deals combat damage to a creature, put a +1/+1 counter on "
            "Mirri."
        ),
    }
    mk = {s.key for s in extract_signals_hybrid(mirri, _bare_ir())}
    assert "voltron_matters" in mk
    assert "combat_damage_to_creature" in mk  # both — the override no longer suppresses
    # (C) Sram rewards casting Auras & Equipment (comma-list phrasing).
    sram = {
        "name": "Sram, Senior Edificer",
        "type_line": "Legendary Creature — Dwarf Advisor",
        "power": "2",
        "oracle_text": "Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.",
    }
    assert "voltron_matters" in {
        s.key for s in extract_signals(sram, include_membership=True)
    }
    # (F) Tromokratis (Kraken, 8/8) is self-unblockable — a fat evasive body.
    tromokratis = {
        "name": "Tromokratis",
        "type_line": "Legendary Creature — Kraken",
        "power": "8",
        "oracle_text": (
            "Tromokratis has hexproof unless it's attacking or blocking.\n"
            "Tromokratis can't be blocked unless all creatures defending player "
            "controls block it."
        ),
    }
    assert "voltron_matters" in {
        s.key for s in extract_signals(tromokratis, include_membership=True)
    }
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
    # self-protection is a resilient-beater tell — neither is a non-voltron PLAN, so a
    # commander whose ONLY signal is one of these reads as the vanilla voltron body it is
    # (Wilson is a trampling bear to suit up; Thrun is an indestructible beater). A REAL
    # engine still suppresses the fallback. Real oracle, full text.
    wilson = {
        "name": "Wilson, Refined Grizzly",
        "type_line": "Legendary Creature — Bear Warrior",
        "power": "4",
        "oracle_text": (
            "This spell can't be countered.\n"
            "Vigilance, reach, trample\n"
            "Ward {2} (Whenever this creature becomes the target of a spell or ability "
            "an opponent controls, counter it unless that player pays {2}.)\n"
            "Choose a Background (You can have a Background as a second commander.)"
        ),
    }
    thrun = {
        "name": "Thrun, Breaker of Silence",
        "type_line": "Legendary Creature — Troll Shaman",
        "power": "5",
        "oracle_text": (
            "This spell can't be countered.\n"
            "Trample\n"
            "Thrun can't be the target of nongreen spells your opponents control or "
            "abilities from nongreen sources your opponents control.\n"
            "During your turn, Thrun has indestructible."
        ),
    }
    assert "voltron_matters" in {
        s.key for s in extract_signals(wilson, include_membership=True)
    }
    assert "voltron_matters" in {
        s.key for s in extract_signals(thrun, include_membership=True)
    }
    # Over-fire guard: a real ENGINE (here a spellslinger draw engine) IS a non-voltron
    # plan — it suppresses the fallback even on an evasive power-2 body with no voltron
    # override match.
    spellslinger = {
        "name": "Generic Spellslinger",
        "type_line": "Legendary Creature — Human Wizard",
        "power": "2",
        "oracle_text": (
            "Flying\nWhenever you cast an instant or sorcery spell, draw a card."
        ),
    }
    assert "voltron_matters" not in {
        s.key for s in extract_signals(spellslinger, include_membership=True)
    }


def test_sea_monster_tribal_group_covers_all_four_types():
    # The sea-monster types (Kraken/Leviathan/Octopus/Serpent) share one tribal identity
    # — no card rewards any member alone (Quest for Ula's Temple / Whelming Wave / Slinn
    # Voda always name all four). So a commander of one type (Lorthos = Octopus) must
    # cover the whole group + the group-naming payoffs. Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    lorthos = {
        "name": "Lorthos, the Tidemaker",
        "type_line": "Legendary Creature — Octopus",
        "oracle_text": (
            "Whenever Lorthos attacks, you may pay {8}. If you do, tap up to eight "
            "target permanents. Those permanents don't untap during their controllers' "
            "next untap steps."
        ),
    }
    octo_sig = next(
        s
        for s in extract_signals(lorthos, include_membership=True)
        if s.key == "type_matters" and s.subject.lower() == "octopus"
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
    # Over-fire guard: a STANDALONE tribe (Goblin) must NOT pick up a sea monster — the
    # group only applies to the four no-solo-identity types.
    from mtg_utils._deck_forge.signals import Signal

    gob = spec_for(
        Signal(key="type_matters", scope="you", subject="Goblin", text="", source="")
    )
    assert gob.serve.matches(tromokratis) is False
    assert not any(
        (ex.serve or serve_from_dict(ex.search)).matches(tromokratis)
        for ex in gob.extras
    )


def test_kazuul_defending_player_opens_goad_and_force_attack_serves():
    # Kazuul rewards opponents attacking YOU ("whenever a creature an opponent controls
    # attacks ... you're the defending player, create an Ogre"), so it wants force-attack
    # / goad to feed the trigger — but its phrasing matched no goad detector. Open
    # goad_matters, and the lane's force-attack sub-avenue covers the force-ALL-attack
    # cards (which carry no "goad" keyword). Real oracle, full text.
    kazuul = {
        "name": "Kazuul, Tyrant of the Cliffs",
        "type_line": "Legendary Creature — Ogre Warrior",
        "oracle_text": (
            "Whenever a creature an opponent controls attacks, if you're the defending "
            "player, create a 3/3 red Ogre creature token unless that creature's "
            "controller pays {3}."
        ),
    }
    # ADR-0027: goad_matters migrated to the IR — the regex path no longer emits it;
    # the hybrid path serves it from the _GOAD_REWARD_REF defending-player marker
    # (mirrored as a goad_all effect).
    assert "goad_matters" not in _keys(kazuul)
    kazuul_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="triggered",
                        effects=(
                            Effect(
                                category="goad_all",
                                scope="opp",
                                raw="creature an opponent controls attacks ... "
                                "you're the defending player",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "goad_matters" in _keys_hybrid_ir(kazuul, kazuul_ir)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    assert lane_covers(diplomats, "goad_matters", "opponents") is True
    assert lane_covers(warstoll, "goad_matters", "opponents") is True
    # Over-fire guard: a SELF forced-attack drawback (Juggernaut) is an aggressive beater,
    # not a force-the-table effect — the plural/symmetric anchors must keep it out.
    juggernaut = {
        "name": "Juggernaut",
        "type_line": "Artifact Creature — Juggernaut",
        "oracle_text": (
            "This creature attacks each combat if able.\n"
            "This creature can't be blocked by Walls."
        ),
    }
    assert lane_covers(juggernaut, "goad_matters", "opponents") is False


def test_low_power_matters_opens_and_serves():
    # Subira rewards "creature you control with power 2 or less"; the lane surfaces the
    # small-creature payoffs (Raid Bombardment, Delney, Arabella). Anchored on "you
    # control with power N or less" so removal and the vanilla power<=2 pool stay out.
    # Real oracle, full text.
    # ADR-0027: low_power_matters migrated to the Card IR — phase drops the power
    # threshold on Subira's buff/etb subject, recovered by a `_LOW_POWER_REF` marker
    # rebuilding the Power:LE Creature subject, read through the hybrid IR path. The
    # serve pool stays oracle-defined (the hand spec).
    subira = {
        "name": "Subira, Tulzidi Caravanner",
        "type_line": "Legendary Creature — Human Shaman",
        "oracle_text": (
            "Haste\n"
            "{1}: Another target creature with power 2 or less can't be blocked this "
            "turn.\n"
            "{1}{R}, {T}, Discard your hand: Until end of turn, whenever a creature you "
            "control with power 2 or less deals combat damage to a player, draw a card."
        ),
    }
    subira_ir = Card(
        oracle_id="x",
        name="Subira, Tulzidi Caravanner",
        faces=(
            Face(
                name="Subira, Tulzidi Caravanner",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="tap",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature",),
                                    controller="you",
                                    predicates=("PtComparison:Power:LE:2",),
                                ),
                                raw="creature you control with power 2 or less",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("low_power_matters", "you") in _ks_hybrid_card(subira, subira_ir)
    assert "low_power_matters" not in _keys(subira)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    assert "low_power_matters" not in _keys(removal)
    assert lane_covers(removal, "low_power_matters") is False
    # Over-fire guard 2: a vanilla small body is not on-theme fodder (no power_max serve).
    bears = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "oracle_text": "",
    }
    assert lane_covers(bears, "low_power_matters") is False


def test_tribal_support_without_you_control_opens_type_matters():
    # A tribal-SUPPORT commander whose tribe reference isn't "Xs you control" — it buffs
    # "target <Type>", tutors "a <Type> card", wraths "destroy all non-<Type>", or
    # cost-reduces "<Type> spells" — is still that tribe's commander. Real oracle.
    def subs(card):
        return {
            s.subject
            for s in extract_signals(card, include_membership=True)
            if s.key == "type_matters"
        }

    owen = {
        "name": "Owen Grady, Raptor Trainer",
        "type_line": "Legendary Creature — Human Soldier Scientist",
        "oracle_text": (
            "Partner with Blue, Loyal Raptor\n"
            "{T}: Put your choice of a menace, trample, reach, or haste counter on "
            "target Dinosaur. Activate only as a sorcery."
        ),
    }
    sivitri = {
        "name": "Sivitri, Dragon Master",
        "type_line": "Legendary Planeswalker — Sivitri",
        "oracle_text": (
            "−3: Search your library for a Dragon card, reveal it, put it into your "
            "hand, then shuffle.\n"
            "−7: Destroy all non-Dragon creatures.\n"
            "Sivitri, Dragon Master can be your commander."
        ),
    }
    nogi = {
        "name": "Nogi, Draco-Zealot",
        "type_line": "Legendary Creature — Kobold Shaman",
        "oracle_text": (
            "Dragon spells you cast cost {1} less to cast.\n"
            "Whenever Nogi attacks, if you control three or more Dragons, until end of "
            "turn, Nogi becomes a Dragon with base power and toughness 5/5 and gains "
            "flying."
        ),
    }
    assert "Dinosaur" in subs(owen)
    assert "Dragon" in subs(sivitri)  # tutor + wrath
    assert "Dragon" in subs(nogi)  # cost reducer
    # Over-fire guard: "non-<Type>" in a DRAWBACK ("sacrifice all non-Ogre creatures",
    # Yukora) is NOT tribal support — only "destroy ALL non-<Type>" wraths around your
    # own tribe.
    yukora = {
        "name": "Yukora, the Prisoner",
        "type_line": "Legendary Creature — Demon Spirit",
        "oracle_text": (
            "When Yukora leaves the battlefield, sacrifice all non-Ogre creatures you "
            "control."
        ),
    }
    assert "Ogre" not in subs(yukora)  # "sacrifice all non-Ogre" drawback != tribal


def test_mutagen_token_maker_opens_artifacts_matter():
    # Mutagen (TMNT) is a resource ARTIFACT token (sac for a +1/+1 counter, like
    # Food/Clue), so a Mutagen maker is an artifact deck — but "mutagen" was missing
    # from the artifact-token-maker vocabulary, so April O'Neil (makes a Mutagen every
    # spell) and the Mutant commanders opened no artifact lane. Real oracle.
    april = {
        "name": "April O'Neil, Human Element",
        "type_line": "Legendary Creature — Human Detective",
        "oracle_text": (
            "Whenever a player casts an artifact, instant, or sorcery spell, you create "
            "a Mutagen token. (It's an artifact with \"{1}, {T}, Sacrifice this token: "
            'Put a +1/+1 counter on target creature. Activate only as a sorcery.")'
        ),
    }
    # ADR-0027: artifacts_matter migrated to the Card IR — the Mutagen artifact-token
    # maker rides the kept oracle mirror on the hybrid path.
    assert "artifacts_matter" in _keys_hybrid(april)
    # Over-fire guard: a "create a <subtype> artifact CREATURE token" go-wide maker is a
    # tokens deck, not an artifacts deck — the addition is resource-token-subtype-only,
    # never the bare parent word "artifact", so a Servo maker stays out.
    servo = {
        "name": "Generic Servo Maker",
        "type_line": "Creature — Artificer",
        "oracle_text": "{T}: Create a 1/1 colorless Servo artifact creature token.",
    }
    assert "artifacts_matter" not in _keys_hybrid(servo)


def test_gowide_package_creature_scoped_and_count_scaler_opens_it():
    # A creature-count-scaling commander (Leonardo "+1/+0 for each other creature you
    # control") is go-wide, so it opens tokens_matter; the lane's go-wide package serves
    # MASS creature-token makers (create 2+/X) and team protection. CREATURE-scoped: a
    # Treasure/Clue maker (non-creature tokens) does NOT widen the board and stays out.
    leonardo = {
        "name": "Leonardo, Big Brother",
        "type_line": "Legendary Creature — Mutant Ninja Turtle",
        "oracle_text": (
            "Sneak {W}\nLeonardo gets +1/+0 for each other creature you control."
        ),
    }
    # ADR-0027: tokens_matter migrated to the Card IR via a byte-identical kept-mirror
    # (the go-wide count-scaler arm), so assert against the hybrid path.
    assert "tokens_matter" in _keys_hybrid(leonardo)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    # Creature-scoping guard: a Treasure maker makes NON-creature tokens — it doesn't go
    # wide and must NOT be in the go-wide package.
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
    # A cost-reduction commander (Stenn makes its chosen type cost {1} less) wants to
    # STACK more category reducers to go off; the lane otherwise served only the bombs
    # that exploit the discount. The reducer sub-avenue serves "<your/type> spells cost
    # {N} less" (Cloud Key, Etherium Sculptor), excluding the self-only "this spell costs
    # {X} less" (Ghalta) and the cost-increase taxes. Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal
    from mtg_utils.card_ir import Ability, Card, Effect, Face, Filter

    stenn = {
        "name": "Stenn, Paranoid Partisan",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "As Stenn enters, choose a card type other than creature or land.\n"
            "Spells you cast of the chosen type cost {1} less to cast.\n"
            "{1}{W}{U}: Exile Stenn. Return it to the battlefield under its owner's "
            "control at the beginning of the next end step."
        ),
    }
    # ADR-0027 β: cost_reduction is IR-served — a static ModifyCost{Reduce} Effect with a
    # non-None spell_filter subject. The legacy regex path no longer emits it.
    stenn_ir = Card(
        oracle_id="x",
        name="Stenn, Paranoid Partisan",
        faces=(
            Face(
                name="Stenn, Paranoid Partisan",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="cost_reduction",
                                scope="you",
                                subject=Filter(card_types=("Card",)),
                                raw=(
                                    "Spells you cast of the chosen type cost "
                                    "{1} less to cast."
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert "cost_reduction" not in _keys(stenn)
    assert "cost_reduction" in {s.key for s in extract_signals_hybrid(stenn, stenn_ir)}

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
    # Over-fire guard (isolates the reducer extra): a SELF-only "this spell costs {2}
    # less" is not a stacking reducer — the plural "spells" anchor keeps it out. Use a
    # fixed cost so the main {X}/storm serve doesn't catch it for unrelated reasons.
    self_only = {
        "name": "Self Discounter",
        "type_line": "Creature — Beast",
        "oracle_text": "This spell costs {2} less to cast.",
    }
    assert lane_covers(self_only, "cost_reduction", "you") is False


def test_token_maker_serves_token_aristocrats_drain():
    # A token-flood commander (Endrek Sahr makes Thrulls) wants token-aristocrats drain
    # that fires on token CREATION (Mirkwood Bats) — it triggers just by going wide, no
    # sac outlet needed. Token-specific, so the generic "whenever a creature dies" Blood
    # Artist (served by the death lanes) does NOT match this sub-avenue. Real oracle.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for

    endrek = {
        "name": "Endrek Sahr, Master Breeder",
        "type_line": "Legendary Creature — Human Wizard",
        "oracle_text": (
            "Whenever you cast a creature spell, create X 1/1 black Thrull creature "
            "tokens, where X is that spell's mana value.\n"
            "When you control seven or more Thrulls, sacrifice Endrek Sahr, Master "
            "Breeder."
        ),
    }
    tm_sig = next(
        s
        for s in extract_signals(endrek, include_membership=True)
        if s.key == "token_maker"
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
    # Over-fire guard: generic "whenever a creature dies" drain is NOT token-specific —
    # it belongs to the death/aristocrats lanes, not this token sub-avenue.
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
    # Role tokens are Aura ENCHANTMENTS (CR), so a commander that makes them (Gylwain,
    # Ellivere) is an enchantment commander — it wants enchantment-count payoffs
    # (Sanctum Weaver) and Aura payoffs. The detector keyed on "enchantment"/"aura"
    # and missed the word "Role".
    gylwain = {
        "name": "Gylwain, Casting Director",
        "type_line": "Legendary Creature — Elf Druid",
        "oracle_text": (
            "Whenever Gylwain or another nontoken creature you control enters, "
            "choose one —\n"
            "• Create a Royal Role token attached to that creature.\n"
            "• Create a Sorcerer Role token attached to that creature.\n"
            "• Create a Monster Role token attached to that creature."
        ),
    }
    # ADR-0027: enchantments_matter migrated to the Card IR — Role tokens are Aura
    # enchantments (CR 303.7 / 111.10j), and the "create … Role token" maker rides the
    # kept oracle mirror on the hybrid path.
    assert "enchantments_matter" in _keys_hybrid(gylwain)
    # Over-fire guard: a plain creature-token maker is not an enchantment deck.
    krenko = {
        "name": "Token Maker",
        "type_line": "Legendary Creature — Goblin",
        "oracle_text": "{T}: Create a 1/1 red Goblin creature token.",
    }
    assert "enchantments_matter" not in _keys_hybrid(krenko)


def test_celebration_archetype_opens_and_serves():
    # Celebration (WOE ability word) keys on the exact phrase "two or more nonland
    # permanents entered the battlefield under your control this turn" — 11 cards share
    # it. A Celebration commander (Ash) wants the other Celebration payoffs; the
    # archetype is its own lane (the baseline saw only the bare attack trigger). Real
    # cards, full oracle.
    ash = {
        "name": "Ash, Party Crasher",
        "type_line": "Legendary Creature — Human Peasant",
        "oracle_text": (
            "Haste\n"
            "Celebration — Whenever Ash attacks, if two or more nonland permanents "
            "entered the battlefield under your control this turn, put a +1/+1 "
            "counter on Ash."
        ),
    }
    # ADR-0027: celebration_matters is IR-served from the kept word-detector mirror
    # (\bcelebration\b), so it comes through the hybrid path, not pure regex.
    assert "celebration_matters" in _keys_hybrid(ash)
    assert "celebration_matters" not in _keys(ash)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    assert "celebration_matters" not in _keys_hybrid(impact)
    assert lane_covers(impact, "celebration_matters") is False


def test_lands_matter_serves_creature_pump_by_basic():
    # A lands-matter commander whose own P/T scales with land count (Molimo) wants the
    # creature pump that scales the SAME way — "+N/+N for each Forest you control"
    # (Blanchwood Armor, Primal Bellow). The serve already takes "for each LAND you
    # control"; the per-basic-subtype form (the mono-color go-tall payoff) was the gap.
    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key):
        sp = spec_for(Signal(key=key, scope="you", subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    molimo = {
        "name": "Molimo, Maro-Sorcerer",
        "type_line": "Legendary Creature — Elemental Sorcerer",
        "oracle_text": (
            "Trample\n"
            "Molimo's power and toughness are each equal to the number of lands "
            "you control."
        ),
    }
    # ADR-0027: lands_matter migrated to the Card IR (the amount.subject=Land count
    # operand + a kept word mirror for the "number of lands you control" P/T phase
    # drops the operand for), so it is served via the hybrid path, not pure regex.
    assert "lands_matter" in _keys_hybrid(molimo)
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
    # ADR-0027: tapped_matters migrated to the Card IR — Masako's dropped "tapped
    # creatures you control" grant is recovered by a `_TAPPED_GRANT` marker (a tap
    # effect with a Tapped-creature subject), read through the hybrid IR path. The
    # serve pool stays oracle-defined (the hand spec). Distinct from tap_untap_matters
    # (becomes-tapped triggers) and convoke (taps UNtapped creatures as a cost).
    masako = {
        "name": "Masako the Humorless",
        "type_line": "Legendary Creature — Human Advisor",
        "oracle_text": (
            "Flash\n"
            "Tapped creatures you control can block as though they were untapped."
        ),
    }
    masako_ir = Card(
        oracle_id="x",
        name="Masako the Humorless",
        faces=(
            Face(
                name="Masako the Humorless",
                abilities=(
                    Ability(
                        kind="static",
                        effects=(
                            Effect(
                                category="tap",
                                scope="you",
                                subject=Filter(
                                    card_types=("Creature",),
                                    controller="you",
                                    predicates=("Tapped",),
                                ),
                                raw="tapped creatures you control can",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("tapped_matters", "you") in _ks_hybrid_card(masako, masako_ir)
    assert "tapped_matters" not in _keys(masako)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    assert "tapped_matters" not in _keys(devout)
    assert lane_covers(devout, "tapped_matters") is False


def test_tapped_threshold_and_count_open_and_serve():
    # The "if you control two or more tapped creatures, <payoff>" THRESHOLD (Sami and
    # the Edge of Eternities tap cluster) and the "for each tapped creature you control"
    # COUNT form are tapped-matters engines, but the detector/serve only keyed on
    # "number of tapped creatures" and the anthem form. Both detector and serve must
    # learn the threshold + count so Sami covers its cluster. Real cards, full oracle.
    sami = {
        "name": "Sami, Ship's Engineer",
        "type_line": "Legendary Creature — Human Artificer",
        "oracle_text": (
            "At the beginning of your end step, if you control two or more tapped "
            "creatures, create a tapped 2/2 colorless Robot artifact creature token."
        ),
    }
    # ADR-0027: the THRESHOLD-GATE form is read off the condition subject's Tapped
    # predicate through the hybrid IR path (the regex no longer produces it).
    sami_ir = Card(
        oracle_id="x",
        name="Sami, Ship's Engineer",
        faces=(
            Face(
                name="Sami, Ship's Engineer",
                abilities=(
                    Ability(
                        kind="triggered",
                        trigger=Trigger(event="end_step", scope="you"),
                        condition=Condition(
                            kind="quantitycomparison",
                            comparator="ge",
                            subject=Filter(
                                card_types=("Creature",),
                                controller="you",
                                predicates=("Tapped", "InZone"),
                            ),
                        ),
                        effects=(
                            Effect(
                                category="make_token",
                                scope="you",
                                raw="create a tapped 2/2 colorless Robot",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    assert ("tapped_matters", "you") in _ks_hybrid_card(sami, sami_ir)
    assert "tapped_matters" not in _keys(sami)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    # Over-fire guard: tapping UNtapped creatures as a cost stays out (the un- prefix
    # means "or more tapped" never matches "or more untapped").
    convoke = {
        "name": "Generic Convoker",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{2}, Tap four untapped creatures you control: Draw two cards.",
    }
    assert "tapped_matters" not in _keys(convoke)


def test_your_graveyard_scope_not_stolen_by_incidental_opponent_mention():
    # A self-graveyard engine that merely MENTIONS opponents elsewhere (Araumi's encore
    # tokens "attack that opponent"; the cost counts "the number of opponents you have")
    # cares about YOUR graveyard — it must open graveyard_matters/you so self-mill
    # enablers (scoped you) serve, not be mis-scoped opponents by the "opponent"-
    # anywhere rule. Real card, full oracle.
    araumi = {
        "name": "Araumi of the Dead Tide",
        "type_line": "Legendary Creature — Merfolk Wizard",
        "oracle_text": (
            "{T}, Exile cards from your graveyard equal to the number of opponents "
            "you have: Target creature card in your graveyard gains encore until end "
            "of turn. The encore cost is equal to its mana cost."
        ),
    }
    assert ("graveyard_matters", "you") in _ks(araumi)
    # Over-fire guard: a pure opponents'-graveyard-hate card (no "your graveyard", no
    # self-reference) stays opponents-scoped and does NOT acquire a "you" avenue — the
    # residual auto-scope is untouched by the fix.
    leyline = {
        "name": "Leyline of the Void",
        "type_line": "Enchantment",
        "oracle_text": (
            "If a card would be put into an opponent's graveyard from anywhere, "
            "exile it instead."
        ),
    }
    assert ("graveyard_matters", "opponents") in _ks(leyline)
    assert ("graveyard_matters", "you") not in _ks(leyline)


def test_multi_tribe_list_anthem_captures_every_named_type():
    # A menagerie anthem ("Other Spiders, Boars, ..., and Wolves you control get +1/+1")
    # lists many subtypes in one comma run — the multi-tribe head form ("creatures
    # that's a X, a Y") doesn't match it, and the single-tribe pattern grabbed only the
    # last type. Capture EVERY named subtype so each tribe's payoffs surface. Real card.
    spider_ham = {
        "name": "Spider-Ham, Peter Porker",
        "type_line": "Legendary Creature — Spider Boar Hero",
        "oracle_text": (
            "When Spider-Ham enters, create a Food token.\n"
            "Animal May-Ham — Other Spiders, Boars, Bats, Bears, Birds, Cats, Dogs, "
            "Frogs, Jackals, Lizards, Mice, Otters, Rabbits, Raccoons, Rats, "
            "Squirrels, Turtles, and Wolves you control get +1/+1."
        ),
    }
    subs = {subj for (key, scope, subj) in _ksub(spider_ham) if key == "type_matters"}
    for t in ("Frog", "Squirrel", "Rabbit", "Raccoon", "Cat", "Bird"):
        assert t in subs, t
    # Over-fire guard: a plain anthem names no subtype, so no spurious tribe.
    glorious = {
        "name": "Glorious Anthem",
        "type_line": "Enchantment",
        "oracle_text": "Creatures you control get +1/+1.",
    }
    glory_subs = {
        subj for (key, scope, subj) in _ksub(glorious) if key == "type_matters"
    }
    assert glory_subs == set()


def test_divinity_indestructible_counter_wants_proliferate():
    # A permanent that "enters with a divinity/indestructible counter" (the Myojin
    # cycle, Arwen) has exactly ONE beneficial counter that gates indestructibility or
    # fuels a remove-a-counter ability — proliferate multiplies it. Unlike COUNTDOWN
    # counters (slumber, egg) you want to REMOVE, divinity/indestructible are always
    # good to multiply, so the lane is precise. Real card, full oracle.
    myojin = {
        "name": "Myojin of Cleansing Fire",
        "type_line": "Legendary Creature — Spirit",
        "oracle_text": (
            "Myojin of Cleansing Fire enters with a divinity counter on it if you "
            "cast it from your hand.\n"
            "Myojin of Cleansing Fire has indestructible as long as it has a divinity "
            "counter on it.\n"
            "Remove a divinity counter from Myojin of Cleansing Fire: Destroy all "
            "other creatures."
        ),
    }
    # ADR-0027: proliferate_matters migrated to the Card IR; the divinity /
    # indestructible enters-with cycle now fires from the _IR_KEPT_DETECTORS
    # mirror, so assert the hybrid path.
    assert "proliferate_matters" in _keys_hybrid(myojin)
    # Over-fire guard: a COUNTDOWN counter you remove to wake a creature (slumber) is
    # anti-proliferate — you want fewer, not more.
    arixmethes = {
        "name": "Arixmethes, Slumbering Isle",
        "type_line": "Legendary Creature — Kraken",
        "oracle_text": (
            "Arixmethes, Slumbering Isle enters tapped with five slumber counters on "
            "it.\n"
            "As long as Arixmethes has a slumber counter on it, it's a land.\n"
            "Whenever you cast a spell, you may remove a slumber counter from "
            "Arixmethes."
        ),
    }
    assert "proliferate_matters" not in _keys_hybrid(arixmethes)


def test_ox_tribe_resolves_despite_two_letters_and_irregular_plural():
    # "Ox" is the only real two-letter creature subtype, so the len>=3 vocab-harvest
    # filter dropped it and "Oxen" (irregular plural) didn't singularize to it. An Ox
    # tribal lord (Bruse Tarl: "Oxen you control have double strike") must open
    # type_matters:Ox so its Oxen (Holy Cow, Makindi Ox) surface. Real card.
    bruse = {
        "name": "Bruse Tarl, Roving Rancher",
        "type_line": "Legendary Creature — Human Nomad",
        "oracle_text": (
            "Oxen you control have double strike.\n"
            "Whenever Bruse Tarl enters or attacks, exile the top card of your "
            "library. If it's a land card, create a 2/2 white Ox creature token."
        ),
    }
    assert ("type_matters", "you", "Ox") in _ksub(bruse)


def test_discard_matters_payoff_opens_opponent_discard():
    # A discard-MATTERS payoff (Tinybones triggers on an opponent HAVING discarded)
    # wants the whole forced-discard package, but the detector only matched present-tense
    # FORCERS ("opponent discards"), not the payoff condition ("discarded a card this
    # turn"). Open the lane so the forcers + payoffs surface. Real oracle.
    tinybones = {
        "name": "Tinybones, Trinket Thief",
        "type_line": "Legendary Creature — Skeleton Rogue",
        "oracle_text": (
            "At the beginning of each end step, if an opponent discarded a card this "
            "turn, you draw a card and you lose 1 life.\n"
            "{4}{B}{B}: Each opponent with no cards in hand loses 10 life."
        ),
    }
    # ADR-0027: opponent_discard migrated to the Card IR; it now fires from the hybrid
    # path (the byte-identical _OPPONENT_DISCARD_MIRROR kept-mirror catches the "opponent
    # discarded a card this turn" payoff over the oracle, so a bare IR suffices).
    assert "opponent_discard" in _keys_hybrid(tinybones)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    # Over-fire guard: a SELF-discard loot ("you discard a card") is not opponent-discard.
    loot = {
        "name": "Generic Looter",
        "type_line": "Creature — Wizard",
        "oracle_text": "{T}: Draw a card, then you discard a card.",
    }
    assert "opponent_discard" not in _keys_hybrid(loot)


def test_symmetric_cast_punisher_opens_opponent_cast_matters():
    # A symmetric cast-PUNISHER with an adjective ("whenever a player casts a NONCREATURE
    # spell, they lose 2 life" — Mai; "… deals 6 damage to that player" — Ruric Thar)
    # slipped past the "casts a spell" branch, so it missed the punish-opponents'-spells
    # lane and its payoffs (Soot Imp, Painful Quandary). Gated on the "that player" /
    # "they lose/discard/sacrifice" punish anchor so benefit-on-cast commanders stay out.
    # ADR-0027: opponent_cast_matters migrated to the Card IR — the symmetric-punisher
    # tail is served by a kept word mirror (phase collapses "whenever a player casts" to
    # scope='any', indistinguishable from a self-cast spellslinger payoff), so it is
    # served via the hybrid path, not pure regex. Real oracle, full text.
    mai = {
        "name": "Mai, Scornful Striker",
        "type_line": "Legendary Creature — Human Noble Ally",
        "oracle_text": (
            "First strike\n"
            "Whenever a player casts a noncreature spell, they lose 2 life."
        ),
    }
    ruric = {
        "name": "Ruric Thar, the Unbowed",
        "type_line": "Legendary Creature — Ogre Warrior",
        "oracle_text": (
            "Vigilance, reach\n"
            "Whenever a player casts a noncreature spell, Ruric Thar deals 6 damage to "
            "that player."
        ),
    }
    assert "opponent_cast_matters" in _keys_hybrid(mai)
    assert "opponent_cast_matters" in _keys_hybrid(ruric)
    assert "opponent_cast_matters" not in _keys(mai)
    assert "opponent_cast_matters" not in _keys(ruric)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

    def lane_covers(card, key, scope):
        sp = spec_for(Signal(key=key, scope=scope, subject="", text="", source=""))
        if sp.serve.matches(card):
            return True
        return any(
            (ex.serve or serve_from_dict(ex.search)).matches(card) for ex in sp.extras
        )

    painful = {
        "name": "Painful Quandary",
        "type_line": "Enchantment",
        "oracle_text": (
            "Whenever an opponent casts a spell, that player loses 5 life unless they "
            "discard a card."
        ),
    }
    assert lane_covers(painful, "opponent_cast_matters", "opponents") is True
    # Over-fire guard: a BENEFIT-on-cast commander (Niv-Mizzet draws) is a spellslinger
    # engine, not a punisher — it must NOT open the punish lane via this branch.
    niv = {
        "name": "Niv-Mizzet, Parun",
        "type_line": "Legendary Creature — Dragon Wizard",
        "oracle_text": (
            "Flying\n"
            "Whenever you draw a card, Niv-Mizzet, Parun deals 1 damage to any target.\n"
            "Whenever a player casts an instant or sorcery spell, you draw a card."
        ),
    }
    assert "opponent_cast_matters" not in _keys(niv)


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


def test_missing_race_tribes_open_membership_but_classes_do_not():
    # The membership gate (TRIBAL_SUBTYPES) missed real RACE tribes that have lords and
    # commanders — Changelings, Myr, Saprolings, Moogles — so a vanilla member of those
    # tribes read as zero-signal instead of surfacing its tribe. Add them; keep class
    # types (Warrior) out, since a class is near-ubiquitous and needs explicit support.
    moogle = {
        "name": "Mog, Moogle Warrior",
        "type_line": "Legendary Creature — Moogle Warrior",
        "oracle_text": "Lifelink",  # no tribal oracle — membership must carry it
    }
    assert ("type_matters", "you", "Moogle") in _ksub(moogle)
    myr = {
        "name": "Generic Myr Lord",
        "type_line": "Legendary Creature — Myr",
        "oracle_text": "",
    }
    assert ("type_matters", "you", "Myr") in _ksub(myr)
    saproling = {
        "name": "Generic Saproling",
        "type_line": "Legendary Creature — Plant Saproling",
        "oracle_text": "",
    }
    assert ("type_matters", "you", "Saproling") in _ksub(saproling)
    gorgon = {
        "name": "Generic Gorgon",
        "type_line": "Legendary Creature — Gorgon",
        "oracle_text": "",
    }
    assert ("type_matters", "you", "Gorgon") in _ksub(gorgon)
    # Over-fire guard: a class type (Warrior) is NOT a membership tribe — a vanilla
    # Human Warrior must not mint a Warrior-tribal avenue from membership alone.
    warrior = {
        "name": "Generic Warrior",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": "",
    }
    subs = {subj for (key, scope, subj) in _ksub(warrior) if key == "type_matters"}
    assert "Warrior" not in subs
    assert "Human" not in subs


def test_land_sacrifice_matters_opens_and_serves():
    # Gitrog/Titania/Slogurk draw/grow when lands hit the graveyard, so repeatable
    # "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb) are their core engine.
    # sacrifice_matters deliberately EXCLUDES "sacrifice a land" (fetchland guard), so
    # this land-sac archetype is its own lane. Real cards, full oracle.
    # ADR-0027: land_sacrifice_matters migrated to the Card IR (the byte-identical
    # LAND_SACRIFICE_REGEX kept WORD MIRROR in _IR_KEPT_DETECTORS — phase carries NO
    # structural form), so this asserts on the HYBRID path. A bare non-None IR routes
    # the hybrid to the IR path; the mirror reads the reminder-stripped oracle off the
    # record. The serve-spec checks (lane_covers) are producer-independent.
    gitrog = {
        "name": "The Gitrog Monster",
        "type_line": "Legendary Creature — Frog Horror",
        "oracle_text": (
            "Deathtouch\n"
            "At the beginning of your upkeep, sacrifice The Gitrog Monster unless you "
            "sacrifice a land.\n"
            "You may play an additional land on each of your turns.\n"
            "Whenever one or more land cards are put into your graveyard from "
            "anywhere, draw a card."
        ),
    }
    assert "land_sacrifice_matters" in _keys_hybrid(gitrog)

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
    assert "land_sacrifice_matters" not in _keys_hybrid(viscera)
    assert lane_covers(viscera, "land_sacrifice_matters") is False


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


def test_lifegain_payoff_matches_your_team_and_contraction():
    # A lifegain-count payoff phrased "if your TEAM gained life this turn" (Regna, a
    # partner commander) or "if you've gained" (the contraction) slipped past the
    # detector's bare "you gained". Real cards, full oracle.
    regna = {
        "name": "Regna, the Redeemer",
        "type_line": "Legendary Creature — Angel Cleric",
        "oracle_text": (
            "Flying\n"
            "At the beginning of each end step, if your team gained life this turn, "
            "create two 1/1 white Warrior creature tokens."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR (byte-identical kept-mirror),
    # so it serves from the hybrid path.
    assert "lifegain_matters" in _keys_hybrid(regna)
    # Over-fire guard: a non-lifegain payoff doesn't open the lane.
    plain = {
        "name": "Generic Beater",
        "type_line": "Creature — Bear",
        "oracle_text": "Trample",
    }
    assert "lifegain_matters" not in _keys_hybrid(plain)


def test_lifegain_matches_variable_that_much_life():
    # Variable self-lifegain phrased "you gain that much life" (Varina attacks with
    # Zombies -> draw/discard/gain life equal to the count) is a real, repeatable
    # lifegain SOURCE — it wants lifegain payoffs. The detector had "gain X life" and
    # "gain life equal to" but not the equally-common "that much" form. Real oracle.
    varina = {
        "name": "Varina, Lich Queen",
        "type_line": "Legendary Creature — Zombie Wizard",
        "oracle_text": (
            "Whenever you attack with one or more Zombies, draw that many cards, then "
            "discard that many cards. You gain that much life.\n"
            "{2}, Exile two cards from your graveyard: Create a tapped 2/2 black "
            "Zombie creature token."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR (byte-identical kept-mirror),
    # so it serves from the hybrid path.
    assert "lifegain_matters" in _keys_hybrid(varina)
    # Over-fire guard: the new clause is self-scoped. A third-person "<opponent>
    # gains that much life" (no "whenever … gain … life" trigger sentence) must not
    # open the lane — only "you gain that much life" does.
    opp = {
        "name": "Generous Foe",
        "type_line": "Legendary Creature — Spirit",
        "oracle_text": (
            "At the beginning of your end step, target opponent gains that much life."
        ),
    }
    assert "lifegain_matters" not in _keys_hybrid(opp)


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
    assert lane_covers(mass_diminish, "debuff_matters", "any") is True
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
    assert lane_covers(mirror, "debuff_matters", "any") is False


def test_lure_commander_cross_opens_blocked_matters():
    # Lure (force blocks) and blocked_matters (punish the blocker) are one archetype:
    # a commander that MUST be blocked / lures (Madame Vastra) wants the punish-when-
    # blocked payoffs (Engulfing Slagwurm, Tolarian Entrancer). Cross-open lure ->
    # blocked (one-directional — a bare "when blocked" trigger isn't a lure deck). Real
    # card, full oracle.
    vastra = {
        "name": "Madame Vastra",
        "type_line": "Legendary Creature — Lizard Detective",
        "oracle_text": (
            "Madame Vastra must be blocked if able.\n"
            "Whenever a creature dealt damage by Madame Vastra this turn dies, create "
            "a Clue token and a Food token."
        ),
    }
    keys = _keys(vastra)
    assert "lure_matters" in keys
    assert "blocked_matters" in keys


def test_significant_bleed_opens_lifegain_but_negligible_rider_does_not():
    # A commander with SIGNIFICANT repeated self-life-loss (Deadpool loses 3 each upkeep;
    # cumulative-upkeep payers; "you lose life equal to" sac engines) bleeds out without
    # sustain, so it wants lifegain. Gated to meaningful bleed — a negligible "lose 1
    # life" rider on an attack/sac/value trigger won't deck you and must NOT open it
    # (that was the 79-commander over-broad lifeloss->lifegain trap). Real cards.
    deadpool = {
        "name": "Deadpool, Trading Card",
        "type_line": "Legendary Creature — Mutant Mercenary",
        "oracle_text": (
            "As Deadpool enters, you may exchange his text box and another "
            "creature's.\n"
            "At the beginning of your upkeep, you lose 3 life.\n"
            "{3}, Sacrifice this creature: Each other player draws a card."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the self-bleed-wants-
    # sustain block (ARM B) rides the byte-identical kept-mirror, served from the hybrid.
    assert "lifegain_matters" in _keys_hybrid(deadpool)
    # A passive, frequent, unavoidable death-triggered draw-and-bleed engine (Kothophed
    # loses 1 life per opponent permanent dying — fast with board wipes) also bleeds you
    # out, so it wants lifegain even though each event is only 1 life.
    kothophed = {
        "name": "Kothophed, Soul Hoarder",
        "type_line": "Legendary Creature — Demon",
        "oracle_text": (
            "Flying\n"
            "Whenever a permanent owned by another player is put into a graveyard "
            "from the battlefield, you draw a card and you lose 1 life."
        ),
    }
    assert "lifegain_matters" in _keys_hybrid(kothophed)
    # Over-fire guard: losing 1 life per attack is a negligible rider, not a bleed engine.
    azula = {
        "name": "Azula, On the Hunt",
        "type_line": "Legendary Creature — Human Noble",
        "oracle_text": (
            "Firebending 2\n"
            "Whenever Azula attacks, you lose 1 life and create a Clue token."
        ),
    }
    assert "lifegain_matters" not in _keys_hybrid(azula)


def test_variable_self_bleed_opens_lifegain_sustain():
    # The significant-bleed -> lifegain cross-open fired on the fixed "you lose life
    # equal to" sac engines but missed the equivalent VARIABLE phrasings. Asmodeus
    # draws its whole library and "you lose that much life"; Be'lakor is the classic
    # "draw X / lose X" engine. Both are deck-defining scaling self-bleed that wants
    # lifegain sustain to not deck the controller. Real oracle, full text.
    asmodeus = {
        "name": "Asmodeus the Archfiend",
        "type_line": "Legendary Creature — Devil God",
        "oracle_text": (
            "Binding Contract — If you would draw a card, exile the top card of your "
            "library face down instead.\n"
            "{B}{B}{B}: Draw seven cards.\n"
            "{B}: Return all cards exiled with Asmodeus to their owner's hand and you "
            "lose that much life."
        ),
    }
    belakor = {
        "name": "Be'lakor, the Dark Master",
        "type_line": "Legendary Creature — Demon Noble",
        "oracle_text": (
            "Flying\n"
            "Prince of Chaos — When Be'lakor enters, you draw X cards and you lose X "
            "life, where X is the number of Demons you control.\n"
            "Lord of Torment — Whenever another Demon you control enters, it deals "
            "damage equal to its power to any target."
        ),
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — the variable self-bleed
    # sustain (ARM B) rides the byte-identical kept-mirror, served from the hybrid.
    assert "lifegain_matters" in _keys_hybrid(asmodeus)
    assert "lifegain_matters" in _keys_hybrid(belakor)
    # Boundary guard: OPTIONAL "you may pay life equal to" (Madame Null) is controlled,
    # affordable life payment, not an unavoidable bleed — it stays out (the over-broad
    # lifeloss trap). Forced "you lose …" opens; optional "you may pay …" does not.
    madame_null = {
        "name": "Madame Null, Power Broker",
        "type_line": "Legendary Creature — Demon Advisor",
        "oracle_text": (
            "Deathtouch\n"
            "Whenever another creature you control enters, you may pay life equal to "
            "its power. If you do, put that many +1/+1 counters on it."
        ),
    }
    assert "lifegain_matters" not in _keys_hybrid(madame_null)


def test_variable_self_lifeloss_opens_life_as_resource_lane():
    # The lifeloss_matters "you" lane (life-as-resource: pay/lose life on demand, plus
    # life-total swap/reset/recovery payoffs like Repay in Kind / Children of Korlis /
    # Near-Death Experience). Its SERVE already matched variable "you lose X life", but
    # the DETECTOR that decides whether a COMMANDER opens it was numeric-only, so the
    # variable-bleed commanders missed this second avenue. Real oracle.
    asmodeus = {
        "name": "Asmodeus the Archfiend",
        "type_line": "Legendary Creature — Devil God",
        "oracle_text": (
            "Binding Contract — If you would draw a card, exile the top card of your "
            "library face down instead.\n"
            "{B}{B}{B}: Draw seven cards.\n"
            "{B}: Return all cards exiled with Asmodeus to their owner's hand and you "
            "lose that much life."
        ),
    }
    belakor = {
        "name": "Be'lakor, the Dark Master",
        "type_line": "Legendary Creature — Demon Noble",
        "oracle_text": (
            "Flying\n"
            "Prince of Chaos — When Be'lakor enters, you draw X cards and you lose X "
            "life, where X is the number of Demons you control.\n"
            "Lord of Torment — Whenever another Demon you control enters, it deals "
            "damage equal to its power to any target."
        ),
    }
    # ADR-0027: lifeloss_matters is IR-served — both fire from the structural
    # `lose_life` ("you lose X/that much life"). phase emits the lose_life Effect; the
    # IR here mirrors that node (the supplement does not synthesize a bare-clause
    # lose_life out of a trimmed activated-ability raw).
    self_loss_ir = Card(
        oracle_id="x",
        name="X",
        faces=(
            Face(
                name="X",
                abilities=(
                    Ability(
                        kind="activated",
                        effects=(Effect(category="lose_life", scope="you"),),
                    ),
                ),
            ),
        ),
    )
    assert ("lifeloss_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(asmodeus, self_loss_ir)
    }
    assert ("lifeloss_matters", "you") in {
        (s.key, s.scope) for s in extract_signals_hybrid(belakor, self_loss_ir)
    }
    # Over-fire guard: a "Ward—Pay life equal to" cost (Raubahn) is the OPPONENT paying,
    # not self life-loss — phase emits no lose_life, so the lane stays out on the IR.
    raubahn = {
        "name": "Raubahn, Bull of Ala Mhigo",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "Ward—Pay life equal to Raubahn's power.\n"
            "Whenever Raubahn attacks, attach up to one target Equipment you control "
            "to target attacking creature."
        ),
    }
    assert "lifeloss_matters" not in {
        s.key for s in extract_signals_hybrid(raubahn, _bare_ir())
    }


def test_attacking_team_double_strike_opens_combat_damage():
    # A commander that grants double strike to your ATTACKING team (Raphael) makes them
    # deal combat damage to players twice — it wants the "whenever creatures you control
    # deal combat damage to a player" payoffs. Tight to "attacking creatures you control
    # have double strike" so go-wide/tribal/conditional double-strike granters (Kwende,
    # Jetmir) — which aren't combat-damage-payoff decks — stay out. Real cards.
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR, so the double-strike-
    # grant tail is served from the hybrid (IR) path via a LOW-confidence inline mirror.
    raphael = {
        "name": "Raphael, the Nightwatcher",
        "type_line": "Legendary Creature — Mutant Ninja Turtle",
        "oracle_text": (
            "Sneak {1}{R}{R}\nAttacking creatures you control have double strike."
        ),
    }
    rsigs = {(s.key, s.scope) for s in extract_signals_hybrid(raphael, _bare_ir())}
    assert ("combat_damage_to_opp", "opponents") in rsigs
    # Over-fire guard: a conditional/non-attacking double-strike grant is not this lane.
    kwende = {
        "name": "Kwende, Pride of Femeref",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "Double strike\nCreatures you control with first strike have double strike."
        ),
    }
    ksigs = {(s.key, s.scope) for s in extract_signals_hybrid(kwende, _bare_ir())}
    assert ("combat_damage_to_opp", "opponents") not in ksigs


def test_remove_counter_to_activate_opens_proliferate():
    # A commander that SPENDS a counter as an activation cost (remove a counter from a
    # permanent: <effect>) wants more counters — i.e. proliferate. Keyed on the MECHANIC
    # (colon = activation cost), not a counter-name list, so it future-proofs for new
    # counter types. COUNTDOWN counters (slumber/egg) use "may remove"/upkeep-remove with
    # NO colon-activation, so they're excluded by construction. Real cards, full oracle.
    tayam = {
        "name": "Tayam, Luminous Enigma",
        "type_line": "Legendary Creature — Hound Spirit",
        "oracle_text": (
            "Each other creature you control enters with an additional vigilance "
            "counter on it.\n"
            "{3}, Remove three counters from among creatures you control: Mill three "
            "cards, then return a permanent card with mana value 3 or less from your "
            "graveyard to the battlefield."
        ),
    }
    # ADR-0027: proliferate_matters migrated to the Card IR; the remove-a-counter-
    # as-cost producer now fires from the LOW-confidence _PROLIFERATE_REMOVE_COST_RE
    # mirror arm, so assert the hybrid path.
    assert "proliferate_matters" in _keys_hybrid(tayam)
    # Over-fire guard: a COUNTDOWN counter removed in upkeep (no colon-activation) — you
    # want FEWER, so it must NOT open proliferate.
    arixmethes = {
        "name": "Arixmethes, Slumbering Isle",
        "type_line": "Legendary Creature — Kraken",
        "oracle_text": (
            "Arixmethes, Slumbering Isle enters tapped with five slumber counters on "
            "it.\n"
            "As long as Arixmethes has a slumber counter on it, it's a land.\n"
            "Whenever you cast a spell, you may remove a slumber counter from "
            "Arixmethes."
        ),
    }
    assert "proliferate_matters" not in _keys_hybrid(arixmethes)


def test_keyword_soup_commander_opens_and_serves_multi_keyword_creatures():
    # A keyword-soup commander (Odric, Lunarch Marshal) SHARES many evergreen keywords
    # across the team, so it wants creatures stacked with keywords. Open on >=5 distinct
    # evergreen keywords in a team-grant context (distinguishes the soup-sharer from a
    # single-keyword anthem); serve creatures with >=3 evergreen keywords. Real cards.
    odric = {
        "name": "Odric, Lunarch Marshal",
        "type_line": "Legendary Creature — Human Soldier",
        "oracle_text": (
            "At the beginning of each combat, creatures you control gain first strike "
            "until end of turn if a creature you control has first strike. The same is "
            "true for flying, deathtouch, double strike, haste, hexproof, "
            "indestructible, lifelink, menace, reach, skulk, trample, and vigilance."
        ),
    }
    assert "keyword_soup_matters" in _keys(odric)

    from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
    from mtg_utils._deck_forge.signals import Signal

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
    assert lane_covers(aerial, "keyword_soup_matters") is True
    # Over-fire guard: a single-keyword anthem commander (grants only vigilance) is not
    # a keyword-soup deck.
    aang = {
        "name": "Aang, Air Nomad",
        "type_line": "Legendary Creature — Human Avatar",
        "oracle_text": "Flying\nVigilance\nOther creatures you control have vigilance.",
    }
    assert "keyword_soup_matters" not in _keys(aang)
    # Over-fire guard: a one-keyword creature is not a multi-keyword body.
    sprite = {
        "name": "Scryb Sprite",
        "type_line": "Creature — Faerie",
        "oracle_text": "Flying",
        "keywords": ["Flying"],
    }
    assert lane_covers(sprite, "keyword_soup_matters") is False


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


def test_acererak_folds_ventured_tomb_of_annihilation():
    # ADR-0025: a commander folds in the SPECIFIC dungeon its oracle names. Acererak
    # ventures into Tomb of Annihilation (named in its ETB), whose rooms repeatedly
    # drain "each player loses N life" — making Acererak a self-bleed + sacrifice
    # commander that wants lifegain (Demon's Horn). Resolver returns the dungeon's real
    # oracle. Real cards, full oracle.
    toa_oracle = (
        "Trapped Entry — Each player loses 1 life. (Leads to: Veils of Fear, "
        "Oubliette)\n"
        "Veils of Fear — Each player loses 2 life unless they discard a card. "
        "(Leads to: Sandfall Cell)\n"
        "Sandfall Cell — Each player loses 2 life unless they sacrifice a creature, "
        "artifact, or land of their choice. (Leads to: Cradle of the Death God)\n"
        "Oubliette — Discard a card and sacrifice a creature, an artifact, and a "
        "land. (Leads to: Cradle of the Death God)\n"
        "Cradle of the Death God — Create The Atropal, a legendary 4/4 black God "
        "Horror creature token with deathtouch."
    )

    def resolver(name):
        if name == "Tomb of Annihilation":
            return {
                "name": "Tomb of Annihilation",
                "type_line": "Dungeon",
                "oracle_text": toa_oracle,
            }
        return None

    acererak = {
        "name": "Acererak the Archlich",
        "type_line": "Legendary Creature — Zombie Wizard",
        "oracle_text": (
            "When Acererak enters, if you haven't completed Tomb of Annihilation, "
            "return Acererak to its owner's hand and venture into the dungeon.\n"
            "Whenever Acererak attacks, for each opponent, you create a 2/2 black "
            "Zombie creature token unless that player sacrifices a creature of their "
            "choice."
        ),
        "all_parts": [
            {
                "component": "combo_piece",
                "type_line": "Dungeon",
                "name": "Tomb of Annihilation",
            },
            {
                "component": "combo_piece",
                "type_line": "Dungeon",
                "name": "Lost Mine of Phandelver",
            },
        ],
    }
    # ADR-0027 β: lifegain_matters migrated to the Card IR — it serves from the hybrid,
    # and extract_signals_hybrid folds referenced objects (the ventured ToA) into the
    # record the IR kept-mirror reads, so the "each player loses N life" bleed still
    # opens the lane.
    without = _keys_hybrid(acererak)
    withfold = {
        s.key
        for s in extract_signals_hybrid(acererak, _bare_ir(), resolve_object=resolver)
    }
    # The folded ToA bleed opens lifegain (sustain for Demon's Horn).
    assert "lifegain_matters" in withfold
    assert "lifegain_matters" not in without

    # Over-fire guards: only the dungeon NAMED in Acererak's oracle (ToA) is folded —
    # Lost Mine of Phandelver is in all_parts but unnamed, so it's never resolved...
    def strict_resolver(name):
        if name == "Lost Mine of Phandelver":
            raise AssertionError("must not resolve an unnamed all_parts dungeon")
        return resolver(name)

    extract_signals(acererak, resolve_object=strict_resolver)
    # ...and a generic venturer that names no dungeon folds nothing.
    nadaar = {
        "name": "Nadaar, Selfless Paladin",
        "type_line": "Legendary Creature — Dragon Knight",
        "oracle_text": (
            "Vigilance\nWhenever Nadaar enters or attacks, venture into the dungeon."
        ),
        "all_parts": [
            {
                "component": "combo_piece",
                "type_line": "Dungeon",
                "name": "Tomb of Annihilation",
            },
        ],
    }
    assert "lifegain_matters" not in {
        s.key
        for s in extract_signals_hybrid(nadaar, _bare_ir(), resolve_object=resolver)
    }


def test_ring_bearer_commander_folds_the_ring():
    # ADR-0025 rules-fixed fold: "the Ring tempts you" maps to the ONE Ring (no
    # disambiguation). The Ring-bearer's levels — "deals combat damage to a player, each
    # opponent loses 3 life" / "draw a card, then discard" — make a Ring commander a
    # combat-damage + loot deck. The Ring's text lives on card_faces (oracle_text is
    # empty), so the fold must read it via get_oracle_text. Real cards, full oracle.
    ring_text = (
        "Your Ring-bearer is legendary and can't be blocked by creatures with "
        "greater power.\n"
        "Whenever your Ring-bearer attacks, draw a card, then discard a card.\n"
        "Whenever your Ring-bearer becomes blocked by a creature, that creature's "
        "controller sacrifices it at end of combat.\n"
        "Whenever your Ring-bearer deals combat damage to a player, each opponent "
        "loses 3 life."
    )

    def resolver(name):
        if name == "The Ring":
            return {"name": "The Ring", "oracle_text": ring_text}
        return None

    aragorn = {
        "name": "Aragorn, Company Leader",
        "type_line": "Legendary Creature — Human Ranger",
        "oracle_text": (
            "Whenever the Ring tempts you, if you chose a creature other than "
            "Aragorn as your Ring-bearer, put your choice of a counter from among "
            "first strike, vigilance, deathtouch, and lifelink on Aragorn.\n"
            "Whenever you put one or more counters on Aragorn, put one of each of "
            "those kinds of counters on up to one other target creature."
        ),
    }
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR, so it is served from the
    # hybrid (IR) path. The hybrid folds the referenced object (the Ring) into the record
    # the IR mirror reads, so the folded combat-damage drain still opens the lane.
    without = {s.key for s in extract_signals_hybrid(aragorn, _bare_ir())}
    withfold = {
        s.key
        for s in extract_signals_hybrid(aragorn, _bare_ir(), resolve_object=resolver)
    }
    # The folded Ring's combat-damage drain opens combat_damage_to_opp.
    assert ("combat_damage_to_opp", "opponents") in {
        (s.key, s.scope)
        for s in extract_signals_hybrid(aragorn, _bare_ir(), resolve_object=resolver)
    }
    assert "combat_damage_to_opp" in withfold
    assert "combat_damage_to_opp" not in without
    # Over-fire guard: a commander that never tempts with the Ring folds nothing.
    plain = {
        "name": "Generic Bear",
        "type_line": "Legendary Creature — Bear",
        "oracle_text": "Vigilance",
    }
    assert "combat_damage_to_opp" not in {
        s.key
        for s in extract_signals_hybrid(plain, _bare_ir(), resolve_object=resolver)
    }


def test_meld_commander_folds_its_meld_result():
    # ADR-0025: a meld commander's plan is to meld into its result, so fold the result's
    # oracle (discovered via the meld_result all_parts component — one per card, no
    # disambiguation). Bruna melds into Brisela, whose "opponents can't cast spells with
    # mana value 3 or less" is a stax lock invisible from Bruna's own text. Real cards.
    brisela_oracle = (
        "Flying, first strike, vigilance, lifelink\n"
        "Your opponents can't cast spells with mana value 3 or less."
    )

    def resolver(name):
        if name == "Brisela, Voice of Nightmares":
            return {
                "name": "Brisela, Voice of Nightmares",
                "type_line": "Legendary Creature — Eldrazi Angel",
                "oracle_text": brisela_oracle,
            }
        return None

    bruna = {
        "name": "Bruna, the Fading Light",
        "type_line": "Legendary Creature — Angel Horror",
        "oracle_text": (
            "When you cast this spell, you may return target Angel or Human creature "
            "card from your graveyard to the battlefield.\n"
            "Flying, vigilance\n"
            "(Melds with Gisela, the Broken Blade.)"
        ),
        "all_parts": [
            {
                "component": "meld_part",
                "type_line": "Legendary Creature — Angel Horror",
                "name": "Gisela, the Broken Blade",
            },
            {
                "component": "meld_result",
                "type_line": "Legendary Creature — Eldrazi Angel",
                "name": "Brisela, Voice of Nightmares",
            },
        ],
    }
    without = _keys(bruna)
    withfold = {s.key for s in extract_signals(bruna, resolve_object=resolver)}
    assert "stax_taxes" in withfold  # Brisela's "can't cast MV<=3" lock
    assert "stax_taxes" not in without
    # Over-fire guard: a non-meld commander folds nothing.
    plain = {
        "name": "Generic Bear",
        "type_line": "Legendary Creature — Bear",
        "oracle_text": "Vigilance",
    }
    assert "stax_taxes" not in {
        s.key for s in extract_signals(plain, resolve_object=resolver)
    }
