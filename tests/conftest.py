"""Suite-wide test settings, shared by every skill's tests."""

import os
import socket

import pytest

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


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "testserver", ""})
_real_getaddrinfo = socket.getaddrinfo


def _no_network_getaddrinfo(host, *args, **kwargs):
    if host is None or (isinstance(host, str) and host in _LOCAL_HOSTS):
        return _real_getaddrinfo(host, *args, **kwargs)
    msg = (
        f"test tried to reach {host!r}: tests make no real network calls "
        "(CLAUDE.md Testing) — mock the fetch or add the card to the fixture data"
    )
    raise RuntimeError(msg)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every test runs offline. A hidden network call (a Scryfall fallback on a
    fixture miss) otherwise passes while the service answers and fails CI when it
    rate-limits; refusing name resolution makes it fail loudly everywhere."""
    monkeypatch.setattr(socket, "getaddrinfo", _no_network_getaddrinfo)
