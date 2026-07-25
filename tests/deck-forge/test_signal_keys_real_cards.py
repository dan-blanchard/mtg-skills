"""Every served signal key is proven against a real card.

For every key in ``_REAL_CASES``, the production extractor
(``extract_signals``) must emit the key for that card. Every case is a
real card looked up by name from the committed snapshot (``mtg_utils.testkit``):
``test_card(name)`` is the minimal Scryfall record, ``test_card_ir(name)`` the
production compat Card built from the stored phase records, ``test_signals(name)``
the production extractor over both. So the proof runs the SAME structural parses
production serves — no hand-built fixture shape that silently drifts, and no
phase / sidecar / network dependency in CI. A new signal lane adds one
``key: name`` row here (and a ``build-card-snapshot`` run); the parametrization
then guards it forever.
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import extract_signals
from mtg_utils.card_ir import Filter
from mtg_utils.testkit import test_card, test_card_ir, test_signals

# Real-card cases: served key → the representative card NAME. The card + its
# production parses come from the committed snapshot, so each key is proven
# against the exact structural builds production serves. Keep sorted by key;
# ``has_<x>`` rows sort by their mechanic name (``has_banding`` files under B).
_REAL_CASES: dict[str, str] = {
    "ability_copy": "Strionic Resonator",
    "ability_strip_payoff": "Abigale, Eloquent First-Year",
    "activated_ability": "The Scarab God",
    "activated_draw": "Arch of Orazca",
    "affinity_type": "Tezzeret, Master of the Bridge",
    "airbend_makers": "Airbender Ascension",
    "all_creatures_kw_grant": "Angel's Trumpet",
    "alt_cost_keyword": "Chameleon, Master of Disguise",
    "animate_artifact": "Karn, Silver Golem",
    "anthem_static": "Glorious Anthem",
    "any_counter_makers": "Karn's Bastion",
    "any_counter_matters": "Moira Brown, Guide Author",
    "aoe_ping": "Pestilence",
    "arcane_matters": "Tallowisp",
    "artifacts_matter": "Storm-Kiln Artist",
    "attack_matters": "Relentless Assault",
    "attractions_matter": "Rad Rascal",
    "aura_equip_kw_grant": "Rashel, Fist of Torm",
    "has_banding": "Timber Wolves",
    "base_pt_set": "Lignify",
    "base_power_matters": "Bess, Soul Nourisher",
    "big_hand_makers": "Reliquary Tower",
    "big_hand_matters": "Maro",
    "big_mana": "Gilded Lotus",
    "blink_flicker": "Flickerwisp",
    "blocked_matters": "Kitsune Blademaster",
    "blood_makers": "Bloodtithe Harvester",
    "blood_matters": "Wedding Security",
    "boast_makers": "Arni Brokenbrow",
    "boast_matters": "Birgi, God of Storytelling",
    "bounce_tempo": "Boomerang",
    "cant_block_grant": "Breeches, Eager Pillager",
    "card_draw_engine": "Phyrexian Arena",
    "cascade_makers": "The First Sliver",
    "cascade_matters": "Maelstrom Nexus",
    "cast_from_exile": "Vega, the Watcher",
    "celebration_matters": "Tuinvale Guide",
    "has_changeling": "Maskwood Nexus",
    "cheat_from_top": "Hans Eriksson",
    "cheat_into_play": "Sneak Attack",
    "clone_makers": "Cytoshape",
    "clue_makers": "Deduce",
    "clue_matters": "Tireless Tracker",
    "cmdzone_ability": "Oloro, Ageless Ascetic",
    "coin_flip": "Chance Encounter",
    "color_change": "Prismatic Lace",
    "color_hoser": "Dark Betrayal",
    "colorless_matters": "Herald of Kozilek",
    "combat_buff_engine": "Alesha, Who Laughs at Fate",
    "combat_damage_matters": "Edric, Spymaster of Trest",
    "combat_damage_to_creature": "Voracious Cobra",
    "combat_damage_to_opp": "Cold-Eyed Selkie",
    "commander_matters": "Kediss, Emberclaw Familiar",
    "companion_keyword": "Lutri, the Spellchaser",
    "conditional_self_protection": "Zurgo Helmsmasher",
    "conjure_makers": "Brave Meadowguard",
    "connive_makers": "Security Bypass",
    "control_exchange": "Meneldor, Swift Savior",
    "convoke_makers": "Chief Engineer",
    "convoke_matters": "Joyful Stormsculptor",
    "copy_limit": "Shadowborn Apostle",
    "cost_reduction": "Goblin Electromancer",
    "count_anthem": "Hold the Gates",
    "counter_control": "Ertai Resurrected",
    "counter_distribute": "Cathars' Crusade",
    "counter_doubling": "Vorel of the Hull Clade",
    "counter_grants_kw": "Bramblewood Paragon",
    "counter_manipulation": "Carnifex Demon",
    "counter_move": "Scrounging Bandar",
    "counter_place_trigger": "Flourishing Defenses",
    "counter_replace_bonus": "Hardened Scales",
    "coven_matters": "Leinore, Autumn Sovereign",
    "creature_cast_trigger": "Glimpse of Nature",
    "creature_etb": "Cathars' Crusade",
    "creature_ping": "Soul's Fire",
    "creature_recursion": "Reanimate",
    "creatures_matter": "Crusader of Odric",
    "crimes_matter": "Oko, the Ringleader",
    "curse_matters": "Lynde, Cheerful Tormentor",
    "cycling_matters": "Faith of the Devoted",
    "damage_doubling": "Fiery Emancipation",
    "damage_equal_power": "Fling",
    "damage_prevention": "Urza's Armor",
    "damage_redirect": "Cho-Manno, Revolutionary",
    "damage_reflect": "Spiteful Sliver",
    "damage_to_opp_matters": "Deus of Calamity",
    "damage_to_you_punish": "Flameblade Angel",
    "has_dash": "Zurgo Bellstriker",
    "daynight_matters": "Tovolar, Dire Overlord",
    "daynight_makers": "Tovolar, Dire Overlord",
    "death_matters": "Blood Artist",
    "debuff_makers": "Dead Weight",
    "destroy_legendary": "Hero's Demise",
    "devotion_matters": "Karametra's Acolyte",
    "has_devour": "Mycoloth",
    "dice_makers": "Captain Rex Nebula",
    "dice_matters": "Brazen Dwarf",
    "dies_recursion": "Bronzehide Lion",
    "dig_until": "Hermit Druid",
    "direct_damage": "Sizzle",
    "discard_matters": "Basking Rootwalla",
    "discard_makers": "Faithless Looting",
    "discard_outlet": "Faithless Looting",
    "discover_makers": "Curator of Sun's Creation",
    "domain_matters": "Matca Rioters",
    "donate_makers": "Harmless Offering",
    "draft_spellbook": "Cogwork Librarian",
    "draw_for_each": "Garruk, Primal Hunter",
    "draw_matters": "Chasm Skulker",
    "each_mode_player": "Vindictive Lich",
    "earthbend_makers": "Earthen Ally",
    "earthbend_matters": "Avatar Aang // Aang, Master of Elements",
    "edict_makers": "Plaguecrafter",
    "enchantments_matter": "Tuvasa the Sunlit",
    "end_the_turn": "Obeka, Brute Chronologist",
    "energy_makers": "Aether Hub",
    "energy_matters": "Whirler Virtuoso",
    "has_enlist": "Benalish Faithbonder",
    "entered_attacker": "Samut, Vizier of Naktamun",
    "evasion_denial": "Staff of the Ages",
    "evasion_self": "Slither Blade",
    "exalted_lone_attacker": "Rogue Kavu",
    "excess_damage": "Aegar, the Freezing Flame",
    "exert_matters": "Brave the Sands",
    "exhaust_makers": "Bitter Work",
    "exhaust_matters": "Pit Automaton",
    "exile_matters": "Mairsil, the Pretender",
    "exile_removal": "Banishing Light",
    "exile_until_leaves": "Oblivion Ring",
    "experience_makers": "Ezuri, Claw of Progress",
    "experience_matters": "Atreus, Impulsive Son",
    "explore_makers": "Topography Tracker",
    "explore_matters": "Wildgrowth Walker",
    "extra_combats": "Aggravated Assault",
    "extra_draw_step": "Sphinx of the Second Sun",
    "extra_end_step": "Y'shtola Rhul",
    "extra_land_drop": "Burgeoning",
    "extra_turns": "Temporal Manipulation",
    "extra_upkeep": "Sphinx of the Second Sun",
    "facedown_makers": "Unexplained Absence",
    "facedown_matters": "Etrata, Deadly Fugitive",
    "fight_makers": "Tolsimir, Friend to Wolves",
    "firebending_makers": "Fire Lord Azula",
    "firebending_matters": "Sozin's Comet",
    "flash_grant": "Vedalken Orrery",
    # ADR-0034 _matters sweep SPLIT: the MAKER arm (flash-granter doer) is flash_makers;
    # Leyline of Anticipation is a real snapshot maker. The PAYOFF arm keeps
    # flash_matters — Katara, Waterbending Master's opponent-turn cast payoff.
    "flash_makers": "Leyline of Anticipation",
    "flash_matters": "Katara, Waterbending Master",
    "flip_self": "Nezumi Graverobber // Nighteyes the Desecrator",
    "food_makers": "Spider-Ham, Peter Porker",
    "food_matters": "Trail of Crumbs",
    "forced_attack": "Public Enemy",
    "foretell_makers": "Doomskar",
    "foretell_matters": "Niko Defies Destiny",
    "free_cast": "Omniscience",
    "free_creature_payoff": "Satoru, the Infiltrator",
    "free_plot": "Fblthp, Lost on the Range",
    "free_spell_storm": "Thrasta, Tempest's Roar",
    "gain_control": "Control Magic",
    "global_ability_grant": "Cryptolith Rite",
    "goad_makers": "Disrupt Decorum",
    # _matters sweep (ADR-0034): graveyard_matters keeps a PAYOFF real case — Araumi
    # exiles cards from your graveyard as a cost and references "creature card in your
    # graveyard", firing the payoff arms but NO maker arm. Reanimate (a pure reanimator
    # MAKER) moved to graveyard_makers.
    "graveyard_makers": "Reanimate",
    "graveyard_matters": "Araumi of the Dead Tide",
    "group_hug_draw": "Wheel of Fortune",
    "group_mana": "Magus of the Vineyard",
    "hand_disruption": "Peek",
    "historic_matters": "Jhoira's Familiar",
    "impulse_top_play": "Light Up the Stage",
    "initiative_makers": "Aarakocra Sneak",
    "initiative_matters": "Imoen, Mystic Trickster",
    # ADR-0034 _matters split: the islandwalk DOER arm (bare `\bislandwalk\b`) now
    # emits island_makers — Lord of Atlantis GRANTS islandwalk. The PAYOFF arm keeps
    # island_matters — Zhou Yu's "can't attack unless defending player controls an
    # Island" cares-about-Islands restriction.
    "island_makers": "Lord of Atlantis",
    "island_matters": "Zhou Yu, Chief Commander",
    "keyword_counter": "Luminous Broodmoth",
    "keyword_grant_target": "Aim High",
    "keyword_soup": "Odric, Lunarch Marshal",
    "keyword_soup_makers": "Odric, Lunarch Marshal",
    "keyword_tribe": "Favorable Winds",
    # ADR-0034 _matters split: the MAKER arm (place_counter ck='ki') now emits
    # ki_counter_makers — Skullmane Baku PERFORMS the ki placement. The PAYOFF
    # arm keeps ki_counter_matters — Faithful Squire // Kaiso's Kamigawa-flip
    # "if there are two or more ki counters" trigger condition.
    "ki_counter_makers": "Skullmane Baku",
    "ki_counter_matters": "Faithful Squire // Kaiso, Memory of Loyalty",
    "kicked_spell_matters": "Verazol, the Split Current",
    "kill_engine": "Visara the Dreadful",
    "land_creatures_matter": "Sylvan Advocate",
    "land_denial": "Taniwha",
    "land_destruction": "Numot, the Devastator",
    "land_exchange": "Political Trickery",
    "land_protection": "Living Plane",
    "land_sacrifice_makers": "Hearthhull, the Worldseed",
    "land_sacrifice_matters": "The Gitrog Monster",
    "landfall": "Lotus Cobra",
    "lands_matter": "Dakkon Blackblade",
    "legend_rule_off": "Mirror Box",
    "legends_matter": "Reki, the History of Kamigawa",
    "lessons_matter": "Sokka, Bold Boomeranger",
    "life_payment_insurance": "Underworld Connections",
    "life_total_set": "Beacon of Immortality",
    # _matters sweep (ADR-0034): Kitchen Finks fires only the MAKER arm ("When this
    # creature enters, you gain 2 life" → a `gain_life` Effect scope you), so it proves
    # lifegain_makers cleanly (no payoff arm). Archangel of Thune keeps the PAYOFF arm
    # ("Whenever you gain life …" → Trigger event='life_gained'), proving the kept
    # lifegain_matters; its lifelink keyword also fires lifegain_makers, but the payoff
    # trigger is what satisfies lifegain_matters here.
    "lifegain_makers": "Kitchen Finks",
    "lifegain_matters": "Archangel of Thune",
    # _matters sweep (ADR-0034): Gray Merchant fires the MAKER arm ("each opponent
    # loses X life" = a lose_life drain), so it proves lifeloss_makers. Vilis fires
    # the PAYOFF arm (Trigger event='life_lost' — "whenever you lose life, draw") so
    # it proves the kept lifeloss_matters.
    "lifeloss_makers": "Gray Merchant of Asphodel",
    "lifeloss_matters": "Vilis, Broker of Blood",
    "lose_unless_hand": "Phage the Untouchable",
    "low_power_matters": "Subira, Tulzidi Caravanner",
    "ltb_matters": "Azorius Aethermage",
    "lure_makers": "Lure",
    "madness_matters": "Anje Falkenrath",
    "magecraft_matters": "Archmage Emeritus",
    "mana_amplifier": "Mana Reflection",
    "mass_bounce": "Evacuation",
    "mass_death_payoff": "Khabál Ghoul",
    "mass_removal": "Wrath of God",
    "meld_pair": "Bruna, the Fading Light",
    "mill_makers": "Stitcher's Supplier",
    "minus_counters_matter": "Crumbling Ashes",
    "miracle_grant": "Lorehold, the Historian",
    "modified_matters": "Chishiro, the Shattered Blade",
    "monarch_makers": "Azure Fleet Admiral",
    "monarch_matters": "Throne Warden",
    "multicolor_matters": "Hero of Precinct One",
    "has_mutate": "Pollywog Symbiote",
    "myriad_grant": "Legion Loyalty",
    "named_counter_misc": "Tetzimoc, Primal Death",
    "named_synergy": "Festering Newt",
    "has_ninjutsu": "Satoru Umezawa",
    "noncombat_damage_payoff": "Spitemare",
    "noncreature_cast_punish": "Kambal, Consul of Allocation",
    "nonhuman_attackers": "Winota, Joiner of Forces",
    # ADR-0034 _matters split: the MAKER arm (place_counter ck='oil') emits
    # oil_counter_makers — Armored Scrapgorger PUTS an oil counter on itself.
    # The PAYOFF arm keeps oil_counter_matters; Kuldotha Cackler fires it
    # SOLELY through the synthetic _OIL_REF reference marker (it places no oil).
    "oil_counter_makers": "Armored Scrapgorger",
    "oil_counter_matters": "Kuldotha Cackler",
    "one_punch": "Yargle and Multani",
    "opp_top_exile": "Villainous Wealth",
    "opponent_cast_matters": "Lavinia, Azorius Renegade",
    "opponent_counter_grant": "Mathas, Fiend Seeker",
    "opponent_discard": "Mind Rot",
    "opponent_draw_matters": "Underworld Dreams",
    "opponent_exile_makers": "Bojuka Bog",
    "opponent_exile_matters": "Umbris, Fear Manifest",
    "opponent_search_matters": "Ob Nixilis, Unshackled",
    "outlaw_matters": "Laughing Jasper Flint",
    "partner_background": "Astarion, the Decadent",
    "party_matters": "Archpriest of Iona",
    "per_target_payoff": "Hinata, Dawn-Crowned",
    "permanent_etb": "Amareth, the Lustrous",
    "phasing_makers": "The War Doctor",
    "play_from_top": "Future Sight",
    "plus_one_makers": "Avenger of Zendikar",
    "plus_one_matters": "Mycoloth",
    "poison_makers": "Phyresis",
    "poison_matters": "Serpent Generator",
    "power_double": "Unleash Fury",
    "power_matters": "Colossal Majesty",
    "power_tap_engine": "Marwyn, the Nurturer",
    "powerup_matters": "Extremis Elite",
    "proliferate_makers": "Evolution Sage",
    "proliferate_matters": "Ezuri, Claw of Progress",
    "protection_grant": "Benevolent Bodyguard",
    "pump_makers": "Giant Growth",
    "rad_counter_makers": "Nuclear Fallout",
    "ramp": "Karametra's Acolyte",
    "reanimator": "Loyal Retainers",
    "recast_etb": "Karai's Technique",
    "regenerate_makers": "Tribal Golem",
    "removal": "Flame Slash",
    "ring_matters": "Faramir, Field Commander",
    "ring_tempters": "Boromir, Warden of the Tower",
    "sacrifice_outlets": "Disciple of Bolas",
    "sacrifice_protection": "Sigarda, Host of Herons",
    "saddle_matters": "Guidelight Matrix",
    "saga_matters": "Keldon Warcaller",
    "scaling_pump": "Sliver Legion",
    "scavenge_fuel": "Varolz, the Scar-Striped",
    "scry_surveil_matters": "Kenessos, Priest of Thassa",
    "second_spell_matters": "Saruman of Many Colors",
    "secret_writedown": "Burning Wish",
    "seek_matters": "Adherent's Heirloom",
    "self_blink": "Norin the Wary",
    "self_counter_grow": "Adaptive Snapjaw",
    "self_death_payoff": "Kokusho, the Evening Star",
    "self_pump": "Shivan Dragon",
    "shield_counter_makers": "Boon of Safety",
    "snow_matters": "Diamond Faerie",
    "has_soulbond": "Flowering Lumberknot",
    "specialize_matters": "Alora, Rogue Companion",
    "speed_makers": "The Speed Demon",
    "speed_matters": "Howlsquad Heavy",
    "spell_copy_makers": "Twincast",
    "spell_keyword_grant": "Thrumming Stone",
    "spellcast_matters": "Talrand, Sky Summoner",
    "starting_life_matters": "Path of Bravery",
    # _matters sweep (ADR-0034): station split. Lumen-Class Frigate is a MAKER (Station
    # keyword, Spacecraft body), so it proves the station_makers arm. The station_matters
    # payoff arm (a card that only REFERENCES Spacecraft) is Focus Fire — its damage
    # formula counts "creatures and/or Spacecraft you control".
    "station_makers": "Lumen-Class Frigate",
    "station_matters": "Focus Fire",
    "stax_taxes": "Gnat Miser",
    "stickers_matter": "Aerialephant",
    "superfriends_matters": "The Chain Veil",
    "suspect_makers": "Case of the Stashed Skeleton",
    "suspect_matters": "Agency Coroner",
    "suspend_makers": "Aeon Chronicler",
    "suspend_matters": "Calciderm",
    "symmetric_damage_each": "Pestilence",
    "symmetric_stax": "Cursed Totem",
    "tap_down": "Frost Lynx",
    "tap_down_blockers": "Tromokratis",
    "tap_untap_matters": "Pheres-Band Tromper",
    "tapped_matters": "Throne of the God-Pharaoh",
    "tapper_engine": "Icy Manipulator",
    "target_own_payoff": "Monk Gyatso",
    # ADR-0039 W7 BRIDGES wave (2026-07-12): Dictate of Kruphix -> Lord of
    # Tresserhorn. target_player_draws PROMOTED — Dictate of Kruphix's
    # "each player" choice-driven skip-draw is an adjudicated SHED under
    # the crosswalk lane (group_hug_draw territory, not a directed gift),
    # so the default-ON hybrid path no longer fires it; Lord of
    # Tresserhorn's "When ~ enters, ... target opponent draws two cards"
    # is a genuine BOTH member (verified this session: legacy and
    # crosswalk both fire).
    "target_player_draws": "Lord of Tresserhorn",
    "target_redirect": "Rayne, Academy Chancellor",
    "targeting_matters": "Reality Smasher",
    "team_buff": "Brave the Sands",
    "team_evasion_grant": "Galerider Sliver",
    # _matters sweep (ADR-0034): the steal-and-cast kept-mirror DOER (Stolen Goods)
    # now fires theft_makers; the LOW gain_control / don't-own cross-open is the
    # wants_theft want-side (Dragonlord Silumgar — IR gain_control opens it via the
    # signals.py facade; the regex path drops it).
    "theft_makers": "Stolen Goods",
    "theft_protection": "Kira, Great Glass-Spinner",
    "timing_control": "City of Solitude",
    "token_copy_makers": "Helm of the Host",
    "token_doubling": "Parallel Lives",
    "token_maker": "Krenko, Mob Boss",
    "tokens_matter": "Intangible Virtue",
    "topdeck_selection": "Sensei's Divining Top",
    "topdeck_stack": "Reclaim",
    "toughness_combat": "Assault Formation",
    "treasure_makers": "Dockside Extortionist",
    # _matters sweep (ADR-0034): the make_token MAKER (Dockside) now fires
    # treasure_makers; treasure_matters is the PAYOFF side — Evereth's "was a
    # Treasure" token_subtype_ref care marker.
    "treasure_matters": "Evereth, Viceroy of Plunder",
    "tribal_etb_multi": "Goblin Assassin",
    "tribe_damage_trigger": "Toski, Bearer of Secrets",
    "trigger_doubling": "The Masamune",
    "tutor": "Demonic Tutor",
    "type_change": "Gor Muldrak, Amphinologist",
    "type_matters": "Odric, Lunarch Marshal",
    "typed_anthem_multi": "Howlpack Resurgence",
    "typed_enters_punish": "Purphoros, God of the Forge",
    "typed_spellcast": "The First Sliver",
    "has_undying_persist": "Mikaeus, the Unhallowed",
    "unspent_mana": "Leyline Tyrant",
    "untap_engine": "Seedborn Muse",
    "vanilla_matters": "Muraganda Petroglyphs",
    "variable_pt": "Nightmare",
    "vehicles_matter": "Cloudspire Captain",
    "venture_makers": "Aarakocra Sneak",
    "venture_matters": "Gloom Stalker",
    "villainous_choice": "The Valeyard",
    "void_warp_makers": "Starfield Vocalist",
    "void_warp_matters": "Alpharael, Stonechosen",
    # _matters sweep (ADR-0034): Kor Outfitter "attach target Equipment you control
    # to target creature" is a pure attach-OTHER doer (no payoff sub-tell), so it
    # proves the MAKER arm voltron_makers. Sram fires the PAYOFF arm (a cast-an-Aura/
    # Equipment-spell trigger), so it keeps the kept voltron_matters.
    "voltron_makers": "Kor Outfitter",
    "voltron_matters": "Sram, Senior Edificer",
    "voting_makers": "Capital Punishment",
    "voting_matters": "Grudge Keeper",
    "wants_cloning": "Arcum Dagsson",
    "wants_theft": "Dragonlord Silumgar",
    "waterbend_makers": "Spirit Water Revival",
    "waterbend_matters": "Avatar Aang // Aang, Master of Elements",
    "win_lose_game": "Thassa's Oracle",
    "xspell_matters": "Zaxara, the Exemplary",
}


def test_every_case_key_is_served():
    """Every proven key must be in the served-key manifest — a case for a key the
    extractor cannot emit is a stale row, not coverage."""
    from mtg_utils._deck_forge.lanes import SERVED_SIGNAL_KEYS

    unserved = sorted(set(_REAL_CASES) - set(SERVED_SIGNAL_KEYS))
    assert not unserved, f"_REAL_CASES rows for unserved keys: {unserved}"


@pytest.mark.parametrize("key", sorted(_REAL_CASES))
def test_served_key_fires_on_real_card(key):
    """The production extractor emits the key for its representative real card.

    Every case loads the card + its production parses from the committed snapshot,
    so the proof runs the same structural builds production serves."""
    name = _REAL_CASES[key]
    card = test_card(name)
    hybrid_keys = {s.key for s in extract_signals(card)}
    assert key in hybrid_keys, f"{key} not served for {name}"


def test_extra_combats_restriction_fold_fires_via_ir():
    """The arm_gap card (ADR-0027): phase folds Illusionist's Gambit's whole body
    into a single `restriction` Effect and never emits the `extra_combat` category,
    so the additional-combat-phase clause survives only in that Effect's raw. The
    restriction-fold structural arm reads it there — replacing the deleted
    EXTRA_COMBATS_REGEX whole-card mirror. CR 505.1a."""
    keys = {s.key for s in test_signals("Illusionist's Gambit")}
    assert "extra_combats" in keys


# ── ADR-0027 #24m F1 — forced_attack → extra_combats re-route correction ──────


def test_extra_combat_rider_is_not_forced_attack():
    """F1 correction: World at War's "Untap all creatures that attacked this turn …
    additional combat phase" is an EXTRA-COMBAT rider (CR 505.1a), NOT a forced-attack
    compulsion (CR 508.1). It rides the extra_combats lane via phase's `extra_combat`
    Effect, and the narrowed forced_attack mirror (which dropped the `that attacked this
    turn` arm) no longer mis-fires forced_attack for it."""
    card = test_card("World at War")
    keys = {s.key for s in extract_signals(card)}
    assert "extra_combats" in keys
    assert "forced_attack" not in keys


def test_forced_attack_punisher_still_fires():
    """F1 correction keeps the attack-RESTRICTION/punisher half: Season of the Witch
    destroys creatures that DIDN'T attack — the `didn't attack this turn` mirror (the
    one structural form phase carries no node for) still opens forced_attack. CR 508.1."""
    card = test_card("Season of the Witch")
    assert "forced_attack" in {s.key for s in extract_signals(card)}


# ── ADR-0027 #24m F1 — base_pt_set SETTER recovery ────────────────────────────


def test_base_pt_set_single_target_animate_fires_via_in_addition_hook():
    """F1 2a: Vengeant Earth's "becomes a 4/4 Elemental creature … in addition to its
    other types" — phase ALREADY emits a base_pt_set Effect, but its raw names no "base
    power", so the old gate missed it (it leaned on the carved mirror). The
    _BASE_PT_ANIMATE_HOOK arm now reads the existing structure. CR 613.4b / 205.1b."""
    card = test_card("Vengeant Earth")
    ir = test_card_ir("Vengeant Earth")
    assert any(
        e.category == "base_pt_set" for ab in ir.all_abilities() for e in ab.effects
    )
    assert "base_pt_set" in {s.key for s in extract_signals(card)}


def test_base_pt_set_dynamic_setter_recovered_node_fires():
    """F1 2b: Fractalize's "becomes … with base power and toughness each equal to X plus
    1" is a DYNAMIC setter phase routed to `animate` with no base_pt_set node.
    supplement._recover_dynamic_base_pt_set re-synthesizes a base_pt_set node (scope any,
    subject None) so the lane reads STRUCTURE, not the deleted whole-card mirror arm. CR
    613.4b layer 7b."""
    card = test_card("Fractalize")
    ir = test_card_ir("Fractalize")
    assert any(
        e.category == "base_pt_set" for ab in ir.all_abilities() for e in ab.effects
    )
    assert "base_pt_set" in {s.key for s in extract_signals(card)}


def test_base_pt_set_mass_animator_stays_out():
    """F1 over-fire guard: the symmetric MASS-animator Living Plane ("All lands are 1/1
    creatures") sets P/T but is a land-creatures THEME, not a base-P/T build-around — it
    says neither "base power" nor "N/N … in addition to its other types", so neither the
    animate hook nor the dynamic recovery admits it. base_pt_set stays OUT (#26)."""
    card = test_card("Living Plane")
    assert "base_pt_set" not in {s.key for s in extract_signals(card)}


# ── ADR-0027 #24n G1 — base_power_matters NEW LANE (base-P/T REFERENCE payoffs) ──


def test_base_power_matters_reference_fires_and_leaves_base_pt_set():
    """G1: a base-power REFERENCE — Bess, Soul Nourisher cares about "creatures you
    control with base power and toughness 1/1" — merely REFERS to base P/T (CR 613.4b
    sentence 2) and SETS nothing, so it carries NO base_pt_set node. The supplement
    `_recover_base_power_ref` synthesizes a base-specific `BasePtRef` marker so the new
    base_power_matters arm reads it STRUCTURALLY. It NO LONGER fires base_pt_set (the
    over-firing references mirror was deleted)."""
    card = test_card("Bess, Soul Nourisher")
    ir = test_card_ir("Bess, Soul Nourisher")
    assert not any(
        e.category == "base_pt_set" for ab in ir.all_abilities() for e in ab.effects
    )
    assert any(
        isinstance(e.subject, Filter) and "BasePtRef" in e.subject.predicates
        for ab in ir.all_abilities()
        for e in ab.effects
    )
    keys = {s.key for s in extract_signals(card)}
    assert "base_power_matters" in keys
    assert "base_pt_set" not in keys


def test_base_power_matters_fires_zinnia():
    """G1: Zinnia, Valley's Voice — "~ gets +X/+0, where X is the number of other
    creatures you control with base power 1" — a base-power REFERENCE payoff. Fires
    base_power_matters via the recovered `BasePtRef` marker, NOT base_pt_set."""
    card = test_card("Zinnia, Valley's Voice")
    keys = {s.key for s in extract_signals(card)}
    assert "base_power_matters" in keys
    assert "base_pt_set" not in keys


def test_base_pt_set_setter_does_not_fire_base_power_matters():
    """G1 boundary guard: Lignify is a genuine SETTER ("has base power and toughness
    0/0" — CR 613.4b sentence 1) — it keeps its base_pt_set node and carries NO
    `BasePtRef` marker, so it fires base_pt_set and NOT base_power_matters. The set-vs-
    refer boundary holds."""
    card = test_card("Lignify")
    ir = test_card_ir("Lignify")
    assert any(
        e.category == "base_pt_set" for ab in ir.all_abilities() for e in ab.effects
    )
    assert not any(
        isinstance(e.subject, Filter) and "BasePtRef" in e.subject.predicates
        for ab in ir.all_abilities()
        for e in ab.effects
    )
    keys = {s.key for s in extract_signals(card)}
    assert "base_pt_set" in keys
    assert "base_power_matters" not in keys


def test_creatures_matter_mass_grant_fires_via_ir():
    """A MASS keyword grant to the generic creature board (Champion of Lambholt's
    CantBeBlockedBy) → creatures_matter via the IR grant_keyword arm, not regex."""
    keys = {s.key for s in test_signals("Champion of Lambholt")}
    assert "creatures_matter" in keys


def test_creatures_matter_does_not_fire_on_a_subtype_lord():
    """The over-fire boundary: a SUBTYPE lord ("Goblin creatures you control get
    +1/+1") is tribal (type_matters, CR 205.3), NOT the generic go-wide lane — its
    IR pump subject carries the Goblin subtype, so the generic-set gate rejects it."""
    keys = {s.key for s in test_signals("Goblin King")}
    assert "creatures_matter" not in keys


def test_blood_matters_fires_from_a_sacrifice_effect_subject():
    """Token-subtype sacrifice PAYOFF (effect side): Wedding Security "sacrifice a
    Blood token" — a `sacrifice` Effect whose subject Filter carries the Blood
    subtype opens blood_matters via the IR, not the deleted floor regex."""
    keys = {s.key for s in test_signals("Wedding Security")}
    assert "blood_matters" in keys


def test_blood_matters_fires_from_a_sacrificed_trigger_subject():
    """Token-subtype sacrifice PAYOFF (trigger side): Blood Hypnotist "whenever you
    sacrifice one or more Blood tokens" — the trigger's own valid_card Filter carries
    the Blood subtype; served by the gap-gated blood_sacrificed_trigger_payoff
    bridge (bridge_ledger.BRIDGES) until _resource_token_matters grows a
    Sacrificed-trigger subject arm."""
    keys = {s.key for s in test_signals("Blood Hypnotist")}
    assert "blood_matters" in keys


def test_blood_makers_fires_from_a_recovered_choice_list_maker():
    """Token-subtype maker (choice list): Transmutation Font "create your choice of
    a Blood token, a Clue token, or a Food token" — the typed Token nodes live on
    ChooseOneOf BRANCHES the concept decoration doesn't descend; served by the
    gap-gated choice_list_token_maker_{blood,clue,food} bridges
    (bridge_ledger.BRIDGES) until the overlay decorates branch effects."""
    keys = {s.key for s in test_signals("Transmutation Font")}
    assert "blood_makers" in keys
    assert "clue_makers" in keys
    assert "food_makers" in keys


def test_blood_makers_fires_from_a_recovered_granted_ability_maker():
    """Token-subtype maker (granted ability): Ceremonial Knife grants the equipped
    creature a quoted "create a Blood token" trigger — the typed Token node lives
    inside a GrantTrigger modification the concept decoration doesn't descend;
    served by the gap-gated granted_trigger_blood_token_maker bridge
    (bridge_ledger.BRIDGES) until the overlay walks granted-trigger bodies."""
    keys = {s.key for s in test_signals("Ceremonial Knife")}
    assert "blood_makers" in keys


def test_blood_makers_fires_from_a_create_x_unimplemented_residue():
    """Token-subtype maker (create-X residue): Odric, Blood-Cursed "create X Blood
    tokens, where X is the number of abilities ..." parks WHOLE as phase
    Unimplemented('create'); recovery decorates make_token with an EMPTY subject —
    the choice_list_token_maker_blood bridge's second match arm serves it."""
    keys = {s.key for s in test_signals("Odric, Blood-Cursed")}
    assert "blood_makers" in keys


def test_folded_dungeon_text_only_tree_serves_lifeloss_makers():
    """ADR-0025 flagship: Tomb of Annihilation is a zero-unit text-only tree
    (phase covers no dungeon), so its "Each player loses N life" rooms ride the
    folded_object_text_only_each_player_loses bridge — scope "each"."""
    idents = {(s.key, s.scope) for s in test_signals("Tomb of Annihilation")}
    assert ("lifeloss_makers", "each") in idents


# ── spellcast_matters (ADR-0027 signals-only) — scope discrimination + recovery ──


def test_spellcast_matters_does_not_fire_on_opponent_cast():
    """Mystic Remora's opponent-cast hoser is opponent_cast_matters, NOT spellcast."""
    keys = {s.key for s in test_signals("Mystic Remora")}
    assert "spellcast_matters" not in keys
    assert "opponent_cast_matters" in keys


def test_spellcast_matters_does_not_fire_on_symmetric_player_cast():
    """A symmetric 'whenever a player casts' punisher (no 'you cast') is not the
    you-cast spellslinger payoff."""
    keys = {s.key for s in test_signals("Eidolon of the Great Revel")}
    assert "spellcast_matters" not in keys


def test_spellcast_matters_fires_on_prowess_keyword():
    """Prowess (CR 702.108a) opens spellcast_matters via the Scryfall keyword array."""
    keys = {s.key for s in test_signals("Jeskai Windscout")}
    assert "spellcast_matters" in keys


def test_spellcast_matters_fires_from_kept_mirror_cost_reducer():
    """An instant/sorcery cost-reducer (Baral) has NO cast_spell trigger — it rides
    the byte-identical _detect_spellcast_matters kept mirror over the oracle."""
    keys = {s.key for s in test_signals("Baral, Chief of Compliance")}
    assert "spellcast_matters" in keys


def test_dies_recursion_self_return_fires_via_recovered_marker():
    """ADR-0027 #24c — the granted "When this dies, return it to the battlefield"
    self-recursion phase flattens to a place_counter(p1p1) Effect (the +1/+1-counter
    rider it saw) and DROPS the reanimate. supplement._recover_dies_return synthesizes
    a dedicated `self_recursion` marker the dies_recursion arm reads; the pure-regex
    path no longer carries the lane (the DIES_RECURSION_REGEX word mirror is deleted).
    CR 700.4 / 603.6c."""
    card = test_card("Feign Death")
    ir = test_card_ir("Feign Death")
    cats = {e.category for ab in ir.all_abilities() for e in ab.effects}
    assert "self_recursion" in cats, "recovered self_recursion marker missing"
    assert "dies_recursion" in {s.key for s in extract_signals(card)}


def test_dies_recursion_granter_fires_off_undying_persist_marker():
    """ADR-0027 #24c — a keyword-LESS undying GRANTER (Mikaeus grants undying to a
    class of creatures, but bears no undying keyword itself) rides phase's
    `undying_persist` marker into dies_recursion, replacing the word mirror's bare
    \\bundying\\b match. CR 702.92.

    ADR-0039 step 7: the ``undying_persist`` marker was a project.py-only name
    and died with the legacy builder; the protected behavior — dies_recursion
    firing for the keyword-less granter — is served by the crosswalk's own
    ``dies_recursion`` lane (the `_UNDYING_PERSIST_GRANT` grant-verb anchor now
    lives in ``text_idioms``, read by ``tree_synthesis``), asserted below on
    the production path."""
    card = test_card("Mikaeus, the Unhallowed")
    assert "dies_recursion" in {s.key for s in extract_signals(card)}


def test_counter_manipulation_cost_removal_fires_via_recovered_kind():
    """ADR-0027 #24c — Triskelion removes a +1/+1 counter as an activation COST; phase
    emits the `removecounter` cost token but DROPS the kind, so no remove_counter
    Effect exists. supplement._recover_counter_removal re-parses the kind (p1p1) from
    raw onto a synthetic remove_counter Effect the counter_manipulation arm reads; the
    cost-tail word mirror is deleted. CR 122.1."""
    card = test_card("Triskelion")
    ir = test_card_ir("Triskelion")
    assert any(
        e.category == "remove_counter" and e.counter_kind == "p1p1"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "recovered remove_counter(p1p1) missing"
    assert "counter_manipulation" in {s.key for s in extract_signals(card)}


def test_tap_untap_matters_fires_off_becomes_untapped_event():
    """ADR-0027 #24c — Arbiter of the Ideal's Inspired "becomes untapped" trigger:
    phase's structured `Untaps` mode now projects to the first-class `untaps` event
    (was folded to `other`), and tap_untap_matters reads ev in {taps, untaps}. The
    becomes-(un)tapped word mirror is deleted. CR 701.20a / 702.108."""
    card = test_card("Arbiter of the Ideal")
    ir = test_card_ir("Arbiter of the Ideal")
    assert any(
        ab.trigger is not None and ab.trigger.event == "untaps"
        for ab in ir.all_abilities()
    ), "becomes-untapped trigger not projected to event=='untaps'"
    assert "tap_untap_matters" in {s.key for s in extract_signals(card)}


def test_tap_untap_matters_recovers_unknown_mode_becomes_tapped():
    """ADR-0039 task #82 (the step-7 tombstone, now closed) — Darksteel
    Garrison's "Whenever fortified land becomes tapped" is an Unknown-mode
    trigger phase leaves at ``event=='other'``;
    ``tree_synthesis._arm_tap_untap_becomes`` reads the trigger's own
    ``mode.inner`` residue and re-types it to the "taps" concept, so
    ``tap_untap_matters`` reads STRUCTURE for the tail too. CR 603.2e (named
    becomes-tapped/untapped trigger events) / 701.26a (tap)."""
    assert "tap_untap_matters" in {s.key for s in test_signals("Darksteel Garrison")}


def test_tap_untap_matters_unknown_mode_becomes_tapped_siblings():
    """ADR-0039 task #82 — the OTHER 2 commander-legal corpus members of the
    same Unknown-mode becomes-tapped tail (blast-radius scan, 2026-07-12):
    Royal Decree's "a Swamp, Mountain, black permanent, or red permanent
    becomes tapped" (the trailing disjunct overflows into a nested ``other``
    Unimplemented node the SAME trigger unit owns — also read) and Roots of
    Life's "a land of the chosen type an opponent controls becomes tapped".
    Both are genuine tap_untap_matters gains, not over-fires: each is the
    idiomatic "whenever ~ becomes tapped, PAYOFF" shape CR 603.2e names.
    CR 701.26a (tap)."""
    assert "tap_untap_matters" in {s.key for s in test_signals("Royal Decree")}
    assert "tap_untap_matters" in {s.key for s in test_signals("Roots of Life")}


# ── ADR-0027 #24d (SIDECAR v55) — SUPPLEMENT_RECOVER B3 real-card structural pins ──
# Each proves the lane fires (or correctly does NOT) off the SUPPLEMENT-recovered
# structure in the REAL projected IR (test_card_ir = a verbatim sidecar slice), not a
# regex mirror — the mirrors for cost_reduction + clone_makers are deleted.


def test_cost_reduction_recovered_ability_cost_reducer_dragonkin():
    """Dragonkin Berserker's "Boast abilities you activate cost {1} less to activate"
    is dropped by phase (no cost_reduction Effect); supplement._recover_cost_reduction
    synthesizes one, so the structural arm fires cost_reduction. CR 601.2f."""
    keys = {s.key for s in extract_signals(test_card("Dragonkin Berserker"))}
    assert "cost_reduction" in keys


def test_cost_reduction_recovered_defiler_conditional():
    """Defiler of Vigor's "Those spells cost {G} less to cast" conditional reducer is
    dropped by phase; the recovery synthesizes the cost_reduction Effect. CR 601.2f."""
    keys = {s.key for s in extract_signals(test_card("Defiler of Vigor"))}
    assert "cost_reduction" in keys


def test_cost_reduction_recovered_saga_chapter_collapse():
    """Invasion of the Giants' chapter-III reducer collapses to a raw "Chapter 3"
    Effect that fails the arm's subject-None screen; the recovery still synthesizes a
    genuine reducer from the oracle clause, so cost_reduction fires. CR 601.2f."""
    keys = {s.key for s in extract_signals(test_card("Invasion of the Giants"))}
    assert "cost_reduction" in keys


def test_clone_makers_recovered_creature_copy_etb():
    """Spark Double's "enter as a copy of a creature" replacement is folded by phase to
    a non-clone node; supplement._recover_clone_creature synthesizes a Creature-subject
    clone Effect, so the copied-type arm fires clone_makers. CR 707.2."""
    keys = {s.key for s in extract_signals(test_card("Spark Double"))}
    assert "clone_makers" in keys


def test_clone_makers_recovered_phase_mistyped_creature_copy_dermotaxi():
    """Dermotaxi copies a CREATURE card ("becomes a copy of the exiled card") but phase
    types its clone subject 'Artifact' (the "Vehicle artifact" rider). The recovery
    runs anyway (the Artifact-typed clone does not fire clone_makers) and recovers the
    Creature copy, so clone_makers fires. CR 707.2."""
    keys = {s.key for s in extract_signals(test_card("Dermotaxi"))}
    assert "clone_makers" in keys


def test_clone_makers_does_not_fire_on_a_noncreature_copy_overfire():
    """Copy Artifact copies an ARTIFACT only (CR 707.2 — an artifact copy, not a
    creature clone). With the over-broad mirror deleted, it correctly does NOT fire
    clone_makers (the creature-blind over-fire is shed); it keeps enchantments_matter
    (it is an Enchantment)."""
    keys = {s.key for s in extract_signals(test_card("Copy Artifact"))}
    assert "clone_makers" not in keys


def test_opponent_discard_recovered_damage_connect_specter():
    """Abyssal Specter's "deals damage to a player, that player discards" is two
    disconnected pieces (a damage-to-player trigger + a discard scope 'any'); supplement.
    _recover_opponent_discard links them and appends a discard scope 'opp', so the arm
    fires opponent_discard. CR 510.1c / 701.9."""
    keys = {s.key for s in extract_signals(test_card("Abyssal Specter"))}
    assert "opponent_discard" in keys


def test_opponent_discard_recovered_bounce_then_discard():
    """Recoil's "Return target permanent …, then that player discards" — the discardER
    is the bounce target's controller (an opponent); the recovery appends a discard
    scope 'opp'. CR 701.9."""
    keys = {s.key for s in extract_signals(test_card("Recoil"))}
    assert "opponent_discard" in keys


def test_opponent_discard_does_not_fire_on_combat_damage_self_loot():
    """Academy Raider's "deals combat damage to a player, you may discard a card. If you
    do, draw" is a SELF-loot (the discardER is YOU), not an opponent discard — the
    recovery's opponent-directed tell ("that player discards") is absent, so it does NOT
    fire opponent_discard. CR 701.8a (loot) vs 701.9 (forced discard)."""
    keys = {s.key for s in extract_signals(test_card("Academy Raider"))}
    assert "opponent_discard" not in keys


# ── ADR-0027 #24h (SIDECAR v56) — SUPPLEMENT_RECOVER C2 real-card structural pins ──
# Each proves the lane fires (or correctly does NOT) off the SUPPLEMENT-recovered
# subject / scope / trigger in the REAL projected IR — the facedown / tap_down /
# damage_to_opp mirrors are deleted.


def test_facedown_recovered_carrier_backslide():
    """Backslide's "Turn target creature with a morph ability face down" leaves no native
    face-down structure in phase's parse (the face-down qualifier is dropped), so
    supplement._recover_facedown appends a `facedown_ref` carrier whose subject carries the
    "Face-down" marker and the effect-subject arm fires facedown_matters. CR 708.2.

    (This replaces the old Break Open case: phase v0.8.0 now emits a native `turn_face_up`
    Effect for "turn … face up", so Break Open no longer needs the recovery — see
    test_facedown_native_turn_face_up_break_open. The recovery still fires for ~99 cards
    phase leaves face-down-blind, of which Backslide is a clean morph-family example.)"""
    ir = test_card_ir("Backslide")
    assert any(
        e.category == "facedown_ref" and "Face-down" in e.subject.subtypes
        for ab in ir.all_abilities()
        for e in ab.effects
        if e.subject is not None
    ), "recovered facedown_ref carrier missing"
    keys = {s.key for s in extract_signals(test_card("Backslide"))}
    assert "facedown_matters" in keys


def test_facedown_native_turn_face_up_break_open():
    """Break Open's "Turn target face-down creature … face up" gains a native `turn_face_up`
    Effect under phase v0.8.0 (the v0.1.60 parse dropped it, which the recovery bridged).
    So _recover_facedown correctly SKIPS it (native facedown structure present) yet
    facedown_matters still fires off the native carrier — the bump closing the gap, not a
    regression. CR 708.2."""
    ir = test_card_ir("Break Open")
    assert any(
        e.category == "turn_face_up" for ab in ir.all_abilities() for e in ab.effects
    ), "expected native turn_face_up effect under phase v0.8.0"
    assert not any(
        e.category == "facedown_ref"
        and (e.raw or "") == "face-down reference (recovered)"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "recovery should skip a card phase parses natively"
    keys = {s.key for s in extract_signals(test_card("Break Open"))}
    assert "facedown_matters" in keys


def test_facedown_does_not_fire_on_name_only_disguise():
    """Chameleon, Master of Disguise is a clone with NO face-down mechanic — only its
    NAME contains "Disguise". The recovery strips the card name before matching, so it is
    NOT swept in (a precision gain over the name-blind regex). CR 707.2."""
    ir = test_card_ir("Chameleon, Master of Disguise")
    assert not any(
        e.category == "facedown_ref" for ab in ir.all_abilities() for e in ab.effects
    )
    keys = {s.key for s in extract_signals(test_card("Chameleon, Master of Disguise"))}
    assert "facedown_matters" not in keys


def test_tap_down_recovered_opp_controller_mind_spiral():
    """Mind Spiral's gift "tap target creature an opponent controls" projects with the
    tap subject DROPPED to None; supplement._recover_tap_down synthesizes a Creature
    subject with controller=='opp', so the structural tap arm fires tap_down. CR 701.20.

    ADR-0039 step 7: the legacy marker check (the exact project.py projection
    shape) died with the builder; the protected behavior — tap_down firing —
    is served by the crosswalk's own structural path (the card's ``tap_untap``
    effect concept feeds the tap_down lane; ``_recover_tap_down`` itself
    survives in ``supplement.py`` as ``field_corrections``' card-level (b)
    arm), asserted below on the production path."""
    keys = {s.key for s in extract_signals(test_card("Mind Spiral"))}
    assert "tap_down" in keys


def test_tap_down_recovered_skip_untap_step_brine_elemental():
    """Brine Elemental's "each opponent skips their next untap step" is a no-tap tempo
    lock; supplement._recover_tap_down resolves the anaphor to `skip_step` scope=='opp',
    read by the new skip-untap arm. CR 701.20.

    ADR-0039 step 7: the legacy marker check died with the builder (see Mind
    Spiral above); the protected behavior — tap_down firing for the skip-untap
    lock — is served by the crosswalk's own structural path (phase's native
    ``skip_next_step`` effect concept on this card), asserted below on the
    production path."""
    keys = {s.key for s in extract_signals(test_card("Brine Elemental"))}
    assert "tap_down" in keys


def test_damage_to_opp_recovered_quoted_trigger_serpent_generator():
    """Serpent Generator's token grant "Whenever ~ deals damage to a player, that player
    gets a poison counter" is a quoted trigger phase leaves unstructured;
    supplement._recover_damage_to_opp synthesized a deals_damage(DamageToPlayer)
    trigger, so the existing arm fired damage_to_opp_matters. CR 119.3.

    ADR-0039 step 7: the legacy marker check (that exact synthesized trigger
    shape, a project.py-only recovery) died with the builder; the protected
    behavior — damage_to_opp_matters firing for the quoted token trigger — is
    served STRUCTURALLY by the crosswalk's damage-to-player trigger cluster
    (``iter_nested_trigger_defs`` + ``damage_to_player_trigger_kind`` reads the
    granted token's own trigger definition — verified kind='Any' this step),
    asserted below on the production path."""
    keys = {s.key for s in extract_signals(test_card("Serpent Generator"))}
    assert "damage_to_opp_matters" in keys


def test_extra_land_drop_recovered_cascade_reanimate_averna():
    """ADR-0027 #24l — Averna's "As you cascade, you may put a land card from among the
    exiled cards onto the battlefield" is the YOUR land-into-play put phase mis-types as
    a `reanimate` Effect (off cat=='cheat_play'). supplement._recover_extra_land_drop
    appends a canonical cheat_play Land (controller='you') Effect the extra_land_drop arm
    reads; the whole signals mirror is deleted. CR 305.4."""
    ir = test_card_ir("Averna, the Chaos Bloom")
    assert any(
        e.category == "cheat_play"
        and isinstance(e.subject, Filter)
        and "Land" in e.subject.card_types
        and e.subject.controller == "you"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "recovered cheat_play Land (controller=you) missing"
    card = test_card("Averna, the Chaos Bloom")
    assert "extra_land_drop" in {s.key for s in extract_signals(card)}


def test_extra_land_drop_recovered_empty_raw_modal_confluence():
    """ADR-0027 #24l — Riveteers Confluence's modal "put a land card from your hand or
    graveyard onto the battlefield" reaches phase as a cheat_play Land controller='any'
    with an EMPTY raw (the "or graveyard" disjunction defeats the YOUR pin), which the
    arm's controller=='you' gate misses. The supplement's joined-oracle recovery appends
    a controller='you' cheat_play Land so the arm fires. CR 305.4."""
    card = test_card("Riveteers Confluence")
    assert "extra_land_drop" in {s.key for s in extract_signals(card)}


def test_group_hug_draw_recovered_folded_each_player_scope_grothama():
    """ADR-0027 #24l — Grothama's "each player draws cards equal to the amount of damage
    …" is a symmetric group-hug draw phase folds to scope=='any' (the variable amount
    defeats its each-scope). supplement._recover_group_hug_draw_scope re-stamped
    scope=='each' on the draw, so the lane read STRUCTURE — and Grothama correctly LEAVES
    target_player_draws (a directed-draw lane scope=='any' feeds; an each-player draw is
    never player-directed). CR 121 / 120.2.

    ADR-0039 step 7: the legacy scope-marker check (a project.py-only recovery
    stamp) died with the builder; the protected behavior — group_hug_draw fires
    AND target_player_draws stays off — is served by the crosswalk's own
    structural group-hug path (the card's ``draw`` effect concept; ADR-0039
    step 5 finding), asserted below on the production path."""
    card = test_card("Grothama, All-Devouring")
    keys = {s.key for s in extract_signals(card)}
    assert "group_hug_draw" in keys
    assert "target_player_draws" not in keys


# ── lf_ramp (2026-07-13 signal-key convention change) ──────────────────────
# Land-fetch-to-battlefield is RAMP, not tutor (mirrors card_classify.is_ramp;
# CR 701.23/701.23a for the search action, CR 305.6 for the basics, CR 205.3i
# for the full land-type vocabulary). Pinned against real snapshot records on
# the production extract path (testkit.test_signals), per clause/mode:
#
#   * a NONLAND card's land-to-battlefield search fires ramp, never tutor
#     (Rampant Growth structural; Wayfarer's Bauble activated; Galactic
#     Wayfarer via the Lander known-token tree's text-only arm);
#   * a land fetch TO HAND (Sylvan Scrying) or an arbitrary-card search
#     (Demonic Tutor) stays tutor and never gains ramp;
#   * a modal clause that can do both fires BOTH keys (Archdruid's Charm's
#     "creature or land card … onto the battlefield tapped if it's a land
#     card. Otherwise … your hand").


class TestLandFetchRampReroute:
    @pytest.mark.parametrize(
        "name",
        [
            "Rampant Growth",
            "Wayfarer's Bauble",
            "Galactic Wayfarer",
        ],
    )
    def test_land_fetch_to_battlefield_is_ramp_not_tutor(self, name):
        keys = {s.key for s in test_signals(name)}
        assert "ramp" in keys, f"{name} must fire ramp (lf_ramp)"
        assert "tutor" not in keys, f"{name} must not fire tutor (lf_ramp)"

    @pytest.mark.parametrize("name", ["Sylvan Scrying", "Demonic Tutor"])
    def test_hand_or_arbitrary_search_stays_tutor(self, name):
        keys = {s.key for s in test_signals(name)}
        assert "tutor" in keys, f"{name} must keep tutor"
        assert "ramp" not in keys, f"{name} must not gain ramp"

    def test_modal_land_or_creature_search_fires_both(self):
        """Archdruid's Charm mode 1 can fetch a creature to hand (tutor) OR
        a land onto the battlefield (ramp) — the adjudicated keep-both
        modal."""
        keys = {s.key for s in test_signals("Archdruid's Charm")}
        assert "ramp" in keys
        assert "tutor" in keys


def test_every_emitted_key_is_manifest_served():
    """Corpus direction of the key-agreement contract (ADR-0014): over every
    snapshot card, the production extractor emits only manifest-served keys.
    This replaces the deleted in-extractor filter — a lane emitting an
    unlisted key now fails HERE, loudly, instead of being silently dropped."""
    import json
    from pathlib import Path

    from mtg_utils._deck_forge.lanes import SERVED_SIGNAL_KEYS
    from mtg_utils.testkit import snapshot_path

    names = list(json.loads(Path(snapshot_path()).read_text())["cards"])
    stray: dict[str, set[str]] = {}
    for name in names:
        emitted = {s.key for s in test_signals(name)}
        extra = emitted - SERVED_SIGNAL_KEYS
        if extra:
            stray[name] = extra
    assert not stray, f"keys emitted outside SERVED_SIGNAL_KEYS: {stray}"
