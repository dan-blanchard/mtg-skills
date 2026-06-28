"""Durable invariant for the ADR-0027 regex→Card-IR strangler.

For EVERY key in ``MIGRATED_KEYS``, the migration must be real and complete:

  * ``extract_signals`` (the legacy regex path) must NO LONGER emit the key — its
    oracle-regex production (``_DETECTORS`` / ``_HAND_FLOOR`` / ``SWEEP_DETECTORS``
    rows + any ``add()``) is deleted.
  * ``extract_signals_hybrid(card, ir)`` (the production dispatcher) DOES emit it,
    served from the Card IR path (``extract_signals_ir``).

Each REAL case (``_REAL_CASES``) is a real card looked up by name from the committed
snapshot (``mtg_utils.testkit``): ``test_card(name)`` is the minimal Scryfall record,
``test_card_ir(name)`` is the REAL projected IR (a verbatim sidecar slice). So the
proof runs the SAME IR production parses — no hand-built ``_ir(Ability(...))`` shape
that silently drifts from ``project_card``, and no phase / sidecar dependency in CI.

A handful of cases stay synthetic on purpose (``_SYNTHETIC_CASES``): a placeholder
mechanic with no real representative, or a key whose real record can't satisfy the
"regex drops it" invariant because of a known residual producer / structural-recovery
gap (each flagged with a TODO). A new migration batch adds one ``key: name`` row to
``_REAL_CASES`` (and a ``build-card-snapshot`` run); the parametrization then guards
it forever.
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.signals import (
    MIGRATED_KEYS,
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
from mtg_utils.testkit import test_card, test_card_ir


def _ir(*abilities: Ability, keywords: tuple[str, ...] = ()) -> Card:
    return Card(
        oracle_id="x",
        name="X",
        faces=(Face(name="X", keywords=keywords, abilities=tuple(abilities)),),
    )


# Real-card cases: migrated key → the representative card NAME. The card + its REAL
# projected IR come from the committed snapshot, so the migration is proven against
# the exact IR production parses (ADR-0027 / task #25). Keep sorted by key.
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
    "any_counter_matters": "Karn's Bastion",
    "aoe_ping": "Pestilence",
    "arcane_matters": "Tallowisp",
    "artifacts_matter": "Storm-Kiln Artist",
    "attack_matters": "Relentless Assault",
    "attractions_matter": "Rad Rascal",
    "aura_equip_kw_grant": "Rashel, Fist of Torm",
    "has_banding": "Timber Wolves",
    "base_pt_set": "Lignify",
    "base_power_matters": "Bess, Soul Nourisher",
    "big_hand_matters": "Reliquary Tower",
    "big_mana": "Gilded Lotus",
    "blink_flicker": "Flickerwisp",
    "blocked_matters": "Kitsune Blademaster",
    "blood_makers": "Bloodtithe Harvester",
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
    "convoke_matters": "Chief Engineer",
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
    "dice_matters": "Brazen Dwarf",
    "dies_recursion": "Bronzehide Lion",
    "dig_until": "Hermit Druid",
    "direct_damage": "Sizzle",
    "discard_matters": "Basking Rootwalla",
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
    "energy_matters": "Aether Hub",
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
    "explore_matters": "Topography Tracker",
    "extra_combats": "Aggravated Assault",
    "extra_draw_step": "Sphinx of the Second Sun",
    "extra_end_step": "Y'shtola Rhul",
    "extra_land_drop": "Burgeoning",
    "extra_turns": "Temporal Manipulation",
    "extra_upkeep": "Sphinx of the Second Sun",
    "facedown_matters": "Etrata, Deadly Fugitive",
    "fight_makers": "Tolsimir, Friend to Wolves",
    "firebending_makers": "Fire Lord Azula",
    "firebending_matters": "Sozin's Comet",
    "flash_grant": "Vedalken Orrery",
    "flash_matters": "Leyline of Anticipation",
    "flip_self": "Nezumi Graverobber // Nighteyes the Desecrator",
    "food_matters": "Trail of Crumbs",
    "forced_attack": "Public Enemy",
    "foretell_matters": "Niko Defies Destiny",
    "free_cast": "Omniscience",
    "free_creature_payoff": "Satoru, the Infiltrator",
    "free_plot": "Fblthp, Lost on the Range",
    "free_spell_storm": "Thrasta, Tempest's Roar",
    "gain_control": "Control Magic",
    "global_ability_grant": "Cryptolith Rite",
    "goad_makers": "Disrupt Decorum",
    "graveyard_matters": "Reanimate",
    "group_hug_draw": "Wheel of Fortune",
    "group_mana": "Magus of the Vineyard",
    "hand_disruption": "Peek",
    "historic_matters": "Jhoira's Familiar",
    "impulse_top_play": "Light Up the Stage",
    "initiative_makers": "Aarakocra Sneak",
    "initiative_matters": "Imoen, Mystic Trickster",
    "island_matters": "Lord of Atlantis",
    "keyword_counter": "Luminous Broodmoth",
    "keyword_grant_target": "Aim High",
    "keyword_soup": "Odric, Lunarch Marshal",
    "keyword_soup_makers": "Odric, Lunarch Marshal",
    "keyword_tribe": "Favorable Winds",
    # ADR-0034 _matters split: the MAKER arm (place_counter ck='ki') now emits
    # ki_counter_makers — Skullmane Baku PERFORMS the ki placement. The PAYOFF
    # arm keeps ki_counter_matters but has no snapshot-resident real card (every
    # ki card is a self-contained Baku maker engine), so it lives in
    # _SYNTHETIC_CASES below as a hascounters-condition fixture.
    "ki_counter_makers": "Skullmane Baku",
    "kicked_spell_matters": "Verazol, the Split Current",
    "kill_engine": "Visara the Dreadful",
    "land_creatures_matter": "Sylvan Advocate",
    "land_denial": "Taniwha",
    "land_destruction": "Numot, the Devastator",
    "land_exchange": "Political Trickery",
    "land_protection": "Living Plane",
    "land_sacrifice_matters": "The Gitrog Monster",
    "landfall": "Lotus Cobra",
    "lands_matter": "Dakkon Blackblade",
    "legend_rule_off": "Mirror Box",
    "legends_matter": "Reki, the History of Kamigawa",
    "lessons_matter": "Sokka, Bold Boomeranger",
    "life_payment_insurance": "Underworld Connections",
    "life_total_set": "Beacon of Immortality",
    "lifegain_matters": "Archangel of Thune",
    "lifeloss_matters": "Gray Merchant of Asphodel",
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
    "opponent_search_matters": "Ob Nixilis, Unshackled",
    "outlaw_matters": "Laughing Jasper Flint",
    "partner_background": "Astarion, the Decadent",
    "party_matters": "Archpriest of Iona",
    "per_target_payoff": "Hinata, Dawn-Crowned",
    "permanent_etb": "Amareth, the Lustrous",
    "phasing_makers": "The War Doctor",
    "play_from_top": "Future Sight",
    "plus_one_matters": "Hardened Scales",
    "poison_matters": "Phyresis",
    "power_double": "Unleash Fury",
    "power_matters": "Colossal Majesty",
    "power_tap_engine": "Marwyn, the Nurturer",
    "powerup_matters": "Extremis Elite",
    "proliferate_matters": "Evolution Sage",
    "protection_grant": "Benevolent Bodyguard",
    "pump_makers": "Giant Growth",
    "rad_counter_makers": "Nuclear Fallout",
    "ramp": "Karametra's Acolyte",
    "reanimator": "Loyal Retainers",
    "recast_etb": "Karai's Technique",
    "regenerate_makers": "Tribal Golem",
    "removal": "Flame Slash",
    "ring_matters": "Faramir, Field Commander",
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
    # payoff arm (a card that only REFERENCES Spacecraft — Focus Fire) has no
    # snapshot-resident card, so it rides a _SYNTHETIC_CASES fixture below.
    "station_makers": "Lumen-Class Frigate",
    "stax_taxes": "Gnat Miser",
    "stickers_matter": "Aerialephant",
    "superfriends_matters": "The Chain Veil",
    "suspect_makers": "Case of the Stashed Skeleton",
    "suspect_matters": "Agency Coroner",
    "suspend_matters": "Calciderm",
    "symmetric_damage_each": "Pestilence",
    "symmetric_stax": "Cursed Totem",
    "tap_down": "Frost Lynx",
    "tap_down_blockers": "Tromokratis",
    "tap_untap_matters": "Pheres-Band Tromper",
    "tapped_matters": "Throne of the God-Pharaoh",
    "tapper_engine": "Icy Manipulator",
    "target_own_payoff": "Monk Gyatso",
    "target_player_draws": "Dictate of Kruphix",
    "target_redirect": "Rayne, Academy Chancellor",
    "targeting_matters": "Reality Smasher",
    "team_buff": "Brave the Sands",
    "team_evasion_grant": "Galerider Sliver",
    "theft_matters": "Stolen Goods",
    "theft_protection": "Kira, Great Glass-Spinner",
    "timing_control": "City of Solitude",
    "token_copy_makers": "Helm of the Host",
    "token_doubling": "Parallel Lives",
    "token_maker": "Krenko, Mob Boss",
    "tokens_matter": "Intangible Virtue",
    "topdeck_selection": "Sensei's Divining Top",
    "topdeck_stack": "Reclaim",
    "toughness_combat": "Assault Formation",
    "treasure_matters": "Dockside Extortionist",
    "tribal_etb_multi": "Goblin Assassin",
    "tribe_damage_trigger": "Toski, Bearer of Secrets",
    "trigger_doubling": "The Masamune",
    "tutor": "Demonic Tutor",
    "type_change": "Gor Muldrak, Amphinologist",
    "typed_anthem_multi": "Howlpack Resurgence",
    "typed_enters_punish": "Purphoros, God of the Forge",
    "typed_spellcast": "The First Sliver",
    "has_undying_persist": "Mikaeus, the Unhallowed",
    "unspent_mana": "Leyline Tyrant",
    "untap_engine": "Seedborn Muse",
    "vanilla_matters": "Muraganda Petroglyphs",
    "variable_pt": "Nightmare",
    "vehicles_matter": "Cloudspire Captain",
    "venture_matters": "Gloom Stalker",
    "villainous_choice": "The Valeyard",
    "void_warp_makers": "Starfield Vocalist",
    "void_warp_matters": "Alpharael, Stonechosen",
    "voltron_matters": "Sram, Senior Edificer",
    "voting_makers": "Capital Punishment",
    "wants_cloning": "Arcum Dagsson",
    "waterbend_makers": "Spirit Water Revival",
    "waterbend_matters": "Avatar Aang // Aang, Master of Elements",
    "win_lose_game": "Thassa's Oracle",
    "xspell_matters": "Zaxara, the Exemplary",
}


# Synthetic cases kept deliberately (NOT real-IR-backed). Each documents why a real
# snapshot card can't (yet) serve as the proof.
_SYNTHETIC_CASES: dict[str, tuple[dict, Card]] = {
    # type_matters — a generic subtype-anthem PROBE with a placeholder name (no single
    # canonical real card; the structural shape is what's under test). Stays synthetic
    # per the keep-synthetic rule for placeholder-name rows.
    "type_matters": (
        {
            "name": "Akroma's Devoted-like",
            "type_line": "Enchantment",
            "oracle_text": "Cleric creatures have vigilance.",
        },
        _ir(
            Ability(
                kind="static",
                effects=(
                    Effect(
                        category="grant_keyword",
                        scope="you",
                        subject=Filter(
                            card_types=("Creature",),
                            subtypes=("Cleric",),
                            controller="you",
                        ),
                        counter_kind="vigilance",
                        raw="Cleric creatures have vigilance.",
                    ),
                ),
            )
        ),
    ),
    # damage_reflect — Spiteful Sliver GRANTS a quoted "whenever dealt damage, deal that
    # much to a player" ability to your Slivers, which phase projects as a board_grant,
    # NOT a first-class damage_reflect Effect — so the real IR does not fire the lane.
    # TODO #24: structural board_grant damage-reflect recovery. Until then this row is a
    # minimal synthetic fixture, not a real-IR proof.
    # ki_counter_matters — ADR-0034 _matters split PAYOFF arm. The MAKER arm
    # (place_counter ck='ki') was relabeled to ki_counter_makers (Skullmane
    # Baku, a real case). The payoff arm — a card GATED on / REFERENCING a ki
    # counter ("as long as ~ has a ki counter …", a hascounters condition) —
    # keeps ki_counter_matters but has no snapshot-resident real card: every
    # ki card in MTG is a self-contained Baku maker, so no "creature with a ki
    # counter" payoff exists in the corpus. Minimal hascounters fixture proving
    # the condition arm still serves the lane via the IR path.
    "ki_counter_matters": (
        {
            "name": "Ki-Gated Sentinel-like",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "As long as this creature has a ki counter on it, it gets +2/+2."
            ),
        },
        _ir(
            Ability(
                kind="static",
                condition=Condition(kind="hascounters", counter_kind="ki"),
            )
        ),
    ),
    # opponent_exile_matters — ADR-0034 _matters split PAYOFF arm. The MAKER arm
    # (the graveyard-hate exile doers — Bojuka Bog, Leyline of the Void) was
    # relabeled to opponent_exile_makers (a real case). The payoff arm — a card
    # that REFERENCES cards opponents own standing in exile so you can play /
    # scale off them (Umbris-style) — keeps opponent_exile_matters but has no
    # snapshot-resident real card (the reference-alt cards aren't in the
    # snapshot). Minimal fixture proving the reference arm still serves the lane
    # via the IR kept-detector mirror. (Mirrors the ki_counter_matters split.)
    "opponent_exile_matters": (
        {
            "name": "Opponents'-Exile Payoff-like",
            "type_line": "Enchantment",
            "oracle_text": "You may play cards your opponents own in exile.",
        },
        _ir(),
    ),
    # voting_matters — ADR-0034 _matters split PAYOFF arm. The MAKER arm (the
    # vote-CREATOR cards that run a will-of-the-council / council's-dilemma vote —
    # Capital Punishment, Expropriate, Tivit, plus the structural cat=='vote' arm)
    # was relabeled to voting_makers (Capital Punishment, a real case). The payoff
    # arm — a card that triggers OFF a vote without creating one ("whenever players
    # finish voting", Grudge Keeper) — keeps voting_matters but has no
    # snapshot-resident real card: the snapshot's only voting cards (Capital
    # Punishment, The Valeyard) both fire the cat=='vote' maker arm. Minimal
    # fixture proving the finish-voting payoff still serves the lane via the IR
    # kept-detector residue mirror (`\bfinish(?:ed)? voting\b`). (Mirrors the
    # ki_counter_matters / opponent_exile_matters splits.) CR 701.38.
    "voting_matters": (
        {
            "name": "Grudge Keeper-like",
            "type_line": "Creature — Spirit",
            "oracle_text": (
                "Whenever players finish voting, each opponent loses 1 life for "
                "each vote they cast."
            ),
        },
        _ir(),
    ),
    # station_matters — ADR-0034 _matters split PAYOFF arm. The MAKER arm (the
    # Spacecraft/Planet bodies with the Station keyword + the chargers that put/double
    # charge counters on a Spacecraft — Lumen-Class Frigate, Drill Too Deep, Loading
    # Zone) was relabeled to station_makers (Lumen-Class Frigate, a real case). The
    # payoff arm — a card that only NAMES Spacecraft to count / destroy / exile / tutor
    # off it (Focus Fire counts Spacecraft, Embrace Oblivion / Gravkill destroy or exile
    # one) — keeps station_matters but has no snapshot-resident real card: the snapshot's
    # only Station cards (Lumen-Class Frigate, Hearthhull) both fire the maker arm.
    # Minimal fixture carrying Focus Fire's REAL oracle, proving the Spacecraft-reference
    # payoff still serves the lane via the IR partition mirror (no Station keyword, no
    # Spacecraft type, no charge-on-Spacecraft effect). (Mirrors the voting_matters /
    # opponent_exile_matters splits.) CR 702.184.
    "station_matters": (
        {
            "name": "Focus Fire-like",
            "type_line": "Instant",
            "oracle_text": (
                "Focus Fire deals X damage to target attacking or blocking "
                "creature, where X is 2 plus the number of creatures and/or "
                "Spacecraft you control."
            ),
        },
        _ir(),
    ),
    # blood_matters — ADR-0034 _matters split PAYOFF arm. The MAKER arm (a
    # Blood-subtype make_token subject — Bloodtithe Harvester, Blood Fountain)
    # was relabeled to blood_makers (Bloodtithe Harvester, a real case). The
    # payoff arm — a card that SACRIFICES or REFERENCES a Blood token (Wedding
    # Security "sacrifice a Blood token", Blood Hypnotist's sacrificed trigger) —
    # keeps blood_matters but has no snapshot-resident real card: the snapshot's
    # only Blood card (Bloodtithe Harvester) fires the make_token maker arm.
    # Minimal sacrifice-effect fixture proving the Blood PAYOFF still serves the
    # lane via the IR structural arm. (Mirrors the voting_matters split.) CR
    # 111.10g.
    "blood_matters": (
        {
            "name": "Wedding Security-like",
            "type_line": "Creature — Human Soldier",
            "oracle_text": (
                "Whenever this creature attacks, you may sacrifice a Blood "
                "token. If you do, put a +1/+1 counter on this creature and "
                "draw a card."
            ),
        },
        _ir(
            Ability(
                kind="triggered",
                trigger=Trigger(event="attacks", scope="you"),
                effects=(
                    Effect(
                        category="sacrifice",
                        scope="any",
                        subject=Filter(
                            subtypes=("Blood",),
                            controller="you",
                            predicates=("Token",),
                        ),
                        raw="you may sacrifice a Blood token",
                    ),
                ),
            )
        ),
    ),
    "damage_reflect": (
        {
            "name": "Spiteful Sliver",
            "type_line": "Creature — Sliver",
            "oracle_text": (
                'Sliver creatures you control have "Whenever this creature is '
                "dealt damage, it deals that much damage to target player or "
                'planeswalker."'
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="damage_reflect",
                        scope="you",
                        raw=(
                            'Sliver creatures you control have "Whenever this '
                            "creature is dealt damage, it deals that much damage "
                            "to target player or planeswalker"
                        ),
                    ),
                ),
            )
        ),
    ),
}


def test_every_migrated_key_has_a_case():
    """No migrated key may be left unproven: the case tables must exactly cover the
    manifest, with no key claimed by both."""
    overlap = set(_REAL_CASES) & set(_SYNTHETIC_CASES)
    assert not overlap, f"keys in both case tables: {overlap}"
    covered = set(_REAL_CASES) | set(_SYNTHETIC_CASES)
    assert covered == set(MIGRATED_KEYS), (
        "every key in MIGRATED_KEYS needs a representative case "
        f"(missing: {sorted(set(MIGRATED_KEYS) - covered)}, "
        f"extra: {sorted(covered - set(MIGRATED_KEYS))})"
    )


@pytest.mark.parametrize("key", sorted(MIGRATED_KEYS))
def test_migrated_key_left_regex_and_is_ir_served(key):
    """Regex path drops the key; the hybrid (IR) path serves it.

    Real cases load the card + its REAL projected IR from the committed snapshot, so
    the proof runs the same IR ``project_card`` produces (no synthetic-IR drift). The
    few ``_SYNTHETIC_CASES`` keep a hand-built IR deliberately (see that table)."""
    if key in _REAL_CASES:
        name = _REAL_CASES[key]
        card = test_card(name)
        ir = test_card_ir(name)
    else:
        card, ir = _SYNTHETIC_CASES[key]
    regex_keys = {s.key for s in extract_signals(card)}
    hybrid_keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert key not in regex_keys, f"{key} still emitted by the legacy regex path"
    assert key in hybrid_keys, f"{key} not served by the hybrid IR path"


def test_extra_combats_restriction_fold_fires_via_ir():
    """The arm_gap card (ADR-0027): phase folds Illusionist's Gambit's whole body
    into a single `restriction` Effect and never emits the `extra_combat` category,
    so the additional-combat-phase clause survives only in that Effect's raw. The
    restriction-fold structural arm reads it there — replacing the deleted
    EXTRA_COMBATS_REGEX whole-card mirror. CR 505.1a."""
    card = {
        "name": "Illusionist's Gambit",
        "type_line": "Instant",
        "oracle_text": (
            "Cast this spell only during the declare blockers step on an "
            "opponent's turn.\nRemove all attacking creatures from combat and "
            "untap them. After this phase, there is an additional combat phase. "
            "Each of those creatures attacks that combat if able. They can't "
            "attack you or planeswalkers you control that combat."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="restriction",
                    scope="any",
                    raw=(
                        "Remove all attacking creatures from combat and untap "
                        "them. After this phase, there is an additional combat "
                        "phase. Each of those creatures attacks that combat if "
                        "able. They can't attack you or planeswalkers you "
                        "control that combat."
                    ),
                ),
            ),
        )
    )
    assert "extra_combats" not in {s.key for s in extract_signals(card)}
    assert "extra_combats" in {s.key for s in extract_signals_hybrid(card, ir)}


# ── ADR-0027 #24m F1 — forced_attack → extra_combats re-route correction ──────


def test_extra_combat_rider_is_not_forced_attack():
    """F1 correction: World at War's "Untap all creatures that attacked this turn …
    additional combat phase" is an EXTRA-COMBAT rider (CR 505.1a), NOT a forced-attack
    compulsion (CR 508.1). It rides the extra_combats lane via phase's `extra_combat`
    Effect, and the narrowed forced_attack mirror (which dropped the `that attacked this
    turn` arm) no longer mis-fires forced_attack for it."""
    card = test_card("World at War")
    ir = test_card_ir("World at War")
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "extra_combats" in keys
    assert "forced_attack" not in keys


def test_forced_attack_punisher_still_fires():
    """F1 correction keeps the attack-RESTRICTION/punisher half: Season of the Witch
    destroys creatures that DIDN'T attack — the `didn't attack this turn` mirror (the
    one structural form phase carries no node for) still opens forced_attack. CR 508.1."""
    card = test_card("Season of the Witch")
    ir = test_card_ir("Season of the Witch")
    assert "forced_attack" in {s.key for s in extract_signals_hybrid(card, ir)}


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
    assert "base_pt_set" not in {s.key for s in extract_signals(card)}
    assert "base_pt_set" in {s.key for s in extract_signals_hybrid(card, ir)}


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
    assert "base_pt_set" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_base_pt_set_mass_animator_stays_out():
    """F1 over-fire guard: the symmetric MASS-animator Living Plane ("All lands are 1/1
    creatures") sets P/T but is a land-creatures THEME, not a base-P/T build-around — it
    says neither "base power" nor "N/N … in addition to its other types", so neither the
    animate hook nor the dynamic recovery admits it. base_pt_set stays OUT (#26)."""
    card = test_card("Living Plane")
    ir = test_card_ir("Living Plane")
    assert "base_pt_set" not in {s.key for s in extract_signals_hybrid(card, ir)}


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
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "base_power_matters" in keys
    assert "base_pt_set" not in keys


def test_base_power_matters_fires_zinnia():
    """G1: Zinnia, Valley's Voice — "~ gets +X/+0, where X is the number of other
    creatures you control with base power 1" — a base-power REFERENCE payoff. Fires
    base_power_matters via the recovered `BasePtRef` marker, NOT base_pt_set."""
    card = test_card("Zinnia, Valley's Voice")
    ir = test_card_ir("Zinnia, Valley's Voice")
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
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
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "base_pt_set" in keys
    assert "base_power_matters" not in keys


def test_creatures_matter_mass_grant_fires_via_ir():
    """A MASS keyword grant to the generic creature board (Champion of Lambholt's
    CantBeBlockedBy) → creatures_matter via the IR grant_keyword arm, not regex."""
    card = {
        "name": "Champion of Lambholt",
        "type_line": "Legendary Creature — Human Warrior",
        "oracle_text": (
            "Creatures with power less than this creature's power can't block "
            "creatures you control.\nWhenever another creature you control enters, "
            "put a +1/+1 counter on this creature."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="grant_keyword",
                    scope="you",
                    subject=Filter(card_types=("Creature",), controller="you"),
                    counter_kind="unblockable",
                    raw="creatures you control can't be blocked",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals(card)}
    assert "creatures_matter" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_creatures_matter_does_not_fire_on_a_subtype_lord():
    """The over-fire boundary: a SUBTYPE lord ("Goblin creatures you control get
    +1/+1") is tribal (type_matters, CR 205.3), NOT the generic go-wide lane — its
    IR pump subject carries the Goblin subtype, so the generic-set gate rejects it."""
    card = {
        "name": "Goblin King",
        "type_line": "Creature — Goblin",
        "oracle_text": (
            "Other Goblin creatures you control get +1/+1 and have mountainwalk."
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="you",
                    subject=Filter(
                        card_types=("Creature",),
                        subtypes=("Goblin",),
                        controller="you",
                    ),
                    raw="Other Goblin creatures you control get +1/+1",
                ),
            ),
        )
    )
    assert "creatures_matter" not in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_sacrifice_effect_subject():
    """Token-subtype sacrifice PAYOFF (effect side): Wedding Security "sacrifice a
    Blood token" — a `sacrifice` Effect whose subject Filter carries the Blood
    subtype opens blood_matters via the IR, not the deleted floor regex."""
    card = {
        "name": "Wedding Security",
        "type_line": "Creature — Human Soldier",
        "oracle_text": (
            "Whenever this creature attacks, you may sacrifice a Blood token. If "
            "you do, put a +1/+1 counter on this creature and draw a card."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(event="attacks", scope="you"),
            effects=(
                Effect(
                    category="sacrifice",
                    scope="any",
                    subject=Filter(
                        subtypes=("Blood",),
                        controller="you",
                        predicates=("Token",),
                    ),
                    raw="you may sacrifice a Blood token",
                ),
            ),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_matters_fires_from_a_sacrificed_trigger_subject():
    """Token-subtype sacrifice PAYOFF (trigger side): Blood Hypnotist "whenever you
    sacrifice one or more Blood tokens" — a `sacrificed` Trigger whose subject Filter
    carries the Blood subtype opens blood_matters via the IR."""
    card = {
        "name": "Blood Hypnotist",
        "type_line": "Creature — Vampire Wizard",
        "oracle_text": (
            "This creature can't block.\nWhenever you sacrifice one or more Blood "
            "tokens, target creature can't block this turn. This ability triggers "
            "only once each turn."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="sacrificed",
                scope="you",
                subject=Filter(
                    subtypes=("Blood",),
                    controller="you",
                    predicates=("Token",),
                ),
            ),
            effects=(Effect(category="cant_block", scope="any", raw="can't block"),),
        )
    )
    assert "blood_matters" not in {s.key for s in extract_signals(card)}
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_blood_makers_fires_from_a_recovered_choice_list_maker():
    """Token-subtype maker recovery (choice list): Transmutation Font "create your
    choice of a Blood token, a Clue token, or a Food token" — phase drops the choice
    subtypes onto a `choose` effect; project._narrow_token_subtype_makers recovers
    them as make_token markers, so all three lanes fire via the IR. ADR-0034: the
    Blood MAKER arm emits blood_makers; clue/food are unsplit (clue/food_matters)."""
    card = {
        "name": "Transmutation Font",
        "type_line": "Artifact",
        "oracle_text": (
            "{T}: Create your choice of a Blood token, a Clue token, or a Food token."
        ),
    }
    ir = _ir(
        Ability(
            kind="activated",
            cost="tap",
            effects=(
                # the recovered make_token markers the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Clue",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Food",), predicates=("Token",)),
                    raw="Create your choice of a Blood token, a Clue token, "
                    "or a Food token.",
                ),
            ),
        )
    )
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "blood_makers" in keys
    # the generalized recovery also opens clue/food (all three are now ADR-0027-migrated,
    # IR-served via _TOKEN_SUBTYPE_KEYS — the structural maker recovery is general, which
    # proves the widening generalized across every artifact/blood token subtype)
    assert "clue_matters" in keys
    assert "food_matters" in keys


def test_blood_makers_fires_from_a_recovered_granted_ability_maker():
    """Token-subtype maker recovery (granted ability): Ceremonial Knife grants the
    equipped creature a quoted "create a Blood token" ability — phase folds it into a
    `pump` carrier raw; the projection recovers the Blood make_token marker, so
    blood_makers fires via the IR (ADR-0034 — the make_token MAKER arm)."""
    card = {
        "name": "Ceremonial Knife",
        "type_line": "Artifact — Equipment",
        "oracle_text": (
            'Equipped creature gets +1/+0 and has "Whenever this creature deals '
            'combat damage, create a Blood token."\nEquip {2}'
        ),
    }
    ir = _ir(
        Ability(
            kind="static",
            effects=(
                Effect(
                    category="pump",
                    scope="any",
                    subject=Filter(
                        card_types=("Creature",), predicates=("EquippedBy",)
                    ),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
                # the recovered make_token marker the projection appends
                Effect(
                    category="make_token",
                    scope="you",
                    subject=Filter(subtypes=("Blood",), predicates=("Token",)),
                    raw='Equipped creature gets +1/+0 and has "Whenever ~ deals '
                    'combat damage, create a Blood token."',
                ),
            ),
        )
    )
    assert "blood_makers" in {s.key for s in extract_signals_hybrid(card, ir)}


# ── spellcast_matters (ADR-0027 signals-only) — scope discrimination + recovery ──


def test_spellcast_matters_does_not_fire_on_opponent_cast():
    """Mystic Remora's opponent-cast hoser is opponent_cast_matters, NOT spellcast."""
    card = {
        "name": "Mystic Remora",
        "type_line": "Enchantment",
        "oracle_text": (
            "Cumulative upkeep {1}\nWhenever an opponent casts a noncreature "
            "spell, you may draw a card unless that player pays {4}."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                subject=Filter(card_types=("Card",), predicates=("NotType:Creature",)),
                scope="opp",
            ),
            effects=(Effect(category="draw", scope="you"),),
        )
    )
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "spellcast_matters" not in keys
    assert "opponent_cast_matters" in keys


def test_spellcast_matters_does_not_fire_on_symmetric_player_cast():
    """A symmetric 'whenever a player casts' punisher (no 'you cast') is not the
    you-cast spellslinger payoff."""
    card = {
        "name": "Eidolon of the Great Revel",
        "type_line": "Enchantment Creature — Spirit",
        "oracle_text": (
            "Whenever a player casts a spell with mana value 3 or less, this "
            "creature deals 2 damage to that player."
        ),
    }
    ir = _ir(
        Ability(
            kind="triggered",
            trigger=Trigger(
                event="cast_spell",
                subject=Filter(card_types=("Card",), predicates=("Cmc:LE:3",)),
                scope="any",
            ),
            effects=(Effect(category="damage", scope="any"),),
        )
    )
    assert "spellcast_matters" not in {s.key for s in extract_signals_hybrid(card, ir)}


def test_spellcast_matters_fires_on_prowess_keyword():
    """Prowess (CR 702.108a) opens spellcast_matters via the Scryfall keyword array."""
    card = {
        "name": "Jeskai Windscout",
        "type_line": "Creature — Bird Monk",
        "oracle_text": (
            "Flying\nProwess (Whenever you cast a noncreature spell, this "
            "creature gets +1/+1 until end of turn.)"
        ),
        "keywords": ["Flying", "Prowess"],
    }
    ir = _ir(keywords=("Prowess",))
    assert "spellcast_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_spellcast_matters_fires_from_kept_mirror_cost_reducer():
    """An instant/sorcery cost-reducer (Baral) has NO cast_spell trigger — it rides
    the byte-identical _detect_spellcast_matters kept mirror over the oracle."""
    card = {
        "name": "Baral, Chief of Compliance",
        "type_line": "Legendary Creature — Vedalken Wizard",
        "oracle_text": (
            "Instant and sorcery spells you cast cost {1} less to cast.\n"
            "Whenever a spell or ability you control counters a spell, you may "
            "draw a card. If you do, discard a card."
        ),
    }
    # IR carries NO cast_spell trigger (a static cost reduction) — proves the mirror.
    ir = _ir(Ability(kind="static", effects=(Effect(category="cost_reduction"),)))
    assert "spellcast_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


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
    assert "dies_recursion" not in {s.key for s in extract_signals(card)}
    assert "dies_recursion" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_dies_recursion_granter_fires_off_undying_persist_marker():
    """ADR-0027 #24c — a keyword-LESS undying GRANTER (Mikaeus grants undying to a
    class of creatures, but bears no undying keyword itself) rides phase's
    `undying_persist` marker into dies_recursion, replacing the word mirror's bare
    \\bundying\\b match. CR 702.92."""
    card = test_card("Mikaeus, the Unhallowed")
    ir = test_card_ir("Mikaeus, the Unhallowed")
    cats = {e.category for ab in ir.all_abilities() for e in ab.effects}
    assert "undying_persist" in cats
    assert "dies_recursion" in {s.key for s in extract_signals_hybrid(card, ir)}


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
    assert "counter_manipulation" not in {s.key for s in extract_signals(card)}
    assert "counter_manipulation" in {s.key for s in extract_signals_hybrid(card, ir)}


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
    assert "tap_untap_matters" not in {s.key for s in extract_signals(card)}
    assert "tap_untap_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_tap_untap_matters_recovers_unknown_mode_becomes_tapped():
    """ADR-0027 #24c — Darksteel Garrison's "Whenever fortified land becomes tapped"
    is an Unknown-mode trigger phase leaves at event=='other';
    supplement._recover_becomes_tap_untap re-types it to `taps` from the trigger
    clause's raw, so tap_untap_matters reads STRUCTURE for the tail too."""
    ir = test_card_ir("Darksteel Garrison")
    assert any(
        ab.trigger is not None and ab.trigger.event == "taps"
        for ab in ir.all_abilities()
    ), "Unknown-mode becomes-tapped not recovered to event=='taps'"


# ── ADR-0027 #24d (SIDECAR v55) — SUPPLEMENT_RECOVER B3 real-card structural pins ──
# Each proves the lane fires (or correctly does NOT) off the SUPPLEMENT-recovered
# structure in the REAL projected IR (test_card_ir = a verbatim sidecar slice), not a
# regex mirror — the mirrors for cost_reduction + clone_makers are deleted.


def test_cost_reduction_recovered_ability_cost_reducer_dragonkin():
    """Dragonkin Berserker's "Boast abilities you activate cost {1} less to activate"
    is dropped by phase (no cost_reduction Effect); supplement._recover_cost_reduction
    synthesizes one, so the structural arm fires cost_reduction. CR 601.2f."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Dragonkin Berserker"), test_card_ir("Dragonkin Berserker")
        )
    }
    assert "cost_reduction" in keys


def test_cost_reduction_recovered_defiler_conditional():
    """Defiler of Vigor's "Those spells cost {G} less to cast" conditional reducer is
    dropped by phase; the recovery synthesizes the cost_reduction Effect. CR 601.2f."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Defiler of Vigor"), test_card_ir("Defiler of Vigor")
        )
    }
    assert "cost_reduction" in keys


def test_cost_reduction_recovered_saga_chapter_collapse():
    """Invasion of the Giants' chapter-III reducer collapses to a raw "Chapter 3"
    Effect that fails the arm's subject-None screen; the recovery still synthesizes a
    genuine reducer from the oracle clause, so cost_reduction fires. CR 601.2f."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Invasion of the Giants"),
            test_card_ir("Invasion of the Giants"),
        )
    }
    assert "cost_reduction" in keys


def test_clone_makers_recovered_creature_copy_etb():
    """Spark Double's "enter as a copy of a creature" replacement is folded by phase to
    a non-clone node; supplement._recover_clone_creature synthesizes a Creature-subject
    clone Effect, so the copied-type arm fires clone_makers. CR 707.2."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Spark Double"), test_card_ir("Spark Double")
        )
    }
    assert "clone_makers" in keys


def test_clone_makers_recovered_phase_mistyped_creature_copy_dermotaxi():
    """Dermotaxi copies a CREATURE card ("becomes a copy of the exiled card") but phase
    types its clone subject 'Artifact' (the "Vehicle artifact" rider). The recovery
    runs anyway (the Artifact-typed clone does not fire clone_makers) and recovers the
    Creature copy, so clone_makers fires. CR 707.2."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Dermotaxi"), test_card_ir("Dermotaxi")
        )
    }
    assert "clone_makers" in keys


def test_clone_makers_does_not_fire_on_a_noncreature_copy_overfire():
    """Copy Artifact copies an ARTIFACT only (CR 707.2 — an artifact copy, not a
    creature clone). With the over-broad mirror deleted, it correctly does NOT fire
    clone_makers (the creature-blind over-fire is shed); it keeps enchantments_matter
    (it is an Enchantment)."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Copy Artifact"), test_card_ir("Copy Artifact")
        )
    }
    assert "clone_makers" not in keys


def test_opponent_discard_recovered_damage_connect_specter():
    """Abyssal Specter's "deals damage to a player, that player discards" is two
    disconnected pieces (a damage-to-player trigger + a discard scope 'any'); supplement.
    _recover_opponent_discard links them and appends a discard scope 'opp', so the arm
    fires opponent_discard. CR 510.1c / 701.9."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Abyssal Specter"), test_card_ir("Abyssal Specter")
        )
    }
    assert "opponent_discard" in keys


def test_opponent_discard_recovered_bounce_then_discard():
    """Recoil's "Return target permanent …, then that player discards" — the discardER
    is the bounce target's controller (an opponent); the recovery appends a discard
    scope 'opp'. CR 701.9."""
    keys = {
        s.key
        for s in extract_signals_hybrid(test_card("Recoil"), test_card_ir("Recoil"))
    }
    assert "opponent_discard" in keys


def test_opponent_discard_does_not_fire_on_combat_damage_self_loot():
    """Academy Raider's "deals combat damage to a player, you may discard a card. If you
    do, draw" is a SELF-loot (the discardER is YOU), not an opponent discard — the
    recovery's opponent-directed tell ("that player discards") is absent, so it does NOT
    fire opponent_discard. CR 701.8a (loot) vs 701.9 (forced discard)."""
    keys = {
        s.key
        for s in extract_signals_hybrid(
            test_card("Academy Raider"), test_card_ir("Academy Raider")
        )
    }
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
    keys = {s.key for s in extract_signals_hybrid(test_card("Backslide"), ir)}
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
    keys = {s.key for s in extract_signals_hybrid(test_card("Break Open"), ir)}
    assert "facedown_matters" in keys


def test_facedown_does_not_fire_on_name_only_disguise():
    """Chameleon, Master of Disguise is a clone with NO face-down mechanic — only its
    NAME contains "Disguise". The recovery strips the card name before matching, so it is
    NOT swept in (a precision gain over the name-blind regex). CR 707.2."""
    ir = test_card_ir("Chameleon, Master of Disguise")
    assert not any(
        e.category == "facedown_ref" for ab in ir.all_abilities() for e in ab.effects
    )
    keys = {
        s.key
        for s in extract_signals_hybrid(test_card("Chameleon, Master of Disguise"), ir)
    }
    assert "facedown_matters" not in keys


def test_tap_down_recovered_opp_controller_mind_spiral():
    """Mind Spiral's gift "tap target creature an opponent controls" projects with the
    tap subject DROPPED to None; supplement._recover_tap_down synthesizes a Creature
    subject with controller=='opp', so the structural tap arm fires tap_down. CR 701.20."""
    ir = test_card_ir("Mind Spiral")
    assert any(
        e.category == "tap" and e.subject is not None and e.subject.controller == "opp"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "recovered opp-controlled tap subject missing"
    keys = {s.key for s in extract_signals_hybrid(test_card("Mind Spiral"), ir)}
    assert "tap_down" in keys


def test_tap_down_recovered_skip_untap_step_brine_elemental():
    """Brine Elemental's "each opponent skips their next untap step" is a no-tap tempo
    lock; supplement._recover_tap_down resolves the anaphor to `skip_step` scope=='opp',
    read by the new skip-untap arm. CR 701.20."""
    ir = test_card_ir("Brine Elemental")
    assert any(
        e.category == "skip_step" and e.scope == "opp"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "recovered skip_step scope=='opp' missing"
    keys = {s.key for s in extract_signals_hybrid(test_card("Brine Elemental"), ir)}
    assert "tap_down" in keys


def test_damage_to_opp_recovered_quoted_trigger_serpent_generator():
    """Serpent Generator's token grant "Whenever ~ deals damage to a player, that player
    gets a poison counter" is a quoted trigger phase leaves unstructured;
    supplement._recover_damage_to_opp synthesizes a deals_damage(DamageToPlayer) trigger,
    so the existing arm fires damage_to_opp_matters. CR 119.3."""
    ir = test_card_ir("Serpent Generator")
    assert any(
        ab.trigger is not None
        and ab.trigger.event == "deals_damage"
        and ab.trigger.subject is not None
        and "DamageToPlayer" in ab.trigger.subject.predicates
        for ab in ir.all_abilities()
    ), "recovered deals_damage(DamageToPlayer) trigger missing"
    keys = {s.key for s in extract_signals_hybrid(test_card("Serpent Generator"), ir)}
    assert "damage_to_opp_matters" in keys


def test_extra_land_drop_recovered_cascade_reanimate_averna():
    """ADR-0027 #24l — Averna's "As you cascade, you may put a land card from among the
    exiled cards onto the battlefield" is the YOUR land-into-play put phase mis-types as
    a `reanimate` Effect (off cat=='cheat_play'). supplement._recover_extra_land_drop
    appends a canonical cheat_play Land (controller='you') Effect the extra_land_drop arm
    reads; the whole signals mirror is deleted. CR 305.9."""
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
    assert "extra_land_drop" not in {s.key for s in extract_signals(card)}
    assert "extra_land_drop" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_extra_land_drop_recovered_empty_raw_modal_confluence():
    """ADR-0027 #24l — Riveteers Confluence's modal "put a land card from your hand or
    graveyard onto the battlefield" reaches phase as a cheat_play Land controller='any'
    with an EMPTY raw (the "or graveyard" disjunction defeats the YOUR pin), which the
    arm's controller=='you' gate misses. The supplement's joined-oracle recovery appends
    a controller='you' cheat_play Land so the arm fires. CR 305.9."""
    card = test_card("Riveteers Confluence")
    ir = test_card_ir("Riveteers Confluence")
    assert "extra_land_drop" in {s.key for s in extract_signals_hybrid(card, ir)}


def test_group_hug_draw_recovered_folded_each_player_scope_grothama():
    """ADR-0027 #24l — Grothama's "each player draws cards equal to the amount of damage
    …" is a symmetric group-hug draw phase folds to scope=='any' (the variable amount
    defeats its each-scope). supplement._recover_group_hug_draw_scope re-stamps
    scope=='each' on the draw, so the lane reads STRUCTURE — and Grothama correctly LEAVES
    target_player_draws (a directed-draw lane scope=='any' feeds; an each-player draw is
    never player-directed). CR 121 / 120.2."""
    card = test_card("Grothama, All-Devouring")
    ir = test_card_ir("Grothama, All-Devouring")
    assert any(
        e.category == "draw" and e.scope == "each"
        for ab in ir.all_abilities()
        for e in ab.effects
    ), "draw scope not re-stamped to 'each'"
    keys = {s.key for s in extract_signals_hybrid(card, ir)}
    assert "group_hug_draw" in keys
    assert "target_player_draws" not in keys
