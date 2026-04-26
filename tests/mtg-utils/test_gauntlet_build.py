"""Tests for the heuristic gauntlet deckbuilder."""

from __future__ import annotations

import importlib.resources
import json as _json

import pytest

from mtg_utils._gauntlet_build import BuildOutcome, build_gauntlet_deck, score_card


def _card(name, **kw):
    return {
        "name": name,
        "type_line": kw.get("type_line", ""),
        "oracle_text": kw.get("oracle_text", ""),
        "mana_cost": kw.get("mana_cost", ""),
        "cmc": kw.get("cmc", 0),
        "power": kw.get("power"),
        "toughness": kw.get("toughness"),
        "color_identity": kw.get("color_identity", []),
    }


class TestScoreCard:
    def test_aggro_rewards_cheap_creatures(self):
        c = _card(
            "Goblin Guide",
            type_line="Creature — Goblin",
            cmc=1,
            power="2",
            toughness="2",
            color_identity=["R"],
        )
        score = score_card(c, archetype="aggro", colors={"R"})
        assert score > 0

    def test_aggro_punishes_expensive_creatures(self):
        cheap = _card(
            "Goblin Guide",
            type_line="Creature — Goblin",
            cmc=1,
            power="2",
            toughness="2",
            color_identity=["R"],
        )
        big = _card(
            "Akroma, Angel of Wrath",
            type_line="Creature — Angel",
            cmc=8,
            power="6",
            toughness="6",
            color_identity=["W"],
        )
        s_cheap = score_card(cheap, archetype="aggro", colors={"R"})
        s_big = score_card(big, archetype="aggro", colors={"W"})
        assert s_cheap > s_big

    def test_control_rewards_counters(self):
        counter = _card(
            "Counterspell",
            type_line="Instant",
            oracle_text="Counter target spell.",
            cmc=2,
            color_identity=["U"],
        )
        bear = _card(
            "Grizzly Bears",
            type_line="Creature — Bear",
            cmc=2,
            power="2",
            toughness="2",
            color_identity=["G"],
        )
        s_counter = score_card(counter, archetype="control", colors={"U"})
        s_bear = score_card(bear, archetype="control", colors={"G"})
        assert s_counter > s_bear

    def test_off_color_returns_negative_or_zero(self):
        c = _card(
            "Goblin Guide",
            type_line="Creature — Goblin",
            cmc=1,
            power="2",
            toughness="2",
            color_identity=["R"],
        )
        score = score_card(c, archetype="aggro", colors={"U"})
        assert score <= 0


def _make_card(name, cmc=2, mana_cost="{R}", color_identity=("R",), produces=()):
    return {
        "name": name,
        "type_line": "Creature — Goblin",
        "oracle_text": "",
        "mana_cost": mana_cost,
        "cmc": cmc,
        "power": "2",
        "toughness": "2",
        "color_identity": list(color_identity),
        "produced_mana": list(produces),
    }


def _mountain():
    return {
        "name": "Mountain",
        "type_line": "Basic Land — Mountain",
        "oracle_text": "({T}: Add {R}.)",
        "mana_cost": "",
        "cmc": 0,
        "color_identity": ["R"],
        "produced_mana": ["R"],
    }


class TestBuildGauntletDeck:
    def test_builds_40_card_deck_with_lands(self):
        # Cube: 40 red one-drops + 30 mountains.
        cube_cards = [_make_card(f"Goblin{i}", cmc=1) for i in range(40)]
        cube_cards += [_mountain() for _ in range(30)]

        archetype_spec = {
            "name": "Aggro",
            "colors": ["R"],
            "preset": "aggro",
            "curve_target": {"1": 14, "2": 6, "3": 3},
        }
        out = build_gauntlet_deck(
            cube_cards,
            archetype_spec,
            deck_size=40,
            lands=17,
        )
        assert isinstance(out, BuildOutcome)
        assert out.status == "ok"
        assert len(out.deck["main"]) >= 1
        assert len(out.deck["main"]) <= 40
        total = sum(e["count"] for e in out.deck["main"])
        assert total == 40
        # 17 of the cards should be Mountains.
        mountains = next(e for e in out.deck["main"] if e["name"] == "Mountain")
        assert mountains["count"] == 17

    def test_reports_insufficient_when_pool_too_small(self):
        cube_cards = [_make_card("Goblin1", cmc=1)]  # only 1 nonland
        cube_cards += [_mountain() for _ in range(20)]
        archetype_spec = {
            "name": "Aggro",
            "colors": ["R"],
            "preset": "aggro",
            "curve_target": {"1": 14, "2": 6, "3": 3},
        }
        out = build_gauntlet_deck(
            cube_cards,
            archetype_spec,
            deck_size=40,
            lands=17,
        )
        assert out.status == "insufficient"
        assert "nonland" in out.reason.lower()


class TestManifests:
    @pytest.mark.parametrize("fmt", [
        "modern_cube", "vintage_cube", "legacy_cube",
        "pauper_cube", "peasant_cube", "commander_cube",
    ])
    def test_manifest_loads_and_has_required_fields(self, fmt):
        data = importlib.resources.files("mtg_utils.data.gauntlets") \
            .joinpath(f"{fmt}.json").read_text()
        m = _json.loads(data)
        assert m["format"] == fmt
        assert m["deck_size"] in (40, 60, 100)
        assert m["lands"] in (17, 24, 36)
        assert len(m["archetypes"]) >= 3
        for a in m["archetypes"]:
            assert {"name", "colors", "preset"}.issubset(a.keys())
            assert a["preset"] in {"aggro", "control", "midrange", "combo"}
