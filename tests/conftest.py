"""Suite-wide test settings, shared by every skill's tests."""

import os

# An installed MTG Arena must never change a test: its card database would decide
# wildcard rarities (``mtg_utils.arena_card_db``). A test that wants one points
# ``MTG_SKILLS_ARENA_CARD_DB`` at a fixture database with ``monkeypatch.setenv``.
os.environ["MTG_SKILLS_ARENA_CARD_DB"] = "none"


def pytest_configure(config):
    # A retirement canary guards a phase-misparse workaround that isn't an
    # ADR-0048 ledger row; ``bump-phase-pin``'s graduation step selects these by
    # marker and reports each one that fails RETIRE-READY (ADR-0049).
    config.addinivalue_line(
        "markers",
        "retirement_canary: fails '<name>: RETIRE-READY — …' once the phase "
        "misparse its workaround guards is gone",
    )
