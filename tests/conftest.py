"""Suite-wide test settings, shared by every skill's tests."""

import os

# An installed MTG Arena must never change a test: its card database would decide
# wildcard rarities (``mtg_utils.arena_card_db``). A test that wants one points
# ``MTG_SKILLS_ARENA_CARD_DB`` at a fixture database with ``monkeypatch.setenv``.
os.environ["MTG_SKILLS_ARENA_CARD_DB"] = "none"
