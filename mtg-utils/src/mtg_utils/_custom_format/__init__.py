"""Custom-format cube simulators.

Each format is its own module exporting setup() / run_turn() / is_terminal()
and constants DEFAULT_PLAYERS / DEFAULT_TURNS / SUPPORTS_ARCHETYPES.
``FORMAT_REGISTRY`` maps format name → module so the CLI can dispatch.
"""

from __future__ import annotations

from mtg_utils._custom_format import shared_library

FORMAT_REGISTRY = {
    "shared_library": shared_library,
}
