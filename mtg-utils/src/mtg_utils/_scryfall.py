"""The one Scryfall client (ADR-0068): every request this package sends to Scryfall's
API (``api.scryfall.com``) or its file hosts (``svgs.scryfall.io``,
``cards.scryfall.io``) goes through :class:`ScryfallClient`.

It is an :class:`~mtg_utils._http.HttpFetcher` configured once for Scryfall:

- **identity** — ``User-Agent: mtg-utils/<package version>`` (:func:`user_agent`);
- **Accept** — ``application/json;q=0.9,*/*;q=0.8`` for the API, ``*/*`` for the file
  hosts (:func:`accept_for`);
- **pace** — one process-wide pacer (:data:`GAP`) with a gap per endpoint class
  (:data:`GAPS`, :func:`lanes_for`): 550 ms between the card searches Scryfall
  limits to 2 a second, 110 ms between any two API requests (10 a second), 50 ms
  of courtesy on the unlimited file hosts;
- **timeout** — :data:`TIMEOUT_SECONDS` (connect, read) per request;
- **retries** — one: after a 429, its ``Retry-After`` or else :data:`LOCKOUT_SECONDS`
  (Scryfall locks a client out for 30 s); after a connection error or timeout,
  :data:`CONNECTION_RETRY_SECONDS`;
- **unavailable** — a request that still fails after its retry (a 429, a connection
  error, a timeout) trips one process-wide latch: every later network request fails
  at once with :class:`ScryfallUnavailable` (a ``requests.ConnectionError``), so a
  batch records its remaining names as missing instead of paying each one's retries.
  Cache hits still serve. Only a new process (or :func:`reset_unavailable`) clears it;
- **cache** — optional, per call (:class:`Cache`: key, lifetime, refresh), under
  :func:`cache_dir` (``<cache_root>/scryfall/``), one subdirectory per site. A body
  that is not JSON is never cached by :meth:`ScryfallClient.get_json`, and raises
  ``requests.JSONDecodeError`` (a ``requests.RequestException``).

It satisfies the :class:`~mtg_utils._http.Fetcher` protocol too, so a site that takes
a ``Fetcher`` (``card_symbols``, ``guide_card_hovers``, ``art_fetcher``'s catalogs)
defaults to a client and a test still hands it a fake. Error handling stays each
caller's: the client raises ``requests`` exceptions, and returns ``None`` for a 404
only when asked (``not_found_none``).
"""

from __future__ import annotations

import functools
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypeVar
from urllib.parse import urlencode, urlsplit

import requests

from mtg_utils._http import (
    DEFAULT_FRESHNESS_SECONDS,
    HttpFetcher,
    RequestGap,
    cache_root,
    retry_after_seconds,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    T = TypeVar("T")

API_ROOT = "https://api.scryfall.com"
API_HOST = "api.scryfall.com"

#: The Accept header for the JSON API, and for the file hosts (symbol SVGs, card
#: images). Scryfall's API documentation names both as acceptable (ADR-0068).
API_ACCEPT = "application/json;q=0.9,*/*;q=0.8"
FILE_ACCEPT = "*/*"

#: The card-search endpoints Scryfall limits to 2 requests a second; every other API
#: path is limited to 10 a second, and the ``*.scryfall.io`` file hosts not at all
#: (scryfall.com/docs/api/rate-limits).
SEARCH_PATHS = frozenset(
    {"/cards/named", "/cards/search", "/cards/random", "/cards/collection"}
)
#: The gap per endpoint class, a tenth over each published minimum (the limit runs
#: on the server's clock, not ours); the file hosts get a courtesy gap.
GAPS = {"search": 0.55, "api": 0.11, "files": 0.05}
#: The pacer every client in the process shares.
GAP = RequestGap(GAPS)

#: (connect, read) seconds: a dead host is given up on fast, a slow answer is not.
TIMEOUT_SECONDS = (5.0, 30.0)
MAX_RETRIES = 1
#: How long Scryfall locks a client out after a 429: the wait when no
#: ``Retry-After`` says otherwise.
LOCKOUT_SECONDS = 30.0
#: The wait before retrying a connection error or a timeout.
CONNECTION_RETRY_SECONDS = 2.0


class ScryfallUnavailable(requests.ConnectionError):
    """Scryfall failed a request past its retries earlier in this process; later
    requests are not sent (see the module docstring)."""


_unavailable: list[str] = []


def reset_unavailable() -> None:
    """Clear the "Scryfall is unavailable" latch (tests; a process starts clear)."""
    _unavailable.clear()


def _trip(reason: str) -> None:
    if not _unavailable:
        _unavailable.append(reason)


def lanes_for(url: str) -> tuple[str, ...]:
    """The pacing lanes a request to *url* belongs to (:data:`GAPS`)."""
    parts = urlsplit(url)
    if parts.hostname != API_HOST:
        return ("files",)
    if parts.path.rstrip("/") in SEARCH_PATHS:
        return ("api", "search")
    return ("api",)


def _pace(url: str) -> None:
    """Before each network attempt: refuse once the latch is tripped, else wait out
    the shared pacer (read at call time, so tests can replace :data:`GAP`)."""
    if _unavailable:
        msg = f"Scryfall is unavailable for the rest of this run ({_unavailable[0]})"
        raise ScryfallUnavailable(msg)
    GAP.wait(lanes_for(url))


def _backoff(_attempt: int, resp: requests.Response | None) -> float:
    if resp is None:
        return CONNECTION_RETRY_SECONDS
    wait = retry_after_seconds(resp)
    return LOCKOUT_SECONDS if wait is None else wait


def _backoff_sleep(seconds: float) -> None:
    """The retry wait: ``time.sleep``, looked up when it runs (tests replace it)."""
    time.sleep(seconds)


def _decode(body: bytes) -> object:
    """*body* as JSON, or ``requests.JSONDecodeError`` (what ``Response.json()``
    raised before the shared client, and a ``RequestException`` callers catch)."""
    try:
        return json.loads(body)
    except ValueError as exc:
        text = body.decode("utf-8", errors="replace")
        msg = f"Scryfall sent a body that is not JSON ({exc})"
        raise requests.JSONDecodeError(msg, text[:200], 0) from exc


@functools.cache
def package_version() -> str:
    """The installed version of the distribution that ships ``mtg_utils`` (each skill
    installs it under its own name: ``mtg-utils``, ``deck-wizard``, …), else
    ``unknown`` when the package runs uninstalled."""
    from importlib import metadata

    names = [*metadata.packages_distributions().get("mtg_utils", ()), "mtg-utils"]
    for name in names:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"


def user_agent() -> str:
    """The identity every Scryfall request carries."""
    return f"mtg-utils/{package_version()}"


def accept_for(url: str) -> str:
    """The Accept header for *url*: JSON for the API, anything for a file host."""
    return API_ACCEPT if urlsplit(url).hostname == API_HOST else FILE_ACCEPT


def cache_dir() -> Path:
    """Where Scryfall responses are cached: ``<cache_root>/scryfall``, read at call
    time (tests redirect it)."""
    return cache_root() / "scryfall"


def _new_session() -> requests.Session:
    """The session a client sends through (the seam tests replace)."""
    return requests.Session()


@dataclass(frozen=True)
class Cache:
    """One call's cache: the file *key* under the client's directory, how long a
    cached copy stays fresh, and whether to skip (and replace) it this time."""

    key: str
    max_age_seconds: float
    refresh: bool = False


class ScryfallClient:
    """Scryfall, through one configured :class:`HttpFetcher`. Cheap to build: a site
    makes one per run (or per call), and every client shares :data:`GAP` and the
    unavailable latch."""

    def __init__(
        self,
        subdir: str | None = None,
        *,
        max_age_seconds: float = DEFAULT_FRESHNESS_SECONDS,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """*subdir* names this site's cache directory under :func:`cache_dir`;
        *max_age_seconds* is the lifetime of a ``fetch`` (Fetcher-protocol) copy.
        *session* and *sleep* (the retry backoff's) are for tests."""
        directory = cache_dir() / subdir if subdir else cache_dir()
        self._http = HttpFetcher(
            directory,
            user_agent=user_agent(),
            max_age_seconds=max_age_seconds,
            timeout=TIMEOUT_SECONDS,
            pace=_pace,
            backoff=_backoff,
            session=session if session is not None else _new_session(),
            sleep=sleep if sleep is not None else _backoff_sleep,
        )

    @property
    def cache_dir(self) -> Path:
        return self._http.cache_dir

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- The client's own reads -------------------------------------------------

    def get_bytes(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, str] | None = None,
        cache: Cache | None = None,
        not_found_none: bool = False,
    ) -> bytes | None:
        """The body at *path_or_url* (a path is under :data:`API_ROOT`), cached per
        *cache* when given. A 404 raises ``requests.HTTPError`` like any HTTP error,
        unless *not_found_none*, when it is ``None``."""
        return self._get(path_or_url, params, cache, not_found_none, check=None)

    def get_json(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, str] | None = None,
        cache: Cache | None = None,
        not_found_none: bool = False,
    ) -> object:
        """The decoded JSON at *path_or_url* (see :meth:`get_bytes`). A body that is
        not JSON raises ``requests.JSONDecodeError`` and is never cached; a cached
        copy that no longer decodes is dropped and fetched again."""
        body = self._get(path_or_url, params, cache, not_found_none, check=_decode)
        if body is None:
            return None
        if cache is None or cache.refresh:
            return _decode(body)
        try:
            return _decode(body)
        except requests.JSONDecodeError:
            (self.cache_dir / cache.key).unlink(missing_ok=True)
            again = Cache(cache.key, cache.max_age_seconds, refresh=True)
            body = self._get(path_or_url, params, again, not_found_none, check=_decode)
            return None if body is None else _decode(body)

    def _get(
        self,
        path_or_url: str,
        params: Mapping[str, str] | None,
        cache: Cache | None,
        not_found_none: bool,  # noqa: FBT001 — private
        *,
        check: Callable[[bytes], object] | None,
    ) -> bytes | None:
        url = _url(path_or_url, params)
        headers = {"Accept": accept_for(url)}
        try:
            if cache is None:
                return self._guarded(
                    lambda: self._http.fetch_uncached(
                        url, max_retries=MAX_RETRIES, headers=headers
                    )
                )
            return self._guarded(
                lambda: self._http.fetch(
                    url,
                    cache.key,
                    max_retries=MAX_RETRIES,
                    max_age_seconds=cache.max_age_seconds,
                    refresh=cache.refresh,
                    headers=headers,
                    check=check,
                )
            )
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if not_found_none and status == 404:
                return None
            raise

    @staticmethod
    def _guarded(call: Callable[[], T]) -> T:
        """Run *call*, tripping the unavailable latch when it fails past its retry
        on a 429, a connection error or a timeout."""
        try:
            return call()
        except ScryfallUnavailable:
            raise
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) == 429:
                _trip("HTTP 429: rate limited")
            raise
        except (requests.ConnectionError, requests.Timeout) as exc:
            _trip(f"{type(exc).__name__}: {exc}")
            raise

    # --- The Fetcher protocol -----------------------------------------------------

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = MAX_RETRIES,
    ) -> bytes:
        """:meth:`Fetcher.fetch`: cached under this client's directory for its
        lifetime. *throttle* is honoured on top of :data:`GAP`."""
        return self._guarded(
            lambda: self._http.fetch(
                url,
                cache_key,
                throttle=throttle,
                max_retries=max_retries,
                headers={"Accept": accept_for(url)},
            )
        )

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        return self._guarded(
            lambda: self._http.fetch_uncached(
                url,
                throttle=throttle,
                max_retries=MAX_RETRIES,
                headers={"Accept": accept_for(url)},
            )
        )

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = MAX_RETRIES,
    ) -> bytes:
        """Scryfall takes no form posts; here only to satisfy the protocol."""
        return self._http.post_form(
            url, form_fields=form_fields, throttle=throttle, max_retries=max_retries
        )


def _url(path_or_url: str, params: Mapping[str, str] | None) -> str:
    url = path_or_url if "://" in path_or_url else f"{API_ROOT}{path_or_url}"
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urlencode(params)}"
    return url


def fetch_named(name: str, *, client: ScryfallClient | None = None) -> dict | None:
    """Scryfall's ``/cards/named?fuzzy=`` record for *name*, ``None`` on a 404. The
    one copy of this read: ``scryfall_lookup.fetch_card`` (the bulk's cache-miss
    path) and ``price_check``'s null-price fallback both call it."""
    params = {"fuzzy": name}
    if client is not None:
        card = client.get_json("/cards/named", params=params, not_found_none=True)
    else:
        with ScryfallClient() as own:
            card = own.get_json("/cards/named", params=params, not_found_none=True)
    return card if isinstance(card, dict) else None
