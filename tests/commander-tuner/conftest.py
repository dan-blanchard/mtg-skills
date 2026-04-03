"""Shared test fixtures for commander_utils tests."""

import json
import textwrap
from pathlib import Path

import pytest


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
