"""The Two-Headed Giant readout, over real cards (ADR-0056).

Every card is read by name from the committed snapshot through ``mtg_utils.testkit``
— the IR path runs phase's real concept trees, and the text path runs the same
real record with its ``oracle_id`` stripped (the shape of a set newer than the
phase pin). CR 805.4d: a step trigger on "each player's" or
"each opponent's" step triggers once per player only when it refers to "that
player".
"""

import json

import pytest
from click.testing import CliRunner

from mtg_utils._analysis.lanes.removal_tutors import removal_edict_answers
from mtg_utils._card_ir.crosswalk import (
    effect_filter,
    effect_owner_player_scope,
    effect_player_reach,
    filter_core_types,
    filter_mana_value_floor,
    refers_to_scoped_player,
    scoped_player_scope,
    tag_of,
    trigger_phase,
)
from mtg_utils.testkit import test_card, test_phase_records, test_signals
from mtg_utils.twohg_scan import (
    _units,
    classify_card,
    main,
    render_twohg_scan,
    twohg_scan,
)


def _no_ir(name):
    """The real record with no ``oracle_id``: the Card IR can't see it, so the
    scan takes the oracle-text path, as it does for a brand-new set."""
    return {k: v for k, v in test_card(name).items() if k != "oracle_id"}


def _unit_list(name):
    return list(_units(test_card(name)))


def _effect(name, concept):
    """The (unit, concept node) of *name*'s first effect named *concept*."""
    return next(
        (u, c) for u in _unit_list(name) for c in u.effects if c.concept == concept
    )


def _row(name):
    row = classify_card(test_card(name))
    assert row is not None, name
    return row


def _no_ir_row(name):
    row = classify_card(_no_ir(name))
    assert row is not None, name
    return row


# ── the shared reads ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "concept", "reach"),
    [
        ("Rank Rat", "discard", "opponents"),  # owner player_scope: Opponent
        ("Juvenile Mist Dragon", "tap_untap", "per_opponent"),  # before TargetPlayer
        ("Pestilence", "deal_damage", "each"),  # player_filter: All
        ("Witty Roastmaster", "deal_damage", "opponents"),  # player_filter: Opponent
        ("Wrath of God", "destroy", "each"),  # mass, no controller
        ("Massacre Wurm", "pump", "opponents"),  # mass, opponents' creatures
        ("Sign in Blood", "draw", "target"),
        # "each creature target player controls"
        ("Twisted Fates", "place_counter", "target"),
        ("Face Yourself", "copy_token", "target"),  # its source_filter
        ("Braids, Cabal Minion", "sacrifice", "scoped"),
        ("Howling Mine", "draw", "scoped"),
        ("Murder", "destroy", None),  # a targeted creature, no player reach
        ("Phyrexian Arena", "draw", None),
    ],
)
def test_effect_player_reach(name, concept, reach):
    unit, c = _effect(name, concept)
    assert effect_player_reach(unit.node, c.node) == reach


def test_step_trigger_reads():
    (mine,) = _unit_list("Howling Mine")
    assert trigger_phase(mine.node) == "Draw"
    assert refers_to_scoped_player(mine.node)  # "that player draws"
    (kraken,) = _unit_list("Verdant Kraken")
    assert trigger_phase(kraken.node) == "Upkeep"
    assert not refers_to_scoped_player(kraken.node)  # "you create"
    (muse,) = _unit_list("Lavaborn Muse")
    # The intervening "if that player has two or fewer cards in hand" counts.
    assert refers_to_scoped_player(muse.node)
    rat, _ = _effect("Rank Rat", "discard")
    assert trigger_phase(rat.node) is None  # an enters trigger


def test_scoped_player_scope_reads_the_turn_constraint():
    yours, theirs = _unit_list("Sheoldred, Whispering One")
    assert scoped_player_scope(theirs) == "opponents"  # each opponent's upkeep
    assert scoped_player_scope(yours) is None  # your upkeep
    (braids,) = _unit_list("Braids, Cabal Minion")
    assert scoped_player_scope(braids) == "each"  # each player's upkeep


def test_filter_mana_value_floor():
    _, destroy = _effect("Your Fate Ends Here", "destroy")
    assert filter_mana_value_floor(effect_filter(destroy.node)) == 3
    _, exile = _effect("Solitary Cell", "change_zone")
    # "mana value 3 or less" is a ceiling, not a floor.
    assert filter_mana_value_floor(effect_filter(exile.node)) is None
    _, murder = _effect("Murder", "destroy")
    assert filter_mana_value_floor(effect_filter(murder.node)) is None


# ── the buckets, IR path ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("bucket", "name", "what", "how"),
    [
        ("doubles", "Gray Merchant of Asphodel", "lose_life", "each opponent"),
        ("doubles", "Rhystic Study", "draw", "opponent trigger (cast_spell)"),
        ("doubles", "Underworld Dreams", "deal_damage", "opponent trigger (drawn)"),
        ("doubles", "Witty Roastmaster", "deal_damage", "each opponent"),
        ("doubles", "Juvenile Mist Dragon", "tap_untap", "for each opponent"),
        ("doubles", "Massacre Wurm", "pump", "your opponents' creatures"),
        ("doubles", "Massacre Wurm", "lose_life", "opponent trigger (dies)"),
        ("doubles", "Rank Rat", "discard", "each opponent"),
        ("doubles", "Extended Absence", "deal_damage", "each opponent"),
        ("doubles", "Winter, Tormented Loner", "sacrifice", "each opponent"),
        ("doubles", "Hapatra, the Desert Fang", "place_counter", "for each opponent"),
        ("doubles", "The Theorist, Jace Beleren", "bounce", "for each opponent"),
        ("doubles", "Garruk, Veiled Butcher", "discard", "each opponent"),
        (
            "doubles",
            "Fulminous Forte",
            "deal_damage",
            "your opponents' creatures and planeswalkers",
        ),
        # A granted planeswalker ability: "[+2]: … 1 damage to each opponent".
        ("doubles", "Sanctum Lurker", "deal_damage", "each opponent"),
        ("doubles", "Tomik, Izzet Sparkmage", "damage", "replacement on opponents"),
        ("doubles", "Solarium Sentry", "gain_life", "opponent trigger (cast_spell)"),
        ("doubles", "Thalia, the Survivor", "tax", "your opponents' spells"),
        ("doubles", "Sheoldred, Whispering One", "sacrifice", "that opponent"),
        ("hits_partner", "Pestilence", "deal_damage", "each player"),
        ("hits_partner", "Cast Away Doubt", "deal_damage", "each player"),
        ("hits_partner", "Wrath of God", "destroy", "all creatures"),
        ("hits_partner", "Pyroclasm", "deal_damage", "all creatures"),
        ("hits_partner", "Kindred Judgment", "destroy", "all creatures"),
        ("hits_partner", "Overwrite the Multiverse", "change_zone", "all creatures"),
        ("hits_partner", "The Echoverse Fulcrum", "destroy", "all creatures"),
        ("hits_partner", "Rise of the Deathbringer", "pump", "all creatures"),
        ("hits_partner", "Ajani Unrelenting", "deal_damage", "all creatures"),
        ("hits_partner", "Garruk, Veiled Butcher", "sacrifice", "each player"),
        # Symmetric help rides the same bucket; ``what`` tells it apart.
        ("hits_partner", "Jace Beleren", "draw", "each player"),
        ("hits_partner", "Howling Mine", "draw", "that player"),
        ("hits_partner", "Braids, Cabal Minion", "sacrifice", "that player"),
        ("hits_partner", "Thalia, Guardian of Thraben", "tax", "every player's spells"),
    ],
)
def test_ir_rows(bucket, name, what, how):
    row = _row(name)
    assert row["path"] == "ir"
    assert {"what": what, "how": how} in row[bucket]


@pytest.mark.parametrize(
    ("name", "what"),
    [
        ("Sign in Blood", "draw"),
        ("Mind Rot", "discard"),
        ("Jace Beleren", "draw"),
        ("Twisted Fates", "place_counter"),
        ("Face Yourself", "copy_token"),
        # The prepare spell on the back face; the front face adds a step trigger.
        ("Bloodline Recollector // Ancestral Craving", "draw"),
    ],
)
def test_target_player(name, what):
    row = _row(name)
    assert {"what": what, "how": "target player"} in row["target_player"]


@pytest.mark.parametrize(
    ("name", "step", "whose", "fires"),
    [
        ("Howling Mine", "Draw", "each", "per_head"),
        ("Braids, Cabal Minion", "Upkeep", "each", "per_head"),
        ("Smokestack", "Upkeep", "each", "per_head"),
        ("Sulfuric Vortex", "Upkeep", "each", "per_head"),
        ("Sheoldred, Whispering One", "Upkeep", "each_opponent", "per_head"),
        ("Lavaborn Muse", "Upkeep", "each_opponent", "per_head"),
        ("Pestilence", "End", "each", "once"),
        ("Verdant Kraken", "Upkeep", "each", "once"),
        ("The Theorist, Jace Beleren", "Draw", "each_opponent", "once"),
        ("Bloodline Recollector // Ancestral Craving", "End", "each", "once"),
    ],
)
def test_step_triggers(name, step, whose, fires):
    """CR 805.4d: per head only when the trigger refers to "that player"; a
    "your [step]" trigger (Smokestack's soot, Sheoldred's reanimation) drops."""
    (trigger,) = _row(name)["step_triggers"]
    assert (trigger["step"], trigger["whose"], trigger["fires"]) == (step, whose, fires)


def test_no_row_for_a_card_2hg_does_not_change():
    assert classify_card(test_card("Phyrexian Arena")) is None  # your upkeep, you draw


@pytest.mark.parametrize(
    ("name", "walkers", "mv_floor"),
    [
        ("Hero's Downfall", True, None),
        ("Lightning Bolt", True, None),  # any target
        ("Extended Absence", True, None),
        ("Solitary Cell", True, None),  # a mana-value ceiling, not a floor
        ("Break Under Pressure", True, None),  # an edict on creature or planeswalker
        ("Your Fate Ends Here", True, 3),
        ("Murder", False, None),
        ("Last Gasp", False, None),
        # The "creature or planeswalker" is YOUR optional sacrifice; theirs is a creature.
        ("Winter, Tormented Loner", False, None),
        # Soft removal (the shared walk's ``soft`` opt-in):
        ("Unsummon", False, None),  # bounce to hand
        ("Multiply by Zero", False, None),  # base power and toughness 0/0
        ("Hapatra, the Desert Fang", False, None),  # -1/-1 counters
        ("Clash of Elements", True, None),  # a tuck through a ParentTarget
    ],
)
def test_removal_reach(name, walkers, mv_floor):
    assert _row(name)["removal_reach"] == {"walkers": walkers, "mv_floor": mv_floor}


def test_forced_only_edict_walk_drops_your_own_sacrifice():
    """The shared edict walk reads no actor by default (the type-scoped presets);
    ``forced_only`` gates it on ``edict_makers``' actor read, so Winter's "you may
    sacrifice a creature or planeswalker" drops while its opponents' creature
    sacrifice stays."""
    winter = test_card("Winter, Tormented Loner")
    every = {t for _, types in removal_edict_answers(winter, "edict") for t in types}
    forced = {
        t
        for _, types in removal_edict_answers(winter, "edict", forced_only=True)
        for t in types
    }
    assert "Planeswalker" in every
    assert forced == {"Creature"}


@pytest.mark.parametrize(
    "name",
    ["Unsummon", "Multiply by Zero", "Hapatra, the Desert Fang", "Clash of Elements"],
)
def test_soft_removal_is_opt_in(name):
    """The type-scoped presets read the shared removal walk's default, which
    never sees soft removal; ``soft=True`` (twohg_scan) does."""
    card = test_card(name)

    def board(answers):
        types = set().union(*(t for _, t in answers))
        return types & {"Creature", "Planeswalker", "Permanent"}

    assert not board(removal_edict_answers(card))
    assert board(removal_edict_answers(card, soft=True))


def test_a_shrink_on_the_card_itself_is_not_removal():
    """Undulating Witness's "{2}: this creature gets +1/-1" reaches no other
    permanent, though the shared walk counts any -X/-X."""
    row = classify_card(test_card("Undulating Witness"))
    assert row is None or row["removal_reach"] is None


def test_player_only_interaction_has_no_removal_reach():
    """Screeching Soulbreaker's "1 damage to each opponent" is interaction to the
    template roles, but it reaches no permanent."""
    row = _row("Screeching Soulbreaker")
    assert row["removal_reach"] is None
    assert {"what": "deal_damage", "how": "each opponent"} in row["doubles"]


@pytest.mark.parametrize("name", ["Grave Pact", "Syphon Mind"])
def test_each_other_player_veto(name):
    """phase reads "each other player" as ``player_scope: Opponent``; at a 2HG
    table it includes your partner."""
    row = _row(name)
    assert row["path"] == "ir+veto"
    assert row["doubles"] == []
    assert row["hits_partner"][0]["how"] == "each other player"


@pytest.mark.retirement_canary
def test_each_other_player_still_reads_opponent_canary():
    """Retirement canary for the "each other player" text veto in
    ``twohg_scan._vetoed``. Phase v0.94.0 gives Grave Pact's "each other player
    sacrifices" the same ``player_scope: Opponent`` as "each opponent". When phase
    gives it its own tag, this fails RETIRE-READY."""
    unit, c = _effect("Grave Pact", "sacrifice")
    assert effect_owner_player_scope(unit.node, c.node) == "Opponent", (
        "twohg_scan._vetoed: RETIRE-READY — phase no longer reads Grave Pact's "
        "'each other player' as player_scope Opponent. Teach effect_player_reach "
        "the new tag (it reaches your partner: 'each'), then delete _vetoed, the "
        "ir+veto path and this canary."
    )


@pytest.mark.retirement_canary
def test_typeless_mass_filter_canary():
    """Retirement canary for ``effect_player_reach``'s typeless-mass guard (a
    mass filter must name a card type), a phase-misparse workaround. Phase v0.94.0 parses Predictive Preparations' "put a
    +1/+1 counter on each of one or two target creatures" as a ``PutCounterAll``
    over a filter with no card type, which would otherwise read as "every
    permanent"."""
    (ability,) = test_phase_records("Predictive Preparations")[0]["abilities"]
    effect = ability["effect"]
    still_typeless = (
        effect["type"] == "PutCounterAll" and not effect["target"]["type_filters"]
    )
    assert still_typeless, (
        "effect_player_reach: RETIRE-READY — phase now parses Predictive "
        "Preparations with a typed or targeted filter. Delete the "
        "filter_core_types condition on effect_player_reach's mass arm (the "
        "typeless-mass guard) and this canary."
    )
    unit, c = _effect("Predictive Preparations", "place_counter")
    assert tag_of(c.node) == "PutCounterAll"
    assert not filter_core_types(effect_filter(c.node))
    assert effect_player_reach(unit.node, c.node) is None


def test_thalia_taxes_agree_with_the_stax_lanes():
    """Neither Thalia's tax has a concept node; the scan reads the raw cost
    static. Cross-check against the stax lanes, which read the same static."""
    survivor = {(s.key, s.scope) for s in test_signals("Thalia, the Survivor")}
    guardian = {(s.key, s.scope) for s in test_signals("Thalia, Guardian of Thraben")}
    assert ("stax_taxes", "opponents") in survivor
    assert ("symmetric_stax", "each") not in survivor
    assert ("symmetric_stax", "each") in guardian
    assert _row("Thalia, the Survivor")["hits_partner"] == []
    assert _row("Thalia, Guardian of Thraben")["doubles"] == []


def test_a_double_faced_card_unions_its_faces():
    row = _row("Bloodline Recollector // Ancestral Craving")
    assert row["step_triggers"]  # the creature face
    assert row["target_player"]  # the prepare spell


def test_an_emblem_is_skipped():
    emblem = {
        "name": "Test Emblem",
        "layout": "emblem",
        "type_line": "Emblem — Test",
        "oracle_text": "Whenever an opponent casts a spell, draw a card.",
    }
    assert classify_card(emblem) is None
    scan = twohg_scan([emblem, test_card("Rank Rat")])
    assert scan["size"] == 1
    assert [c["name"] for c in scan["cards"]] == ["Rank Rat"]


# ── the text path (the no-coverage degrade) ─────────────────────────────────


def _shape(row):
    """What a row says, minus the path-specific labels."""
    return {
        "buckets": {b for b in ("doubles", "hits_partner", "target_player") if row[b]},
        "steps": {(t["step"], t["whose"], t["fires"]) for t in row["step_triggers"]},
        "removal": row["removal_reach"],
    }


@pytest.mark.parametrize(
    "name",
    [
        "Rank Rat",
        "Cast Away Doubt",
        "Twisted Fates",
        "Howling Mine",
        "Verdant Kraken",
        "Grave Pact",
        "Your Fate Ends Here",
        "Sheoldred, Whispering One",
        "Extended Absence",
    ],
)
def test_text_path_agrees_with_the_ir(name):
    text = _no_ir_row(name)
    assert text["path"] == "text"
    assert _shape(text) == _shape(_row(name))


def test_text_path_labels():
    assert _no_ir_row("Grave Pact")["hits_partner"] == [
        {"what": "sacrifice", "how": "each other player"}
    ]
    assert _no_ir_row("Rank Rat")["doubles"] == [
        {"what": "discard", "how": "each opponent"}
    ]
    assert _no_ir_row("Your Fate Ends Here")["removal_reach"]["mv_floor"] == 3


# ── the set readout and its CLI ──────────────────────────────────────────────

_SET = [
    "Rank Rat",
    "Cast Away Doubt",
    "Twisted Fates",
    "Verdant Kraken",
    "Your Fate Ends Here",
    "Grave Pact",
    "Phyrexian Arena",
]


def test_twohg_scan_counts_and_renders():
    records = [test_card(n) for n in _SET]
    records.append(_no_ir("Howling Mine"))
    scan = twohg_scan(records, code="fra")
    assert scan["code"] == "FRA"
    assert scan["size"] == 8
    assert scan["coverage"] == {"ir": 7, "text": 1}
    names = [c["name"] for c in scan["cards"]]
    assert names == sorted(names)
    assert "Phyrexian Arena" not in names
    assert scan["counts"]["doubles"] == 1  # Rank Rat
    assert scan["counts"]["hits_partner"] == 3  # Cast Away Doubt, Grave Pact, Mine
    assert scan["counts"]["target_player"] == 1  # Twisted Fates
    assert scan["counts"]["step_triggers"] == 2  # Verdant Kraken, Howling Mine
    text = render_twohg_scan(scan)
    assert "Rank Rat [ir]: discard (each opponent)" in text
    assert "Howling Mine [text]: Draw, each turn: draw, once per head" in text
    assert "Grave Pact [ir+veto]: sacrifice (each other player)" in text
    assert "Your Fate Ends Here [ir]: hits planeswalkers; mana value 3+" in text
    assert "Verdant Kraken [ir]: Upkeep, each turn: make_token, once" in text


def test_cli(tmp_path):
    bulk = tmp_path / "bulk.json"
    bulk.write_text(
        json.dumps(
            [
                {
                    **test_card(name),
                    "id": f"id-{i}",
                    "set": "fra",
                    "collector_number": str(i),
                }
                for i, name in enumerate(_SET)
            ]
        )
    )
    res = CliRunner().invoke(main, ["--set", "FRA", "--bulk-data", str(bulk), "--json"])
    assert res.exit_code == 0, res.output
    scan = json.loads(res.output)
    assert scan["size"] == len(_SET)
    assert scan["counts"]["doubles"] == 1
    human = CliRunner().invoke(main, ["--set", "FRA", "--bulk-data", str(bulk)])
    assert human.exit_code == 0, human.output
    assert "Step triggers" in human.output
    missing = CliRunner().invoke(main, ["--set", "ZZZ", "--bulk-data", str(bulk)])
    assert missing.exit_code != 0
    assert "no cards found" in missing.output
