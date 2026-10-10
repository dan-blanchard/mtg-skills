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


@pytest.fixture(autouse=True)
def _no_arena_log(monkeypatch, tmp_path_factory):
    """No test reads this machine's real MTG Arena ``Player.log`` (the wildcard
    counts deck-forge seeds its budget from, the collection ``mtga-import``
    reads): every lookup of the platform log lands on a missing path. A test that
    wants a log monkeypatches ``player_log_path`` to its own file."""
    from mtg_utils import arena_card_db, mtga_import

    missing = tmp_path_factory.getbasetemp() / "no-arena" / "Player.log"
    monkeypatch.setattr(mtga_import, "player_log_path", lambda: missing)
    monkeypatch.setattr(arena_card_db, "player_log_path", lambda: missing)


@pytest.fixture(autouse=True)
def _known_tokens_cached_only(request, monkeypatch):
    """``_phase.ensure_known_tokens`` fetches phase's known-tokens.toml on a cold
    cache. In tests it answers from the cache or ``None`` (its offline contract, so
    the Card IR falls back to the committed subset) instead of reaching the
    network guard above. Here rather than in tests/mtg-utils/conftest.py because
    every skill's suite builds Card IR through ``mtg_utils.testkit``.
    ``test_phase_wrapper`` owns the real download tests (urllib mocked)."""
    if request.module.__name__ == "test_phase_wrapper":
        return
    from mtg_utils import _phase

    cached = _phase._known_tokens_path()
    monkeypatch.setattr(
        _phase, "ensure_known_tokens", lambda: cached if cached.exists() else None
    )


# The cache dir the run started with (CI points it at an empty dir; locally it is
# usually unset, i.e. the user's real ~/.cache/mtg-skills).
_OUTER_CACHE_DIR = os.environ.get("MTG_SKILLS_CACHE_DIR") or None


@pytest.fixture(autouse=True)
def _no_user_arena_meta(monkeypatch, tmp_path_factory):
    """The user's arena-meta cache must never change a test: a digital build's Find
    and Tune read ``untapped.meta_dir()`` (ADR-0059), so a cached ladder snapshot
    would reorder their candidates. Unless the test points ``MTG_SKILLS_CACHE_DIR``
    at its own dir (the meta tests do, then write their snapshot there), the meta
    and sign-in profile dirs resolve to a fresh empty dir of the test's own. Narrower
    than redirecting the whole cache root, which also holds the card data the
    local-only tests read."""
    from mtg_utils._arena_meta import untapped

    own: dict[str, object] = {}

    def isolated(real, sub: str):
        def resolve():
            if (os.environ.get("MTG_SKILLS_CACHE_DIR") or None) != _OUTER_CACHE_DIR:
                return real()  # the test chose its own cache dir
            if "root" not in own:
                own["root"] = tmp_path_factory.mktemp("untapped")
            return own["root"] / sub

        return resolve

    monkeypatch.setattr(untapped, "meta_dir", isolated(untapped.meta_dir, "meta"))
    monkeypatch.setattr(
        untapped, "profile_dir", isolated(untapped.profile_dir, "profile")
    )


@pytest.fixture
def meta_tiebreak_pair() -> tuple[dict, dict]:
    """``(staple, rogue)``: two synthetic candidates (machinery only, ADR-0056) with
    the same text, so the same synergy, for the ADR-0059 meta-share tiebreak — the
    rogue is cheaper, so only a meta read in which the staple's lists run it puts
    the staple first."""
    staple = {
        "name": "Test Meta Staple",
        "type_line": "Sorcery",
        "cmc": 2.0,
        "color_identity": ["R"],
        "oracle_text": "Create a 1/1 red Goblin creature token.",
        "prices": {"usd": "5.00"},
    }
    return staple, {**staple, "name": "Test Meta Rogue", "prices": {"usd": "0.10"}}
