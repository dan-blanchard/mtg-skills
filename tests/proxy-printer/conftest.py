"""proxy-printer test setup: no test fetches card symbols over the network."""

from __future__ import annotations

import pytest
import requests

from mtg_utils import card_symbols


class _OfflineFetcher:
    """Stands in for ``HttpFetcher``: every fetch fails like a dead network."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def fetch(self, url, cache_key, **_kwargs) -> bytes:
        raise requests.ConnectionError(f"tests are offline: {url}")


@pytest.fixture(autouse=True)
def offline_card_symbols(monkeypatch):
    """``SymbolSet.load`` with no fetcher builds an ``HttpFetcher`` on the real
    cache; replace it so a CLI test prints symbols as text instead of fetching
    (or reading the developer's cached images)."""
    monkeypatch.setattr(card_symbols, "HttpFetcher", _OfflineFetcher)
