"""Tests for the heuristic cube drafter."""

from __future__ import annotations

from mtg_utils._draft_ai import DrafterState, score_pick


def _c(name, ci, cmc, type_line="Creature"):
    return {
        "name": name,
        "color_identity": list(ci),
        "cmc": cmc,
        "type_line": type_line,
        "mana_cost": "{" + ci[0] + "}" if ci else "",
        "oracle_text": "",
        "power": "2",
        "toughness": "2",
        "produced_mana": [],
    }


class TestScorePick:
    def test_first_picks_use_raw_power(self):
        state = DrafterState()
        bomb = _c("Bomb", "U", 4)
        chaff = _c("Chaff", "U", 1)
        bomb_score = score_pick(bomb, state)
        chaff_score = score_pick(chaff, state)
        assert bomb_score >= chaff_score

    def test_after_pick_3_color_commitment_kicks_in(self):
        state = DrafterState()
        # Take three blue cards.
        for _ in range(3):
            state.add_pick(_c("BlueX", "U", 2))
        on_color = _c("BlueY", "U", 2)
        off_color = _c("RedY", "R", 2)
        s_on = score_pick(on_color, state)
        s_off = score_pick(off_color, state)
        assert s_on > s_off

    def test_open_signal_rewards_passed_colors(self):
        state = DrafterState()
        # Pretend pack 1 had 4 reds passed by upstream.
        state.note_passed_colors(["R", "R", "R", "R"])
        red = _c("RedY", "R", 2)
        green = _c("GreenY", "G", 2)
        # Both off-color from our pile (empty pile), but red is being passed.
        s_red = score_pick(red, state)
        s_green = score_pick(green, state)
        assert s_red > s_green
