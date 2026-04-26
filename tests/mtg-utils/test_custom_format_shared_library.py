"""Tests for the shared-library format module."""

from __future__ import annotations

import random

from mtg_utils._custom_format import shared_library
from mtg_utils._custom_format._common import precompute_metadata

BASIC_NAMES = ("Plains", "Island", "Swamp", "Mountain", "Forest")


def _stub_cube(n_nonlands=80):
    """Generate a synthetic 80-nonland + 20-land cube for setup tests."""
    hydrated = []
    for color in ["W", "U", "B", "R", "G"]:
        for i in range(n_nonlands // 5):
            hydrated.append(
                {
                    "name": f"{color}{i}",
                    "type_line": "Creature — Beast",
                    "oracle_text": "",
                    "mana_cost": f"{{{color}}}",
                    "cmc": (i % 5) + 1,
                    "color_identity": [color],
                    "produced_mana": [],
                }
            )
    for color in ["W", "U", "B", "R", "G"]:
        for i in range(4):
            hydrated.append(
                {
                    "name": f"{color}-Land-{i}",
                    "type_line": "Land",
                    "oracle_text": f"({{T}}: Add {{{color}}}.)",
                    "mana_cost": "",
                    "cmc": 0,
                    "color_identity": [color],
                    "produced_mana": [color],
                }
            )
    return hydrated


class TestSharedLibrarySetup:
    def test_default_constants(self):
        assert shared_library.DEFAULT_PLAYERS == 4
        assert shared_library.DEFAULT_TURNS == 10
        assert shared_library.SUPPORTS_ARCHETYPES is True
        assert shared_library.MARKETPLACE_SIZE_BY_PLAYERS == {3: 5, 4: 6, 5: 7}

    def test_setup_creates_4_players_with_5_basics(self):
        hydrated = _stub_cube()
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        assert len(state.players) == 4
        for p in state.players:
            assert len(p.hand) == 5
            # Indices 0..4 are basics by convention.
            assert sorted(p.hand) == [0, 1, 2, 3, 4]

    def test_setup_marketplace_has_6_cards_for_4_players(self):
        hydrated = _stub_cube()
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        assert len(state.marketplace) == 6

    def test_setup_marketplace_has_min_2_nonlands(self):
        # Force the synthetic cube to be land-heavy and verify the redeal rule.
        hydrated = _stub_cube(n_nonlands=10)  # only 10 nonlands among 30 cards
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        # Cube indices start at 5 (basics are 0..4). marketplace contents are
        # cube indices.
        nonlands = [
            i
            for i in state.marketplace
            if not meta[i - len(shared_library.BASIC_METADATA)].is_land
        ]
        assert len(nonlands) >= 2

    def test_setup_initial_seat_and_turn(self):
        hydrated = _stub_cube()
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        assert state.active_seat == 0
        assert state.turn == 1

    def test_basic_metadata_has_5_basics(self):
        bm = shared_library.BASIC_METADATA
        assert len(bm) == 5
        names = [m.name for m in bm]
        assert names == list(BASIC_NAMES)
        for m in bm:
            assert m.is_land is True
            assert len(m.produced_mana) == 1


class TestSharedLibraryRunTurn:
    def test_runs_full_round_advances_turn_counter(self):
        hydrated = _stub_cube()
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        # 4 turns advances 4 seats; turn counter ticks every full round.
        for _ in range(4):
            shared_library.run_turn(
                state,
                cube_metadata=meta,
                basic_metadata=shared_library.BASIC_METADATA,
                rng=rng,
            )
        assert state.turn == 2
        assert state.active_seat == 0

    def test_marketplace_refills_to_size_after_pick(self):
        hydrated = _stub_cube()
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        size_before = len(state.marketplace)
        shared_library.run_turn(
            state,
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
        )
        # Either picked from marketplace or blind-drew. Either way, after end
        # step, marketplace refills to size 6.
        assert len(state.marketplace) == size_before

    def test_terminal_at_max_turns(self):
        state = shared_library.setup(
            cube_metadata=precompute_metadata(_stub_cube(), presets=[]),
            basic_metadata=shared_library.BASIC_METADATA,
            rng=random.Random(0),
            n_players=4,
        )
        state.turn = 11
        assert shared_library.is_terminal(state, max_turns=10) is True

    def test_terminal_when_library_exhausted(self):
        state = shared_library.setup(
            cube_metadata=precompute_metadata(_stub_cube(), presets=[]),
            basic_metadata=shared_library.BASIC_METADATA,
            rng=random.Random(0),
            n_players=4,
        )
        state.library = []
        state.marketplace = []
        assert shared_library.is_terminal(state, max_turns=100) is True


class TestColorScrewTracking:
    def test_color_screw_increments_after_off_color_held_card(self):
        """Player picks up an off-color marketplace card; should be screwed.

        Setup: cube of only {B} (Swamp-cost) nonlands. Player has all 5
        basics in hand from setup, so on turn 1 they play one basic.
        After picking up a {B} card from marketplace, they have:
        - 4 basics in hand (all 5 colors covered)
        - 1 basic in play (one color)
        - {B} spell in hand (uncastable until they play Swamp)

        On turn 1 the basic played is index 0 = Plains (W). The {B} spell
        in hand can't be cast → color-screw flag fires.
        """
        hydrated = []
        for i in range(40):
            hydrated.append(
                {
                    "name": f"BlackSpell{i}",
                    "type_line": "Creature — Zombie",
                    "oracle_text": "",
                    "mana_cost": "{B}",
                    "cmc": 1,
                    "color_identity": ["B"],
                    "produced_mana": [],
                }
            )
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        # Run a couple of full rounds; players will accumulate {B} cards
        # in hand and play one basic per turn — the basic in play won't
        # produce {B} until they happen to play their Swamp.
        for _ in range(8):  # 2 full rounds
            shared_library.run_turn(
                state,
                cube_metadata=meta,
                basic_metadata=shared_library.BASIC_METADATA,
                rng=rng,
            )
        # Each player held {B} spells they couldn't cast for at least one
        # turn (until they played Swamp). At least one player must have
        # been color-screwed.
        total_screws = sum(state.metrics.times_color_screwed)
        assert total_screws > 0, (
            f"expected color-screw events, got {state.metrics.times_color_screwed}"
        )

    def test_color_screw_zero_when_all_colors_available(self):
        """Player has all 5 basics in play covering all colors; no screw."""
        # Custom: every nonland is colorless (matches any color pool).
        hydrated = []
        for i in range(40):
            hydrated.append(
                {
                    "name": f"Colorless{i}",
                    "type_line": "Artifact",
                    "oracle_text": "",
                    "mana_cost": f"{{{i % 3 + 1}}}",  # generic 1, 2, or 3
                    "cmc": (i % 3) + 1,
                    "color_identity": [],
                    "produced_mana": [],
                }
            )
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(0)
        state = shared_library.setup(
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
        )
        for _ in range(8):
            shared_library.run_turn(
                state,
                cube_metadata=meta,
                basic_metadata=shared_library.BASIC_METADATA,
                rng=rng,
            )
        # Colorless spells with no color_identity are always on-color.
        total_screws = sum(state.metrics.times_color_screwed)
        assert total_screws == 0, (
            f"expected zero color-screws for colorless cube, "
            f"got {state.metrics.times_color_screwed}"
        )


class TestRegistry:
    def test_registry_contains_shared_library(self):
        from mtg_utils._custom_format import FORMAT_REGISTRY

        assert "shared_library" in FORMAT_REGISTRY
        assert FORMAT_REGISTRY["shared_library"].DEFAULT_PLAYERS == 4


class TestSimulateGame:
    def test_one_game_runs_to_completion(self):
        from mtg_utils._custom_format import shared_library
        from mtg_utils._custom_format._common import simulate_one_game

        hydrated = _stub_cube(n_nonlands=80)
        meta = precompute_metadata(hydrated, presets=[])
        rng = random.Random(7)
        metrics = simulate_one_game(
            shared_library,
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            rng=rng,
            n_players=4,
            max_turns=5,
        )
        # 4 players x 5 turns = 20 turns recorded.
        n_lands_recorded = sum(len(d) for d in metrics.lands_in_play_by_turn)
        assert n_lands_recorded > 0
        # Every player has nonneg picks/draws.
        for p in range(4):
            assert metrics.marketplace_picks[p] + metrics.blind_draws[p] > 0


class TestRunSimulation:
    def test_runs_n_games_returns_aggregated(self):
        from mtg_utils._custom_format import shared_library
        from mtg_utils._custom_format._common import run_simulation

        hydrated = _stub_cube(n_nonlands=80)
        meta = precompute_metadata(hydrated, presets=[])
        result = run_simulation(
            shared_library,
            cube_metadata=meta,
            basic_metadata=shared_library.BASIC_METADATA,
            archetype_names=[],
            n_players=4,
            max_turns=5,
            n_games=10,
            base_seed=1,
        )
        assert "per_archetype" in result
        assert "marketplace_dynamics" in result
        assert "per_player_mana" in result
