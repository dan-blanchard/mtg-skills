"""The template-role owner (ADR-0051): ``roles.is_ramp`` is ONE answer, read off the
signal path, for every surface that counts or sources ramp.

Real snapshot cards throughout (``mtg_utils.testkit``) — the production
``extract_signals`` path, not hand-built oracle dicts. The text degrade
(``card_classify.ramp_by_text``) keeps its own tests in ``test_card_classify.py``.
"""

import pytest

from mtg_utils._analysis import roles
from mtg_utils._analysis.roles import (
    DeckMana,
    _restriction_admits,
    is_ramp,
    is_reliable_ramp,
    role_of,
)
from mtg_utils._card_ir.crosswalk.reads import (
    ATTACHED_OBJECT_PREDICATES,
    ObjectFacts,
    filter_predicates,
    iter_typed_nodes,
    names_attached_object,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._tuner.issues import ROLE_SEARCH
from mtg_utils.card_classify import is_land
from mtg_utils.testkit import snapshot_records, test_card, test_signals
from mtg_utils.theme_presets import get_preset, has_signal_coverage


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


@pytest.mark.parametrize(
    "name",
    [
        "Sol Ring",  # rock
        "Llanowar Elves",  # dork
        "Cultivate",  # land-fetch-to-battlefield (lf_ramp)
        # Number-word mana — the text read's blind spot ("Add three mana of any one
        # color" has no "{" / "one mana" after "add"), so these never counted.
        "Gilded Lotus",
        "Black Lotus",
        "Zaxara, the Exemplary",
        "Azusa, Lost but Seeking",  # extra land PLAY (the concept arm)
        "Burgeoning",  # land PUT (extra_land_drop)
        "Dockside Extortionist",  # a Treasure maker you keep
        "Tireless Provisioner",  # "a Food token or a Treasure token": your choice
        # Firebending isn't ramp (below), but chapter II's "Add one mana of any
        # color" is a ritual.
        "The Legend of Roku",
        # Puts basic lands onto the battlefield (lf_ramp), though phase parks its
        # search: the put is the structure left (parked_search_puts_onto_battlefield).
        "Surveyor's Scope",
    ],
)
def test_ramp_is_read_off_the_signal_path(name):
    card = _real(name)
    assert is_ramp(card)
    assert "ramp" in role_of(card)


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Bolt",
        "Demonic Tutor",
        "Sylvan Scrying",  # a land tutor TO HAND adds no mana and drops no land
        "Murder",
        # Near misses (Dan, 2026-10-09): firebending's mana comes only as the
        # creature attacks and lasts until end of combat (CR 702.189a), so no
        # firebending card is ramp — a bearer, a token maker or a grant.
        "Uncle Iroh",
        "Fire Nation Attacks",
        "Sozin's Comet",
    ],
)
def test_non_ramp_is_not_ramp(name):
    assert not is_ramp(_real(name))


def test_a_land_fetch_to_the_battlefield_is_not_a_tutor():
    """Surveyor's Scope's search puts basic lands onto the battlefield: ramp, never
    a tutor (the lf_ramp convention, ``_tutor_lane``)."""
    scope = _real("Surveyor's Scope")
    assert "tutor" not in {s.key for s in test_signals(scope["name"])}
    assert not get_preset("tutors").matches(scope)


def test_a_land_is_the_mana_base_never_ramp():
    # Command Tower fires the `ramp` KEY (a fixing land) — the role and its preset
    # still say no: lands are the `lands` role and the land band's business (CR 305),
    # and a land-filled search page would starve the tuner's ramp sourcing.
    tower = _real("Command Tower")
    assert "ramp" in {s.key for s in test_signals("Command Tower")}
    assert not get_preset("ramp").matches(tower)
    assert not is_ramp(tower)
    assert role_of(tower) == {"lands"}


def test_a_treasure_handed_to_an_opponent_is_not_ramp():
    # Both fire `treasure_makers|you` (phase scopes the maker, not the recipient);
    # the Token node's own `owner` tells them apart.
    offer = _real("An Offer You Can't Refuse")  # "Its controller creates two Treasure"
    assert "treasure_makers" in {s.key for s in test_signals(offer["name"])}
    assert not is_ramp(offer)
    assert is_ramp(_real("Smothering Tithe"))
    # One Treasure for you, one for an opponent — still yours.
    assert is_ramp(_real("Generous Plunderer"))


def test_a_card_the_signal_path_cannot_see_degrades_to_text():
    rock = {
        "name": "Test Rock",
        "type_line": "Artifact",
        "oracle_text": "{T}: Add {C}.",
    }
    assert not has_signal_coverage(rock)
    assert is_ramp(rock)
    bear = {"name": "Test Bear", "type_line": "Creature — Bear", "oracle_text": ""}
    assert not is_ramp(bear)


def test_covered_card_never_falls_back_to_text():
    # Covered + no ramp signal ⇒ not ramp, even when the text read would say yes: a
    # DFC whose BACK face is a land joins "{T}: Add …" into the card's oracle text.
    bolt = _real("Lightning Bolt")
    assert has_signal_coverage(bolt)
    lying = {**bolt, "oracle_text": "{T}: Add {R}."}
    assert not is_ramp(lying)


def _no_ir(name: str) -> dict:
    """The real record with no ``oracle_id``: the signal path can't see it, the
    shape of a set newer than the phase pin (as ``test_twohg_scan`` strips it)."""
    return {k: v for k, v in test_card(name).items() if k != "oracle_id"}


@pytest.mark.parametrize("name", ["Murder", "Lightning Bolt", "Wrath of God"])
def test_removal_degrades_to_text_without_coverage(name):
    """``set-scan`` on a set phase hasn't parsed still counts its removal: the
    interaction role reads ``card_classify.removal_reach_by_text``, the degrade
    ``twohg_scan``'s removal reach shares."""
    card = _no_ir(name)
    assert not has_signal_coverage(card)
    assert "interaction" in role_of(card)


@pytest.mark.parametrize("name", ["Grizzly Bears", "Divination"])
def test_no_removal_text_no_interaction_without_coverage(name):
    assert "interaction" not in role_of(_no_ir(name))


def test_covered_card_never_falls_back_to_removal_text():
    # Covered + no interaction preset ⇒ no interaction, whatever the text says.
    bears = _real("Grizzly Bears")
    lying = {**bears, "oracle_text": "Destroy target creature."}
    assert has_signal_coverage(lying)
    assert "interaction" not in role_of(lying)


@pytest.mark.parametrize(
    "name",
    [
        "Lightning Bolt",  # "any target" (CR 115.4) — direct_damage alone
        "Chain Lightning",  # "any target" — direct_damage alone
        "Mayhem Devil",  # a permanent's "1 damage to any target" trigger
        "Flame Slash",  # creature-only burn (the `removal` key)
        "Electrickery",  # creature-only burn, either mode
        "Fiery Confluence",  # modal: a creature mode beside the player modes
        "Screaming Nemesis",  # "any other target"
        "Comet Storm",  # "Choose any target … deals X damage to each of them"
    ],
)
def test_damage_that_can_reach_a_permanent_is_interaction(name):
    """Damage a battle, creature or planeswalker can be dealt (CR 120.1) is
    removal: the ``removal`` lane reads "any target" burn (CR 115.4) itself."""
    card = _real(name)
    assert get_preset("removal").matches(card)
    assert "interaction" in role_of(card)


@pytest.mark.parametrize(
    "name",
    [
        "Mogis, God of Slaughter",  # "2 damage to that player"
        "Enchanter's Bane",  # an enchantment deals damage to its controller
        "Fate Unraveler",  # "1 damage to that player"
        "Sulfuric Vortex",  # "2 damage to that player"
        "Spiteful Visions",  # "1 damage to that player"
        "Guttersnipe",  # "2 damage to each opponent"
        "Harsh Mentor",  # "2 damage to that player"
        "Aggressive Sabotage",  # "target player discards … 3 damage to that player"
    ],
)
def test_player_only_damage_is_not_interaction(name):
    """Damage to a player makes them lose life (CR 120.3a) and removes nothing from
    the board: the punisher fires ``direct_damage`` (the ``burn`` preset), never a
    removal-family key, so neither the ``removal`` preset the tuner sources
    interaction by nor the role it counts by reads it (ADR-0051)."""
    card = _real(name)
    assert get_preset("burn").matches(card)
    assert not get_preset("removal").matches(card)
    assert not get_preset("creature-removal").matches(card)
    assert "interaction" not in role_of(card)


@pytest.mark.parametrize("name", ["Blasphemous Act", "Pyroclasm"])
def test_damage_sweepers_stay_interaction_and_board_wipe(name):
    assert {"interaction", "board_wipe"} <= role_of(_real(name))


@pytest.mark.parametrize(
    "name",
    [
        "Elesh Norn, Grand Cenobite",  # "creatures your opponents control get -2/-2"
        "Night of Souls' Betrayal",  # "all creatures get -1/-1"
    ],
)
def test_a_static_shrink_on_a_population_is_a_board_wipe(name):
    """A continuous toughness shrink on a population of creatures (layer 7c, CR
    613.4c) puts every creature it brings to 0 toughness into its owner's
    graveyard (CR 704.5f). The ``population_shrink`` key carries it, so the
    board-wipe preset reads the signals index alone."""
    assert "board_wipe" in role_of(_real(name))
    assert "population_shrink" in {s.key for s in test_signals(name)}


@pytest.mark.parametrize(
    "name",
    [
        "Skullclamp",  # "Equipped creature gets +1/-1" (CR 301.5a)
        "Dead Weight",  # "Enchanted creature gets -2/-2" (CR 303.4)
        "Nameless Inversion",  # "Target creature gets +3/-3"
    ],
)
def test_a_shrink_on_one_creature_is_not_a_board_wipe(name):
    """The creature an Equipment or Aura is attached to, or a spell's target, is
    one creature, not a board: Skullclamp was the tuner's board-wipe upgrade
    pick (2026-10-19)."""
    assert "board_wipe" not in role_of(_real(name))
    assert "population_shrink" not in {s.key for s in test_signals(name)}


def test_a_targeted_toughness_shrink_is_removal():
    """Nameless Inversion's "+3/-3" on its target can put it to 0 toughness
    (CR 704.5f): interaction. A creature lowering its own toughness (Leaping
    Lizard's "-0/-1") removes nothing."""
    assert "interaction" in role_of(_real("Nameless Inversion"))
    assert "interaction" not in role_of(_real("Leaping Lizard"))


def test_a_mass_bounce_is_a_board_wipe():
    """Returning every nonland permanent an opponent has to hand clears their
    board as a wipe does: Cyclonic Rift overloaded (CR 702.96a), Evacuation."""
    assert "board_wipe" in role_of(_real("Cyclonic Rift"))
    assert "board_wipe" in role_of(_real("Evacuation"))


def test_damage_to_each_player_is_not_a_board_wipe():
    """Damage only to players removes nothing from the board (CR 120.3a): the
    board-wipe view reads sweeps, not ``symmetric_damage_each``."""
    card = _real("Price of Progress")
    assert not get_preset("board-wipe").matches(card)
    assert "board_wipe" not in role_of(card)


def test_the_preset_and_the_role_agree_on_every_covered_card():
    """The agreement test that replaces the "mirrors is_ramp" comments: over the whole
    snapshot, the preset the tuner SEARCHES by and the role the budgets row COUNTS by
    are the same set — and the text degrade is never consulted for a covered card."""
    preset = get_preset(ROLE_SEARCH["ramp"]["preset_names"][0])
    # A card phase has no record for (Undercity, a folded dungeon) is no covered
    # card: the role reads its text degrade.
    records = [r for r in snapshot_records() if has_signal_coverage(r)]
    matched = {r["name"] for r in records if preset.matches(r)}
    counted = {r["name"] for r in records if "ramp" in role_of(r)}
    assert matched == counted
    assert len(matched) > 40


def test_the_board_wipe_preset_and_the_role_agree_on_every_covered_card():
    """The board-wipe twin of the ramp agreement: the preset the tuner SEARCHES
    by (the spec ``roles`` exports, which the tuner reads unchanged) and the role
    the budgets row COUNTS by are the same set over the whole snapshot — the
    one-sided shrinks included (they used to split: the role counted Elesh
    Norn's -2/-2, the preset excluded Massacre Wurm)."""
    assert ROLE_SEARCH["board_wipe"] is roles.ROLE_SEARCH["board_wipe"]
    preset = get_preset(ROLE_SEARCH["board_wipe"]["preset_names"][0])
    records = snapshot_records()
    matched = {r["name"] for r in records if preset.matches(r)}
    counted = {r["name"] for r in records if "board_wipe" in role_of(r)}
    assert matched == counted
    assert {
        "Wrath of God",
        "Cyclonic Rift",
        "Massacre Wurm",
        "Elesh Norn, Grand Cenobite",
    } <= matched
    assert len(matched) > 40


@pytest.mark.parametrize("name", ["Massacre Wurm", "Bite of the Black Rose"])
def test_a_one_sided_mass_shrink_is_a_board_wipe(name):
    """ "Creatures your opponents control get -2/-2" clears the opponents' board
    as a one-sided destroy (Plague Wind) does, so the board-wipe job counts it —
    Bite of the Black Rose's from a vote branch. The ``mass_removal`` key stays
    the symmetric shrink the mass-death payoffs read; ``population_shrink``
    carries the one-sided one."""
    assert "board_wipe" in role_of(_real(name))
    keys = {s.key for s in test_signals(name)}
    assert "mass_removal" not in keys
    assert "population_shrink" in keys


@pytest.mark.parametrize(
    "name",
    [
        "Baneblade Scoundrel",  # each creature blocking it gets -1/-1
        "Knight of Valor",  # flanking: only the creatures blocking it (CR 702.25a)
        "The Eagles Are Coming!",  # returns the chosen creatures, not the board
    ],
)
def test_a_combat_or_chosen_set_effect_is_not_a_board_wipe(name):
    """The old compat mass marker read these as sweeps; the lanes' vetoes, which
    the role now reads, don't."""
    assert "board_wipe" not in role_of(_real(name))


@pytest.mark.parametrize(
    ("name", "predicate"),
    [
        ("Champion of the Flame", "AttachedToRecipient"),
        ("Halvar, God of Battle // Sword of the Realms", "HasAnyAttachmentOf"),
    ],
)
def test_attachment_state_predicates_name_no_single_object(name, predicate):
    """Phase's ``AttachedToRecipient`` is the Auras and Equipment attached to a
    creature (Champion of the Flame's "+2/+2 for each Aura and Equipment attached
    to it"); ``HasAnyAttachmentOf`` is every enchanted or equipped creature
    (Halvar's "Creatures you control that are enchanted or equipped have double
    strike" — its ruling: a creature "is enchanted or equipped if there's an Aura
    or an Equipment attached to it"). Neither is THE object an Equipment or Aura
    is attached to (CR 301.5a, 303.4b), so neither joins
    ``ATTACHED_OBJECT_PREDICATES``, the attachment veto the sweep reads share."""
    test_signals(name)
    carriers = [
        n
        for tree in trees_for(test_card(name))
        for unit in tree.units
        for n in iter_typed_nodes(unit.node)
        if predicate in filter_predicates(n)
    ]
    assert carriers
    assert not any(names_attached_object(n) for n in carriers)
    assert predicate not in ATTACHED_OBJECT_PREDICATES


def test_the_tuner_ramp_search_page_is_nonland_ramp():
    """A search page is small and cmc-ascending, so a preset that matched mana lands
    (the `ramp` key fires for every fixing land) filled it with lands and starved the
    sourcing. Every preset hit must survive the tuner's own nonland gate."""
    preset = get_preset("ramp")
    hits = [r for r in snapshot_records() if preset.matches(r)]
    assert hits
    # The tuner's gate is ``is_land`` (the FRONT face): a Saga // Land DFC such as
    # Welcome to . . . // Jurassic Park is a nonland card the tuner may source.
    assert not [r["name"] for r in hits if is_land(r)]
    # The precision filter removes a rock whose every mana / Treasure ability is
    # gated on a condition (CR 602.5), and nothing else. Mox Amber has no gate: its
    # ruling says you can activate it with no legendary permanent (it then adds no
    # mana). Fanatic of Rhonas' first ability is ungated.
    names = {r["name"] for r in hits}
    gated = {"Mox Opal", "Mox Jasper", "Tablet of Compleation", "Boxing Ring"}
    ungated = {"Mox Amber", "Fanatic of Rhonas", "Sol Ring", "Arcane Signet"}
    assert gated | ungated <= names
    dropped = {r["name"] for r in hits if not is_reliable_ramp(r)}
    assert gated <= dropped
    assert not ungated & dropped
    # The tuner sources ramp by the spec ``roles`` exports, unchanged.
    assert ROLE_SEARCH["ramp"] is roles.ROLE_SEARCH["ramp"]
    assert ROLE_SEARCH["ramp"]["_filter"] is is_reliable_ramp


@pytest.mark.parametrize("name", ["Skyshroud Claim", "Hunting Wilds"])
def test_multi_land_fetch_is_ramp(name):
    # "up to two Forest cards" — the text read's fetch pattern never matched it.
    assert is_ramp(_real(name))


def test_a_seed_outlives_signal_keys_read_without_trees(monkeypatch):
    """CI order bug: with no phase cache, a card read before any test seeded its
    trees memoizes empty trees and an empty signal-key set; a later ``test_card``
    must re-seed the real trees and drop the stale keys, or Cultivate stops being
    ramp for the rest of the process (main's CI failure before this fix)."""
    from mtg_utils import theme_presets
    from mtg_utils._card_ir import trees

    oid = test_card("Cultivate")["oracle_id"]
    monkeypatch.setitem(trees._TREES_MEMO, oid, ())  # read with no phase data
    monkeypatch.setitem(theme_presets._SIGNAL_KEY_INDEX, oid, frozenset())
    # The failing test's own path: seed the real trees, then read the role.
    assert is_ramp(_real("Cultivate"))


# --- The deck context: mana the deck can't use isn't ramp ------------------------


def _deck(commander: str | None, *spells: str) -> DeckMana:
    """A deck's mana context: its commander and its nonland cards (one copy each)."""
    return DeckMana.of(
        [_real(commander)] if commander else [],
        [(_real(name), 1) for name in spells],
    )


_OMNATH = "Omnath, Locus of the Void"  # colorless identity, a creature
_KRENKO = "Krenko, Mob Boss"  # mono-red, a creature
_MEMNARCH = "Memnarch"  # colorless, an artifact creature


@pytest.mark.parametrize(
    "name",
    [
        # Its ruling: under a colorless commander it "produces no mana. It doesn't
        # produce {C}." (Commander's Sphere's ruling says the same.)
        "Arcane Signet",
        "Commander's Sphere",
        # Ruling: "If your legendary creatures and legendary planeswalkers are all
        # colorless, ... you won't add any mana."
        "Mox Amber",
        # Ruling: if "the exiled card is colorless", it "can't add mana".
        "Chrome Mox",
    ],
)
def test_deck_colored_mana_is_dead_under_a_colorless_commander(name):
    card = _real(name)
    assert is_ramp(card)  # the card alone is ramp
    assert not is_ramp(card, deck_mana=_deck(_OMNATH))
    assert is_ramp(card, deck_mana=_deck(_KRENKO))


@pytest.mark.parametrize("name", ["Mox Opal", "Mind Stone", "Sol Ring"])
def test_colorless_or_any_color_mana_stays_ramp_under_a_colorless_commander(name):
    assert is_ramp(_real(name), deck_mana=_deck(_OMNATH))


def test_artifact_only_mana_is_ramp_where_the_deck_can_spend_it():
    """The Mightstone and Weakstone's {C}{C} "can't be spent to cast nonartifact
    spells" (CR 106.6). It's ramp when it can cast the commander or a third of the
    deck — an artifact deck under a creature commander included."""
    stone = _real("The Mightstone and Weakstone")
    assert is_ramp(stone, deck_mana=_deck(_MEMNARCH))
    assert not is_ramp(stone, deck_mana=_deck(_OMNATH, "Lightning Bolt", "Cultivate"))
    artifacts = _deck(_OMNATH, "Sol Ring", "Mind Stone", "Lightning Bolt")
    assert is_ramp(stone, deck_mana=artifacts)
    assert "card_draw" in role_of(stone, deck_mana=_deck(_OMNATH))


def test_one_usable_mana_ability_keeps_a_source_live():
    """Eldrazi Temple's {C}{C} is Eldrazi-only, but its plain {C} works for anyone."""
    assert _deck(_OMNATH).dead_mana(_real("Eldrazi Temple")) is None


@pytest.mark.parametrize(
    ("restriction", "subtypes", "admits"),
    [
        ("Instant, Sorcery, Demon, and Spirit", {"Spirit"}, True),
        ("Vampire, Cleric, And/or Demon", {"Cleric"}, True),
        ("Vampire, Cleric, And/or Demon", {"Goblin"}, False),
        ("Outlaw", {"Pirate"}, True),  # CR 700.12
        ("Colorless Eldrazi", {"Goblin"}, False),
        ("Unrecognizedword", set(), True),  # never condemned on vocabulary alone
    ],
)
def test_spell_type_restrictions_read_their_lists(restriction, subtypes, admits):
    facts = ObjectFacts(
        types=frozenset({"Creature"}),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(),
        colors=frozenset({"B"}),
    )
    assert _restriction_admits(restriction, facts) is admits


def test_noncreature_restriction_admits_a_planeswalker():
    facts = ObjectFacts(
        types=frozenset({"Planeswalker"}),
        subtypes=frozenset(),
        supertypes=frozenset({"Legendary"}),
        colors=frozenset({"B", "G"}),
    )
    assert _restriction_admits("Noncreature", facts)


def test_creature_only_mana_casts_a_commander_that_is_a_creature_spell():
    """Beastcaller Savant's mana casts only creature spells (CR 106.6). Grist, the
    Hunger Tide is a creature anywhere but the battlefield (its ruling; CR 113.6b),
    so the mana casts it; Teferi, Temporal Archmage is no creature anywhere."""
    savant = _real("Beastcaller Savant")
    spells = ("Lightning Bolt", "Cultivate")
    assert is_ramp(savant, deck_mana=_deck("Grist, the Hunger Tide", *spells))
    assert not is_ramp(savant, deck_mana=_deck("Teferi, Temporal Archmage", *spells))


def test_without_a_commander_deck_colored_mana_is_untouched():
    assert is_ramp(_real("Arcane Signet"), deck_mana=_deck(None, "Sol Ring"))


def test_the_tuner_never_sources_dead_ramp():
    assert not is_reliable_ramp(_real("Arcane Signet"), deck_mana=_deck(_OMNATH))
    assert is_reliable_ramp(_real("Arcane Signet"), deck_mana=_deck(_KRENKO))


@pytest.mark.parametrize(
    "name",
    ["Pacifism", "Darksteel Mutation", "Song of the Dryads", "Imprisoned in the Moon"],
)
def test_a_neutralize_aura_is_interaction(name):
    """An Aura that locks the enchanted threat (can't attack or block, CR
    508.1c / 509.1b) or makes it a 0/1 or a land (CR 613.4b / 205.1a) answers
    it like removal: the ``pacify-aura`` preset reads both lanes."""
    assert "interaction" in role_of(_real(name))


@pytest.mark.parametrize(
    "name",
    [
        "Tidecaller Mentor",  # threshold ETB: return target nonland permanent
        "Council of Echoes",  # descend ETB: return target nonland permanent
        "Foul Renewal",  # a recall beside "target creature gets -X/-X"
        "Wail of War",  # a recall mode beside a one-sided -1/-1
        "Find // Finality",  # Finality's "all creatures get -4/-4"
    ],
)
def test_a_graveyard_recall_beside_a_real_answer_is_interaction(name):
    """The lanes read the recall as recursion and the answer as an answer, so
    no consumer-side veto drops the card (a condition naming the graveyard —
    threshold, descend — is no recall at all)."""
    assert "interaction" in role_of(_real(name))


def test_a_pure_graveyard_recall_is_not_interaction():
    """Pharika's Mender returns a creature or enchantment CARD from your
    graveyard: recursion, not an answer."""
    assert "interaction" not in role_of(_real("Pharika's Mender"))


@pytest.mark.parametrize(
    "name",
    ["Monsoon", "One with the Stars", "Swift Reconfiguration"],
)
def test_no_answer_is_not_interaction(name):
    """Monsoon's damage goes to the player whose Islands it taps; One with the
    Stars and Swift Reconfiguration leave the permanent its abilities."""
    assert "interaction" not in role_of(_real(name))


@pytest.mark.parametrize("name", ["Imprisoned in the Moon", "Minimus Containment"])
def test_a_neutralize_aura_is_not_ramp(name):
    roles_ = role_of(_real(name))
    assert "interaction" in roles_
    assert "ramp" not in roles_


@pytest.mark.parametrize(
    "name",
    [
        "Kumano Faces Kakkazan // Etching of Kumano",
        "Cavalier of Flame",
        "Omnath, Locus of Creation",
        "Noxious Field",
    ],
)
def test_a_planeswalker_or_granted_sweep_is_a_board_wipe(name):
    roles_ = role_of(_real(name))
    assert {"board_wipe", "interaction"} <= roles_
