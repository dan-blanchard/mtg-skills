"""Shared HTTP layer.

Every skill that talks to a remote source (Scryfall, EDHREC, Commander
Spellbook, CubeCobra, MTGJSON, the Comprehensive Rules landing page, phase's
GitHub releases, generic strategy-article URLs) re-implemented a slice of the
same handful of concerns: a default ``User-Agent``, a "reuse the file on disk
if it's not stale yet" freshness check, a browser-headers + curl-fallback
escape hatch for sites that 403 plain ``requests`` (TLS fingerprinting), and
a cached/retrying GET+POST client. This module centralizes the pieces that
were byte-for-byte (or near-byte-for-byte) duplicated across those modules.

What stays bespoke, deliberately: each consumer's own cache **layout** and
**freshness window** where those genuinely differ from the 24h default here
(``rulings_lookup``'s 30-day oracle_id-keyed cache; ``art_fetcher``'s 7-day
window, threaded through :class:`HttpFetcher`'s ``max_age_seconds``;
``download_mtgjson``'s gzip streaming decompress), and any source-specific
identity (``art_fetcher``'s own ``USER_AGENT``, naming the ASCII-art crawler
distinctly; ``_phase``'s ``mtg-skills/_phase``, naming the phase subsystem
to GitHub) — a shared default doesn't mean every caller must use it.
"""

from __future__ import annotations

import subprocess
import time
import urllib.request
from typing import TYPE_CHECKING, Protocol

import requests

if TYPE_CHECKING:
    from pathlib import Path

# --- User agent --------------------------------------------------------------

# Shared default identity for HTTP clients that don't need a distinct one
# (Scryfall, EDHREC, Commander Spellbook). Was duplicated verbatim as
# "commander-utils/0.1.0" in scryfall_lookup.py, edhrec_lookup.py, and
# combo_search.py, and as a near-duplicate ("mtg-skills/0.1.0") in
# download_mtgjson.py.
USER_AGENT = "commander-utils/0.1.0"


# --- Browser headers + curl fallback ------------------------------------------

# Mimics a real browser — some sites (CubeCobra, strategy-article hosts) 403
# a plain ``requests`` UA via TLS fingerprinting. Lifted from web_fetch.py;
# cubecobra_fetch.py's ``_fetch_text`` uses the same escape hatch.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Avoid Brotli — requests can't decode it without extra dependencies
    "Accept-Encoding": "gzip, deflate",
}


def _fetch_with_curl(url: str) -> str:
    """Fetch via curl — bypasses TLS fingerprinting that blocks requests."""
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "-H",
            f"User-Agent: {BROWSER_HEADERS['User-Agent']}",
            "-H",
            f"Accept: {BROWSER_HEADERS['Accept']}",
            "-H",
            f"Accept-Language: {BROWSER_HEADERS['Accept-Language']}",
            "--compressed",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        msg = f"curl failed with exit code {result.returncode}: {result.stderr}"
        raise RuntimeError(msg)
    return result.stdout


# --- Plain urllib GET (no requests dependency, no caching) -------------------


def urllib_get(url: str, *, user_agent: str, timeout: float | None = None) -> bytes:
    """GET ``url`` via ``urllib`` (follows redirects); return the raw body.

    No on-disk caching — for one-off fetches (release manifests, raw GitHub
    files) where the caller owns its own cache-once-forever semantics on top
    (see ``_phase.py``'s ``ensure_card_data`` / ``ensure_known_tokens``)
    rather than the freshness-window model :func:`is_fresh` /
    :class:`HttpFetcher` assume. Raises ``urllib.error.URLError`` / ``OSError``
    on failure — callers wrap with their own error message.
    """
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    # Branch rather than splat a kwargs dict: urlopen's overloads key on the
    # cafile/capath/context names, so `**dict[str, float]` matches none of them.
    if timeout is None:
        with urllib.request.urlopen(request) as resp:
            return resp.read()
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


# --- Freshness -----------------------------------------------------------------


def is_fresh(path: Path, *, max_age_hours: float = 24) -> bool:
    """True if ``path`` exists and was modified within ``max_age_hours``.

    Replaces the near-identical ``_is_fresh`` helper duplicated in
    ``download_mtgjson.py`` and ``download_rules.py`` (both used the same
    24-hour window).
    """
    return path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600


# --- Cached/retrying Fetcher protocol -------------------------------------------

# Default on-disk cache TTL for HttpFetcher.fetch — matches art_fetcher's
# original 7-day window (its only production caller today).
DEFAULT_FRESHNESS_SECONDS = 7 * 86400


class Fetcher(Protocol):
    """Seam for HTTP-with-cache.

    A ``Fetcher`` returns the bytes for a URL, caching them under
    ``cache_key`` for the fetcher's configured freshness window. The
    interface owns freshness, retry, throttle, and disk-write — callers only
    know "give me the bytes for this URL, please."

    Two adapters live behind this seam: :class:`HttpFetcher` (production,
    backed by ``requests.Session``) and ``FakeFetcher`` (test-only, in
    ``tests/proxy-printer/_fake_fetcher.py``, dict-backed).
    """

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        """Return cached bytes for ``url``, fetching if stale/missing.

        ``cache_key`` is a flat filename (the fetcher resolves it under
        its own cache root). ``throttle`` sleeps before each *network*
        call (cache hits return immediately). On HTTP 429 / connection
        error, the fetcher retries with linear backoff (5s, 10s, …) up
        to ``max_retries`` additional attempts; if all retries fail the
        final exception is raised (fail-loud).
        """
        ...

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        """GET without caching. Used for short-lived resources like CSRF
        tokens that must be fresh on every call."""
        ...

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        """POST a form-encoded body. Never cached (POST responses depend
        on session state). Retry / throttle behaviour mirrors ``fetch``."""
        ...


class HttpFetcher:
    """Production :class:`Fetcher`. Wraps a private ``requests.Session``."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        user_agent: str = USER_AGENT,
        cookies: dict[str, dict[str, str]] | None = None,
        max_age_seconds: int = DEFAULT_FRESHNESS_SECONDS,
    ) -> None:
        """``cache_dir`` is the on-disk cache root (auto-created).
        ``cookies`` maps domain → {name: value} for cookies that must
        be pre-set (e.g. asciiart.website's sort-order cookie).
        ``max_age_seconds`` is how long a cached ``fetch`` response is
        considered fresh before a re-fetch (default 7 days).
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir = cache_dir
        self._max_age_seconds = max_age_seconds
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        if cookies:
            for domain, by_name in cookies.items():
                for name, value in by_name.items():
                    self._session.cookies.set(name, value, domain=domain)

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        path = self._cache_dir / cache_key
        if (
            path.is_file()
            and (time.time() - path.stat().st_mtime) < self._max_age_seconds
        ):
            return path.read_bytes()
        for attempt in range(max_retries + 1):
            if throttle > 0:
                time.sleep(throttle)
            try:
                resp = self._session.get(url, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt < max_retries:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise
            status = getattr(resp, "status_code", 200)
            if status == 429 and attempt < max_retries:
                time.sleep(5.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(resp.content)
            tmp.replace(path)
            return resp.content
        # Unreachable: the loop either returns or raises.
        msg = "exhausted retries without raising or returning"
        raise RuntimeError(msg)

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        if throttle > 0:
            time.sleep(throttle)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        for attempt in range(max_retries + 1):
            if throttle > 0:
                time.sleep(throttle)
            try:
                resp = self._session.post(url, data=form_fields, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt < max_retries:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise
            status = getattr(resp, "status_code", 200)
            if status == 429 and attempt < max_retries:
                time.sleep(5.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.content
        msg = "exhausted retries without raising or returning"
        raise RuntimeError(msg)
