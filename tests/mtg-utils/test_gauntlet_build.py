"""Tests for the heuristic gauntlet deckbuilder."""

from __future__ import annotations

from mtg_utils._gauntlet_build import score_card


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
