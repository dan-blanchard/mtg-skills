"""Serve-ident conversions in ``signal_specs/data_3.py`` (2026-10-18).

Each converted spec's enabler arm is now the lanes' own structural idents, not an
oracle regex (docs/plans/serve-idents-and-avenue-support.md, Pass A). One row per
spec pins: the regex arm is gone, the ident arm is in place, a real card the regex
MISSED now serves, and (where the regex had one) a card it wrongly served no longer
does. Where the regex and the lane agreed card for card, the positive is a shared
card: the row then pins only that the ident arm carries the lane.
"""

import pytest
from conftest import extra

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils.testkit import test_card, test_card_ir


def _sig(key, scope="you"):
    return Signal(key=key, scope=scope, subject="", text="", source="cmd")


def _card(name):
    """The real snapshot record for *name* (ADR-0056), with its crosswalk trees
    memo seeded first — so a serve's structural ``signal_idents`` arm reads the
    card's real idents in CI exactly as it does locally (no phase cache)."""
    test_card_ir(name)
    return test_card(name)


# (key, scope, ident, a card that serves, a card the regex wrongly served or None)
_CONVERTED = [
    (
        "commander_matters",
        "you",
        "commander_matters|you|",
        "Command Beacon",
        "Faceless One",
    ),
    ("has_devour", "you", "has_devour|you|", "Dragon Broodmother", "Devour in Flames"),
    (
        "exile_until_leaves",
        "you",
        "exile_until_leaves|you|",
        "Oblivion Ring",
        "Lumbering Battlement",
    ),
    (
        "dice_makers",
        "you",
        "dice_makers|you|",
        "Circuits Act",
        '"Lifetime" Pass Holder',
    ),
    (
        "dice_matters",
        "you",
        "dice_matters|you|",
        "Circuits Act",
        '"Lifetime" Pass Holder',
    ),
    (
        "single_target_neutralize",
        "you",
        "single_target_neutralize|you|",
        "Cursed Courtier",
        "Awakened Awareness",
    ),
    ("extra_land_drop", "you", "extra_land_drop|you|", "Kamahl's Druidic Vow", None),
    (
        "phasing_makers",
        "you",
        "phasing_makers|you|",
        "Blink Dog",
        "Cloak of Invisibility",
    ),
    (
        "firebending_makers",
        "you",
        "firebending_makers|you|",
        "Azula, On the Hunt",
        "Firebending Lesson",
    ),
    (
        "firebending_matters",
        "you",
        "firebending_matters|you|",
        "Azula, On the Hunt",
        "Firebending Lesson",
    ),
    (
        "myriad_grant",
        "you",
        "myriad_grant|you|",
        "Blade of Selves",
        "The Everflowing Well // The Myriad Pools",
    ),
    (
        "opponent_discard",
        "opponents",
        "opponent_discard|opponents|",
        "Alley Grifters",
        "Compulsive Research",
    ),
    (
        "partner_background",
        "you",
        "partner_background|you|",
        "Akiri, Line-Slinger",
        None,
    ),
    (
        "facedown_matters",
        "you",
        "facedown_matters|you|",
        "Bonethorn Valesk",
        "Cloak and Dagger, Entwined",
    ),
    (
        "facedown_makers",
        "you",
        "facedown_makers|you|",
        "Bonethorn Valesk",
        "Cloak and Dagger, Entwined",
    ),
    (
        "hand_disruption",
        "opponents",
        "hand_disruption|opponents|",
        "Lay Bare",
        "Wild Evocation",
    ),
    ("counter_control", "you", "counter_control|you|", "Glyph Keeper", None),
    ("ki_counter_makers", "you", "ki_counter_makers|you|", "Petalmane Baku", None),
    ("ki_counter_matters", "you", "ki_counter_matters|you|", "Petalmane Baku", None),
    (
        "destroy_legendary",
        "any",
        "destroy_legendary|any|",
        "Invasion of Fiora // Marchesa, Resolute Monarch",
        None,
    ),
    ("airbend_makers", "you", "airbend_makers|you|", "Aang, Airbending Master", None),
    ("earthbend_makers", "you", "earthbend_makers|you|", "Badgermole", None),
    ("earthbend_matters", "you", "earthbend_matters|you|", "Badgermole", None),
    ("waterbend_makers", "you", "waterbend_makers|you|", "Giant Koi", None),
    ("waterbend_matters", "you", "waterbend_matters|you|", "Giant Koi", None),
    ("stickers_matter", "you", "stickers_matter|you|", "Aerialephant", None),
    (
        "companion_keyword",
        "you",
        "companion_keyword|you|",
        "Jegantha, the Wellspring",
        None,
    ),
    ("has_soulbond", "you", "has_soulbond|you|", "Deadeye Navigator", None),
    ("boast_makers", "you", "boast_makers|you|", "Frenzied Raider", None),
    ("boast_matters", "you", "boast_matters|you|", "Frenzied Raider", None),
    ("exhaust_makers", "you", "exhaust_makers|you|", "Adrenaline Jockey", None),
    ("exhaust_matters", "you", "exhaust_matters|you|", "Adrenaline Jockey", None),
    ("station_makers", "you", "station_makers|you|", "Hearthhull, the Worldseed", None),
    (
        "station_matters",
        "you",
        "station_matters|you|",
        "Hearthhull, the Worldseed",
        None,
    ),
    ("tap_down", "opponents", "tap_down|opponents|", "Blustersquall", None),
    ("end_the_turn", "you", "end_the_turn|you|", "Time Stop", None),
    (
        "trigger_doubling",
        "you",
        "trigger_doubling|you|",
        "Delney, Streetwise Lookout",
        None,
    ),
    ("convoke_makers", "you", "convoke_makers|you|", "Chord of Calling", None),
    ("convoke_matters", "you", "convoke_matters|you|", "Chord of Calling", None),
    ("named_counter_misc", "you", "named_counter_misc|you|", "Bomb Squad", None),
    ("powerup_matters", "you", "powerup_matters|you|", "Extremis Elite", None),
    (
        "rad_counter_makers",
        "opponents",
        "rad_counter_makers|opponents|",
        "Feral Ghoul",
        None,
    ),
    (
        "oil_counter_makers",
        "you",
        "oil_counter_makers|you|",
        "Armored Scrapgorger",
        None,
    ),
    (
        "oil_counter_matters",
        "you",
        "oil_counter_matters|you|",
        "Armored Scrapgorger",
        None,
    ),
    ("fight_makers", "you", "fight_makers|you|", "Hans Eriksson", None),
    ("has_changeling", "you", "has_changeling|you|", "Mutavault", None),
    (
        "starting_life_matters",
        "you",
        "starting_life_matters|you|",
        "Angel of Destiny",
        None,
    ),
    ("affinity_type", "you", "affinity_type|you|", "Brine Giant", None),
    ("evasion_denial", "opponents", "evasion_denial|opponents|", "Great Wall", None),
    ("lure_makers", "you", "lure_makers|you|", "Talruum Piper", None),
    (
        "opponent_exile_matters",
        "opponents",
        "opponent_exile_matters|opponents|",
        "Umbris, Fear Manifest",
        None,
    ),
    ("villainous_choice", "you", "villainous_choice|you|", "Dr. Eggman", None),
    ("crimes_matter", "you", "crimes_matter|you|", "Gisa, the Hellraiser", None),
    ("cascade_makers", "you", "cascade_makers|you|", "Ardent Plea", None),
    ("cascade_matters", "you", "cascade_matters|you|", "Ardent Plea", None),
    ("regenerate_makers", "you", "regenerate_makers|you|", "Clot Sliver", None),
    # The +1/+1 counter package: plus_one_makers reads the keyword actions, so a
    # connive printed without its reminder text serves; the regex served a "no
    # +1/+1 counters" negation.
    (
        "amass_makers",
        "you",
        "plus_one_makers|you|",
        "Baron Helmut Zemo",
        "Hindervines",
    ),
    (
        "incubate_makers",
        "you",
        "plus_one_makers|you|",
        "Baron Helmut Zemo",
        "Hindervines",
    ),
    # "destroy target tapped creature" wasn't in the regex's type list; one-shot
    # land destruction isn't removal to the lane.
    ("removal", "you", "removal|you|", "Royal Assassin", "Stone Rain"),
    # An overloaded Cyclonic Rift sweeps; Denizen of the Deep bounces your own.
    ("mass_bounce", "any", "mass_bounce|any|", "Cyclonic Rift", "Denizen of the Deep"),
    # A creature that becomes a pacifying Aura (the Enchantment type arm misses it).
    ("pacify_makers", "you", "pacify_makers|you|", "Convulsing Licid", None),
    (
        "life_total_set",
        "any",
        "life_total_set|any|",
        "Loxodon Lifechanter",
        "Heartless Hidetsugu",
    ),
    # Exiling a card from a graveyard isn't exile removal.
    ("exile_removal", "you", "exile_removal|you|", "Oblivion Ring", "Deathrite Shaman"),
    # "Search your library and/or graveyard"; basic landcycling isn't a tutor.
    ("tutor", "you", "tutor|you|", "Finale of Devastation", "Migratory Route"),
    # A number-word ritual; a basic land to hand isn't ramp.
    ("ramp", "you", "ramp|you|", "Dark Ritual", "Sylvan Scrying"),
    # A {T}-only engine; an equip cost isn't one.
    (
        "activated_ability",
        "you",
        "activated_ability|you|",
        "Royal Assassin",
        "Leonin Scimitar",
    ),
    # A ninjutsu payoff with no ninjutsu keyword of its own; protection's
    # reminder text isn't evasion.
    # The Equipment movers serve through the extra now, not the main serve.
    ("has_dash", "you", "has_dash|you|", "Mardu Scout", "Battlefield Improvisation"),
    # "Copy it" engines; a card named Storm isn't a spell copier.
    (
        "spell_copy_makers",
        "you",
        "spell_copy_makers|you|",
        "Thousand-Year Storm",
        "Storm of Souls",
    ),
    ("cant_block_grant", "you", "cant_block_grant|you|", "Bedlam", None),
    (
        "conditional_self_protection",
        "you",
        "conditional_self_protection|you|",
        "Fleecemane Lion",
        "Bello, Bard of the Brambles",
    ),
    ("aura_equip_kw_grant", "you", "aura_equip_kw_grant|you|*", "Hemlock Vial", None),
    ("counter_grants_kw", "you", "counter_grants_kw|you|", "Cathedral Acolyte", None),
    (
        "typed_anthem_multi",
        "you",
        "typed_anthem_multi|you|",
        "Gisa, the Hellraiser",
        None,
    ),
    (
        "all_creatures_kw_grant",
        "any",
        "all_creatures_kw_grant|any|*",
        "Absolute Grace",
        None,
    ),
    (
        "specialize_matters",
        "you",
        "specialize_matters|you|",
        "Klement, Novice Acolyte",
        None,
    ),
    # Phase C: the copy lanes, the opponent-facing lanes and the evasion lanes. Each
    # positive is a card the old regex missed; each dropped card is one it served.
    (
        "opponent_exile_makers",
        "opponents",
        "opponent_exile_makers|opponents|",
        "Crypt Incursion",
        None,
    ),
    ("clone_makers", "you", "clone_makers|you|", "Aggressive Biomancy", "Double Major"),
    (
        "copy_permanent",
        "you",
        "copy_permanent|you|",
        "Aggressive Biomancy",
        "Double Major",
    ),
    (
        "wants_cloning",
        "you",
        "token_copy_makers|you|",
        "Aggressive Biomancy",
        "Double Major",
    ),
    (
        "token_copy_makers",
        "you",
        "token_copy_makers|you|",
        "Aggressive Biomancy",
        None,
    ),
    (
        "opponent_draw_matters",
        "opponents",
        "opponent_draw_matters|opponents|",
        "Baleful Mastery",
        "Opt",
    ),
    (
        "opponent_draw_matters",
        "opponents",
        "target_player_draws|any|",
        "Inspiration",
        "Opt",
    ),
    (
        "permanent_recast",
        "you",
        "self_etb_payload|you|",
        "Aerial Extortionist",
        "Aether Flash",
    ),
    ("untap_engine", "you", "untap_engine|you|*", "Candelabra of Tawnos", "Abduction"),
    (
        "damage_doubling",
        "you",
        "damage_doubling|you|",
        "Furnace of Rath",
        "Goblin Charbelcher",
    ),
    (
        "opponent_cast_matters",
        "opponents",
        "opponent_cast_matters|opponents|",
        "Lunar Force",
        "Angel's Feather",
    ),
    (
        "evasion_self",
        "you",
        "evasion_self|you|fear",
        "Abyssal Nocturnus",
        "Alpha Authority",
    ),
    (
        "has_ninjutsu",
        "you",
        "team_evasion_grant|you|*",
        "Akroma's Memorial",
        "Alpha Authority",
    ),
    (
        "damage_to_opp_matters",
        "opponents",
        "damage_to_opp_matters|opponents|",
        "Gruesome Scourger",
        "Boggart Brute",
    ),
    # Phase E: seek reads "its owner seeks"; a return-all bounce; a flip-gated win/lose;
    # heroic payoffs; a shuffle-watcher. Graveyard returns and each-player tutors drop.
    ("seek_matters", "you", "seek_matters|you|", "Darkstar Banisher", None),
    ("bounce_tempo", "you", "bounce_tempo|you|", "Aetherize", "Pulse of Murasa"),
    ("win_lose_game", "any", "win_lose_game|any|", "Angel of Destiny", None),
    ("own_target_spell", "you", "targeting_matters|any|you", "Heartfire Hero", None),
    (
        "opponent_search_matters",
        "opponents",
        "opponent_search_matters|opponents|",
        "Psychic Surgery",
        "Maralen of the Mornsong",
    ),
]


@pytest.mark.parametrize(
    ("key", "scope", "ident", "serves", "dropped"),
    _CONVERTED,
    ids=[f"{k}|{s}" for k, s, *_ in _CONVERTED],
)
def test_serve_is_the_lane_not_a_regex(key, scope, ident, serves, dropped):
    spec = spec_for(_sig(key, scope))
    assert spec is not None
    assert spec.serve.oracle is None
    assert ident in spec.serve.signal_idents
    assert spec.serve.matches(_card(serves)), serves
    if dropped is not None:
        assert not spec.serve.matches(_card(dropped)), dropped


@pytest.mark.parametrize("key", ["connive_makers", "connive_matters"])
def test_connive_serve_is_the_doers_and_the_payoffs(key):
    spec = spec_for(_sig(key))
    assert spec.serve.oracle is None
    assert spec.search["oracle"]
    serve = spec.serve
    assert serve.matches(_card("Raffine's Informant"))
    assert serve.matches(_card("Security Bypass"))  # a granted connive
    # connive_matters: "Whenever a creature you control connives" and a
    # replacement of the connive event.
    assert serve.matches(_card("Glorious Purpose"))
    assert serve.matches(_card("Leader, Super-Genius"))
    # A loot isn't a connive.
    assert not serve.matches(_card("Faithless Looting"))


# Serves read off granted alternative costs, explore, shield counters and
# attractions: (key, ident, a card that serves, a card the regex wrongly served
# or None).
_LANE_READ_SERVES = [
    (
        "shield_counter_makers",
        "shield_counter_makers|you|",
        "Boon of Safety",
        "Call In a Professional",
    ),
    # A granted sneak: the regex read it, and now the lane does too.
    ("alt_cost_keyword", "alt_cost_keyword|you|", "Ninja Teen", "Lightfoot Rogue"),
    (
        "alt_cost_keyword",
        "alt_cost_keyword|you|",
        "Peter Parker // Amazing Spider-Man",
        None,
    ),
    # A granted explore, and a Map maker the regex never saw.
    ("explore_makers", "explore_makers|you|", "Glowcap Lantern", None),
    ("explore_makers", "explore_matters|you|", "Restless Anchorage", None),
    ("explore_matters", "explore_makers|you|", "Glowcap Lantern", None),
    ("explore_matters", "explore_matters|you|", "Wildgrowth Walker", None),
    ("attractions_matter", "attractions_matter|you|", "Step Right Up", None),
    ("attractions_matter", "attractions_matter|you|", "Line Cutter", None),
]


@pytest.mark.parametrize(
    ("key", "ident", "serves", "dropped"),
    _LANE_READ_SERVES,
    ids=[f"{k}-{s}" for k, _i, s, _d in _LANE_READ_SERVES],
)
def test_lane_read_serve_is_the_lane(key, ident, serves, dropped):
    spec = spec_for(_sig(key))
    assert spec is not None
    assert spec.serve.oracle is None
    assert ident in spec.serve.signal_idents
    assert spec.serve.matches(_card(serves)), serves
    if dropped is not None:
        assert not spec.serve.matches(_card(dropped)), dropped


def test_gain_control_serve_is_the_theft_lane():
    spec = spec_for(_sig("gain_control"))
    assert spec is not None
    assert spec.serve.oracle is None
    assert spec.serve.not_oracle is None
    assert "gain_control|you|" in spec.serve.signal_idents
    # A card out of an opponent's library onto the battlefield under your
    # control: you control a permanent you don't own (CR 110.2).
    for name in ("Bribery", "Acquire", "Telemin Performance"):
        assert spec.serve.matches(_card(name)), name
    # Granted theft: an Aura-granted activated ability and a token's trigger.
    assert spec.serve.matches(_card("Chamber of Manipulation"))
    assert spec.serve.matches(_card("Wake the Dragon"))
    # The regex served a control reset ("gain control of all permanents you
    # own") and a give-away; the lane vetoes both.
    assert not spec.serve.matches(_card("Brand"))
    assert not spec.serve.matches(_card("Sky Swallower"))
    # Reanimating from any graveyard isn't theft from a library.
    assert not spec.serve.matches(_card("Animate Dead"))


def test_tap_untap_matters_serve_reads_granted_tap_triggers():
    spec = spec_for(_sig("tap_untap_matters"))
    assert spec is not None
    assert spec.serve.oracle is None
    assert "tap_untap_matters|you|" in spec.serve.signal_idents
    # A "becomes tapped" trigger (CR 603.2e) of its own, and the same trigger
    # granted to your Elves (Dionus) or by an Aura (Well Rested, "becomes
    # untapped").
    for name in (
        "Emmara, Soul of the Accord",
        "Dionus, Elvish Archdruid",
        "Well Rested",
    ):
        assert spec.serve.matches(_card(name)), name


def test_spell_copy_serve_keeps_storm_by_keyword():
    # Storm copies the spell it's on (CR 702.40a); the keyword arm serves it.
    spec = spec_for(_sig("spell_copy_makers"))
    assert spec.serve.matches(_card("Grapeshot"))


def test_tutor_serve_keeps_the_land_fetch_veto():
    # The tutor lane fires on a fetch land; a land put onto the battlefield is
    # ramp, not a tutor.
    spec = spec_for(_sig("tutor"))
    assert spec.serve.not_oracle is not None
    assert not spec.serve.matches(_card("Evolving Wilds"))


def test_activated_ability_untap_haste_and_cost_reducers_are_an_extra():
    spec = spec_for(_sig("activated_ability"))
    untap = extra(spec, "Untap, haste and cheaper activations")
    # The cost reducer is the extra's oracle arm; the haste grant is its idents.
    assert untap.serve.matches(_card("Training Grounds"))
    assert untap.serve.matches(_card("Thousand-Year Elixir"))
    assert untap.serve.matches(_card("Fervor"))
    assert not spec.serve.matches(_card("Training Grounds"))
    # The untap of the enchanted creature is the main spec's own untap_engine ident
    # now; the extra no longer carries it. Abduction (a steal) stays out.
    assert spec.serve.matches(_card("Freed from the Real"))
    assert not untap.serve.matches(_card("Freed from the Real"))
    assert not spec.serve.matches(_card("Abduction"))
    assert not untap.serve.matches(_card("Abduction"))


def test_dash_equipment_movers_are_an_extra():
    spec = spec_for(_sig("has_dash"))
    assert extra(spec, "Equipment movers").serve.matches(
        _card("Battlefield Improvisation")
    )
    # The Equipment themselves still serve through the type arm.
    assert spec.serve.matches(_card("Leonin Scimitar"))


def test_token_copy_serve_keeps_the_self_copy_keywords():
    # The lane excludes self-copy by design; myriad (CR 702.116a) still serves by
    # keyword.
    spec = spec_for(_sig("token_copy_makers"))
    assert spec.serve.matches(_card("Banshee of the Dread Choir"))


def test_evasion_serve_keeps_sun_quan_out():
    # Sun Quan grants horsemanship to others; he has none himself.
    assert not spec_for(_sig("evasion_self")).serve.matches(
        _card("Sun Quan, Lord of Wu")
    )


def test_bounce_tempo_self_bounce_engines_are_an_extra():
    # Whitemane Lion returns your own creature on enter; the lane reads it as no
    # bounce, so the recast-engine extra carries it.
    spec = spec_for(_sig("bounce_tempo"))
    assert not spec.serve.matches(_card("Whitemane Lion"))
    assert extra(spec, "Self-bounce recast engines").serve.matches(
        _card("Whitemane Lion")
    )
