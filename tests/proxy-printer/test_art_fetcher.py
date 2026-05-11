"""Tests for ``mtg_utils.art_fetcher``.

HTTP is fully mocked — no real network calls. The mock targets the
``requests.Session.get`` method (the only HTTP surface the fetcher uses)
and returns canned responses keyed by URL.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mtg_utils import art_fetcher
from mtg_utils.art_fetcher import (
    ASCIIART_BASE,
    _fits,
    _parse_cards,
    _score,
    _title_matches,
    queries_for,
    run,
    select,
    write_art,
)

# ---------------------------------------------------------------------------
# HTML fragment that mirrors asciiart.eu's category-page card markup.
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<html><body>
<div class="card art-card foo"
     data-id="123"
     data-title="Vampire Bat"
     data-artist="Jane Doe"
     data-height="10"
     data-width="20">
  <div class="art-card__ascii">  /\\__/\\
( o.o )
 &gt; ^ &lt;</div>
</div>
<div class="card art-card other"
     data-id="456"
     data-title="Giant Spider"
     data-artist="John Smith"
     data-height="40"
     data-width="50">
  <div class="art-card__ascii">/\\___/\\</div>
</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# Pure-logic units.
# ---------------------------------------------------------------------------


def test_parse_cards_extracts_fields() -> None:
    cards = _parse_cards(SAMPLE_HTML, "animals/bats")
    assert len(cards) == 2
    bat = cards[0]
    assert bat["id"] == "123"
    assert bat["title"] == "Vampire Bat"
    assert bat["artist"] == "Jane Doe"
    assert bat["height"] == 10
    assert bat["width"] == 20
    assert "/\\__/\\" in bat["art"]
    # HTML entities resolved.
    assert "> ^ <" in bat["art"]
    assert bat["source_path"] == "animals/bats"


def test_parse_cards_returns_empty_on_no_matches() -> None:
    assert _parse_cards("<html>nothing here</html>", "x") == []


def test_fits_target_card() -> None:
    card = {"width": 20, "height": 10}
    assert _fits(card)


def test_fits_rejects_oversize() -> None:
    assert not _fits({"width": 40, "height": 10})
    assert not _fits({"width": 20, "height": 20})


def test_score_prefers_target_dimensions() -> None:
    target = {"width": 20, "height": 10}
    too_small = {"width": 8, "height": 4}
    too_wide = {"width": 28, "height": 10}
    assert _score(target) < _score(too_small)
    assert _score(target) < _score(too_wide)


def test_title_matches_word_boundary() -> None:
    card = {"title": "Vampire Bat"}
    assert _title_matches(card, "bat")
    assert _title_matches(card, "vampire")
    # 'at' is a substring of Bat but not a word — should not match.
    assert not _title_matches(card, "at")


def test_queries_for_uses_synonyms() -> None:
    # 'ape' has a synonym list in art_fetcher.SYNONYMS.
    qs = queries_for("ape")
    assert qs[0] == "ape"
    assert "gorilla" in qs
    assert "monkey" in qs


def test_queries_for_no_synonyms() -> None:
    # 'vampire' isn't in SYNONYMS — just the bare query.
    assert queries_for("vampire") == ["vampire"]


def test_select_picks_best_in_budget() -> None:
    pool = [
        {"title": "Bat tiny", "artist": "x", "width": 6, "height": 3,
         "source_path": "a", "art": "x"},
        {"title": "Bat big-but-fits", "artist": "x", "width": 20, "height": 10,
         "source_path": "a", "art": "x"},
        {"title": "Bat too big", "artist": "x", "width": 50, "height": 50,
         "source_path": "a", "art": "x"},
    ]
    chosen = select(["bat"], pool)
    assert chosen is not None
    assert chosen["title"] == "Bat big-but-fits"


def test_select_returns_none_when_no_match() -> None:
    pool = [
        {"title": "Spider", "artist": "x", "width": 20, "height": 10,
         "source_path": "a", "art": "x"},
    ]
    assert select(["bat"], pool) is None


def test_select_falls_through_to_synonyms() -> None:
    pool = [
        {"title": "Gorilla portrait", "artist": "x", "width": 20, "height": 10,
         "source_path": "a", "art": "x"},
    ]
    # No 'ape' match — but synonym 'gorilla' is in the pool.
    chosen = select(queries_for("ape"), pool)
    assert chosen is not None
    assert chosen["title"] == "Gorilla portrait"


# ---------------------------------------------------------------------------
# Writer — contract with proxy_print._try_read_attributed.
# ---------------------------------------------------------------------------


def test_write_art_emits_three_header_lines(tmp_path: Path) -> None:
    card = {
        "title": "Vampire Bat",
        "artist": "Jane Doe (jd)",
        "width": 20,
        "height": 10,
        "art": "  /\\__/\\\n ( o.o )",
        "source_path": "animals/bats",
    }
    path = write_art(tmp_path, "bat", card)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Vampire Bat (by Jane Doe (jd))"
    assert lines[1] == f"# Source: {ASCIIART_BASE}/animals/bats"
    assert lines[2].startswith("# Used with attribution per ")
    # Blank separator, then the art body.
    assert lines[3] == ""
    assert "/\\__/\\" in text


def test_write_art_round_trips_with_proxy_print(tmp_path: Path, monkeypatch) -> None:
    """Header written by write_art must parse cleanly with _try_read_attributed."""
    from mtg_utils import proxy_print
    from mtg_utils.proxy_print import _try_read_attributed

    card = {
        "title": "Vampire Bat",
        "artist": "Jane Doe",
        "width": 20,
        "height": 10,
        "art": "art-body-marker",
        "source_path": "animals/bats",
    }
    write_art(tmp_path, "bat", card)

    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    result = _try_read_attributed("bat")
    assert result is not None
    body, artist = result
    assert artist == "Jane Doe"
    assert "art-body-marker" in body
    # Header lines must NOT leak into the art body.
    assert "Vampire Bat (by" not in body
    assert "Source:" not in body


# ---------------------------------------------------------------------------
# Mocked-HTTP end-to-end: fetch_subtypes / build_pool / run().
# ---------------------------------------------------------------------------


def _mock_session(routes: dict[str, bytes | str]) -> MagicMock:
    """Build a mock requests.Session whose .get(url) returns canned bytes.

    Keys are matched against the URL suffix (anything after the host) so
    tests don't have to type the full URL.
    """
    session = MagicMock()
    session.headers = {}

    def fake_get(url: str, **_kwargs: object) -> MagicMock:
        body: bytes | str | None = None
        for suffix, content in routes.items():
            if suffix in url:
                body = content
                break
        if body is None:
            msg = f"unmocked URL: {url}"
            raise AssertionError(msg)
        resp = MagicMock()
        resp.content = body.encode("utf-8") if isinstance(body, str) else body
        resp.raise_for_status = MagicMock()
        return resp

    session.get = MagicMock(side_effect=fake_get)
    return session


def test_fetch_subtypes_collects_and_slugs(tmp_path: Path) -> None:
    catalog_blob = json.dumps({"data": ["Vampire", "Knight", "Eldrazi Spawn"]})
    routes = {f"/catalog/{cat}": catalog_blob for cat in art_fetcher.SCRYFALL_CATALOGS}
    session = _mock_session(routes)
    subs = art_fetcher.fetch_subtypes(session, tmp_path)
    assert "vampire" in subs
    assert "knight" in subs
    assert "eldrazi-spawn" in subs
    # Sorted and deduped.
    assert subs == sorted(set(subs))


def test_build_pool_parses_every_category(tmp_path: Path) -> None:
    routes = {f"/{cat}": SAMPLE_HTML for cat in art_fetcher.CATEGORIES}
    session = _mock_session(routes)
    pool = art_fetcher.build_pool(session, tmp_path)
    # SAMPLE_HTML has 2 cards, times N categories.
    assert len(pool) == 2 * len(art_fetcher.CATEGORIES)
    # Each card retains its source_path.
    sources = {c["source_path"] for c in pool}
    assert sources == set(art_fetcher.CATEGORIES)


def test_run_end_to_end_writes_attributed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full pipeline: mocked Scryfall + asciiart.eu → real .txt files on disk."""
    catalog_blob = json.dumps({"data": ["Vampire"]})
    routes: dict[str, bytes | str] = {
        f"/catalog/{cat}": catalog_blob for cat in art_fetcher.SCRYFALL_CATALOGS
    }
    # One category page that contains a Vampire-titled card.
    vamp_html = SAMPLE_HTML.replace("Vampire Bat", "Vampire Lord")
    for cat in art_fetcher.CATEGORIES:
        routes[f"/{cat}"] = vamp_html

    session = _mock_session(routes)
    monkeypatch.setattr(art_fetcher.requests, "Session", lambda: session)

    cache = tmp_path / "cache"
    out = tmp_path / "out"
    written, skipped, missing, missing_keys = run(
        cache_dir=cache, out_dir=out, search_fallback=False
    )
    assert written == 1
    assert skipped == 0
    assert missing == 0
    assert missing_keys == []
    vampire_file = out / "vampire.txt"
    assert vampire_file.is_file()
    text = vampire_file.read_text()
    assert text.startswith("# Vampire Lord (by ")


def test_run_records_missing_when_no_fit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subtype with no candidate match ends up in missing_keys, not written."""
    catalog_blob = json.dumps({"data": ["Lhurgoyf"]})
    routes: dict[str, bytes | str] = {
        f"/catalog/{cat}": catalog_blob for cat in art_fetcher.SCRYFALL_CATALOGS
    }
    # Pool has no Lhurgoyf / monster / anything matching its synonym list.
    no_match_html = "<html>nothing</html>"
    for cat in art_fetcher.CATEGORIES:
        routes[f"/{cat}"] = no_match_html
    # Also stub the search-fallback URL so _fetch_cached doesn't raise.
    routes["/search"] = no_match_html

    session = _mock_session(routes)
    monkeypatch.setattr(art_fetcher.requests, "Session", lambda: session)

    written, _skipped, missing, missing_keys = run(
        cache_dir=tmp_path / "cache",
        out_dir=tmp_path / "out",
        search_fallback=True,
    )
    assert written == 0
    assert missing == 1
    assert "lhurgoyf" in missing_keys


def test_run_skips_known_non_art_subtypes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SKIP_SUBTYPES (e.g. 'treasure', 'saga') never trigger a write."""
    # Pick a subtype that's both in Scryfall and in SKIP_SUBTYPES.
    assert "treasure" in art_fetcher.SKIP_SUBTYPES
    catalog_blob = json.dumps({"data": ["Treasure"]})
    routes: dict[str, bytes | str] = {
        f"/catalog/{cat}": catalog_blob for cat in art_fetcher.SCRYFALL_CATALOGS
    }
    for cat in art_fetcher.CATEGORIES:
        routes[f"/{cat}"] = SAMPLE_HTML

    session = _mock_session(routes)
    monkeypatch.setattr(art_fetcher.requests, "Session", lambda: session)

    written, skipped, _missing, _missing_keys = run(
        cache_dir=tmp_path / "cache",
        out_dir=tmp_path / "out",
        search_fallback=False,
    )
    assert written == 0
    assert skipped == 1
    assert not (tmp_path / "out" / "treasure.txt").exists()
