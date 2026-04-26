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
    Zone,
    choose_library_target,
    choose_pick,
    commitment_check,
    lookup_card,
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


# ---------------------------------------------------------------------------
# Turn loop
# ---------------------------------------------------------------------------


def is_terminal(state: GameState, *, max_turns: int) -> bool:
    """Stop when we've run max_turns OR the library is exhausted."""
    if state.turn > max_turns:
        return True
    return not state.library and not state.marketplace


def _refill_marketplace(state: GameState, *, target_size: int) -> None:
    """Move cards from the top of the library into the marketplace until full."""
    while len(state.marketplace) < target_size and state.library:
        state.marketplace.append(state.library.pop(0))


def _player_color_pool(
    player: Player,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...],
) -> frozenset[str]:
    """Aggregate produced-mana colors across the player's lands in play."""
    colors: set[str] = set()
    for idx in player.lands_in_play:
        colors |= set(
            lookup_card(
                idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
            ).produced_mana
        )
    return frozenset(colors)


def _build_marketplace_view(
    state: GameState,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...],
) -> list[CardMetadata]:
    """Materialize the marketplace as a list of CardMetadata for choose_pick."""
    return [
        lookup_card(idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata)
        for idx in state.marketplace
    ]


def _record_archetype_match(
    state: GameState,
    seat: int,
    card_meta: CardMetadata,
) -> None:
    """Record a card joining a player's pile.

    Updates pile_size, pile_archetype_counts, and first_enabler_turn
    (recorded once per archetype the first time a matching card lands).
    """
    player = state.players[seat]
    player.pile_size += 1
    for archetype in card_meta.archetype_matches:
        prior = player.pile_archetype_counts.get(archetype, 0)
        player.pile_archetype_counts[archetype] = prior + 1
        if prior == 0:
            # First enabler for this archetype in this player's pile.
            state.metrics.first_enabler_turn[seat][archetype] = state.turn


def _do_draw_step(
    state: GameState,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...],
) -> None:
    """Active player picks from marketplace or blind-draws."""
    player = state.players[state.active_seat]
    market_view = _build_marketplace_view(
        state, cube_metadata=cube_metadata, basic_metadata=basic_metadata
    )
    color_pool = _player_color_pool(
        player, cube_metadata=cube_metadata, basic_metadata=basic_metadata
    )
    pick = choose_pick(
        market_view,
        committed=player.committed_archetype,
        available_mana=len(player.lands_in_play),
        available_colors=color_pool,
    )
    drew_idx: int | None = None
    if pick.kind == "marketplace" and pick.card_index is not None:
        drew_idx = state.marketplace.pop(pick.card_index)
        player.hand.append(drew_idx)
        state.metrics.marketplace_picks[state.active_seat] += 1
    elif state.library:
        drew_idx = state.library.pop(0)
        player.hand.append(drew_idx)
        state.metrics.blind_draws[state.active_seat] += 1

    if drew_idx is not None:
        card_meta = lookup_card(
            drew_idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
        )
        _record_archetype_match(state, state.active_seat, card_meta)
        # Re-check commitment after every acquired card (pick OR blind draw).
        if player.committed_archetype is None:
            player.committed_archetype = commitment_check(
                player.pile_archetype_counts, pile_size=player.pile_size
            )
            if player.committed_archetype is not None:
                state.metrics.committed_archetype[state.active_seat] = (
                    player.committed_archetype
                )


def _resolve_library_effect(
    state: GameState,
    effect: LibraryEffect,
    zone: Zone,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...],
) -> None:
    """Mutate state per Silver-model effect rules."""
    if effect in (LibraryEffect.PEEK, LibraryEffect.REORDER):
        return  # No state change in v1.

    if effect == LibraryEffect.MILL:
        # Self-mill: top 1 of draw pile to graveyard.
        if state.library:
            state.graveyard.append(state.library.pop(0))
            state.metrics.cards_milled += 1
        return

    if effect in (LibraryEffect.DISCARD, LibraryEffect.EXILE):
        if zone == Zone.MARKETPLACE and state.marketplace:
            # Pick the highest-CMC nonland card to deny. If marketplace
            # holds only lands, fall through to the draw-pile branch rather
            # than denying a land (which would contradict the denial intent).
            best_pos: int | None = None
            best_cmc = -1
            for pos, idx in enumerate(state.marketplace):
                card = lookup_card(
                    idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
                )
                if card.is_land:
                    continue
                if card.cmc > best_cmc:
                    best_cmc = card.cmc
                    best_pos = pos
            if best_pos is not None:
                removed = state.marketplace.pop(best_pos)
                if effect == LibraryEffect.EXILE:
                    state.exile.append(removed)
                    state.metrics.marketplace_cards_exiled += 1
                else:
                    state.graveyard.append(removed)
                    state.metrics.marketplace_cards_discarded += 1
                return
        # Either zone == DRAW_PILE, marketplace was empty, or marketplace
        # had only lands. Peel one card from the draw pile.
        if state.library:
            taken = state.library.pop(0)
            if effect == LibraryEffect.EXILE:
                state.exile.append(taken)
            else:
                state.graveyard.append(taken)


def _play_main_phase(
    state: GameState,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...],
) -> None:
    """Play one land if available; cast as many spells as mana permits.

    For each cast spell with a library effect, apply the effect against the
    chosen zone (marketplace vs draw pile).
    """
    player = state.players[state.active_seat]

    # Play a land if hand has any (greedy: first land found).
    land_in_hand: int | None = None
    for h_idx in player.hand:
        card = lookup_card(
            h_idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
        )
        if card.is_land:
            land_in_hand = h_idx
            break
    if land_in_hand is not None:
        player.hand.remove(land_in_hand)
        player.lands_in_play.append(land_in_hand)

    color_pool = _player_color_pool(
        player, cube_metadata=cube_metadata, basic_metadata=basic_metadata
    )
    available_mana = len(player.lands_in_play)

    # Try to cast spells in ascending CMC order. Track color-screw events
    # for the metric: any held nonland whose color identity isn't covered
    # by the player's land pool is "uncastable due to color."
    castable: list[tuple[int, int]] = []  # (cmc, hand_idx)
    color_screwed_this_turn = False
    for h_idx in player.hand:
        card = lookup_card(
            h_idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
        )
        if card.is_land:
            continue
        if not card.color_identity.issubset(color_pool):
            color_screwed_this_turn = True
            continue
        castable.append((card.cmc, h_idx))
    if color_screwed_this_turn:
        state.metrics.times_color_screwed[state.active_seat] += 1
    castable.sort()

    cast_this_turn: list[int] = []
    for cmc, h_idx in castable:
        if cmc > available_mana:
            break
        # Cast the spell.
        cast_this_turn.append(h_idx)
        available_mana -= cmc
        card = lookup_card(
            h_idx, cube_metadata=cube_metadata, basic_metadata=basic_metadata
        )
        # Apply library effect, if any. SEARCH (tutors) is format-disallowed
        # in shared-library; we skip both the metric and the no-op resolve.
        if card.library_effect not in (LibraryEffect.NONE, LibraryEffect.SEARCH):
            state.metrics.library_effects_cast[state.active_seat] += 1
            target_zone = choose_library_target(
                card.library_effect,
                marketplace=_build_marketplace_view(
                    state, cube_metadata=cube_metadata, basic_metadata=basic_metadata
                ),
            )
            _resolve_library_effect(
                state,
                card.library_effect,
                target_zone,
                cube_metadata=cube_metadata,
                basic_metadata=basic_metadata,
            )

    for h_idx in cast_this_turn:
        player.hand.remove(h_idx)
        player.battlefield.append(h_idx)


def run_turn(
    state: GameState,
    *,
    cube_metadata: list[CardMetadata],
    basic_metadata: tuple[CardMetadata, ...] = BASIC_METADATA,
    rng: random.Random,  # noqa: ARG001 — kept for format-module signature uniformity (turn loop is deterministic in v1)
) -> None:
    """Advance one turn for the active player; mutate state in place."""
    n_players = len(state.players)
    market_size = MARKETPLACE_SIZE_BY_PLAYERS[n_players]

    _do_draw_step(state, cube_metadata=cube_metadata, basic_metadata=basic_metadata)
    _play_main_phase(state, cube_metadata=cube_metadata, basic_metadata=basic_metadata)

    # End step: refill marketplace.
    _refill_marketplace(state, target_size=market_size)

    # Per-turn telemetry for the active player.
    seat = state.active_seat
    state.metrics.lands_in_play_by_turn[seat][state.turn] = len(
        state.players[seat].lands_in_play
    )
    state.metrics.mana_available_by_turn[seat][state.turn] = len(
        state.players[seat].lands_in_play
    )

    # Advance seat / turn.
    state.active_seat = (state.active_seat + 1) % n_players
    if state.active_seat == 0:
        state.turn += 1
