"""Suite-wide test settings, shared by every skill's tests."""

import os
import socket
import sys

import pytest

# An installed MTG Arena must never change a test: its card database would decide
# wildcard rarities (``mtg_utils.arena_card_db``). A test that wants one points
# ``MTG_SKILLS_ARENA_CARD_DB`` at a fixture database with ``monkeypatch.setenv``.
os.environ["MTG_SKILLS_ARENA_CARD_DB"] = "none"
# Nor may a trees store (``_card_ir.tree_store``): one beside the user's card-data
# would serve trees a test's monkeypatched pipeline never built, and take the run's
# trees into the user's cache. The store's own tests delete the variable.
os.environ["MTG_SKILLS_TREE_STORE"] = "none"
# Nor the Card IR sidecar's span index (``_card_ir.load``) beside the user's
# sidecar: a test reads that sidecar, never writes beside it. The index's own
# tests delete the variable.
os.environ["MTG_SKILLS_CARD_IR_SPANS"] = "none"


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


@pytest.fixture(autouse=True)
def _phase_records_sidecar_in_tmp(monkeypatch, tmp_path_factory):
    """No test writes a phase-records sidecar beside the user's card-data: the
    ``_cached_only`` fixtures hand the real cached card-data to the Card IR,
    whose index keeps its per-oracle_id records in a sidecar beside it
    (``trees._records_sidecar_path``). Every test's goes to one temp dir of the
    session's instead, keyed by the card-data path."""
    import hashlib

    from mtg_utils._card_ir import trees

    root = tmp_path_factory.getbasetemp() / "phase-records"
    root.mkdir(exist_ok=True)

    def in_tmp(card_data):
        digest = hashlib.sha256(str(card_data).encode()).hexdigest()[:16]
        return root / f"{digest}.records.pkl"

    monkeypatch.setattr(trees, "_records_sidecar_path", in_tmp)


@pytest.fixture(autouse=True)
def _no_write_back_sidecars():
    """No test leaves a write-back sidecar attached for the tests after it:
    ``deck-tune --bulk-data`` attaches the ident-provenance, job-read and
    card-read ones process-wide (``write_back.WriteBackSidecar``), and an attachment would serve
    the next test a stale value and write the run's into the fixture bulk's
    sidecar at exit. Each test starts and ends detached, so the exit write has
    nothing to write."""

    def detach() -> None:
        module = sys.modules.get("mtg_utils._analysis.write_back")
        if module is not None:
            module.detach_all()

    detach()
    yield
    detach()


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


@pytest.fixture(autouse=True)
def _scryfall_isolated(monkeypatch, tmp_path_factory):
    """The shared Scryfall client (``_scryfall``, ADR-0068) never waits out its
    gaps or retry backoff in a test, starts every test with its "unavailable" latch clear (a test
    that trips it can't fail the next), and never caches into the user's cache:
    unless the test points ``MTG_SKILLS_CACHE_DIR`` at its own dir,
    ``_scryfall.cache_dir()`` is a fresh empty dir of the test's own (rulings,
    symbols, card images, catalogs and the lookup batch files all live under it)."""
    from mtg_utils import _http, _scryfall

    monkeypatch.setattr(
        _scryfall, "GAP", _http.RequestGap(_scryfall.GAPS, sleep=lambda _s: None)
    )
    monkeypatch.setattr(_scryfall, "_unavailable", [])
    monkeypatch.setattr(_scryfall, "_backoff_sleep", lambda _s: None)
    real = _scryfall.cache_dir
    own: dict[str, object] = {}

    def resolve():
        if (os.environ.get("MTG_SKILLS_CACHE_DIR") or None) != _OUTER_CACHE_DIR:
            return real()  # the test chose its own cache dir
        if "root" not in own:
            own["root"] = tmp_path_factory.mktemp("scryfall")
        return own["root"]

    monkeypatch.setattr(_scryfall, "cache_dir", resolve)


class ScryfallWire:
    """Stands in for Scryfall below a real ``requests.Session``: every request a
    ``ScryfallClient`` sends in the test lands here (headers, URL and timeout as
    sent) and is answered from ``routes``. An unrouted request fails the test."""

    def __init__(self) -> None:
        import requests

        self.sent: list = []  # requests.PreparedRequest, in order
        self.timeouts: list = []
        self.routes: dict[str, list] = {}
        self._requests = requests

    def route(self, fragment: str, *answers) -> None:
        """Answer requests whose URL contains *fragment* with *answers* in turn (the
        last repeats). An answer is a ``(status, body)`` or ``(status, body,
        headers)`` tuple, a dict / list (200 JSON), bytes (200), or an exception
        to raise."""
        self.routes[fragment] = list(answers)

    def urls(self) -> list[str]:
        return [r.url for r in self.sent]

    def session(self):
        requests = self._requests
        wire = self

        class _Adapter(requests.adapters.BaseAdapter):
            def send(self, request, timeout=None, **_kwargs):
                wire.sent.append(request)
                wire.timeouts.append(timeout)
                return wire._answer(request)

            def close(self):
                pass

        session = requests.Session()
        session.mount("https://", _Adapter())
        session.mount("http://", _Adapter())
        return session

    def _answer(self, request):
        import json as _json

        from requests.structures import CaseInsensitiveDict

        for fragment, answers in self.routes.items():
            if fragment not in request.url:
                continue
            answer = answers.pop(0) if len(answers) > 1 else answers[0]
            if isinstance(answer, BaseException):
                raise answer
            if isinstance(answer, (dict, list)):
                answer = (200, _json.dumps(answer).encode())
            elif isinstance(answer, bytes):
                answer = (200, answer)
            status, body, *rest = answer
            resp = self._requests.Response()
            resp.status_code = status
            resp._content = body if isinstance(body, bytes) else body.encode()
            resp.headers = CaseInsensitiveDict(rest[0] if rest else {})
            resp.url = request.url
            resp.request = request
            resp.encoding = "utf-8"
            return resp
        msg = f"unrouted Scryfall request in a test: {request.url}"
        raise AssertionError(msg)


@pytest.fixture
def scryfall_wire(monkeypatch) -> ScryfallWire:
    """Every ``ScryfallClient`` the test builds sends through a :class:`ScryfallWire`
    (``_scryfall._new_session``), so the client's own headers, pacing, retries and
    cache run for real with no network."""
    from mtg_utils import _scryfall

    wire = ScryfallWire()
    monkeypatch.setattr(_scryfall, "_new_session", wire.session)
    return wire


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
