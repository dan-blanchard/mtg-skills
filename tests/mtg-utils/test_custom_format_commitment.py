"""Tests for the archetype-commitment heuristic."""

from __future__ import annotations

from mtg_utils._custom_format._common import (
    GameState,
    PerGameMetrics,
    Player,
    commitment_check,
)


class TestCommitmentCheck:
    def test_empty_pile_no_commit(self):
        assert commitment_check({}, pile_size=0) is None

    def test_below_min_count_no_commit(self):
        # 1 reanimate card in a 1-card pile: 100% but only 1 card.
        assert commitment_check({"reanimate": 1}, pile_size=1) is None

    def test_meets_threshold_commits(self):
        # 2 of 2 reanimate.
        assert commitment_check({"reanimate": 2}, pile_size=2) == "reanimate"

    def test_exact_40_percent_commits(self):
        # 2 of 5 = 40%.
        assert commitment_check({"reanimate": 2}, pile_size=5) == "reanimate"

    def test_below_40_percent_no_commit(self):
        # 2 of 6 = 33%.
        assert commitment_check({"reanimate": 2}, pile_size=6) is None

    def test_picks_highest_count_when_two_qualify(self):
        # reanimate 3/5 (60%), self-mill 2/5 (40%) — both qualify; pick highest.
        result = commitment_check(
            {"reanimate": 3, "self-mill": 2},
            pile_size=5,
        )
        assert result == "reanimate"

    def test_tie_breaks_alphabetically(self):
        # Both at 2/5 — deterministic tiebreak: alphabetical.
        result = commitment_check(
            {"reanimate": 2, "removal": 2},
            pile_size=5,
        )
        assert result == "reanimate"


class TestStateTypes:
    def test_default_construction(self):
        s = GameState()
        assert s.turn == 1
        assert s.active_seat == 0
        assert s.players == []
        assert isinstance(s.metrics, PerGameMetrics)

    def test_player_known_colors_empty(self):
        from mtg_utils._custom_format._common import CardMetadata, LibraryEffect

        meta = [
            CardMetadata(
                name="Mountain",
                cmc=0,
                color_identity=frozenset({"R"}),
                produced_mana=("R",),
                is_land=True,
                library_effect=LibraryEffect.NONE,
                archetype_matches=frozenset(),
            )
        ]
        p = Player(seat=0, hand=[0])
        assert p.known_colors(meta) == frozenset({"R"})
