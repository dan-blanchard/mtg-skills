"""The limited readouts: what a set holds, and what a pool supports per colour pair."""

import json

from click.testing import CliRunner

from mtg_utils.set_scan import (
    pool_color_pairs,
    pool_colors_main,
    render_color_pairs,
    render_set_scan,
    set_scan,
    set_scan_main,
)
from mtg_utils.testkit import test_card, test_card_ir

# Real structural reads: removal / sweepers are template roles over the Card IR
# (ADR-0051), so they need a real oracle_id — seeded from the committed snapshot.
test_card_ir("Murder")
test_card_ir("Wrath of God")
MURDER = {**test_card("Murder"), "rarity": "common", "set": "hob"}
WRATH = {**test_card("Wrath of God"), "rarity": "rare", "set": "hob"}


def _creature(
    name, power, toughness, *, keywords=(), colors=(), rarity="common", cmc=3
):
    return {
        "name": name,
        "type_line": "Creature — Beast",
        "oracle_text": "",
        "cmc": float(cmc),
        "power": str(power),
        "toughness": str(toughness),
        "keywords": list(keywords),
        "color_identity": list(colors),
        "rarity": rarity,
        "set": "hob",
    }


FLYER = _creature("Eagle", 4, 3, keywords=["Flying"], colors=["W"], rarity="uncommon")
WALL = _creature("Wall", 0, 7, colors=["G"], cmc=2)
TROLL = _creature(
    "Troll", 6, 6, keywords=["Trample"], colors=["G"], rarity="rare", cmc=5
)
BEAR = _creature("Bear", 2, 2, colors=["G"], cmc=2)
FOREST = {
    "name": "Forest",
    "type_line": "Basic Land — Forest",
    "oracle_text": "",
    "cmc": 0.0,
    "keywords": [],
    "color_identity": ["G"],
    "rarity": "common",
    "set": "hob",
}
RECORDS = [MURDER, WRATH, FLYER, WALL, TROLL, BEAR, FOREST]


def test_set_scan_counts_answers_evasion_and_bodies():
    scan = set_scan(RECORDS, code="hob")
    assert scan["code"] == "HOB"
    assert scan["size"] == 7
    assert scan["removal"]["total"] == 2  # Murder + Wrath both interact
    assert scan["removal"]["by_rarity"]["common"] == 1
    assert scan["removal"]["by_rarity"]["rare"] == 1
    assert scan["sweepers"] == ["Wrath of God"]
    assert scan["creatures"] == 4
    assert scan["evasion"] == {"total": 2, "by_keyword": {"Flying": 1, "Trample": 1}}
    assert scan["toughness_6_plus"] == 2  # Wall (7) and Troll (6)
    assert [b["name"] for b in scan["biggest_bodies"]["by_toughness"][:2]] == [
        "Wall",
        "Troll",
    ]
    assert scan["biggest_bodies"]["by_power"][0]["name"] == "Troll"
    assert scan["curve"]["2"] == 2  # Wall + Bear; the Forest never curves
    text = render_set_scan(scan)
    assert "Sweepers: Wrath of God" in text


def test_pool_color_pairs_counts_copies_and_ranks_pairs():
    rows = pool_color_pairs(
        [(FLYER, 1), (TROLL, 1), (BEAR, 3), (MURDER, 2), (FOREST, 17)]
    )
    by_pair = {r["pair"]: r for r in rows}
    # Green: three Bears + a Troll (copies count); the Murder is black.
    assert by_pair["G"]["playables"] == 4
    assert by_pair["G"]["creatures"] == 4
    assert by_pair["G"]["power_4_plus"] == 1
    assert by_pair["G"]["rares"] == 1
    assert by_pair["BG"]["playables"] == 6
    assert by_pair["BG"]["removal"] == 2
    assert by_pair["WG"]["evasion"] == 2  # the flyer and the trampler
    assert by_pair["W"]["playables"] == 1
    # Ranked by playables: the pairs that hold green lead.
    assert rows[0]["pair"] == "BG"
    assert rows[0]["playables"] >= rows[1]["playables"]
    assert len(rows) == 15
    assert "BG" in render_color_pairs(rows)


def test_clis(tmp_path):
    bulk = tmp_path / "bulk.json"
    bulk.write_text(
        json.dumps(
            [
                {
                    **r,
                    "id": f"id-{r['name']}",
                    "oracle_id": r.get("oracle_id", r["name"]),
                    "layout": "normal",
                    "collector_number": str(i),
                }
                for i, r in enumerate(RECORDS)
            ]
        )
    )
    res = CliRunner().invoke(
        set_scan_main, ["--set", "HOB", "--bulk-data", str(bulk), "--json"]
    )
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["size"] == 7
    missing = CliRunner().invoke(
        set_scan_main, ["--set", "ZZZ", "--bulk-data", str(bulk)]
    )
    assert missing.exit_code != 0
    deck = tmp_path / "pool.json"
    deck.write_text(
        json.dumps(
            {
                "format": "sealed",
                "commanders": [],
                "cards": [],
                "sideboard": [],
                "pool": [
                    {"name": "Bear", "quantity": 2},
                    {"name": "Murder", "quantity": 1},
                ],
            }
        )
    )
    res = CliRunner().invoke(
        pool_colors_main, [str(deck), "--bulk-data", str(bulk), "--json"]
    )
    assert res.exit_code == 0, res.output
    rows = {r["pair"]: r for r in json.loads(res.output)}
    assert rows["BG"]["playables"] == 3
