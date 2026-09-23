"""Shared test fixtures for mtg_utils tests."""

import json
import os
import sqlite3
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _block_card_data_download(request, monkeypatch):
    """Keep the suite network-free: ``_phase.ensure_card_data`` must not download.

    Card IR auto-build paths (``deck-signals``/``-rank``, deck-forge launch) call
    ``ensure_card_data``, which fetches the phase release tarball when the
    tag-versioned card-data cache is cold. In tests we never want that network
    hit: short-circuit to "cached-or-raise" so callers degrade to the regex path
    exactly as they did before the download was wired in. ``test_phase_wrapper``
    owns the real ``ensure_card_data`` download tests (urllib mocked) and opts
    out so it can exercise the genuine fetch/extract logic.
    """
    if request.module.__name__ == "test_phase_wrapper":
        return
    from mtg_utils import _phase

    real_path = _phase._card_data_path

    def _cached_only() -> Path:
        cached = real_path()
        if cached.exists():
            return cached
        raise RuntimeError(
            "card-data download blocked in tests (no network); the tag-versioned "
            f"cache at {cached} is absent."
        )

    monkeypatch.setattr(_phase, "ensure_card_data", _cached_only)


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


def _real(name: str, **per_printing) -> dict:
    """The real card *name* from the testkit snapshot (ADR-0056), with only the
    per-printing facts a fixture varies (id, prices, rarity, …) overlaid.

    Also seeds the crosswalk trees memo for the card's real ``oracle_id`` from the
    snapshot's stored phase records, so a structural-view preset or signal lane
    resolves the card identically locally and in CI (no phase cache there)."""
    from mtg_utils import testkit

    testkit.test_card_ir(name)  # seeds the crosswalk trees memo
    return {**testkit.test_card(name), **per_printing}


@pytest.fixture
def sample_bulk_data(tmp_path: Path) -> Path:
    """A minimal Scryfall-shaped bulk JSON of real cards (ADR-0056).

    Card facts come from the testkit snapshot; only per-printing facts (``id``,
    ``prices``) and the Scryfall-served flags the snapshot doesn't carry
    (``game_changer``, ``edhrec_rank``) are written here.
    """
    cards = [
        _real(
            "Korvold, Fae-Cursed King",
            id="aaa-korvold",
            prices={"usd": "3.50", "usd_foil": "7.00"},
            game_changer=False,
        ),
        _real(
            "Viscera Seer",
            id="bbb-viscera",
            prices={"usd": "0.50", "usd_foil": "2.00"},
            game_changer=False,
            edhrec_rank=253,
        ),
        _real(
            "Blood Artist",
            id="ccc-blood-artist",
            prices={"usd": "1.00", "usd_foil": "3.00"},
            game_changer=False,
        ),
        _real(
            "Sol Ring",
            id="ddd-sol-ring",
            prices={"usd": "1.00", "usd_foil": "5.00"},
            game_changer=False,
        ),
        _real(
            "Command Tower",
            id="eee-command-tower",
            prices={"usd": "0.25", "usd_foil": "1.00"},
            game_changer=False,
        ),
        _real(
            "Sakura-Tribe Elder",
            id="fff-sakura",
            prices={"usd": "0.35", "usd_foil": "1.50"},
            game_changer=False,
        ),
        _real(
            "Deadly Rollick",
            id="ggg-deadly-rollick",
            prices={"usd": "8.00", "usd_foil": "12.00"},
            game_changer=False,
        ),
        _real(
            "Cultivate",
            id="hhh-cultivate",
            prices={"usd": "0.25", "usd_foil": "0.75"},
            game_changer=False,
        ),
        _real(
            "Ashnod's Altar",
            id="iii-ashnods",
            prices={"usd": "2.50", "usd_foil": "8.00"},
            game_changer=False,
        ),
        _real(
            "Dictate of Erebos",
            id="jjj-dictate",
            prices={"usd": "3.00", "usd_foil": "6.00"},
            game_changer=False,
        ),
        _real(
            "Overgrown Tomb",
            id="kkk-overgrown",
            prices={"usd": "9.00", "usd_foil": "15.00"},
            game_changer=False,
        ),
        _real(
            "Thrasios, Triton Hero",
            id="lll-thrasios",
            prices={"usd": "5.00", "usd_foil": "10.00"},
            game_changer=False,
        ),
        _real(
            "Tymna the Weaver",
            id="mmm-tymna",
            prices={"usd": "15.00", "usd_foil": "25.00"},
            game_changer=False,
        ),
        _real(
            "Fire // Ice",
            id="nnn-fire-ice",
            prices={"usd": "0.25", "usd_foil": "1.00"},
            game_changer=False,
        ),
        {
            # Fictional machinery (ADR-0056 "synthetic records are for machinery
            # only"): a big evasive body that exercises the tuner's
            # `is_creature(card) and card_pt_int(card) >= 6` wincon arm end-to-end
            # through hydration, rather than by patching power onto a small card.
            "id": "qqq-ancient-wyrm",
            "oracle_id": "orc-ancient-wyrm",
            "name": "Ancient Wyrm",
            "mana_cost": "{5}{R}{R}",
            "cmc": 7.0,
            "type_line": "Creature — Dragon",
            "oracle_text": "Flying",
            "power": "7",
            "toughness": "7",
            "keywords": ["Flying"],
            "colors": ["R"],
            "color_identity": ["R"],
            "legalities": {"commander": "legal"},
            "prices": {"usd": "1.00", "usd_foil": "3.00"},
            "game_changer": False,
        },
        # A modal DFC with a creature front face: Scryfall (and the MTGJSON
        # adapter) put P/T, mana_cost and colors ONLY on card_faces for this
        # layout, never at top level. Guards the card_faces projection in
        # CARD_FIELDS.
        _real(
            "Blackbloom Rogue // Blackbloom Bog",
            id="ppp-blackbloom",
            prices={"usd": "2.00", "usd_foil": "5.00"},
            game_changer=False,
        ),
        _real(
            "Rhystic Study",
            id="ooo-rhystic",
            prices={"usd": "8.00", "usd_foil": "40.00"},
            game_changer=True,
        ),
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
    """Extra real cards for cube tests: gold cards, rares for the rarity
    breakdown, and legendary creatures for the commander pool.

    Tests combine this with sample_bulk_data entries via cube_hydrated fixture.
    Rarity, id and prices are the per-printing overlays (ADR-0056).
    """
    cards = [
        _real("Lightning Bolt", id="cbk-bolt", rarity="common", prices={"usd": "0.50"}),
        _real(
            "Swords to Plowshares",
            id="cbk-stp",
            rarity="uncommon",
            prices={"usd": "1.50"},
        ),
        _real(
            "Counterspell", id="cbk-counter", rarity="common", prices={"usd": "0.75"}
        ),
        _real(
            "Dark Ritual", id="cbk-dark-rit", rarity="common", prices={"usd": "1.50"}
        ),
        _real(
            "Llanowar Elves", id="cbk-elves", rarity="common", prices={"usd": "0.25"}
        ),
        _real(
            "Atraxa, Praetors' Voice",
            id="cbk-atraxa",
            rarity="mythic",
            prices={"usd": "20.00"},
        ),
        _real(
            "Tuvasa the Sunlit",
            id="cbk-tuvasa",
            rarity="mythic",
            prices={"usd": "3.00"},
        ),
        _real("Wildfire", id="cbk-wildfire", rarity="rare", prices={"usd": "2.00"}),
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
def cube_hydrated_real_removal(cube_hydrated: list[dict]) -> list[dict]:
    """``cube_hydrated`` for the tests that exercise the structural-view
    ``removal`` preset, which never matches a card whose ``oracle_id`` doesn't
    resolve against the crosswalk (see ``theme_presets.py``'s "Structural views"
    module-docstring section).

    Every real card in ``cube_hydrated`` now carries its real ``oracle_id`` and
    has its crosswalk trees seeded from the testkit snapshot (``_real``), so this
    is the same list; the name stays for the tests that ask for it.
    """
    return cube_hydrated


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
    """Real cards with various alternative casting costs (ADR-0056)."""
    return [
        _real("Star Whale"),
        _real("Ancestral Vision"),
        _real("Fury"),
        _real("Goldvein Hydra"),
        _real("Sol Ring"),
        _real("Command Tower"),
        _real("Murderous Cut"),
    ]


@pytest.fixture
def trigger_test_cards() -> list[dict]:
    """Cards with known trigger types and numeric values for cut-check testing.

    Real cards come from the testkit snapshot with a ``prices`` overlay
    (ADR-0056); the fictionally named records are machinery for trigger shapes.
    """
    return [
        _real("Obeka, Splitter of Seconds", prices={"usd": "1.00"}),
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
        _real("Helm of the Host", prices={"usd": "7.00"}),
        _real("Spark Double", prices={"usd": "3.00"}),
        _real("Strionic Resonator", prices={"usd": "1.50"}),
        _real("Panharmonicon", prices={"usd": "5.00"}),
        _real("Rings of Brighthearth", prices={"usd": "4.00"}),
        _real("Counterspell", prices={"usd": "0.50"}),
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


def make_arena_card_db(path: Path, printings: list[tuple]) -> Path:
    """An Arena-shaped card database. Each printing is ``(title, rarity, primary)``
    with optional ``is_token`` / ``is_rebalanced`` / ``formatted_title``; the title is
    stored the way Arena stores it — a plain row (``Formatted`` 0) plus a formatted
    row (``Formatted`` 1) that may carry markup."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE Cards (GrpId INTEGER, TitleId INTEGER, Rarity INTEGER, "
        "IsPrimaryCard INTEGER, IsToken INTEGER, IsRebalanced INTEGER)"
    )
    con.execute(
        "CREATE TABLE Localizations_enUS (LocId INTEGER, Formatted INTEGER, Loc TEXT)"
    )
    for grp_id, printing in enumerate(printings, start=1):
        title, rarity, primary, *rest = printing
        is_token, is_rebalanced, formatted = [*rest, 0, 0, None][:3]
        con.execute(
            "INSERT INTO Cards VALUES (?, ?, ?, ?, ?, ?)",
            (grp_id, grp_id, rarity, primary, is_token, is_rebalanced),
        )
        if title is not None:
            con.execute(
                "INSERT INTO Localizations_enUS VALUES (?, 0, ?)", (grp_id, title)
            )
        con.execute(
            "INSERT INTO Localizations_enUS VALUES (?, 1, ?)",
            (grp_id, formatted if formatted is not None else title),
        )
    con.commit()
    con.close()
    return path
