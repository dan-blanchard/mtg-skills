"""Each OR arm of a theme's page serve admits a card on its own (backlog (o)).

Serves were written to credit a deck's own cards; now that every theme pages
by its serve (``signal_specs.theme_page``), each structured arm — a type list,
a keyword list, a mana-value / power / toughness floor, an {X} cost, a devotion
count, a self-recursion route — pages every card it admits. This guard pins,
the ``theme_presets`` should_match / should_not_match way, a real card each
arm is meant to admit and a near miss the serve must not, for every page
serve (main or sub-avenue) carrying such an arm. A new arm needs a row; an arm
loosened past its near miss fails. The signal-ident arm is the lanes' own
(their tests pin it), and a pattern arm is the open pattern-serve item.

Real cards only (ADR-0056), legal in some format.
"""

from __future__ import annotations

import dataclasses

import pytest

from mtg_utils._analysis.signal_specs import SPECS, Serve, page_serve
from mtg_utils.testkit import test_card, test_card_ir

# The structured arms a serve ORs (``Serve.matches``), beside its pattern and
# signal-ident arms.
_STRUCTURED_ARMS = (
    "types",
    "keywords",
    "cmc_min",
    "cmc_max",
    "min_devotion",
    "produces_mana",
    "power_min",
    "toughness_min",
    "toughness_over_power",
    "keyword_count_min",
    "vanilla",
    "self_recur",
    "names",
    "mana_cost",
)

_COUNTER_KEYWORDS = ("Abzan Falconer", "Grizzly Bears")  # outlast; a vanilla 2/2

# (serve, arm) -> (a card the arm admits, a near miss the serve rejects). The
# serve is "key|scope" or "key|scope|sub-avenue label"; an ``all_of`` serve's
# arm is "all_of[i].<arm>".
ARM_PINS: dict[tuple[str, str], tuple[str, str]] = {
    # a crippling drawback beside a power floor; the floor alone admits nothing
    ("ability_strip_payoff|you", "all_of[1].power_min"): (
        "Aboroth",
        "Colossal Dreadmaw",
    ),
    ("alt_cost_keyword|you", "keywords"): ("Amazing Spider-Girl", "Lightning Bolt"),
    # haste: an attacker that swings the turn it lands
    ("attack_matters|you", "keywords"): ("Ahn-Crop Crasher", "Giant Spider"),
    (
        "attack_matters|you|Equipment and Auras that suit up the attacker",
        "types",
    ): ("Bonesplitter", "Pacifism"),
    ("big_mana|you", "mana_cost"): ("Walking Ballista", "Sol Ring"),
    ("blocked_matters|you|Force blocks (Lure)", "keywords"): (
        "Deftblade Elite",
        "Giant Spider",
    ),
    # the instants and sorceries a cantrip deck casts (a source type, ADR-0026)
    ("cantrip|you", "types"): ("Opt", "Sol Ring"),
    # cascade into a fattie
    ("cascade_makers|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    ("cascade_matters|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    ("cast_from_exile|you", "keywords"): ("Aloe Alchemist", "Lightning Bolt"),
    ("clone_makers|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    # a death trigger worth copying beside a mana-value floor
    ("clone_makers|you|High-value death triggers to copy", "all_of[1].cmc_min"): (
        "Antler Skulkin",
        "Colossal Dreadmaw",
    ),
    ("colorless_matters|you", "types"): ("Reality Smasher", "Grizzly Bears"),
    ("colorless_matters|you", "keywords"): ("Barrage Tyrant", "Grizzly Bears"),
    ("combat_damage_to_opp|opponents", "keywords"): ("Hidden Strings", "Counterspell"),
    ("cost_reduction|you", "cmc_min"): ("Worldspine Wurm", "Colossal Dreadmaw"),
    ("cost_reduction|you", "mana_cost"): ("Walking Ballista", "Sol Ring"),
    ("cost_reduction|you|Storm payoffs", "keywords"): (
        "Empty the Warrens",
        "Dark Ritual",
    ),
    ("counter_distribute|you|Counter-keyword creatures", "keywords"): (
        _COUNTER_KEYWORDS
    ),
    ("counter_doubling|you|Counter-keyword creatures", "keywords"): _COUNTER_KEYWORDS,
    ("counter_manipulation|you|Counter-keyword creatures", "keywords"): (
        _COUNTER_KEYWORDS
    ),
    ("counter_move|you|Counter-keyword creatures", "keywords"): _COUNTER_KEYWORDS,
    ("counter_place_trigger|you|Counter-keyword creatures", "keywords"): (
        _COUNTER_KEYWORDS
    ),
    ("counter_replace_bonus|you|Counter-keyword creatures", "keywords"): (
        _COUNTER_KEYWORDS
    ),
    ("creature_cast_trigger|you", "power_min"): (
        "Ghalta, Primal Hunger",
        "Shivan Dragon",
    ),
    # power as damage: a 5/5 pings for five, a 4/4 is the near miss
    ("creature_ping|you", "power_min"): ("Shivan Dragon", "Serra Angel"),
    ("damage_equal_power|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    # devotion counts colored pips (CR 700.5): {1}{B}{B}, against {1}{G}
    ("devotion_matters|you", "min_devotion"): ("Phyrexian Arena", "Grizzly Bears"),
    ("discover_makers|you", "keywords"): ("Chimil, the Inner Sun", "Lightning Bolt"),
    ("evasion_self|you", "keywords"): ("Academy Raider", "Grizzly Bears"),
    ("exalted_lone_attacker|you", "keywords"): ("Ardent Plea", "Grizzly Bears"),
    # trample assigns damage beyond its blockers' lethal to the player (CR 702.19b)
    ("excess_damage|you", "keywords"): ("Colossal Dreadmaw", "Hill Giant"),
    ("exert_matters|you", "keywords"): ("Ahn-Crop Crasher", "Grizzly Bears"),
    ("fight_makers|you", "power_min"): ("Serra Angel", "Hill Giant"),
    ("foretell_makers|you", "keywords"): ("Battle Mammoth", "Counterspell"),
    ("foretell_matters|you", "keywords"): ("Battle Mammoth", "Counterspell"),
    # a free spell (mana value 0) beside the spell types; a land is no spell
    ("free_spell_storm|you", "all_of[1].types"): ("Memnite", "Forest"),
    ("graveyard_makers|you", "keywords"): ("Adorned Pouncer", "Lightning Bolt"),
    ("graveyard_matters|you", "keywords"): ("Adorned Pouncer", "Lightning Bolt"),
    ("has_banding|you", "keywords"): ("Ayesha Tanaka", "Grizzly Bears"),
    ("has_changeling|you", "keywords"): ("Amoeboid Changeling", "Grizzly Bears"),
    ("has_enlist|you", "keywords"): ("Aradesh, the Founder", "Grizzly Bears"),
    ("has_enlist|you|Enlist fodder", "all_of[1].power_min"): (
        "Aboroth",
        "Colossal Dreadmaw",
    ),
    # an evasive body that connects unblocked
    ("has_ninjutsu|you", "keywords"): ("Fallen Shinobi", "Grizzly Bears"),
    ("has_undying_persist|you", "keywords"): ("Butcher Ghoul", "Grizzly Bears"),
    # historic: an artifact, a legendary or a Saga (CR 700.6)
    ("historic_matters|you", "types"): ("Sol Ring", "Grizzly Bears"),
    # indestructible survives the wipe
    ("keep_n_wrath|each", "keywords"): ("Athreos, Shroud-Veiled", "Serra Angel"),
    ("keyword_counter|you|Counter-keyword creatures", "keywords"): _COUNTER_KEYWORDS,
    # three evergreen keywords; Serra Angel's flying and vigilance are two
    ("keyword_soup|you", "keyword_count_min"): ("Baneslayer Angel", "Serra Angel"),
    ("keyword_soup_makers|you", "keyword_count_min"): (
        "Baneslayer Angel",
        "Serra Angel",
    ),
    ("kicked_spell_matters|you", "keywords"): ("Desolation Angel", "Grizzly Bears"),
    ("legends_matter|you", "types"): ("Krenko, Mob Boss", "Grizzly Bears"),
    ("lifegain_makers|you", "keywords"): ("Baneslayer Angel", "Serra Angel"),
    ("lifegain_matters|you", "keywords"): ("Baneslayer Angel", "Serra Angel"),
    ("madness_matters|you", "keywords"): ("Anje's Ravager", "Grizzly Bears"),
    ("magecraft_matters|you", "types"): ("Opt", "Grizzly Bears"),
    ("magecraft_matters|you", "keywords"): ("Abbot of Keral Keep", "Grizzly Bears"),
    ("mana_amplifier|you", "mana_cost"): ("Walking Ballista", "Sol Ring"),
    ("mass_removal|you", "keywords"): ("Athreos, Shroud-Veiled", "Serra Angel"),
    ("minus_counters_matter|you", "keywords"): ("Infestation", "Grizzly Bears"),
    # modified: equipped, enchanted or countered (CR 700.9)
    ("modified_matters|you", "types"): ("Rancor", "Glorious Anthem"),
    ("multicolor_matters|you", "keywords"): ("Bring to Light", "Lightning Bolt"),
    # fliers connect for a non-Human attack payoff
    ("nonhuman_attackers|you", "keywords"): ("Serra Angel", "Giant Spider"),
    # outlaws: Assassins, Mercenaries, Pirates, Rogues, Warlocks
    ("outlaw_matters|you", "types"): ("Graywater's Fixer", "Grizzly Bears"),
    ("partner_background|you", "keywords"): (
        "Abdel Adrian, Gorion's Ward",
        "Krenko, Mob Boss",
    ),
    # party: Cleric, Rogue, Warrior, Wizard (CR 700.8)
    ("party_matters|you", "types"): ("Archpriest of Iona", "Grizzly Bears"),
    ("plus_one_makers|any|Counter-keyword creatures", "keywords"): _COUNTER_KEYWORDS,
    ("plus_one_matters|any|Counter-keyword creatures", "keywords"): _COUNTER_KEYWORDS,
    ("power_double|you", "power_min"): ("Shivan Dragon", "Serra Angel"),
    ("powerup_matters|you", "keywords"): ("Extremis Elite", "Grizzly Bears"),
    # the fattie a ramp deck accelerates into
    ("ramp|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    ("reanimator|you", "keywords"): ("Alex Wilder, Runaway", "Grizzly Bears"),
    ("reanimator|you", "self_recur"): ("Bloodghast", "Grizzly Bears"),
    ("saddle_matters|you", "keywords"): ("Archmage's Newt", "Grizzly Bears"),
    ("self_counter_grow|you|Counter-keyword creatures", "keywords"): (
        _COUNTER_KEYWORDS
    ),
    ("snow_matters|you", "types"): ("Abominable Treefolk", "Grizzly Bears"),
    ("speed_makers|you", "keywords"): ("Avishkar Raceway", "Grizzly Bears"),
    # can't be blocked, and cheap: Phantom Warrior costs three
    ("speed_makers|you|Cheap unblockable", "all_of[1].cmc_max"): (
        "Aether Figment",
        "Phantom Warrior",
    ),
    ("speed_matters|you", "keywords"): ("Avishkar Raceway", "Grizzly Bears"),
    ("spell_copy_makers|you", "keywords"): ("Empty the Warrens", "Dark Ritual"),
    # instants and sorceries are a spellslinger's fuel (a source type)
    ("spellcast_matters|you", "types"): ("Opt", "Grizzly Bears"),
    ("spellcast_matters|you", "keywords"): ("Abbot of Keral Keep", "Grizzly Bears"),
    ("superfriends_matters|you", "types"): ("Ajani Steadfast", "Grizzly Bears"),
    ("superfriends_matters|you", "keywords"): (
        "Atraxa, Praetors' Voice",
        "Grizzly Bears",
    ),
    ("suspend_makers|you", "keywords"): ("Aeon Chronicler", "Counterspell"),
    ("suspend_matters|you", "keywords"): ("Aeon Chronicler", "Counterspell"),
    ("token_copy_makers|you", "keywords"): ("Adorned Pouncer", "Grizzly Bears"),
    ("token_copy_makers|you", "power_min"): ("Ghalta, Primal Hunger", "Shivan Dragon"),
    ("token_maker|you", "keywords"): ("Fountainport Charmer", "Grizzly Bears"),
    ("tokens_matter|you", "keywords"): ("Zurgo Stormrender", "Grizzly Bears"),
    # Doran: toughness assigns the damage, so a butt (toughness > power) or a
    # defender is the body; a 2/2 is not
    ("toughness_combat|you", "keywords"): ("Wall of Omens", "Grizzly Bears"),
    ("toughness_combat|you", "toughness_over_power"): (
        "Wall of Omens",
        "Grizzly Bears",
    ),
    # a cheap token maker to sacrifice; Hornet Queen costs seven
    ("wants_fodder|you", "all_of[1].cmc_max"): ("Hangarback Walker", "Hornet Queen"),
    ("wants_lifegain|you", "keywords"): ("Baneslayer Angel", "Serra Angel"),
    ("xspell_matters|you", "mana_cost"): ("Walking Ballista", "Sol Ring"),
}


def _card(name: str) -> dict:
    test_card_ir(name)  # seeds the snapshot's trees (CI-safe idents)
    return test_card(name)


def _arm_names(serve: Serve) -> list[str]:
    return [
        f
        for f in _STRUCTURED_ARMS
        if getattr(serve, f) not in (None, False, frozenset(), ())
    ]


def _page_serves() -> dict[str, Serve]:
    """Every theme's page serve, main and sub-avenue, by "key|scope[|label]"."""
    out: dict[str, Serve] = {}
    for (key, scope), spec in SPECS.items():
        if (srv := page_serve(spec.search, spec.serve)) is not None:
            out[f"{key}|{scope}"] = srv
        for extra in spec.extras:
            if (srv := page_serve(extra.search, extra.serve)) is not None:
                out[f"{key}|{scope}|{extra.label}"] = srv
    return out


def _guarded_arms() -> dict[tuple[str, str], Serve]:
    """(serve ref, arm) -> the serve, for every structured arm a page serve ORs
    (an ``all_of`` serve's arms per sub-serve)."""
    out: dict[tuple[str, str], Serve] = {}
    for ref, serve in _page_serves().items():
        if serve.all_of:
            for i, sub in enumerate(serve.all_of):
                for arm in _arm_names(sub):
                    out[(ref, f"all_of[{i}].{arm}")] = serve
        else:
            for arm in _arm_names(serve):
                out[(ref, arm)] = serve
    return out


def _arm_alone(serve: Serve, arm: str) -> Serve:
    """The one arm as a serve of its own (a types arm keeps its gates)."""
    if arm.startswith("all_of["):
        idx, _, arm = arm.removeprefix("all_of[").partition("].")
        serve = serve.all_of[int(idx)]
    kw = {arm: getattr(serve, arm)}
    if arm == "types":
        kw |= {"not_types": serve.not_types, "types_cmc_min": serve.types_cmc_min}
    return dataclasses.replace(Serve(), **kw)


def test_every_structured_arm_is_pinned():
    guarded = set(_guarded_arms())
    assert guarded - set(ARM_PINS) == set(), "pin each new arm in ARM_PINS"
    assert set(ARM_PINS) - guarded == set(), "drop the pins of a removed arm"


_CASES = sorted(ARM_PINS)


@pytest.mark.parametrize(("ref", "arm"), _CASES, ids=[f"{r}:{a}" for r, a in _CASES])
def test_arm_admits_its_card_and_the_serve_rejects_the_near_miss(ref, arm):
    serve = _guarded_arms()[(ref, arm)]
    should, should_not = ARM_PINS[(ref, arm)]
    assert _arm_alone(serve, arm).matches(_card(should)), (ref, arm, should)
    assert serve.matches(_card(should)), (ref, should)
    assert not serve.matches(_card(should_not)), (ref, should_not)


@pytest.mark.parametrize("name", ["Roaming Throne", "Wall of Omens"])
def test_a_big_body_is_no_damage_reflector(name):
    """The damage a reflector deals is the damage dealt to it (Boros Reckoner),
    so a high-toughness body reflects nothing: the toughness >= 4, toughness >
    power and defender arms are gone from the damage_reflect serve."""
    serve = SPECS[("damage_reflect", "you")].serve
    assert not serve.matches(_card(name))
    assert serve.matches(_card("Boros Reckoner"))
