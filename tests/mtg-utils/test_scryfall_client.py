"""The shared Scryfall client (``_scryfall``, ADR-0068): what goes on the wire, the
process-wide gap, retries, 404s and the per-call cache. Every request lands on the
``scryfall_wire`` fixture (tests/conftest.py), below a real ``requests.Session``."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import pytest
import requests

from mtg_utils import (
    _http,
    _scryfall,
    art_fetcher,
    price_check,
    rulings_lookup,
    scryfall_lookup,
)
from mtg_utils._scryfall import Cache, ScryfallClient
from mtg_utils.card_symbols import SymbolSet

CIRCLE_SVG = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    b"<circle cx='50' cy='50' r='50'/></svg>"
)


@pytest.fixture(autouse=True)
def _no_sockets(monkeypatch):
    """Belt and braces on top of the suite's name-resolution guard: no test here
    opens a socket, so a request that slipped past the wire fails loudly."""

    def refuse(*_a, **_k):
        msg = "test_scryfall_client opened a socket"
        raise AssertionError(msg)

    monkeypatch.setattr(socket.socket, "connect", refuse)


class FakeClock:
    """A monotonic clock that only moves when slept on (or told to)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(round(seconds, 6))
        self.now += seconds


# --- What goes on the wire ------------------------------------------------------


def test_identity_and_accept_on_the_wire(scryfall_wire):
    scryfall_wire.route("/cards/named", {"object": "card", "name": "Zzyx Testwing"})
    scryfall_wire.route("svgs.scryfall.io", CIRCLE_SVG)

    assert scryfall_lookup.fetch_card("Zzyx Testwing") == {
        "object": "card",
        "name": "Zzyx Testwing",
    }
    assert "{W}" in SymbolSet.load(["{W}"])

    api, svg = scryfall_wire.sent
    identity = f"mtg-utils/{_http.package_version()}"
    assert api.headers["User-Agent"] == svg.headers["User-Agent"] == identity
    assert api.headers["Accept"] == "application/json;q=0.9,*/*;q=0.8"
    assert svg.headers["Accept"] == "*/*"
    assert api.url == "https://api.scryfall.com/cards/named?fuzzy=Zzyx+Testwing"
    assert svg.url == "https://svgs.scryfall.io/card-symbols/W.svg"
    assert "commander-utils" not in identity


def test_the_identity_names_the_installed_version():
    from importlib import metadata

    assert _http.package_version() == metadata.version("mtg-utils")
    assert _http.user_agent() == f"mtg-utils/{metadata.version('mtg-utils')}"


def test_the_identity_survives_an_uninstalled_package(monkeypatch):
    from importlib import metadata

    def missing(_name):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(metadata, "version", missing)
    monkeypatch.setattr(metadata, "packages_distributions", dict)
    _http.package_version.cache_clear()
    try:
        assert _http.user_agent() == "mtg-utils/unknown"
    finally:
        _http.package_version.cache_clear()


def test_the_timeout_is_passed(scryfall_wire):
    scryfall_wire.route("/catalog/", {"data": []})
    ScryfallClient().get_json("/catalog/land-types")
    assert scryfall_wire.timeouts == [_scryfall.TIMEOUT_SECONDS]
    connect, read = _scryfall.TIMEOUT_SECONDS
    assert connect < read


def test_the_art_fetcher_catalogs_carry_the_scryfall_identity(scryfall_wire):
    scryfall_wire.route("/catalog/", {"data": ["Vampire"]})
    assert art_fetcher.fetch_subtypes() == ["vampire"]
    assert len(scryfall_wire.sent) == len(art_fetcher.SCRYFALL_CATALOGS)
    assert {r.headers["User-Agent"] for r in scryfall_wire.sent} == {_http.user_agent()}
    assert art_fetcher.USER_AGENT not in {
        r.headers["User-Agent"] for r in scryfall_wire.sent
    }


# --- One pacer for the whole process, a gap per endpoint class ------------------


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    """The shared pacer on a fake clock, with Scryfall's real gaps."""
    clock = FakeClock()
    monkeypatch.setattr(
        _scryfall,
        "GAP",
        _http.RequestGap(_scryfall.GAPS, clock=clock, sleep=clock.sleep),
    )
    return clock


@pytest.mark.parametrize(
    ("url", "lanes"),
    [
        ("https://api.scryfall.com/cards/named?fuzzy=x", ("api", "search")),
        ("https://api.scryfall.com/cards/search?q=t", ("api", "search")),
        ("https://api.scryfall.com/cards/random", ("api", "search")),
        ("https://api.scryfall.com/cards/collection", ("api", "search")),
        ("https://api.scryfall.com/cards/abc/rulings", ("api",)),
        ("https://api.scryfall.com/catalog/land-types", ("api",)),
        ("https://svgs.scryfall.io/card-symbols/W.svg", ("files",)),
        ("https://cards.scryfall.io/normal/front/a/b/x.jpg", ("files",)),
    ],
)
def test_each_url_is_paced_in_its_endpoint_class(url, lanes):
    assert _scryfall.lanes_for(url) == lanes


def test_the_published_limits_with_margin():
    # 2 a second for the card searches, 10 a second for the rest of the API.
    assert _scryfall.GAPS["search"] >= 0.5
    assert _scryfall.GAPS["api"] >= 0.1
    assert _scryfall.GAPS["files"] < _scryfall.GAPS["api"]


def test_two_named_lookups_are_half_a_second_apart(scryfall_wire, clock):
    scryfall_wire.route("/cards/named", {"name": "Test Relic"})
    scryfall_lookup.fetch_card("Test Relic")
    scryfall_lookup.fetch_card("Test Relic")
    assert clock.slept == [0.55]


def test_the_gap_is_shared_across_call_sites(scryfall_wire, clock):
    scryfall_wire.route("/cards/named", {"name": "Test Relic"})
    scryfall_wire.route("/rulings", {"data": []})
    scryfall_wire.route("/catalog/", {"data": []})
    scryfall_wire.route("svgs.scryfall.io", CIRCLE_SVG)

    scryfall_lookup.fetch_card("Test Relic")  # first request: no wait
    clock.now += 0.03
    # A different site, its own client, straight after: waits out the API gap.
    with ScryfallClient() as client:
        rulings_lookup._fetch_rulings("card-x", client, oracle_id="oid-x")
    assert clock.slept == [0.08]
    # A third site's named lookup waits out the search gap from the first.
    price_check._api_price_lookup("Test Relic")
    assert clock.slept == [0.08, 0.44]
    # The file host has its own (courtesy) lane: no wait after an API request.
    SymbolSet.load(["{W}"])
    assert clock.slept == [0.08, 0.44]

    clock.now += 5  # long after: no wait
    ScryfallClient().get_json("/catalog/card-names")
    assert clock.slept == [0.08, 0.44]
    assert len(scryfall_wire.sent) == 5


def test_request_gap_waits_for_every_lane_a_request_is_in():
    clock = FakeClock()
    gap = _http.RequestGap({"a": 0.1, "b": 0.5}, clock=clock, sleep=clock.sleep)
    gap.wait(["a", "b"])
    gap.wait(["a"])  # a's gap only
    gap.wait(["a", "b"])  # b's gap since the first, the longer
    assert clock.slept == [0.1, 0.4]


# --- Retries ----------------------------------------------------------------------


def _client(clock: FakeClock) -> ScryfallClient:
    return ScryfallClient(sleep=clock.sleep)


@pytest.mark.parametrize(
    ("retry_after", "waited"),
    [({"Retry-After": "45"}, 45.0), ({}, 30.0), ({"Retry-After": "3600"}, 120.0)],
)
def test_a_429_waits_out_the_lockout_then_retries(scryfall_wire, retry_after, waited):
    scryfall_wire.route("/catalog/", (429, b"slow down", retry_after), {"data": [1]})
    clock = FakeClock()
    assert _client(clock).get_json("/catalog/x") == {"data": [1]}
    assert clock.slept == [waited]
    assert len(scryfall_wire.sent) == 2


def test_a_retry_after_date_is_honoured(scryfall_wire):
    from email.utils import formatdate

    when = formatdate(time.time() + 30, usegmt=True)
    scryfall_wire.route("/catalog/", (429, b"", {"Retry-After": when}), {"data": []})
    clock = FakeClock()
    _client(clock).get_json("/catalog/x")
    assert 25 <= clock.slept[0] <= 30


@pytest.mark.parametrize(
    "error", [requests.ConnectionError("reset"), requests.Timeout("slow")]
)
def test_a_connection_or_timeout_error_is_retried_once_quickly(scryfall_wire, error):
    scryfall_wire.route("/catalog/", error, {"data": []})
    clock = FakeClock()
    assert _client(clock).get_json("/catalog/x") == {"data": []}
    assert clock.slept == [_scryfall.CONNECTION_RETRY_SECONDS]


def test_it_gives_up_after_the_retry(scryfall_wire):
    scryfall_wire.route("/catalog/", (429, b"slow down"))
    clock = FakeClock()
    with pytest.raises(requests.HTTPError) as excinfo:
        _client(clock).get_json("/catalog/x")
    assert excinfo.value.response.status_code == 429
    assert len(scryfall_wire.sent) == _scryfall.MAX_RETRIES + 1 == 2
    assert clock.slept == [30.0]


def test_other_http_errors_are_not_retried(scryfall_wire):
    scryfall_wire.route("/catalog/", (503, b"down"))
    with pytest.raises(requests.HTTPError):
        ScryfallClient().get_json("/catalog/x")
    assert len(scryfall_wire.sent) == 1
    assert _scryfall._unavailable == []  # ...and don't make Scryfall unavailable


# --- Scryfall unavailable: one latch for the process ------------------------------


@pytest.mark.parametrize(
    "failure",
    [(429, b"slow down"), requests.ConnectionError("refused"), requests.Timeout("x")],
)
def test_a_request_failing_past_its_retry_stops_every_later_one(scryfall_wire, failure):
    scryfall_wire.route("/catalog/", failure)
    scryfall_wire.route("/cards/named", {"name": "x"})
    clock = FakeClock()
    with pytest.raises(requests.RequestException):
        _client(clock).get_json("/catalog/x")
    sent = len(scryfall_wire.sent)

    # Every later request, from any site, fails at once without going out.
    with pytest.raises(_scryfall.ScryfallUnavailable):
        scryfall_lookup.fetch_card("x")
    assert isinstance(
        _scryfall.ScryfallUnavailable("x"), requests.ConnectionError
    )  # what callers already catch
    assert len(scryfall_wire.sent) == sent

    _scryfall.reset_unavailable()
    assert scryfall_lookup.fetch_card("x") == {"name": "x"}


def test_cache_hits_still_serve_while_unavailable(scryfall_wire):
    scryfall_wire.route("/sets/tst", {"code": "tst"})
    client = ScryfallClient("sets")
    cache = Cache("tst.json", 3600)
    client.get_json("/sets/tst", cache=cache)
    _scryfall._trip("test")
    assert client.get_json("/sets/tst", cache=cache) == {"code": "tst"}


def test_a_batch_with_scryfall_down_fails_fast(scryfall_wire, tmp_path):
    # No bulk: every name goes to Scryfall. The first pays its one retry; the other
    # 99 are recorded missing at once, never sent.
    import json

    scryfall_wire.route("/cards/named", requests.ConnectionError("refused"))
    names = tmp_path / "names.json"
    names.write_text(json.dumps([f"Card {i}" for i in range(100)]))
    results, cache_path, _ = scryfall_lookup.lookup_cards(
        names, cache_dir=tmp_path / "c"
    )
    assert results == [None] * 100
    assert len(scryfall_wire.sent) == 2
    assert not cache_path.exists()


def test_symbols_warn_once_when_scryfall_is_unavailable(scryfall_wire, capsys):
    _scryfall._trip("test")
    assert len(SymbolSet.load(["{W}", "{U}", "{B}"])) == 0
    err = capsys.readouterr().err
    assert err.count("printing them as text") == 1
    assert scryfall_wire.sent == []


# --- A body that is not JSON ------------------------------------------------------


def test_a_body_that_is_not_json_raises_a_requests_error_and_is_not_cached(
    scryfall_wire,
):
    scryfall_wire.route("/sets/", (200, b"<html>maintenance</html>"))
    client = ScryfallClient("sets")
    with pytest.raises(requests.JSONDecodeError) as excinfo:
        client.get_json("/sets/tst", cache=Cache("tst.json", 3600))
    assert isinstance(excinfo.value, requests.RequestException)
    assert not (client.cache_dir / "tst.json").exists()
    with pytest.raises(requests.RequestException):
        client.get_json("/sets/tst")  # uncached too


def test_a_batch_counts_a_name_answered_with_html_as_missing(scryfall_wire, tmp_path):
    import json

    scryfall_wire.route("Bad+Card", (200, b"<html>oops</html>"))
    scryfall_wire.route("Good+Card", {"name": "Good Card", "type_line": "Instant"})
    names = tmp_path / "names.json"
    names.write_text(json.dumps(["Bad Card", "Good Card"]))
    results, cache_path, _ = scryfall_lookup.lookup_cards(
        names, cache_dir=tmp_path / "c"
    )
    assert results == [None, {"name": "Good Card", "type_line": "Instant"}]
    assert not cache_path.exists()  # a failed name is retried next run
    assert _scryfall._unavailable == []  # a bad body is not an outage


# --- 404s -------------------------------------------------------------------------


def test_a_404_is_none_only_when_asked(scryfall_wire):
    scryfall_wire.route("/cards/named", (404, b'{"object": "error"}'))
    scryfall_wire.route("cards.scryfall.io", (404, b""))
    client = ScryfallClient()
    assert (
        client.get_json("/cards/named", params={"fuzzy": "x"}, not_found_none=True)
        is None
    )
    with pytest.raises(requests.HTTPError) as excinfo:
        client.get_json("/cards/named", params={"fuzzy": "x"})
    assert excinfo.value.response.status_code == 404
    assert (
        client.get_bytes("https://cards.scryfall.io/x.jpg", not_found_none=True) is None
    )


# --- The per-call cache -----------------------------------------------------------


def test_the_cache_lifetime_and_refresh(scryfall_wire):
    scryfall_wire.route("/sets/tst", {"code": "tst"})
    client = ScryfallClient("sets")
    cache = Cache("tst.json", max_age_seconds=3600)

    assert client.get_json("/sets/tst", cache=cache) == {"code": "tst"}
    client.get_json("/sets/tst", cache=cache)
    assert len(scryfall_wire.sent) == 1  # a hit

    path = client.cache_dir / "tst.json"
    old = time.time() - 7200
    os.utime(path, (old, old))
    client.get_json("/sets/tst", cache=cache)
    assert len(scryfall_wire.sent) == 2  # expired

    client.get_json("/sets/tst", cache=Cache("tst.json", 3600, refresh=True))
    assert len(scryfall_wire.sent) == 3  # refreshed

    path.write_text("not json")
    assert client.get_json("/sets/tst", cache=cache) == {"code": "tst"}
    assert len(scryfall_wire.sent) == 4  # an unreadable copy is fetched again


def test_a_404_is_never_cached(scryfall_wire):
    scryfall_wire.route("/cards/x", (404, b"{}"))
    client = ScryfallClient("cards")
    cache = Cache("x.json", 3600)
    assert client.get_json("/cards/x", cache=cache, not_found_none=True) is None
    assert not (client.cache_dir / "x.json").exists()


def test_the_cache_lives_under_the_cache_root_never_tmpdir(
    scryfall_wire, tmp_path, monkeypatch
):
    root = tmp_path / "cache"
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(root))
    monkeypatch.setenv("TMPDIR", str(tmpdir))
    scryfall_wire.route("/rulings", {"data": [{"comment": "x"}]})
    card = {"id": "card-x", "oracle_id": "oid-x", "name": "Test Relic"}
    monkeypatch.setattr(rulings_lookup, "lookup_single", lambda *_a, **_k: card)

    rulings_lookup.lookup_rulings("Test Relic")

    assert (root / "scryfall" / "rulings" / "oid-x.json").is_file()
    assert list(tmpdir.iterdir()) == []


def test_the_cache_is_redirected_under_tests(tmp_path_factory):
    # Unless a test chooses its own MTG_SKILLS_CACHE_DIR, tests/conftest.py points
    # the Scryfall cache at a fresh dir of the test's own: never the user's cache.
    base = Path(tmp_path_factory.getbasetemp())
    here = _scryfall.cache_dir()
    assert base in here.parents
    assert _http.default_cache_root() not in here.parents
    assert ScryfallClient("rulings").cache_dir == here / "rulings"


# --- Retry-After edge cases and the lockout ---------------------------------------


def _resp(value):
    resp = requests.Response()
    resp.status_code = 429
    resp.headers["Retry-After"] = value
    return resp


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("nan", None),
        ("inf", None),
        ("-inf", None),
        ("garbage", None),
        ("-5", 0.0),
        ("0", 0.0),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0),  # a date in the past
        ("7", 7.0),
        ("3600", 120.0),
    ],
)
def test_retry_after_is_read_safely(value, seconds):
    assert _http.retry_after_seconds(_resp(value)) == seconds


@pytest.mark.parametrize(
    "value", ["nan", "inf", "-5", "0", "Wed, 21 Oct 2015 07:28:00 GMT", "garbage"]
)
def test_a_429_never_retries_inside_the_lockout(scryfall_wire, value):
    scryfall_wire.route("/catalog/", (429, b"", {"Retry-After": value}), {"data": []})
    clock = FakeClock()
    assert _client(clock).get_json("/catalog/x") == {"data": []}
    assert clock.slept == [_scryfall.LOCKOUT_SECONDS]


def test_a_429_holds_the_shared_pacer_for_every_other_caller(scryfall_wire, clock):
    scryfall_wire.route("/catalog/", (429, b"", {"Retry-After": "45"}), {"data": []})
    scryfall_wire.route("/sets/", {"code": "tst"})
    _client(FakeClock()).get_json("/catalog/x")  # its own backoff sleep is fake
    # The pacer was held for the 45 s; the retry and anyone after wait it out.
    assert clock.slept
    assert max(clock.slept) == pytest.approx(45.0)
    clock.slept.clear()
    clock.now += 60
    ScryfallClient().get_json("/sets/tst")
    assert clock.slept == []


def test_request_gap_pause_holds_every_lane():
    clock = FakeClock()
    gap = _http.RequestGap({"a": 0.1}, clock=clock, sleep=clock.sleep)
    gap.pause(30)
    gap.wait(["a"])
    gap.wait(["b"])  # the pause is over: no further wait
    assert clock.slept == [30.0]


# --- The CLI boundary: Scryfall unreachable is one line, not a traceback ----------


def _assert_clean_failure(result, what):
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit)  # a ClickException, not a crash
    assert f"could not reach Scryfall to fetch {what}" in result.output
    assert "Traceback" not in result.output


def test_price_check_cli(scryfall_wire, tmp_path, monkeypatch):
    import json

    from click.testing import CliRunner

    from mtg_utils import card_pool

    monkeypatch.setattr(card_pool, "default_bulk_path", lambda: None)
    scryfall_wire.route("/cards/named", requests.ConnectionError("refused"))
    names = tmp_path / "names.json"
    names.write_text(json.dumps(["Sol Ring"]))
    result = CliRunner().invoke(
        price_check.main, [str(names), "--output", str(tmp_path / "o.json")]
    )
    _assert_clean_failure(result, "prices")
    assert "uv run download-mtgjson" in result.output


def _deck_with_a_new_card(tmp_path):
    import json

    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps(
            {
                "format": "commander",
                "commanders": [],
                "cards": [
                    {"name": "Sol Ring", "quantity": 1},
                    {"name": "Zzyx Not In Bulk", "quantity": 1},
                ],
            }
        )
    )
    return deck


def test_a_deck_cli_through_acquire_for_cli(scryfall_wire, tmp_path, sample_bulk_data):
    from click.testing import CliRunner

    from mtg_utils import deck_hydrate

    scryfall_wire.route("/cards/named", requests.ConnectionError("refused"))
    result = CliRunner().invoke(
        deck_hydrate.main,
        [str(_deck_with_a_new_card(tmp_path)), "--bulk-data", str(sample_bulk_data)],
    )
    _assert_clean_failure(result, "the deck's cards")
    assert "uv run download-mtgjson" in result.output


def test_build_deck_cli_missing_adds(scryfall_wire, tmp_path, sample_bulk_data):
    import json

    from click.testing import CliRunner

    from mtg_utils import build_deck

    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps(
            {
                "format": "commander",
                "commanders": [],
                "cards": [{"name": "Sol Ring", "quantity": 1}],
            }
        )
    )
    adds = tmp_path / "adds.json"
    adds.write_text(json.dumps([{"name": "Zzyx Not In Bulk", "quantity": 1}]))
    scryfall_wire.route("/cards/named", requests.ConnectionError("refused"))
    result = CliRunner().invoke(
        build_deck.main,
        [
            str(deck),
            *("--bulk-data", str(sample_bulk_data)),
            *("--adds", str(adds)),
            *("--output-dir", str(tmp_path / "out")),
        ],
    )
    _assert_clean_failure(result, "the added cards")


def test_rulings_lookup_cli(scryfall_wire, monkeypatch):
    from click.testing import CliRunner

    card = {"id": "card-x", "oracle_id": "oid-x", "name": "Test Relic"}
    monkeypatch.setattr(rulings_lookup, "default_bulk_path", lambda: None)
    monkeypatch.setattr(rulings_lookup, "lookup_single", lambda *_a, **_k: card)
    scryfall_wire.route("/rulings", requests.Timeout("slow"))
    result = CliRunner().invoke(rulings_lookup.main, ["--card", "Test Relic"])
    _assert_clean_failure(result, "rulings")
    assert "local bulk first" in result.output
