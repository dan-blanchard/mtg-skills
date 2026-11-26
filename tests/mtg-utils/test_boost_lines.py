"""The creature-boost lines of ADR-0065 (Dan's rulings, 2026-11-25), on real cards.

* ``effect_boost``: an effect (a spell, an activated or a triggered ability) that
  boosts ANOTHER creature or a group, until end of turn or perpetually.
* ``self_boost``: a creature raising its OWN power or toughness — ``""`` for a
  triggered or perpetual effect on itself, ``activated`` for an activated
  ability, ``counters`` for +1/+1 counters it puts on itself.
* ``boosts_others``: anything that makes your OTHER creatures bigger, by delivery
  — ``effect``, ``counters``, ``anthem``, ``attached``, and ``target_spell`` /
  ``target_ability`` for a boost of one chosen creature that isn't an opponent's.
* ``combat_trigger_boost``: a combat-keyed raise (its counter arm reads only a
  counter that raises power or toughness).

Real cards via ``mtg_utils.testkit`` (ADR-0056).
"""

from __future__ import annotations

import pytest

from mtg_utils._card_ir.crosswalk import controller_reach, counter_raises
from mtg_utils.testkit import test_signals


def _idents(name: str) -> set[tuple[str, str, str]]:
    return {(s.key, s.scope, s.subject) for s in test_signals(name)}


def _subjects(name: str, key: str) -> set[str]:
    return {sub for k, _scope, sub in _idents(name) if k == key}


# ── effect_boost: another creature or a group ────────────────────────────────


def test_a_pump_spell_is_an_effect_boost_of_one_chosen_creature():
    """Giant Growth's "Target creature gets +3/+3 until end of turn": an effect
    that boosts a creature, delivered as a spell that targets it (CR 115.1a)."""
    idents = _idents("Giant Growth")
    assert ("effect_boost", "you", "") in idents
    assert _subjects("Giant Growth", "boosts_others") == {"effect", "target_spell"}
    assert "self_boost" not in {k for k, _s, _sub in idents}


def test_a_team_pump_boosts_a_group_and_targets_none():
    """Overrun's "Creatures you control get +3/+3 and gain trample until end of
    turn": a group, no target."""
    assert ("effect_boost", "you", "") in _idents("Overrun")
    assert _subjects("Overrun", "boosts_others") == {"effect"}


def test_the_effect_boost_target_subject_is_retired():
    """Whether a boost targets one creature, and how, is boosts_others' now."""
    assert ("effect_boost", "you", "target") not in _idents("Giant Growth")


@pytest.mark.parametrize("name", ["Glaze Fiend", "Gloryscale Viashino"])
def test_a_trigger_that_pumps_only_the_card_is_a_self_boost(name):
    """ "Whenever another artifact you control enters, this creature gets +2/+2
    until end of turn" (Glaze Fiend), "Whenever you cast a multicolored spell,
    this creature gets +3/+3" (Gloryscale Viashino): the pump only ever lands on
    the card itself, so it boosts no other creature (ruling 1)."""
    idents = _idents(name)
    assert ("self_boost", "you", "") in idents
    assert ("effect_boost", "you", "") not in idents
    assert "boosts_others" not in {k for k, _s, _sub in idents}


def test_exalted_is_an_effect_boost():
    """CR 702.83a: "Whenever a creature you control attacks alone, that creature
    gets +1/+1 until end of turn" — timed once the keyword's pump gets its
    duration back (``misparsed_shapes``); the lone attacker can be another
    creature."""
    idents = _idents("Akrasan Squire")
    assert ("effect_boost", "you", "") in idents
    assert ("boosts_others", "you", "effect") in idents
    assert "self_boost" not in {k for k, _s, _sub in idents}


def test_battle_cry_is_an_effect_boost():
    """CR 702.91a: "each other attacking creature gets +1/+0 until end of turn"."""
    idents = _idents("Accorder Paladin")
    assert ("effect_boost", "you", "") in idents
    assert ("combat_trigger_boost", "you", "") in idents


def test_bushido_is_a_self_boost_in_combat():
    """CR 702.45a: "Whenever this creature blocks or becomes blocked, it gets
    +N/+N until end of turn" — the card itself, in combat."""
    idents = _idents("Samurai of the Pale Curtain")
    assert ("self_boost", "you", "") in idents
    assert ("combat_trigger_boost", "you", "") in idents
    assert ("effect_boost", "you", "") not in idents


def test_the_prowess_keyword_is_a_self_boost():
    """CR 702.108a: "Whenever you cast a noncreature spell, this creature gets
    +1/+1 until end of turn" — the keyword phase keeps unexpanded."""
    assert ("self_boost", "you", "") in _idents("Monastery Swiftspear")


def test_a_boost_of_the_vehicle_it_crews_is_another_creatures():
    """Veteran Motorist's "Whenever ~ crews a Vehicle, that Vehicle gets +1/+1
    until end of turn": the trigger's other object, the Vehicle (ruling 7)."""
    idents = _idents("Veteran Motorist")
    assert ("effect_boost", "you", "") in idents
    assert "self_boost" not in {k for k, _s, _sub in idents}


def test_a_boost_of_the_creature_in_combat_with_it_is_an_opponents():
    """Flailing Drake's "Whenever ~ blocks or becomes blocked by a creature,
    that creature gets +1/+1 until end of turn": the other combatant, which
    another player controls (CR 509.1a) — never a boost of yours, nor of itself
    (rulings 6 and 7)."""
    keys = {k for k, _s, _sub in _idents("Flailing Drake")}
    assert not keys & {
        "effect_boost",
        "self_boost",
        "boosts_others",
        "combat_trigger_boost",
    }


def test_a_raise_and_a_shrink_is_both():
    """Lash of Malice's "+2/-2": a pump and a shrink (ruling 6)."""
    idents = _idents("Lash of Malice")
    assert ("effect_boost", "you", "") in idents
    assert ("debuff_makers", "any", "") in idents


@pytest.mark.parametrize(
    ("controller", "reach"),
    [
        ("Opponent", "opponents"),  # "creatures your opponents control"
        ("You", "yours"),
        (None, "yours"),  # either side's: Bad Moon's "Black creatures"
        ("DefendingPlayer", "yours"),  # you defend when you cast Yare
    ],
)
def test_a_boost_only_opponents_creatures_get_is_never_yours(controller, reach):
    """No real card at v0.131.0 has a static boost only opponents' creatures
    get, so the rule an anthem's group is read by is tested on its own; Flailing
    Drake is its effect-side case."""
    assert controller_reach(controller) == reach


# ── self_boost: activated, counters, perpetual ───────────────────────────────


def test_firebreathing_is_the_activated_self_boost():
    """Shivan Dragon's "{R}: ~ gets +1/+0 until end of turn"; self_pump is
    retired into this subject."""
    idents = _idents("Shivan Dragon")
    assert ("self_boost", "you", "activated") in idents
    assert ("effect_boost", "you", "") not in idents
    assert "self_pump" not in {k for k, _s, _sub in idents}


def test_a_creature_putting_counters_on_itself_is_a_counters_self_boost():
    """Ajani's Pridemate's "Whenever you gain life, put a +1/+1 counter on ~":
    the self_counter_grow population, which keeps its own key."""
    idents = _idents("Ajani's Pridemate")
    assert ("self_boost", "you", "counters") in idents
    assert ("self_counter_grow", "you", "") in idents
    assert "boosts_others" not in {k for k, _s, _sub in idents}


def test_a_returned_card_that_grows_is_a_plain_self_boost():
    """Vladimir and Godfrey's graveyard activation returns the card and it
    perpetually gets +1/+1: recursion that grows it, not firebreathing."""
    assert _subjects("Vladimir and Godfrey", "self_boost") == {""}


@pytest.mark.parametrize(
    "name",
    ["Ichor Aberration", "Perennial Gravewarden", "Steady Tortoise // Harried Dash"],
)
def test_a_perpetual_self_grower_is_a_self_boost(name):
    assert ("self_boost", "you", "") in _idents(name)
    assert ("effect_boost", "you", "") not in _idents(name)


# ── boosts_others: counters, anthem, attached, targets ───────────────────────


def test_equipment_boosts_the_creature_it_is_attached_to_by_an_ability():
    """Bonesplitter's "Equipped creature gets +2/+0": attached, delivered by
    equip, an activated ability that targets (CR 702.6a)."""
    assert _subjects("Bonesplitter", "boosts_others") == {"attached", "target_ability"}


def test_a_boost_aura_is_attached_and_targets_as_a_spell():
    """Rancor's "Enchanted creature gets +2/+0 and has trample": an Aura spell
    targets as it is cast (CR 303.4a)."""
    assert _subjects("Rancor", "boosts_others") == {"attached", "target_spell"}


def test_a_counter_spell_on_one_creature_is_counters_and_a_spell():
    """Dragonscale Boon's "Put two +1/+1 counters on target creature"."""
    assert _subjects("Dragonscale Boon", "boosts_others") == {
        "counters",
        "target_spell",
    }


@pytest.mark.parametrize("name", ["Glorious Anthem", "Bad Moon"])
def test_an_anthem_reaching_your_creatures_is_an_anthem(name):
    """ "Creatures you control get +1/+1" and the symmetric "Black creatures get
    +1/+1" both reach yours."""
    assert ("boosts_others", "you", "anthem") in _idents(name)


def test_boosts_others_opens_no_avenue():
    from mtg_utils._analysis.signal_specs import avenue_spec_for

    sigs = [s for s in test_signals("Glorious Anthem") if s.key == "boosts_others"]
    assert sigs
    assert all(avenue_spec_for(s) is None for s in sigs)


# ── combat_trigger_boost ─────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Chub Toad", "Brushwagg", "Hooded Brawler"])
def test_phases_other_combat_triggers_are_combat_boosts(name):
    """Chub Toad's and Brushwagg's "blocks or becomes blocked" (phase's
    ``BlocksOrBecomesBlocked``) and exert, an optional cost to attack (CR
    701.43d): combat-keyed self-boosts carry both keys."""
    idents = _idents(name)
    assert ("combat_trigger_boost", "you", "") in idents
    assert ("self_boost", "you", "") in idents


def test_a_counter_that_raises_nothing_is_no_combat_boost():
    """Lara Croft's attack trigger puts a discovery counter on the card it
    exiles."""
    assert ("combat_trigger_boost", "you", "") not in _idents("Lara Croft, Tomb Raider")


@pytest.mark.parametrize(
    ("kind", "raises"),
    [("P1P1", True), ("P1P0", True), ("P0P1", True), ("M1M1", False), ("STUN", False)],
)
def test_only_a_pt_raising_counter_is_a_buff(kind, raises):
    """CR 122.1a: a +X/+Y counter adds X and Y; -1/-1 subtracts."""
    assert counter_raises(kind) is raises


# ── targeting_matters: who fires the payoff ──────────────────────────────────


def test_a_heroic_payoff_watches_spells_only():
    """ "Whenever you cast a spell that targets ~" (Akroan Crusader)."""
    assert ("targeting_matters", "any", "spell") in _idents("Akroan Crusader")


def test_a_spell_or_ability_payoff_watches_both():
    """ "Whenever ~ becomes the target of a spell or ability" (Cephalid
    Illusionist)."""
    assert ("targeting_matters", "any", "") in _idents("Cephalid Illusionist")


def test_an_activated_ability_payoff_watches_abilities_only():
    """ "Whenever one or more creatures you control become the target of an
    activated ability" (Professor Hojo)."""
    assert ("targeting_matters", "any", "ability") in _idents("Professor Hojo")


# ── The second pass (review of 8b): anaphora, choices, movers, statics ────────


def test_a_heroic_creature_putting_counters_on_itself_grows_itself():
    """Fabled Hero's "put a +1/+1 counter on it": the card (the spell targets it),
    not another creature."""
    idents = _idents("Fabled Hero")
    assert ("self_boost", "you", "counters") in idents
    assert "boosts_others" not in {k for k, _s, _sub in idents}


@pytest.mark.parametrize("name", ["Thriving Rhino", "Riparian Tiger"])
def test_an_energy_self_grower_grows_itself(name):
    """ "you may pay {E}{E}. If you do, put a +1/+1 counter on it" / "it gets
    +2/+2": the card, so no effect_boost and no boosts_others."""
    keys = {k for k, _s, _sub in _idents(name)}
    assert "self_boost" in keys
    assert not keys & {"effect_boost", "boosts_others"}


@pytest.mark.parametrize("name", ["Agitator Ant", "Daily Regimen", "Kayla's Command"])
def test_a_placement_that_targets_nothing_has_no_target_subject(name):
    """A creature chosen as the ability resolves (Agitator Ant's "each player may
    put two +1/+1 counters on a creature they control"), the creature an Aura
    is attached to (Daily Regimen's "on enchanted creature" — the Aura spell
    targets, the ability doesn't), "each creature you control" (Kayla's
    Command): CR 115.10a, affected is not targeted."""
    subjects = _subjects(name, "boosts_others")
    assert "counters" in subjects
    assert "target_ability" not in subjects
    if name == "Kayla's Command":
        assert "target_spell" not in subjects


def test_a_delayed_trigger_a_spell_creates_targets_as_an_ability():
    """Ride the Avalanche's "When you next cast a spell this turn, put X +1/+1
    counters on up to one target creature": a delayed triggered ability (CR
    603.7), targeted as an ability (115.1d), not as the spell."""
    subjects = _subjects("Ride the Avalanche", "boosts_others")
    assert "target_ability" in subjects
    assert "target_spell" not in subjects


@pytest.mark.parametrize("name", ["Weapon Rack", "Simic Initiate"])
def test_moving_a_counter_onto_another_creature_boosts_it(name):
    """CR 122.5: to move a counter is to put it onto a second object — Weapon
    Rack's "Move a +1/+1 counter from this artifact onto target creature", graft
    (702.58a)."""
    assert ("boosts_others", "you", "counters") in _idents(name)


@pytest.mark.parametrize("name", ["Weapon Rack", "Afiya Grove", "Costume Closet"])
def test_a_noncreature_holding_counters_does_not_grow_itself(name):
    """A noncreature permanent has no power or toughness (CR 208.3)."""
    assert not _subjects(name, "self_boost")


def test_a_grant_of_growth_to_the_enchanted_creature_is_attached():
    """Sunbond: "Enchanted creature has 'Whenever you gain life, put that many
    +1/+1 counters on this creature'" grows the creature it enchants."""
    assert _subjects("Sunbond", "boosts_others") == {"attached", "target_spell"}
    assert not _subjects("Sunbond", "self_boost")


def test_a_bestow_creature_boosts_the_creature_it_enchants():
    """Nighthowler's "This creature and enchanted creature each get +X/+X":
    attached, its bestowed spell targets (CR 702.103b), no anthem."""
    subjects = _subjects("Nighthowler", "boosts_others")
    assert {"attached", "target_spell"} <= subjects
    assert "anthem" not in subjects


def test_an_anaphoric_targeted_pump_targets():
    """Spidery Grasp's "Untap target creature. It gets +2/+4": the "it" is the
    chain's own target."""
    assert _subjects("Spidery Grasp", "boosts_others") == {"effect", "target_spell"}


def test_a_static_self_boost_is_its_own_subject():
    """Kird Ape's "This creature gets +1/+2 as long as you control a Forest"; a
    characteristic-defining P/T (Tarmogoyf's "*/1+*", CR 604.3) is no boost."""
    assert _subjects("Kird Ape", "self_boost") == {"static"}
    assert not _subjects("Tarmogoyf", "self_boost")


def test_a_granted_targeting_trigger_names_its_source():
    """Livewire Lash grants "Whenever this creature becomes the target of a
    spell, …": a payoff only a spell fires."""
    assert _subjects("Livewire Lash", "targeting_matters") == {"spell"}


def test_bill_potts_reads_both_halves():
    """ "Whenever you cast an instant or sorcery spell that targets only Bill
    Potts or activate an ability that targets only Bill Potts": phase types the
    cast half and leaves the activation an ``Unknown`` mode, which the clause
    grammar reads (``crosswalk.parked_targeting_payoffs``): spells and
    abilities both, ``""``."""
    assert _subjects("Bill Potts", "targeting_matters") == {"", "you"}


def test_a_granted_lord_targeting_trigger_names_its_source():
    """Kira, Great Glass-Spinner grants "Whenever this creature becomes the
    target of a spell or ability for the first time each turn": either."""
    assert _subjects("Kira, Great Glass-Spinner", "targeting_matters") == {""}


def test_an_aura_upkeep_pump_is_the_enchanted_creatures():
    """Paroxysm's "it gets +3/+3" lands on the enchanted creature (CR 208.3)."""
    assert ("effect_boost", "you", "") in _idents("Paroxysm")
    assert not _subjects("Paroxysm", "self_boost")


def test_boosts_others_reads_a_bridge_rows_effect_boost():
    """The umbrella runs after every lane and the bridge rows: Alex Wilder's
    conditional pump is a ledger row's ``effect_boost`` (no structural one), and
    it is ``boosts_others|you|effect`` all the same."""
    from mtg_utils._analysis.tree_synthesis import has_structural_effect_boost
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    test_signals("Alex Wilder, Runaway")
    assert not any(
        has_structural_effect_boost(t)
        for t in trees_for(test_card("Alex Wilder, Runaway"))
    )
    assert ("boosts_others", "you", "effect") in _idents("Alex Wilder, Runaway")


def test_every_effect_boost_holder_holds_boosts_others_effect():
    """Over the whole snapshot: the umbrella's ``effect`` is every effect_boost
    card."""
    from mtg_utils._analysis.signals import extract_signals
    from mtg_utils.testkit import snapshot_records

    missing = []
    for record in snapshot_records():
        idents = {(s.key, s.subject) for s in extract_signals(record)}
        if ("effect_boost", "") in idents and ("boosts_others", "effect") not in idents:
            missing.append(record["name"])
    assert not missing


# ── Review round 4 (2026-11-25) ─────────────────────────────────────────────


@pytest.mark.parametrize("name", ["Metallic Mimic", "Arwen, Weaver of Hope"])
def test_an_enters_with_counters_replacement_boosts_others(name):
    """ "Each other creature you control enters with an additional +1/+1
    counter": phase's replacement names the entering creature ``SelfRef``; it is
    the watched creature, not the card."""
    assert "counters" in _subjects(name, "boosts_others")
    assert "counters" not in _subjects(name, "self_boost")


def test_a_would_die_replacement_on_the_card_grows_it():
    """Ravenous Slime's "If a creature an opponent controls would die, instead
    exile it and put … +1/+1 counters … on ~": the card itself."""
    assert "counters" in _subjects("Ravenous Slime", "self_boost")


def test_a_pending_enters_with_counter_is_another_creatures():
    """Yuna, Grand Summoner's "When you next cast a creature spell this turn,
    that creature enters with two additional +1/+1 counters": not Yuna."""
    assert "counters" not in _subjects("Yuna, Grand Summoner", "self_boost")
    assert "counters" in _subjects("Yuna, Grand Summoner", "boosts_others")


def test_a_modal_mode_its_it_is_the_chosen_creature():
    """Mikey & Mona's "Target player chooses a creature they control and puts two
    +1/+1 counters on it": the "it" in a mode is the mode's creature."""
    assert "counters" in _subjects("Mikey & Mona, Mutant Sitters", "boosts_others")
    assert not _subjects("Mikey & Mona, Mutant Sitters", "self_boost")


def test_a_returned_card_is_no_chosen_target():
    """Defy Death's "Return target creature card from your graveyard to the
    battlefield. If it's an Angel, put two +1/+1 counters on it": the target is a
    card in a graveyard, no creature to boost as a spell."""
    assert _subjects("Defy Death", "boosts_others") == {"counters"}


@pytest.mark.parametrize(
    "name", ["First Responder", "Torrent Sculptor // Flamethrower Sonata"]
)
def test_a_counter_after_a_move_away_is_the_cards(name):
    """ "Return another creature you control to its owner's hand, then put …
    +1/+1 counters … on this creature": the card, not the bounced creature."""
    assert "counters" in _subjects(name, "self_boost")
    assert not _subjects(name, "boosts_others")


def test_a_delayed_triggers_it_is_no_chosen_target():
    """Love on the Battlefield's "those creatures gain first strike … Whenever
    either of those creatures deals combat damage to a player this combat, put a
    +1/+1 counter on it": the attacker of yours, untargeted."""
    assert _subjects("Love on the Battlefield", "boosts_others") == {"counters"}


@pytest.mark.parametrize("name", ["Vigor", "Panther Habit"])
def test_a_damage_replacement_counter_is_the_damaged_creatures(name):
    """ "If damage would be dealt to another creature you control, prevent that
    damage. Put a +1/+1 counter on that creature" (Vigor); "equipped creature"
    (Panther Habit): phase's ``PostReplacementDamageTarget`` is the watched
    creature."""
    assert "counters" in _subjects(name, "boosts_others")


def test_a_manifested_creature_is_yours():
    """Underwater Tunnel // Slimy Aquarium's door: "manifest dread, then put a
    +1/+1 counter on that creature"."""
    assert "counters" in _subjects(
        "Underwater Tunnel // Slimy Aquarium", "boosts_others"
    )


def test_a_counted_counter_on_the_card_is_its_own():
    """Joven and Chandler's "put a number of +1/+1 counters equal to that
    artifact's mana value on ~": the card grows (the recovery's on-self read)."""
    assert "counters" in _subjects("Joven and Chandler", "self_boost")
    assert not _subjects("Joven and Chandler", "boosts_others")


def test_gear_that_attaches_only_to_an_opponents_creature_is_no_boost():
    """Bloodthirsty Blade's "{1}: Attach this Equipment to target creature an
    opponent controls" (the coordinator's call; its ruling: "There's normally no
    way to have it attached to your own creature"): no voltron gear either, the
    read ``counters_voltron.gear_pump_subjects`` both keys share. Bonesplitter
    still is."""
    assert not _subjects("Bloodthirsty Blade", "boosts_others")
    assert not _subjects("Bloodthirsty Blade", "voltron_makers")
    assert _subjects("Bonesplitter", "boosts_others") == {"attached", "target_ability"}
    assert "pump" in _subjects("Bonesplitter", "voltron_makers")


@pytest.mark.parametrize(
    "name",
    [
        "Rose Tyler",
        "Gavel of the Righteous",
        "Beastmaster Ascension",
        "Moira Brown, Guide Author",
    ],
)
def test_a_combat_counter_a_static_turns_into_power_is_a_combat_boost(name):
    """Dan's ruling (2026-11-25): Rose Tyler's attack-trigger time counters feed
    "+1/+1 for each time counter on it"; Gavel's charge counter, "+1/+1 for each
    counter on this Equipment"; Beastmaster Ascension's quest counters, its
    seven-counter anthem; Moira Brown's quest counter, her Book's "+1/+1 for each
    quest counter among permanents you control"."""
    assert ("combat_trigger_boost", "you", "") in _idents(name)


@pytest.mark.parametrize("name", ["Beorn the Fierce", "Sephiroth, Fallen Hero"])
def test_a_combat_counter_no_static_counts_is_no_combat_boost(name):
    """Beorn's trample counter is a keyword counter (its +2/+2 is the Bear
    lord's, by the type change); Sephiroth's cell counter makes a creature
    modified, whose base P/T a one-shot sets (CR 613.4b), no static's raise."""
    assert ("combat_trigger_boost", "you", "") not in _idents(name)


def test_counter_fed_statics_reads_kind_and_site():
    from mtg_utils._card_ir.crosswalk import counter_fed_statics
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    def fed(name: str) -> frozenset:
        card = test_card(name)
        return frozenset().union(
            *(counter_fed_statics(t) for t in trees_for(card, bulk=card))
        )

    assert ("time", "self") in fed("Rose Tyler")
    assert ("*", "self") in fed("Gavel of the Righteous")
    assert ("quest", "self") in fed("Beastmaster Ascension")
    assert ("quest", "yours") in fed("Moira Brown, Guide Author")
    assert not fed("Beorn the Fierce")


def test_a_flattened_boon_is_a_stack_card_boost():
    """ "You get a boon with \\"When you cast your next creature spell, it
    perpetually gets +1/+0.\\"" (Flaming Fist Duskguard; Valiant Farewell's
    leaves-the-battlefield one): a creature spell's perpetual boost."""
    assert "stack" in _subjects("Flaming Fist Duskguard", "card_boost")
    assert "stack" in _subjects("Valiant Farewell", "card_boost")
    assert not _subjects("Dark Salvation", "card_boost")


# ── Phase v0.133.0's block: parked targeting payoffs, granted boost keywords ───


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # "Whenever ~ becomes the target of an ability that targets only it"
        ("Agrus Kos, Eternal Soldier", {"ability"}),
        # "… becomes the target of an ability of a land you control named …"
        ("Skophos Maze-Warden", {"ability"}),
        # "Whenever you become the target of a spell"
        ("Dormant Gomazoa", {"spell"}),
        # "Whenever you cast a spell that targets a creature you control"
        ("Iron Fist, Living Weapon", {"spell", "you"}),
        ("Ms. Marvel, Kamala Khan", {"spell", "you"}),
    ],
)
def test_parked_targeting_payoff_canary(name, subjects):
    """A targeting payoff phase parks (an ``Unknown`` trigger mode, a whole-ability
    residue) names its source through the clause grammar
    (``crosswalk.parked_targeting_payoffs``), so it is offered only the cards
    that fire it. Fails once phase types the trigger: then the typed read
    (``targeting_trigger_source``) takes over and the parked one can go."""
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    trees = trees_for(test_card(name))
    assert any(
        next(t.unknown_trigger_modes(), None) is not None
        or next(t.residues("granter_reference_unreached"), None) is not None
        for t in trees
    ), (
        f"parked targeting payoff: RETIRE-READY — phase types {name}'s trigger. "
        "Delete its case here; once none is left, retire "
        "crosswalk.parked_targeting_payoffs and clause_grammar.targeting_payoffs."
    )
    assert _subjects(name, "targeting_matters") == subjects


def test_a_dropped_half_of_a_typed_trigger_names_its_source():
    """Brine Comber's back face: "Whenever this Aura enters or enchanted creature
    becomes the target of an Aura spell", typed as the enters trigger alone."""
    assert _subjects("Brine Comber // Brinebound Gift", "targeting_matters") == {
        "spell"
    }


@pytest.mark.parametrize(
    ("text", "reads"),
    [
        ("Whenever ~ becomes the target of a spell or ability", {("", "any")}),
        (
            "Whenever ~ becomes the target of a spell or ability an opponent controls",
            {("", "opponents")},
        ),
        ("Whenever you cast a spell that targets ~", {("spell", "you")}),
        ("Whenever you activate an ability that targets only ~", {("ability", "you")}),
        ("Whenever you attack", set()),
    ],
)
def test_targeting_payoffs_grammar(text, reads):
    from mtg_utils._card_ir.clause_grammar import targeting_payoffs

    assert {(p.source, p.side) for p in targeting_payoffs(text)} == reads


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # "Other creatures you control have prowess" (CR 702.108a)
        ("Bria, Riptide Rogue", {"anthem"}),
        ("Narset, Enlightened Exile", {"anthem"}),
        # "Equipped creature has prowess": equip is an ability (CR 702.6a)
        ("Wizard's Staff", {"attached", "target_ability"}),
        # "Enchanted creature has prowess and ward {2}": an Aura spell targets
        ("Taught by Narset", {"attached", "target_spell"}),
        # exalted on any permanent of yours boosts your lone attacker (702.83a)
        ("Merchant of Truth", {"anthem"}),
        ("Rashel, Fist of Torm", {"anthem"}),
        ("Zarda, the Power Princess", {"anthem"}),
        # a group grant that lasts a turn is an effect, as a one-shot team pump
        # is (the coordinator's choice): a trigger's, a sorcery's
        ("Rammas Echor, Ancient Shield", {"effect"}),
        ("Vivien's Stampede", {"effect"}),
        # a standing grant, a static's, is an anthem
        ("Sublime Archangel", {"anthem", "effect"}),  # its printed exalted: effect
    ],
)
def test_a_granted_boost_keyword_boosts_your_other_creatures(name, subjects):
    """Dan's ruling (2026-11-25): a grant of a keyword whose whole effect is a
    power/toughness boost — prowess, exalted, bushido (CR 702.108a, 702.83a,
    702.45a), rampage, melee — boosts your other creatures, filed by how it is
    granted (ADR-0065)."""
    assert _subjects(name, "boosts_others") == subjects


@pytest.mark.parametrize(
    ("name", "subjects"),
    [
        # battle cry granted to others (CR 702.91a): a team boost
        ("Syr Joshua and Syr Saxon", {"anthem"}),
        # battle cry given to itself boosts the other attackers, as printed
        ("Reckless Pyrosurfer", {"effect"}),
        # parked "~ perpetually gains battle cry"
        ("Marshland Hordemaster", {"effect"}),
        # one target creature of yours: the target flag, by delivery
        ("Fang of the Pack", {"effect", "target_ability"}),
        ("Rapid Fire", {"effect", "target_spell"}),
        ("Sensei Golden-Tail", {"effect", "target_ability"}),
    ],
)
def test_battle_cry_and_a_targeted_boost_keyword_boost_others(name, subjects):
    """Dan's ruling (2026-11-25): battle cry counts too; the coordinator's
    decision: a boost keyword granted to one target creature that isn't an
    opponent's carries the target flag."""
    assert _subjects(name, "boosts_others") == subjects


@pytest.mark.parametrize("name", ["Fumiko the Lowblood", "Cavalry Master"])
def test_a_boost_keyword_on_itself_or_flanking_is_no_grant_to_others(name):
    """Fumiko's "has bushido X" grows itself; flanking shrinks the blocker
    (CR 702.25a), so Cavalry Master's flanking grant is no boost."""
    assert not _subjects(name, "boosts_others")


def test_a_quoted_payoff_in_a_typed_triggers_description_is_not_its_own():
    """Niambi, Beloved Protector's enters trigger hands the returned creature
    "Whenever ~ becomes the target of a spell or ability, draw a card": the
    description scan of ``parked_targeting_payoffs`` leaves quoted words out,
    while Brine Comber's back face's unquoted dropped half is read."""
    from mtg_utils._card_ir.clause_grammar import targeting_payoffs

    niambi = (
        "When ~ enters, if you cast it, choose target nonlegendary creature card "
        "in your graveyard that was put there from the battlefield this turn. "
        'Return it to the battlefield. It perpetually gains "Whenever ~ becomes '
        'the target of a spell or ability, draw a card."'
    )
    assert targeting_payoffs(niambi, quoted=False) == frozenset()
    assert targeting_payoffs(niambi)
    from mtg_utils._card_ir.crosswalk import parked_targeting_payoffs
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.testkit import test_card

    assert not any(
        parked_targeting_payoffs(t)
        for t in trees_for(test_card("Niambi, Beloved Protector"))
    )
