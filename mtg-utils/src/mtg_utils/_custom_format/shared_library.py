"""Shared-library multiplayer cube format.

Players share one library split into a face-up marketplace and a hidden
draw pile. Each player starts with 5 basic lands in hand. Draw step picks
from marketplace OR blind-draws.
"""

from __future__ import annotations

import random

from mtg_utils._custom_format._common import (
    CardMetadata,
    GameState,
    LibraryEffect,
    Player,
)

DEFAULT_PLAYERS = 4
DEFAULT_TURNS = 10
SUPPORTS_ARCHETYPES = True

# Marketplace size = 2 + n_players (per format rules).
MARKETPLACE_SIZE_BY_PLAYERS = {3: 5, 4: 6, 5: 7}

# Minimum non-lands required in the initial marketplace; below this the
# format calls for a marketplace mulligan (reshuffle and redeal).
MIN_INITIAL_NONLANDS = 2

# Basic lands fixed in every player's opening hand.
BASIC_METADATA: tuple[CardMetadata, ...] = (
    CardMetadata(
        "Plains",
        0,
        frozenset({"W"}),
        ("W",),
        True,  # noqa: FBT003
        LibraryEffect.NONE,
        frozenset(),
    ),
    CardMetadata(
        "Island",
        0,
        frozenset({"U"}),
        ("U",),
        True,  # noqa: FBT003
        LibraryEffect.NONE,
        frozenset(),
    ),
    CardMetadata(
        "Swamp",
        0,
        frozenset({"B"}),
        ("B",),
        True,  # noqa: FBT003
        LibraryEffect.NONE,
        frozenset(),
    ),
    CardMetadata(
        "Mountain",
        0,
        frozenset({"R"}),
        ("R",),
        True,  # noqa: FBT003
        LibraryEffect.NONE,
        frozenset(),
    ),
    CardMetadata(
        "Forest",
        0,
        frozenset({"G"}),
        ("G",),
        True,  # noqa: FBT003
        LibraryEffect.NONE,
        frozenset(),
    ),
)
N_BASICS = len(BASIC_METADATA)


def setup(
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...] = BASIC_METADATA,
    rng: random.Random,
    n_players: int = DEFAULT_PLAYERS,
) -> GameState:
    """Initialize one game's state.

    Card-index convention: basics are 0..len(basic_metadata)-1; cube cards
    are len(basic_metadata)..N. The combined-index space lets the harness
    look up any card via a single list at the call site.
    """
    if n_players not in MARKETPLACE_SIZE_BY_PLAYERS:
        raise ValueError(
            f"shared_library supports {sorted(MARKETPLACE_SIZE_BY_PLAYERS)} "
            f"players, got {n_players}",
        )

    n_basics = len(basic_metadata)
    cube_first_index = n_basics
    cube_indices = list(range(cube_first_index, cube_first_index + len(cube_metadata)))

    market_size = MARKETPLACE_SIZE_BY_PLAYERS[n_players]

    # Marketplace mulligan loop: reshuffle until at least MIN_INITIAL_NONLANDS
    # non-lands appear in the marketplace.
    for _ in range(100):
        rng.shuffle(cube_indices)
        marketplace = list(cube_indices[:market_size])
        nonland_count = sum(
            1
            for idx in marketplace
            if not cube_metadata[idx - cube_first_index].is_land
        )
        if nonland_count >= MIN_INITIAL_NONLANDS:
            library = list(cube_indices[market_size:])
            break
    else:
        # Cube has too few nonlands; take what we have.
        library = list(cube_indices[market_size:])

    # Each player's hand is the 5 basics (indices 0..n_basics-1).
    players = [
        Player(seat=seat, hand=list(range(n_basics))) for seat in range(n_players)
    ]

    state = GameState(
        library=library,
        marketplace=marketplace,
        players=players,
        active_seat=0,
        turn=1,
    )
    # Pre-size per-player metric arrays so `run_turn` can index directly.
    state.metrics.marketplace_picks = [0] * n_players
    state.metrics.blind_draws = [0] * n_players
    state.metrics.library_effects_cast = [0] * n_players
    state.metrics.times_color_screwed = [0] * n_players
    state.metrics.lands_in_play_by_turn = [{} for _ in range(n_players)]
    state.metrics.mana_available_by_turn = [{} for _ in range(n_players)]
    state.metrics.pile_archetype_counts = [{} for _ in range(n_players)]
    state.metrics.committed_archetype = [None] * n_players
    state.metrics.first_enabler_turn = [{} for _ in range(n_players)]
    return state
