"""Tests for parse_cube CLI."""

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.parse_cube import main, parse_cube


@pytest.fixture
def plain_cube_file(tmp_path: Path) -> Path:
    path = tmp_path / "mycube.txt"
    path.write_text(
        textwrap.dedent("""\
            1 Lightning Bolt
            1 Swords to Plowshares
            1 Counterspell
            1 Dark Ritual
            1 Llanowar Elves
            1 Sol Ring
            1 Command Tower
        """)
    )
    return path


@pytest.fixture
def cubecobra_csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "cube.csv"
    path.write_text(
        "name,CMC,Type,Color,Set,Collector Number,Rarity,Color Category,"
        "Status,Finish,Maybeboard,Image URL,Image Back URL,Tags,Notes,MTGO ID\n"
        "Lightning Bolt,1,Instant,R,LEA,161,Common,R,Owned,Non-foil,false,,,burn,,\n"
        "Swords to Plowshares,1,Instant,W,LEA,18,Common,W,Owned,Non-foil,false,,,removal,,\n"
        "Hero of Bladehold,4,Creature - Human Knight,W,MBS,8,Mythic,W,Owned,"
        'Non-foil,false,,,"aggro, tokens",,\n'
        # maybeboard entry should be dropped
        "Flame Slash,1,Instant,R,WWK,75,Uncommon,R,Owned,Non-foil,true,,,,,\n"
    )
    return path


@pytest.fixture
def cubecobra_json_file(tmp_path: Path) -> Path:
    path = tmp_path / "cube.json"
    path.write_text(
        json.dumps(
            {
                "shortID": "regular",
                "name": "Regular Cube",
                "description": "My unpowered cube",
                "tags": ["unpowered", "vintage"],
                "type": "vintage",
                "mainboard": [
                    {
                        "cardID": "abc-123",
                        "details": {
                            "name": "Lightning Bolt",
                            "type_line": "Instant",
                        },
                        "tags": ["burn"],
                        "cmc": 1,
                    },
                    {
                        "cardID": "def-456",
                        "details": {
                            "name": "Bloodghast",
                            "type_line": "Creature — Vampire Spirit",
                        },
                        "tags": ["reanimator"],
                    },
                ],
                "maybeboard": [],
            }
        )
    )
    return path


@pytest.fixture
def cubecobra_v2_json_file(tmp_path: Path) -> Path:
    """CubeCobra's current (v2) JSON shape: mainboard nested under 'cards'."""
    path = tmp_path / "cube.json"
    path.write_text(
        json.dumps(
            {
                "shortId": "modovintage",
                "name": "MTGO Vintage Cube",
                "description": "WotC MTGO Vintage Cube",
                "cardCount": 2,
                "cards": {
                    "mainboard": [
                        {
                            "cardID": "abc-123",
                            "name": "Lightning Bolt",
                            "cmc": "1",
                            "type_line": "Instant",
                            "colors": ["R"],
                            "tags": ["burn"],
                            "colorCategory": None,
                            "details": {
                                "name": "Lightning Bolt",
                                "type_line": "Instant",
                                "scryfall_id": "abc-123",
                            },
                        },
                        {
                            "cardID": "def-456",
                            "name": "Bloodghast",
                            "cmc": "2",
                            "type_line": "Creature",
                            "colors": ["B"],
                            "tags": [],
                            "colorCategory": "Black",
                            "details": {
                                "name": "Bloodghast",
                                "type_line": "Creature — Vampire Spirit",
                                "scryfall_id": "def-456",
                            },
                        },
                    ],
                    "maybeboard": [],
                },
            }
        )
    )
    return path


@pytest.fixture
def deck_json_file(tmp_path: Path) -> Path:
    path = tmp_path / "deck.json"
    path.write_text(
        json.dumps(
            {
                "format": "commander",
                "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
                "cards": [
                    {"name": "Sol Ring", "quantity": 1},
                    {"name": "Command Tower", "quantity": 1},
                ],
                "sideboard": [],
            }
        )
    )
    return path


class TestParseCubePlain:
    def test_parses_plain_list(self, plain_cube_file: Path):
        cube = parse_cube(plain_cube_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Lightning Bolt" in names
        assert "Command Tower" in names
        assert cube["total_cards"] == 7

    def test_default_format_is_vintage(self, plain_cube_file: Path):
        cube = parse_cube(plain_cube_file)
        assert cube["cube_format"] == "vintage"
        assert cube["target_size"] == 540

    def test_target_size_override(self, plain_cube_file: Path):
        cube = parse_cube(plain_cube_file, target_size=360)
        assert cube["target_size"] == 360
        assert cube["drafters"] == 8

    def test_cube_format_override(self, plain_cube_file: Path):
        cube = parse_cube(plain_cube_file, cube_format="pauper")
        assert cube["cube_format"] == "pauper"

    def test_name_defaults_to_filename_stem(self, plain_cube_file: Path):
        cube = parse_cube(plain_cube_file)
        assert cube["name"] == "mycube"


class TestParseCubecobraCSV:
    def test_parses_mainboard(self, cubecobra_csv_file: Path):
        cube = parse_cube(cubecobra_csv_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Lightning Bolt" in names
        assert "Swords to Plowshares" in names
        assert "Hero of Bladehold" in names

    def test_drops_maybeboard(self, cubecobra_csv_file: Path):
        cube = parse_cube(cubecobra_csv_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Flame Slash" not in names

    def test_preserves_cube_overrides(self, cubecobra_csv_file: Path):
        cube = parse_cube(cubecobra_csv_file)
        bolt = next(c for c in cube["cards"] if c["name"] == "Lightning Bolt")
        assert bolt["cube_color"] == "R"
        assert bolt["cube_cmc"] == 1.0
        assert bolt["tags"] == ["burn"]

    def test_parses_multi_tag(self, cubecobra_csv_file: Path):
        cube = parse_cube(cubecobra_csv_file)
        hero = next(c for c in cube["cards"] if c["name"] == "Hero of Bladehold")
        assert set(hero["tags"]) == {"aggro", "tokens"}


class TestParseCubecobraJSON:
    def test_parses_mainboard(self, cubecobra_json_file: Path):
        cube = parse_cube(cubecobra_json_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Lightning Bolt" in names
        assert "Bloodghast" in names

    def test_sets_source_from_shortid(self, cubecobra_json_file: Path):
        cube = parse_cube(cubecobra_json_file)
        assert cube["source"] == "cubecobra:regular"

    def test_captures_designer_intent(self, cubecobra_json_file: Path):
        cube = parse_cube(cubecobra_json_file)
        intent = cube["designer_intent"]
        assert intent["description"] == "My unpowered cube"
        assert "unpowered" in intent["tags"]

    def test_preserves_scryfall_id(self, cubecobra_json_file: Path):
        cube = parse_cube(cubecobra_json_file)
        bolt = next(c for c in cube["cards"] if c["name"] == "Lightning Bolt")
        assert bolt["scryfall_id"] == "abc-123"

    def test_name_from_json(self, cubecobra_json_file: Path):
        cube = parse_cube(cubecobra_json_file)
        assert cube["name"] == "Regular Cube"


class TestParseCubecobraV2JSON:
    """CubeCobra's current JSON shape nests mainboard under 'cards'."""

    def test_parses_nested_mainboard(self, cubecobra_v2_json_file: Path):
        cube = parse_cube(cubecobra_v2_json_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Lightning Bolt" in names
        assert "Bloodghast" in names
        assert cube["total_cards"] == 2

    def test_captures_short_id_camelcase(self, cubecobra_v2_json_file: Path):
        cube = parse_cube(cubecobra_v2_json_file)
        assert cube["source"] == "cubecobra:modovintage"

    def test_color_category_override(self, cubecobra_v2_json_file: Path):
        cube = parse_cube(cubecobra_v2_json_file)
        bloodghast = next(c for c in cube["cards"] if c["name"] == "Bloodghast")
        assert bloodghast["cube_color"] == "Black"

    def test_ignores_none_color_category(self, cubecobra_v2_json_file: Path):
        cube = parse_cube(cubecobra_v2_json_file)
        bolt = next(c for c in cube["cards"] if c["name"] == "Lightning Bolt")
        assert "cube_color" not in bolt

    def test_category_prefixes_list_triggers_commander_detection(self, tmp_path: Path):
        """CubeCobra's category_prefixes is usually a list; we must detect
        'Commander' inside it, not stringify the whole list."""
        path = tmp_path / "cc.json"
        path.write_text(
            json.dumps(
                {
                    "shortId": "cc",
                    "name": "Commander Cube",
                    "category_prefixes": ["Commander", "Vintage"],
                    "cards": {
                        "mainboard": [
                            {
                                "cardID": "atraxa-id",
                                "name": "Atraxa, Praetors' Voice",
                                "type_line": "Legendary Creature — Phyrexian Angel Horror",
                                "colors": ["W", "U", "B", "G"],
                                "details": {
                                    "name": "Atraxa, Praetors' Voice",
                                    "type_line": "Legendary Creature — Phyrexian Angel Horror",
                                },
                            },
                            {
                                "cardID": "bolt-id",
                                "name": "Lightning Bolt",
                                "type_line": "Instant",
                                "colors": ["R"],
                                "details": {
                                    "name": "Lightning Bolt",
                                    "type_line": "Instant",
                                },
                            },
                        ],
                        "maybeboard": [],
                    },
                }
            )
        )
        cube = parse_cube(path)
        cmd_names = [c["name"] for c in cube.get("commander_pool", [])]
        assert "Atraxa, Praetors' Voice" in cmd_names
        # Non-legendary stays in main
        card_names = [c["name"] for c in cube["cards"]]
        assert "Lightning Bolt" in card_names
        assert "Atraxa, Praetors' Voice" not in card_names


class TestParseDeckJSON:
    def test_reshapes_deck_to_cube(self, deck_json_file: Path):
        cube = parse_cube(deck_json_file)
        names = [c["name"] for c in cube["cards"]]
        assert "Atraxa, Praetors' Voice" in names
        assert "Sol Ring" in names
        assert cube["total_cards"] == 3


class TestCLIInterface:
    def test_help_works(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Parse a cube" in result.output

    def test_writes_to_output_file(self, plain_cube_file: Path, tmp_path: Path):
        runner = CliRunner()
        out = tmp_path / "cube.json"
        result = runner.invoke(main, [str(plain_cube_file), "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert "Full JSON:" in result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["cube_format"] == "vintage"
        assert data["total_cards"] == 7

    def test_refuses_overwrite(self, plain_cube_file: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, [str(plain_cube_file), "--output", str(plain_cube_file)]
        )
        assert result.exit_code != 0
        assert "overwrite" in result.output.lower()

    def test_format_override_via_cli(self, plain_cube_file: Path, tmp_path: Path):
        runner = CliRunner()
        out = tmp_path / "cube.json"
        result = runner.invoke(
            main,
            [str(plain_cube_file), "--cube-format", "pauper", "--output", str(out)],
        )
        assert result.exit_code == 0
        data = json.loads(out.read_text())
        assert data["cube_format"] == "pauper"
