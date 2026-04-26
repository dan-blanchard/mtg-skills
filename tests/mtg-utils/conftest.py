"""Shared test fixtures for mtg_utils tests."""

import json
import os
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

import pytest

# Real 2024 Comprehensive Rules, mirrored on GitHub. Used by the
# ``real_cr_path`` fixture so tests can parse an actual CR document
# instead of only our minimized hand-rolled fixture — catches parser
# drift against formatting quirks we don't know about (the February
# 2024 doc exposed three: a trailing period after 119.1d, a missing
# period in 606.5, a missing space after 901.4). Not proxied behind an
# env var: CI runs on GitHub and hitting raw.githubusercontent.com
# from GitHub Actions is reliable.
_REAL_CR_URL = (
    "https://raw.githubusercontent.com/Chertus/MTGRules/main/"
    "MagicCompRules_20240206.txt"
)
_REAL_CR_CACHE_TTL = 7 * 86400  # a week — the mirrored file is static


def json_from_cli_output(result) -> object:
    """Load the JSON file referenced by a 'Full JSON: <path>' footer in CLI output.

    Scripts emit human-readable text reports or JSON envelopes to stdout and
    always write their full structured output to a file. Tests use this helper
    to dual-assert: loose substring checks on the text, strict correctness
    checks on the structured file.
    """
    for line in result.output.splitlines():
        if line.startswith("Full JSON:"):
            path = Path(line.split(":", 1)[1].strip())
            return json.loads(path.read_text(encoding="utf-8"))
    msg = f"No 'Full JSON:' line in CLI output:\n{result.output}"
    raise ValueError(msg)


@pytest.fixture
def moxfield_deck(tmp_path: Path) -> Path:
    """Create a sample Moxfield-format deck list."""
    deck_path = tmp_path / "deck.txt"
    deck_path.write_text(
        textwrap.dedent("""\
            //Commander
            1 Korvold, Fae-Cursed King

            //Creature
            1 Viscera Seer
            1 Blood Artist
            1 Sakura-Tribe Elder

            //Instant
            1 Deadly Rollick

            //Sorcery
            1 Cultivate

            //Artifact
            1 Sol Ring
            1 Ashnod's Altar

            //Enchantment
            1 Dictate of Erebos

            //Land
            1 Command Tower
            1 Overgrown Tomb
        """)
    )
    return deck_path


@pytest.fixture
def mtgo_deck(tmp_path: Path) -> Path:
    """Create a sample MTGO-format deck list."""
    deck_path = tmp_path / "deck.txt"
    deck_path.write_text(
        textwrap.dedent("""\
            1 Korvold, Fae-Cursed King
            1 Viscera Seer
            1 Blood Artist
            1 Sol Ring
            1 Command Tower
        """)
    )
    return deck_path


@pytest.fixture
def plain_deck(tmp_path: Path) -> Path:
    """Create a plain text deck list (names only)."""
    deck_path = tmp_path / "deck.txt"
    deck_path.write_text(
        textwrap.dedent("""\
            Korvold, Fae-Cursed King
            Viscera Seer
            Blood Artist
            Sol Ring
            Command Tower
        """)
    )
    return deck_path


@pytest.fixture
def csv_deck(tmp_path: Path) -> Path:
    """Create a CSV-format deck list."""
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text(
        textwrap.dedent("""\
            quantity,name
            1,Korvold, Fae-Cursed King
            1,Viscera Seer
            1,Blood Artist
            1,Sol Ring
            1,Command Tower
        """)
    )
    return deck_path


@pytest.fixture
def partner_deck(tmp_path: Path) -> Path:
    """Create a deck with partner commanders."""
    deck_path = tmp_path / "deck.txt"
    deck_path.write_text(
        textwrap.dedent("""\
            //Commander
            1 Thrasios, Triton Hero
            1 Tymna the Weaver

            //Creature
            1 Viscera Seer

            //Land
            1 Command Tower
        """)
    )
    return deck_path


@pytest.fixture
def sample_bulk_data(tmp_path: Path) -> Path:
    """Create a minimal Scryfall bulk data JSON for testing."""
    cards = [
        {
            "id": "aaa-korvold",
            "oracle_id": "orc-korvold",
            "name": "Korvold, Fae-Cursed King",
            "mana_cost": "{2}{B}{R}{G}",
            "cmc": 5.0,
            "type_line": "Legendary Creature — Dragon Noble",
            "oracle_text": "Flying\nWhenever Korvold, Fae-Cursed King enters the battlefield or attacks, sacrifice another permanent.\nWhenever you sacrifice a permanent, put a +1/+1 counter on Korvold and draw a card.",
            "keywords": ["Flying"],
            "colors": ["B", "G", "R"],
            "color_identity": ["B", "G", "R"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "3.50", "usd_foil": "7.00"},
            "game_changer": False,
        },
        {
            "id": "bbb-viscera",
            "oracle_id": "orc-viscera",
            "name": "Viscera Seer",
            "mana_cost": "{B}",
            "cmc": 1.0,
            "type_line": "Creature — Vampire Wizard",
            "oracle_text": "Sacrifice a creature: Scry 1.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "0.50", "usd_foil": "2.00"},
            "game_changer": False,
        },
        {
            "id": "ccc-blood-artist",
            "oracle_id": "orc-blood-artist",
            "name": "Blood Artist",
            "mana_cost": "{1}{B}",
            "cmc": 2.0,
            "type_line": "Creature — Vampire",
            "oracle_text": "Whenever Blood Artist or another creature dies, target player loses 1 life and you gain 1 life.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "1.00", "usd_foil": "3.00"},
            "game_changer": False,
        },
        {
            "id": "ddd-sol-ring",
            "oracle_id": "orc-sol-ring",
            "name": "Sol Ring",
            "mana_cost": "{1}",
            "cmc": 1.0,
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "produced_mana": ["C"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "1.00", "usd_foil": "5.00"},
            "game_changer": False,
        },
        {
            "id": "eee-command-tower",
            "oracle_id": "orc-command-tower",
            "name": "Command Tower",
            "mana_cost": "",
            "cmc": 0.0,
            "type_line": "Land",
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "produced_mana": ["W", "U", "B", "R", "G"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "0.25", "usd_foil": "1.00"},
            "game_changer": False,
        },
        {
            "id": "fff-sakura",
            "oracle_id": "orc-sakura",
            "name": "Sakura-Tribe Elder",
            "mana_cost": "{1}{G}",
            "cmc": 2.0,
            "type_line": "Creature — Snake Shaman",
            "oracle_text": "Sacrifice Sakura-Tribe Elder: Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.",
            "keywords": [],
            "colors": ["G"],
            "color_identity": ["G"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "0.35", "usd_foil": "1.50"},
            "game_changer": False,
        },
        {
            "id": "ggg-deadly-rollick",
            "oracle_id": "orc-deadly-rollick",
            "name": "Deadly Rollick",
            "mana_cost": "{3}{B}",
            "cmc": 4.0,
            "type_line": "Instant",
            "oracle_text": "If you control a commander, you may cast this spell without paying its mana cost.\nExile target creature.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "8.00", "usd_foil": "12.00"},
            "game_changer": False,
        },
        {
            "id": "hhh-cultivate",
            "oracle_id": "orc-cultivate",
            "name": "Cultivate",
            "mana_cost": "{2}{G}",
            "cmc": 3.0,
            "type_line": "Sorcery",
            "oracle_text": "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
            "keywords": [],
            "colors": ["G"],
            "color_identity": ["G"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "0.25", "usd_foil": "0.75"},
            "game_changer": False,
        },
        {
            "id": "iii-ashnods",
            "oracle_id": "orc-ashnods",
            "name": "Ashnod's Altar",
            "mana_cost": "{3}",
            "cmc": 3.0,
            "type_line": "Artifact",
            "oracle_text": "Sacrifice a creature: Add {C}{C}.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "2.50", "usd_foil": "8.00"},
            "game_changer": False,
        },
        {
            "id": "jjj-dictate",
            "oracle_id": "orc-dictate",
            "name": "Dictate of Erebos",
            "mana_cost": "{3}{B}{B}",
            "cmc": 5.0,
            "type_line": "Enchantment",
            "oracle_text": "Flash\nWhenever a creature you control dies, each opponent sacrifices a creature.",
            "keywords": ["Flash"],
            "colors": ["B"],
            "color_identity": ["B"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "3.00", "usd_foil": "6.00"},
            "game_changer": False,
        },
        {
            "id": "kkk-overgrown",
            "oracle_id": "orc-overgrown",
            "name": "Overgrown Tomb",
            "mana_cost": "",
            "cmc": 0.0,
            "type_line": "Land — Swamp Forest",
            "oracle_text": "({T}: Add {B} or {G}.)\nAs Overgrown Tomb enters the battlefield, you may pay 2 life. If you don't, it enters tapped.",
            "keywords": [],
            "colors": [],
            "color_identity": ["B", "G"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "9.00", "usd_foil": "15.00"},
            "game_changer": False,
        },
        {
            "id": "lll-thrasios",
            "oracle_id": "orc-thrasios",
            "name": "Thrasios, Triton Hero",
            "mana_cost": "{G}{U}",
            "cmc": 2.0,
            "type_line": "Legendary Creature — Merfolk Wizard",
            "oracle_text": "{4}: Scry 1, then reveal the top card of your library. If it's a land card, put it onto the battlefield tapped. Otherwise, draw a card.\nPartner",
            "keywords": ["Partner"],
            "colors": ["G", "U"],
            "color_identity": ["G", "U"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "5.00", "usd_foil": "10.00"},
            "game_changer": False,
        },
        {
            "id": "mmm-tymna",
            "oracle_id": "orc-tymna",
            "name": "Tymna the Weaver",
            "mana_cost": "{1}{W}{B}",
            "cmc": 3.0,
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Lifelink\nAt the beginning of your postcombat main phase, you may pay X life, where X is the number of opponents that were dealt combat damage this turn. If you do, draw X cards.\nPartner",
            "keywords": ["Lifelink", "Partner"],
            "colors": ["B", "W"],
            "color_identity": ["B", "W"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "15.00", "usd_foil": "25.00"},
            "game_changer": False,
        },
        {
            "id": "nnn-fire-ice",
            "oracle_id": "orc-fire-ice",
            "name": "Fire // Ice",
            "mana_cost": "{1}{R} // {1}{U}",
            "cmc": 4.0,
            "type_line": "Instant // Instant",
            "oracle_text": "Fire deals 2 damage divided as you choose among one or two targets.\n//\nTap target permanent.\nDraw a card.",
            "keywords": [],
            "colors": ["R", "U"],
            "color_identity": ["R", "U"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "0.25", "usd_foil": "1.00"},
            "game_changer": False,
        },
        {
            "id": "ooo-rhystic",
            "oracle_id": "orc-rhystic",
            "name": "Rhystic Study",
            "mana_cost": "{2}{U}",
            "cmc": 3.0,
            "type_line": "Enchantment",
            "oracle_text": "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "8.00", "usd_foil": "40.00"},
            "game_changer": True,
        },
    ]
    bulk_path = tmp_path / "default-cards.json"
    bulk_path.write_text(json.dumps(cards))
    return bulk_path


@pytest.fixture
def hydrated_cards(sample_bulk_data: Path) -> list[dict]:
    """Load sample bulk data as a hydrated card list."""
    return json.loads(sample_bulk_data.read_text(encoding="utf-8"))


@pytest.fixture
def cube_bulk_data(tmp_path: Path) -> Path:
    """Extra cards for cube tests: a few duals, gold cards, rares for rarity
    breakdown, and an uncommon creature commander for PDH-style tests.

    Tests combine this with sample_bulk_data entries via cube_hydrated fixture.
    """
    cards = [
        {
            "id": "cbk-bolt",
            "oracle_id": "orc-bolt",
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "keywords": [],
            "colors": ["R"],
            "color_identity": ["R"],
            "rarity": "common",
            "legalities": {"modern": "legal", "legacy": "legal", "vintage": "legal"},
            "prices": {"usd": "0.50"},
        },
        {
            "id": "cbk-stp",
            "oracle_id": "orc-stp",
            "name": "Swords to Plowshares",
            "mana_cost": "{W}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
            "keywords": [],
            "colors": ["W"],
            "color_identity": ["W"],
            "rarity": "uncommon",
            "legalities": {"legacy": "legal", "vintage": "legal"},
            "prices": {"usd": "1.50"},
        },
        {
            "id": "cbk-counter",
            "oracle_id": "orc-counter",
            "name": "Counterspell",
            "mana_cost": "{U}{U}",
            "cmc": 2.0,
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "rarity": "common",
            "legalities": {"modern": "legal", "legacy": "legal"},
            "prices": {"usd": "0.75"},
        },
        {
            "id": "cbk-dark-rit",
            "oracle_id": "orc-dark-rit",
            "name": "Dark Ritual",
            "mana_cost": "{B}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Add {B}{B}{B}.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "rarity": "common",
            "legalities": {"legacy": "legal", "vintage": "legal"},
            "prices": {"usd": "1.50"},
        },
        {
            "id": "cbk-elves",
            "oracle_id": "orc-elves",
            "name": "Llanowar Elves",
            "mana_cost": "{G}",
            "cmc": 1.0,
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
            "keywords": [],
            "colors": ["G"],
            "color_identity": ["G"],
            "rarity": "common",
            "legalities": {"modern": "legal", "legacy": "legal"},
            "prices": {"usd": "0.25"},
        },
        {
            "id": "cbk-atraxa",
            "oracle_id": "orc-atraxa",
            "name": "Atraxa, Praetors' Voice",
            "mana_cost": "{G}{W}{U}{B}",
            "cmc": 4.0,
            "type_line": "Legendary Creature — Phyrexian Angel Horror",
            "oracle_text": "Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
            "keywords": ["Flying", "Vigilance", "Deathtouch", "Lifelink"],
            "colors": ["B", "G", "U", "W"],
            "color_identity": ["B", "G", "U", "W"],
            "rarity": "mythic",
            "legalities": {"commander": "legal"},
            "prices": {"usd": "20.00"},
        },
        {
            "id": "cbk-tuvasa",
            "oracle_id": "orc-tuvasa",
            "name": "Tuvasa the Sunlit",
            "mana_cost": "{G}{W}{U}",
            "cmc": 3.0,
            "type_line": "Legendary Creature — Merfolk Druid",
            "oracle_text": "Tuvasa the Sunlit gets +1/+1 for each enchantment you control.\nWhenever you cast your first enchantment spell each turn, draw a card.",
            "keywords": [],
            "colors": ["G", "U", "W"],
            "color_identity": ["G", "U", "W"],
            "rarity": "mythic",
            "legalities": {"commander": "legal"},
            "prices": {"usd": "3.00"},
        },
        {
            "id": "cbk-wildfire",
            "oracle_id": "orc-wildfire",
            "name": "Wildfire",
            "mana_cost": "{4}{R}{R}",
            "cmc": 6.0,
            "type_line": "Sorcery",
            "oracle_text": "Each player sacrifices four lands, then Wildfire deals 4 damage to each creature.",
            "keywords": [],
            "colors": ["R"],
            "color_identity": ["R"],
            "rarity": "rare",
            "legalities": {"legacy": "legal", "vintage": "legal"},
            "prices": {"usd": "2.00"},
        },
    ]
    bulk_path = tmp_path / "cube-cards.json"
    bulk_path.write_text(json.dumps(cards))
    return bulk_path


@pytest.fixture
def cube_hydrated(sample_bulk_data: Path, cube_bulk_data: Path) -> list[dict]:
    """Merged hydrated data: deck-test cards + cube-test extras."""
    deck_cards = json.loads(sample_bulk_data.read_text(encoding="utf-8"))
    cube_cards = json.loads(cube_bulk_data.read_text(encoding="utf-8"))
    return [*deck_cards, *cube_cards]


@pytest.fixture
def sample_cube_json() -> dict:
    """Small cube JSON with a spread of colors, types, and rarities."""
    return {
        "cube_format": "vintage",
        "target_size": 12,
        "name": "Sample Cube",
        "drafters": 8,
        "pack_size": 15,
        "packs_per_drafter": 3,
        "cards": [
            # Mono-colored non-lands
            {"name": "Lightning Bolt", "quantity": 1},
            {"name": "Swords to Plowshares", "quantity": 1},
            {"name": "Counterspell", "quantity": 1},
            {"name": "Dark Ritual", "quantity": 1},
            {"name": "Llanowar Elves", "quantity": 1},
            {"name": "Viscera Seer", "quantity": 1},
            {"name": "Rhystic Study", "quantity": 1},
            # Multicolor
            {"name": "Thrasios, Triton Hero", "quantity": 1},
            {"name": "Fire // Ice", "quantity": 1},
            # Artifacts (colorless)
            {"name": "Sol Ring", "quantity": 1},
            # Lands
            {"name": "Overgrown Tomb", "quantity": 1},
            {"name": "Command Tower", "quantity": 1},
        ],
        "total_cards": 12,
    }


@pytest.fixture
def sample_commander_cube_json() -> dict:
    """Small commander cube with a dedicated commander pool."""
    return {
        "cube_format": "commander",
        "target_size": 8,
        "name": "Sample Commander Cube",
        "drafters": 8,
        "pack_size": 15,
        "packs_per_drafter": 3,
        "commander_pool": [
            {"name": "Atraxa, Praetors' Voice", "quantity": 1},
            {"name": "Tuvasa the Sunlit", "quantity": 1},
            {"name": "Thrasios, Triton Hero", "quantity": 1},
            {"name": "Korvold, Fae-Cursed King", "quantity": 1},
        ],
        "cards": [
            {"name": "Lightning Bolt", "quantity": 1},
            {"name": "Counterspell", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
            {"name": "Command Tower", "quantity": 1},
        ],
        "total_cards": 8,
    }


@pytest.fixture
def sample_edhrec_response() -> dict:
    """Sample EDHREC JSON response for Korvold."""
    return {
        "container": {
            "json_dict": {
                "cardlists": [
                    {
                        "header": "High Synergy Cards",
                        "tag": "highsynergycards",
                        "cardviews": [
                            {
                                "name": "Pitiless Plunderer",
                                "sanitized": "pitiless-plunderer",
                                "synergy": 0.55,
                                "inclusion": 78,
                                "num_decks": 45000,
                                "potential_decks": 58000,
                            },
                            {
                                "name": "Mayhem Devil",
                                "sanitized": "mayhem-devil",
                                "synergy": 0.48,
                                "inclusion": 72,
                                "num_decks": 41000,
                                "potential_decks": 58000,
                            },
                        ],
                    },
                    {
                        "header": "Top Cards",
                        "tag": "topcards",
                        "cardviews": [
                            {
                                "name": "Sol Ring",
                                "sanitized": "sol-ring",
                                "synergy": 0.01,
                                "inclusion": 98,
                                "num_decks": 57000,
                                "potential_decks": 58000,
                            },
                        ],
                    },
                ],
            },
        },
    }


@pytest.fixture
def alt_cost_cards():
    """Cards with various alternative casting costs."""
    return [
        {
            "name": "Star Whale",
            "cmc": 8.0,
            "type_line": "Creature — Alien Whale",
            "oracle_text": "Flying, vigilance\nOther creatures you control have ward {2}.\nSuspend 6—{1}{U}",
            "mana_cost": "{6}{U}{U}",
            "keywords": ["Flying", "Vigilance", "Ward", "Suspend"],
        },
        {
            "name": "Ancestral Vision",
            "cmc": 0.0,
            "type_line": "Sorcery",
            "oracle_text": "Suspend 4—{U}\nTarget player draws three cards.",
            "mana_cost": "",
            "keywords": ["Suspend"],
        },
        {
            "name": "Fury",
            "cmc": 5.0,
            "type_line": "Creature — Elemental Incarnation",
            "oracle_text": "Double strike\nWhen this creature enters, it deals 4 damage divided as you choose among any number of targets.\nEvoke—Exile a red card from your hand.",
            "mana_cost": "{3}{R}{R}",
            "keywords": ["Double strike", "Evoke"],
        },
        {
            "name": "Goldvein Hydra",
            "cmc": 1.0,
            "type_line": "Creature — Hydra",
            "oracle_text": "Trample\nGoldvein Hydra enters with X +1/+1 counters on it.\nWhen Goldvein Hydra dies, create a number of Treasure tokens equal to its power.",
            "mana_cost": "{X}{G}",
            "keywords": ["Trample"],
        },
        {
            "name": "Sol Ring",
            "cmc": 1.0,
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
            "mana_cost": "{1}",
            "keywords": [],
        },
        {
            "name": "Command Tower",
            "cmc": 0.0,
            "type_line": "Land",
            "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
            "mana_cost": "",
            "keywords": [],
        },
        {
            "name": "Murderous Cut",
            "cmc": 5.0,
            "type_line": "Instant",
            "oracle_text": "Delve\nDestroy target creature.",
            "mana_cost": "{4}{B}",
            "keywords": ["Delve"],
        },
    ]


@pytest.fixture
def trigger_test_cards() -> list[dict]:
    """Cards with known trigger types and numeric values for cut-check testing."""
    return [
        {
            "name": "Obeka, Splitter of Seconds",
            "mana_cost": "{1}{U}{B}{R}",
            "cmc": 4.0,
            "type_line": "Legendary Creature — Ogre Warlock",
            "oracle_text": "Menace\nWhenever Obeka deals combat damage to a player, you get that many additional upkeep steps after this phase.",
            "keywords": ["Menace"],
            "colors": ["B", "R", "U"],
            "color_identity": ["B", "R", "U"],
            "prices": {"usd": "1.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Upkeep Drainer",
            "mana_cost": "{1}{B}",
            "cmc": 2.0,
            "type_line": "Creature — Vampire",
            "oracle_text": "At the beginning of your upkeep, this creature deals 1 damage to each opponent. You gain life equal to the damage dealt this way.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "prices": {"usd": "0.50"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Suspend Bouncer",
            "mana_cost": "{4}{U}{U}",
            "cmc": 6.0,
            "type_line": "Sorcery",
            "oracle_text": "Return target permanent to its owner's hand. Exile Suspend Bouncer with three time counters on it.\nSuspend 3—{2}{U}",
            "keywords": ["Suspend"],
            "colors": ["U"],
            "color_identity": ["U"],
            "prices": {"usd": "0.25"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Blocking Restrictor",
            "mana_cost": "{2}",
            "cmc": 2.0,
            "type_line": "Artifact — Equipment",
            "oracle_text": "Equipped creature has trample and can't be blocked by more than one creature.\nEquip {1}",
            "keywords": ["Equip"],
            "colors": [],
            "color_identity": [],
            "prices": {"usd": "0.10"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Double Striker",
            "mana_cost": "{1}{R}",
            "cmc": 2.0,
            "type_line": "Artifact Creature — Equipment Lizard",
            "oracle_text": "Double strike\nEquipped creature has double strike.\nReconfigure {2}",
            "keywords": ["Double strike", "Reconfigure"],
            "colors": ["R"],
            "color_identity": ["R"],
            "prices": {"usd": "0.75"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Variable Trigger",
            "mana_cost": "{2}{B}",
            "cmc": 3.0,
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, repeat the following process for each opponent in turn order. Reveal the top card of your library. Any opponent may pay life equal to that card's mana value. If they don't, put it into your hand.",
            "keywords": [],
            "colors": ["B"],
            "color_identity": ["B"],
            "prices": {"usd": "1.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Attack Trigger Guy",
            "mana_cost": "{3}{R}{R}",
            "cmc": 5.0,
            "type_line": "Creature — Dragon",
            "oracle_text": "Flying\nWhenever you attack, create two 1/1 red Goblin creature tokens that are tapped and attacking.",
            "keywords": ["Flying"],
            "colors": ["R"],
            "color_identity": ["R"],
            "prices": {"usd": "2.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Buyback Spell",
            "mana_cost": "{2}{U}",
            "cmc": 3.0,
            "type_line": "Instant",
            "oracle_text": "Buyback {3}\nDraw a card.",
            "keywords": ["Buyback"],
            "colors": ["U"],
            "color_identity": ["U"],
            "prices": {"usd": "0.50"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Helm of the Host",
            "mana_cost": "{4}",
            "cmc": 4.0,
            "type_line": "Legendary Artifact — Equipment",
            "oracle_text": "At the beginning of combat on your turn, create a token that's a copy of equipped creature, except the token isn't legendary. That token gains haste.\nEquip {5}",
            "keywords": ["Equip"],
            "colors": [],
            "color_identity": [],
            "prices": {"usd": "7.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Spark Double",
            "mana_cost": "{3}{U}",
            "cmc": 4.0,
            "type_line": "Creature — Illusion",
            "oracle_text": "You may have Spark Double enter as a copy of a creature or planeswalker you control, except it enters with an additional +1/+1 counter on it if it's a creature, it enters with an additional loyalty counter on it if it's a planeswalker, and it isn't legendary.",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "prices": {"usd": "3.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Strionic Resonator",
            "mana_cost": "{2}",
            "cmc": 2.0,
            "type_line": "Artifact",
            "oracle_text": "{2}, {T}: Copy target triggered ability you control. You may choose new targets for the copy.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "prices": {"usd": "1.50"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Panharmonicon",
            "mana_cost": "{4}",
            "cmc": 4.0,
            "type_line": "Artifact",
            "oracle_text": "If an artifact or creature entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "prices": {"usd": "5.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Rings of Brighthearth",
            "mana_cost": "{3}",
            "cmc": 3.0,
            "type_line": "Artifact",
            "oracle_text": "Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that ability. You may choose new targets for the copy.",
            "keywords": [],
            "colors": [],
            "color_identity": [],
            "prices": {"usd": "4.00"},
            "legalities": {"commander": "legal"},
        },
        {
            "name": "Counterspell",
            "mana_cost": "{U}{U}",
            "cmc": 2.0,
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "prices": {"usd": "0.50"},
            "legalities": {"commander": "legal"},
        },
    ]


@pytest.fixture
def sample_combo_response() -> dict:
    """Sample Commander Spellbook /find-my-combos response."""
    return {
        "results": {
            "included": [
                {
                    "id": "combo-1",
                    "uses": [
                        {
                            "card": {"name": "Viscera Seer"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Blood Artist"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Reassembling Skeleton"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Ashnod's Altar"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                    ],
                    "produces": [
                        {"name": "Infinite ETB"},
                        {"name": "Infinite death triggers"},
                        {"name": "Infinite colorless mana"},
                    ],
                    "description": "1. Sacrifice Reassembling Skeleton to Ashnod's Altar for {C}{C}.\n2. Pay {1}{B} to return Skeleton from graveyard to battlefield.\n3. Blood Artist triggers on each death.\n4. Repeat.",
                    "identity": "B",
                    "manaNeeded": "{1}{B}",
                    "popularity": 5000,
                    "bracketTag": "B3",
                    "legalities": {"commander": True},
                },
            ],
            "almostIncluded": [
                {
                    "id": "combo-2",
                    "uses": [
                        {
                            "card": {"name": "Viscera Seer"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Blood Artist"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Gravecrawler"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                    ],
                    "produces": [
                        {"name": "Infinite death triggers"},
                        {"name": "Infinite ETB"},
                    ],
                    "description": "1. Sacrifice Gravecrawler to Viscera Seer.\n2. Recast Gravecrawler from graveyard.\n3. Blood Artist triggers.\n4. Repeat.",
                    "identity": "B",
                    "manaNeeded": "{B}",
                    "popularity": 8000,
                    "bracketTag": "B3",
                    "legalities": {"commander": True},
                },
                {
                    "id": "combo-3",
                    "uses": [
                        {
                            "card": {"name": "Sol Ring"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                        {
                            "card": {"name": "Dramatic Reversal"},
                            "quantity": 1,
                            "zoneLocations": "H",
                        },
                        {
                            "card": {"name": "Isochron Scepter"},
                            "quantity": 1,
                            "zoneLocations": "B",
                        },
                    ],
                    "produces": [
                        {"name": "Infinite colorless mana"},
                    ],
                    "description": "1. Imprint Dramatic Reversal on Isochron Scepter.\n2. Activate Scepter to untap all nonland permanents.\n3. Tap Sol Ring for mana.\n4. Repeat.",
                    "identity": "",
                    "manaNeeded": "{2}",
                    "popularity": 12000,
                    "bracketTag": "B4",
                    "legalities": {"commander": True},
                },
            ],
            "almostIncludedByAddingColors": [],
            "includedByChangingCommanders": [],
            "almostIncludedByChangingCommanders": [],
            "almostIncludedByAddingColorsAndChangingCommanders": [],
        }
    }


@pytest.fixture
def sample_combo_empty_response() -> dict:
    """Empty Commander Spellbook response."""
    return {
        "results": {
            "included": [],
            "almostIncluded": [],
            "almostIncludedByAddingColors": [],
            "includedByChangingCommanders": [],
            "almostIncludedByChangingCommanders": [],
            "almostIncludedByAddingColorsAndChangingCommanders": [],
        }
    }


@pytest.fixture(scope="session")
def real_cr_path() -> Path:
    """Return a path to the real 2024 Comprehensive Rules TXT.

    Downloads from a GitHub mirror on first use per test session, with
    a 7-day on-disk cache at ``/tmp/pytest-comprehensive-rules.txt`` so
    local edit-rerun loops don't refetch constantly. Session-scoped so
    a single pytest invocation reuses the text across tests.

    Used by parser-drift tests that assert invariants against the real
    CR — we own the tiny hand-rolled fixture in ``test_rules_lookup``,
    so only real-document tests live here.
    """
    cache = Path(tempfile.gettempdir()) / "pytest-comprehensive-rules.txt"
    fresh = (
        cache.exists()
        and (time.time() - cache.stat().st_mtime) < _REAL_CR_CACHE_TTL
        and cache.stat().st_size > 100_000
    )
    if not fresh:
        req = urllib.request.Request(
            _REAL_CR_URL,
            headers={"User-Agent": "mtg-skills-tests/0.1"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(cache)
        os.utime(cache, None)
    return cache
