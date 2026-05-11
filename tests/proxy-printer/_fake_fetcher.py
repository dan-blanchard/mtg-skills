"""In-memory :class:`Fetcher` for test_art_fetcher.

Maps URL substrings → canned response bytes. Records every fetch call so
tests can assert on URL ordering / cache-key usage / throttle values.
Honors ``max_retries`` for 429 / connection-error scenarios via injected
``error_responses`` (a list of exceptions or ``(429-once, 200)`` tuples).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class FetchCall:
    """One ``fetcher.fetch(...)`` invocation, recorded for assertions."""

    url: str
    cache_key: str
    throttle: float
    max_retries: int


@dataclass
class FakeFetcher:
    """Test :class:`mtg_utils.art_fetcher.Fetcher`.

    ``routes`` maps URL *substrings* (matched in iteration order) to
    response bytes or strings. A test sets it up once::

        fetcher = FakeFetcher(routes={
            "/catalog/creature-types": json_blob,
            "/animals/cats": SAMPLE_HTML,
        })

    and the fetcher returns the first route whose substring is in the
    request URL. Unmocked URLs raise ``AssertionError`` (fail-loud
    matches production HttpFetcher behavior).
    """

    routes: dict[str, bytes | str] = field(default_factory=dict)
    calls: list[FetchCall] = field(default_factory=list)

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        self.calls.append(FetchCall(url, cache_key, throttle, max_retries))
        return self._lookup(url)

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        self.calls.append(FetchCall(url, "", throttle, 0))
        return self._lookup(url)

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        self.calls.append(FetchCall(url, "", throttle, max_retries))
        return self._lookup(url)

    def _lookup(self, url: str) -> bytes:
        for suffix, content in self.routes.items():
            if suffix in url:
                return content.encode("utf-8") if isinstance(content, str) else content
        msg = f"unmocked URL: {url}"
        raise AssertionError(msg)

    def urls_fetched(self) -> Sequence[str]:
        """Convenience for assertions on which URLs were touched."""
        return [c.url for c in self.calls]
