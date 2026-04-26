"""Tests for cross-game aggregation."""

from __future__ import annotations

from mtg_utils._custom_format._common import PerGameMetrics, aggregate_runs


def _per_game(
    *,
    picks_by_player,
    drawn_by_player,
    committed,
    piles,
    lib_casts,
    exiled=0,
    discarded=0,
    milled=0,
    lands_t4=None,
):
    """Build a synthetic PerGameMetrics for testing."""
    n = len(picks_by_player)
    m = PerGameMetrics()
    m.marketplace_picks = list(picks_by_player)
    m.blind_draws = list(drawn_by_player)
    m.library_effects_cast = list(lib_casts)
    m.pile_archetype_counts = list(piles)
    m.committed_archetype = list(committed)
    m.marketplace_cards_exiled = exiled
    m.marketplace_cards_discarded = discarded
    m.cards_milled = milled
    if lands_t4 is None:
        lands_t4 = [4] * n
    m.lands_in_play_by_turn = [{4: cnt} for cnt in lands_t4]
    m.mana_available_by_turn = [{4: cnt} for cnt in lands_t4]
    m.times_color_screwed = [0] * n
    m.first_enabler_turn = [{} for _ in range(n)]
    return m


class TestAggregateRuns:
    def test_assembly_rate_zero_when_no_archetype_assembled(self):
        # All players committed but pile counts < 4 each → not assembled.
        games = [
            _per_game(
                picks_by_player=[1, 1, 1, 1],
                drawn_by_player=[5, 5, 5, 5],
                committed=["reanimate", None, None, None],
                piles=[{"reanimate": 2}, {}, {}, {}],
                lib_casts=[0, 0, 0, 0],
            ),
        ]
        out = aggregate_runs(games, archetype_names=["reanimate"], max_turns=10)
        assert out["per_archetype"]["reanimate"]["assembly_rate"] == 0.0

    def test_assembly_rate_one_when_a_player_has_4_plus(self):
        games = [
            _per_game(
                picks_by_player=[5, 5, 5, 5],
                drawn_by_player=[1, 1, 1, 1],
                committed=["reanimate", None, None, None],
                piles=[{"reanimate": 4}, {}, {}, {}],
                lib_casts=[0, 0, 0, 0],
            ),
        ]
        out = aggregate_runs(games, archetype_names=["reanimate"], max_turns=10)
        assert out["per_archetype"]["reanimate"]["assembly_rate"] == 1.0

    def test_marketplace_utilization(self):
        games = [
            _per_game(
                picks_by_player=[3, 3, 3, 3],  # 12 picks
                drawn_by_player=[1, 1, 1, 1],  # 4 blind draws
                committed=[None] * 4,
                piles=[{}] * 4,
                lib_casts=[0] * 4,
            ),
        ]
        out = aggregate_runs(games, archetype_names=[], max_turns=10)
        # 12/(12+4) = 0.75
        assert out["marketplace_dynamics"]["utilization_rate"] == 0.75

    def test_exile_count_per_game_average(self):
        games = [
            _per_game(
                picks_by_player=[1] * 4,
                drawn_by_player=[1] * 4,
                committed=[None] * 4,
                piles=[{}] * 4,
                lib_casts=[0] * 4,
                exiled=8,
            ),
            _per_game(
                picks_by_player=[1] * 4,
                drawn_by_player=[1] * 4,
                committed=[None] * 4,
                piles=[{}] * 4,
                lib_casts=[0] * 4,
                exiled=4,
            ),
        ]
        out = aggregate_runs(games, archetype_names=[], max_turns=10)
        assert out["marketplace_dynamics"]["exiled_per_game"] == 6.0

    def test_reaches_4_mana_by_t4(self):
        games = [
            _per_game(
                picks_by_player=[1] * 4,
                drawn_by_player=[1] * 4,
                committed=[None] * 4,
                piles=[{}] * 4,
                lib_casts=[0] * 4,
                lands_t4=[4, 4, 3, 4],
            ),  # 3 of 4 reach 4 mana
        ]
        out = aggregate_runs(games, archetype_names=[], max_turns=10)
        assert out["per_player_mana"]["reaches_4_mana_by_t4"] == 0.75
