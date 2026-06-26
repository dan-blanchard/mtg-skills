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
    "airbend_matters": "Airbender Ascension",
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
    "banding_matters": "Timber Wolves",
    "base_pt_set": "Lignify",
    "big_hand_matters": "Reliquary Tower",
    "big_mana": "Gilded Lotus",
    "blink_flicker": "Flickerwisp",
    "blocked_matters": "Kitsune Blademaster",
    "blood_matters": "Bloodtithe Harvester",
    "boast_matters": "Birgi, God of Storytelling",
    "bounce_tempo": "Boomerang",
    "cant_block_grant": "Breeches, Eager Pillager",
    "card_draw_engine": "Phyrexian Arena",
    "cascade_matters": "Maelstrom Nexus",
    "cast_from_exile": "Vega, the Watcher",
    "celebration_matters": "Tuinvale Guide",
    "changeling_matters": "Maskwood Nexus",
    "cheat_from_top": "Hans Eriksson",
    "cheat_into_play": "Sneak Attack",
    "clone_matters": "Cytoshape",
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
    "conjure_matters": "Brave Meadowguard",
    "connive_matters": "Security Bypass",
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
    "dash_matters": "Zurgo Bellstriker",
    "daynight_matters": "Tovolar, Dire Overlord",
    "death_matters": "Blood Artist",
    "debuff_matters": "Dead Weight",
    "destroy_legendary": "Hero's Demise",
    "devotion_matters": "Karametra's Acolyte",
    "devour_matters": "Mycoloth",
    "dice_matters": "Brazen Dwarf",
    "dies_recursion": "Bronzehide Lion",
    "dig_until": "Hermit Druid",
    "direct_damage": "Sizzle",
    "discard_matters": "Basking Rootwalla",
    "discard_outlet": "Faithless Looting",
    "discover_matters": "Curator of Sun's Creation",
    "domain_matters": "Matca Rioters",
    "donate_matters": "Harmless Offering",
    "draft_spellbook": "Cogwork Librarian",
    "draw_for_each": "Garruk, Primal Hunter",
    "draw_matters": "Chasm Skulker",
    "each_mode_player": "Vindictive Lich",
    "earthbend_matters": "Earthen Ally",
    "edict_matters": "Plaguecrafter",
    "enchantments_matter": "Tuvasa the Sunlit",
    "end_the_turn": "Obeka, Brute Chronologist",
    "energy_matters": "Aether Hub",
    "enlist_matters": "Benalish Faithbonder",
    "entered_attacker": "Samut, Vizier of Naktamun",
    "evasion_denial": "Staff of the Ages",
    "evasion_self": "Slither Blade",
    "exalted_lone_attacker": "Rogue Kavu",
    "excess_damage": "Aegar, the Freezing Flame",
    "exert_matters": "Brave the Sands",
    "exhaust_matters": "Pit Automaton",
    "exile_matters": "Mairsil, the Pretender",
    "exile_removal": "Banishing Light",
    "exile_until_leaves": "Oblivion Ring",
    "experience_matters": "Atreus, Impulsive Son",
    "explore_matters": "Topography Tracker",
    "extra_combats": "Aggravated Assault",
    "extra_draw_step": "Sphinx of the Second Sun",
    "extra_end_step": "Y'shtola Rhul",
    "extra_land_drop": "Burgeoning",
    "extra_turns": "Temporal Manipulation",
    "extra_upkeep": "Sphinx of the Second Sun",
    "facedown_matters": "Etrata, Deadly Fugitive",
    "fight_matters": "Tolsimir, Friend to Wolves",
    "firebending_matters": "Fire Lord Azula",
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
    "graveyard_matters": "Reanimate",
    "group_hug_draw": "Wheel of Fortune",
    "group_mana": "Magus of the Vineyard",
    "hand_disruption": "Peek",
    "historic_matters": "Jhoira's Familiar",
    "impulse_top_play": "Light Up the Stage",
    "initiative_matters": "Aarakocra Sneak",
    "island_matters": "Lord of Atlantis",
    "keyword_counter": "Luminous Broodmoth",
    "keyword_grant_target": "Aim High",
    "keyword_soup": "Odric, Lunarch Marshal",
    "keyword_soup_matters": "Odric, Lunarch Marshal",
    "keyword_tribe": "Favorable Winds",
    "ki_counter_matters": "Skullmane Baku",
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
    "lure_matters": "Lure",
    "madness_matters": "Anje Falkenrath",
    "magecraft_matters": "Archmage Emeritus",
    "mana_amplifier": "Mana Reflection",
    "mass_bounce": "Evacuation",
    "mass_death_payoff": "Khabál Ghoul",
    "mass_removal": "Wrath of God",
    "meld_pair": "Bruna, the Fading Light",
    "mill_matters": "Stitcher's Supplier",
    "minus_counters_matter": "Crumbling Ashes",
    "miracle_grant": "Lorehold, the Historian",
    "modified_matters": "Chishiro, the Shattered Blade",
    "monarch_matters": "Throne Warden",
    "multicolor_matters": "Hero of Precinct One",
    "mutate_matters": "Pollywog Symbiote",
    "myriad_grant": "Legion Loyalty",
    "named_counter_misc": "Tetzimoc, Primal Death",
    "named_synergy": "Festering Newt",
    "ninjutsu_matters": "Satoru Umezawa",
    "noncombat_damage_payoff": "Spitemare",
    "noncreature_cast_punish": "Kambal, Consul of Allocation",
    "nonhuman_attackers": "Winota, Joiner of Forces",
    "oil_counter_matters": "Kuldotha Cackler",
    "one_punch": "Yargle and Multani",
    "opp_top_exile": "Villainous Wealth",
    "opponent_cast_matters": "Lavinia, Azorius Renegade",
    "opponent_counter_grant": "Mathas, Fiend Seeker",
    "opponent_discard": "Mind Rot",
    "opponent_draw_matters": "Underworld Dreams",
    "opponent_exile_matters": "Bojuka Bog",
    "opponent_search_matters": "Ob Nixilis, Unshackled",
    "outlaw_matters": "Laughing Jasper Flint",
    "partner_background": "Astarion, the Decadent",
    "party_matters": "Archpriest of Iona",
    "per_target_payoff": "Hinata, Dawn-Crowned",
    "permanent_etb": "Amareth, the Lustrous",
    "phasing_matters": "The War Doctor",
    "play_from_top": "Future Sight",
    "plus_one_matters": "Hardened Scales",
    "poison_matters": "Phyresis",
    "power_double": "Unleash Fury",
    "power_matters": "Colossal Majesty",
    "power_tap_engine": "Marwyn, the Nurturer",
    "powerup_matters": "Extremis Elite",
    "proliferate_matters": "Evolution Sage",
    "protection_grant": "Benevolent Bodyguard",
    "pump_matters": "Giant Growth",
    "rad_counter_matters": "Nuclear Fallout",
    "ramp_matters": "Karametra's Acolyte",
    "reanimator": "Loyal Retainers",
    "recast_etb": "Karai's Technique",
    "regenerate_matters": "Tribal Golem",
    "removal_matters": "Flame Slash",
    "ring_matters": "Faramir, Field Commander",
    "sacrifice_matters": "Disciple of Bolas",
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
    "shield_counter_matters": "Boon of Safety",
    "snow_matters": "Diamond Faerie",
    "soulbond_matters": "Flowering Lumberknot",
    "specialize_matters": "Alora, Rogue Companion",
    "speed_matters": "The Speed Demon",
    "spell_copy_matters": "Twincast",
    "spell_keyword_grant": "Thrumming Stone",
    "spellcast_matters": "Talrand, Sky Summoner",
    "starting_life_matters": "Path of Bravery",
    "station_matters": "Lumen-Class Frigate",
    "stax_taxes": "Gnat Miser",
    "stickers_matter": "Aerialephant",
    "superfriends_matters": "The Chain Veil",
    "suspect_matters": "Case of the Stashed Skeleton",
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
    "token_copy_matters": "Helm of the Host",
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
    "tutor_matters": "Demonic Tutor",
    "type_change": "Gor Muldrak, Amphinologist",
    "typed_anthem_multi": "Howlpack Resurgence",
    "typed_enters_punish": "Purphoros, God of the Forge",
    "typed_spellcast": "The First Sliver",
    "undying_persist_matters": "Mikaeus, the Unhallowed",
    "unspent_mana": "Leyline Tyrant",
    "untap_engine": "Seedborn Muse",
    "vanilla_matters": "Muraganda Petroglyphs",
    "variable_pt": "Nightmare",
    "vehicles_matter": "Cloudspire Captain",
    "venture_matters": "Gloom Stalker",
    "villainous_choice": "The Valeyard",
    "void_warp_matters": "Starfield Vocalist",
    "voltron_matters": "Sram, Senior Edificer",
    "voting_matters": "Capital Punishment",
    "waterbend_matters": "Spirit Water Revival",
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
    # goad_matters — migrated to a structural `goad_all` Effect arm, BUT the Goad
    # Scryfall keyword still produces goad_matters via _PRESET_KEYWORD_SIGNALS['goad']
    # in the regex path. A real record (keywords=["Goad"]) therefore still trips the
    # regex producer, so it can't satisfy the "regex drops it" invariant. The original
    # fixture masked this by omitting `keywords`; we keep that keyword-less synthetic
    # shape, which honestly proves the ORACLE-TEXT regex producer is deleted.
    # TODO #24: drop the residual _PRESET_KEYWORD_SIGNALS['goad'] producer (the hybrid
    # already strips it and re-serves goad_matters structurally), then promote this to a
    # real case (e.g. "Disrupt Decorum").
    "goad_matters": (
        {
            "name": "Disrupt Decorum",
            "type_line": "Sorcery",
            "oracle_text": (
                "Goad all creatures your opponents control. (Until your next "
                "turn, those creatures attack each combat if able and attack a "
                "player other than you if able.)"
            ),
        },
        _ir(
            Ability(
                kind="spell",
                effects=(
                    Effect(
                        category="goad_all",
                        scope="opp",
                        raw="Goad all creatures your opponents control.",
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


def test_blood_matters_fires_from_a_recovered_choice_list_maker():
    """Token-subtype maker recovery (choice list): Transmutation Font "create your
    choice of a Blood token, a Clue token, or a Food token" — phase drops the choice
    subtypes onto a `choose` effect; project._narrow_token_subtype_makers recovers
    them as make_token markers, so all three lanes fire via the IR."""
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
    assert "blood_matters" in keys
    # the generalized recovery also opens clue/food (all three are now ADR-0027-migrated,
    # IR-served via _TOKEN_SUBTYPE_KEYS — the structural maker recovery is general, which
    # proves the widening generalized across every artifact/blood token subtype)
    assert "clue_matters" in keys
    assert "food_matters" in keys


def test_blood_matters_fires_from_a_recovered_granted_ability_maker():
    """Token-subtype maker recovery (granted ability): Ceremonial Knife grants the
    equipped creature a quoted "create a Blood token" ability — phase folds it into a
    `pump` carrier raw; the projection recovers the Blood make_token marker, so
    blood_matters fires via the IR."""
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
    assert "blood_matters" in {s.key for s in extract_signals_hybrid(card, ir)}


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
