"""Tests for ``mtg_utils.art_fetcher``.

HTTP is fully mocked via the :class:`FakeFetcher` in `_fake_fetcher.py`
— no real network calls. Tests construct a ``FakeFetcher`` with a
``routes`` dict mapping URL substrings to canned bytes, then pass it
to the function under test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _fake_fetcher import FakeFetcher

from mtg_utils import art_fetcher
from mtg_utils.art_fetcher import (
    ASCIIART_BASE,
    HttpFetcher,
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
# End-to-end tests against the Fetcher seam.
# ---------------------------------------------------------------------------


def test_fetch_subtypes_collects_and_slugs() -> None:
    catalog_blob = json.dumps({"data": ["Vampire", "Knight", "Eldrazi Spawn"]})
    routes = {f"/catalog/{cat}": catalog_blob for cat in art_fetcher.SCRYFALL_CATALOGS}
    fetcher = FakeFetcher(routes=routes)
    subs = art_fetcher.fetch_subtypes(fetcher)
    assert "vampire" in subs
    assert "knight" in subs
    assert "eldrazi-spawn" in subs
    # Sorted and deduped.
    assert subs == sorted(set(subs))


def test_build_pool_parses_every_category() -> None:
    routes = {f"/{cat}": SAMPLE_HTML for cat in art_fetcher.CATEGORIES}
    # Stub the asciiart.website source with an empty browse so this test
    # stays focused on asciiart.eu coverage.
    routes["/browse.php"] = "<html>no categories</html>"
    fetcher = FakeFetcher(routes=routes)
    pool = art_fetcher.build_pool(fetcher)
    # SAMPLE_HTML has 2 cards, times N categories.
    assert len(pool) == 2 * len(art_fetcher.CATEGORIES)
    # Each card retains its source_path.
    sources = {c["source_path"] for c in pool}
    assert sources == set(art_fetcher.CATEGORIES)
    # All cards come from the eu source.
    assert all(c["_source"] == "eu" for c in pool)


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
    routes["/browse.php"] = "<html>no categories</html>"

    fetcher = FakeFetcher(routes=routes)
    monkeypatch.setattr(art_fetcher, "HttpFetcher", lambda **_kw: fetcher)

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
    routes["/browse.php"] = "<html>no categories</html>"

    fetcher = FakeFetcher(routes=routes)
    monkeypatch.setattr(art_fetcher, "HttpFetcher", lambda **_kw: fetcher)

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
    routes["/browse.php"] = "<html>no categories</html>"

    fetcher = FakeFetcher(routes=routes)
    monkeypatch.setattr(art_fetcher, "HttpFetcher", lambda **_kw: fetcher)

    written, skipped, _missing, _missing_keys = run(
        cache_dir=tmp_path / "cache",
        out_dir=tmp_path / "out",
        search_fallback=False,
    )
    assert written == 0
    assert skipped == 1
    assert not (tmp_path / "out" / "treasure.txt").exists()


# ---------------------------------------------------------------------------
# asciiart.website source.
# ---------------------------------------------------------------------------

WEBSITE_BROWSE_HTML = """<html><body>
<a href="tag.php?tag_id=12" onclick="x">
  Aardvarks  <span class="tag-count">(4)</span>
</a>
<a href="tag.php?tag_id=47" onclick="y">
  Dinosaurs  <span class="tag-count">(31)</span>
</a>
<a href="tag.php?tag_id=474" onclick="z">
  Big Cats  <span class="tag-count">(38)</span>
</a>
</body></html>"""

WEBSITE_CAT_HTML = """<html><body>
<script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "Category: Big Cats",
    "hasPart": [
        {
            "@type": "CreativeWork",
            "name": "Lion King",
            "url": "https://asciiart.website/art/100",
            "author": {"@type": "Person", "name": "Alice Author"}
        },
        {
            "@type": "CreativeWork",
            "name": "Tiger Stripes",
            "url": "https://asciiart.website/art/101",
            "author": {"@type": "Person", "name": "Bob Builder"}
        }
    ]
}</script>
<pre data-artwork-id="100" id="artwork-pre-100">  /\\___/\\
 ( o.o )
  > ^ <</pre>
<pre data-artwork-id="101" id="artwork-pre-101">  /\\___/\\
 ( T.T )</pre>
</body></html>"""


def test_parse_cards_website_zips_jsonld_with_pre_bodies() -> None:
    cards = art_fetcher._parse_cards_website(WEBSITE_CAT_HTML, "Big Cats")
    assert len(cards) == 2
    by_id = {c["id"]: c for c in cards}
    lion = by_id["100"]
    assert lion["_source"] == "website"
    assert lion["title"] == "Lion King"
    assert lion["artist"] == "Alice Author"
    assert lion["url"] == "https://asciiart.website/art/100"
    assert "/\\___/\\" in lion["art"]
    assert lion["source_path"] == "Big Cats"
    # Dimensions computed from the art body.
    assert lion["height"] == 3
    assert lion["width"] >= 8


def test_parse_cards_website_skips_pre_without_metadata() -> None:
    """Orphan <pre> blocks (no matching JSON-LD entry) are silently skipped."""
    text = """<html><body>
<script type="application/ld+json">{
    "@type": "CollectionPage",
    "hasPart": [{"@type": "CreativeWork", "name": "X", "url": "https://asciiart.website/art/1"}]
}</script>
<pre data-artwork-id="1">art</pre>
<pre data-artwork-id="999">orphan art</pre>
</body></html>"""
    cards = art_fetcher._parse_cards_website(text, "cat")
    assert len(cards) == 1
    assert cards[0]["id"] == "1"


def test_fetch_website_tags_parses_browse_page() -> None:
    routes = {"/browse.php": WEBSITE_BROWSE_HTML}
    fetcher = FakeFetcher(routes=routes)
    cats = art_fetcher.fetch_website_tags(fetcher)
    by_id = dict(cats)
    assert by_id["12"] == "Aardvarks"
    assert by_id["47"] == "Dinosaurs"
    assert by_id["474"] == "Big Cats"


def test_build_pool_merges_both_sources() -> None:
    """build_pool combines asciiart.eu CATEGORIES + asciiart.website cats."""
    routes: dict[str, bytes | str] = {
        f"/{cat}": SAMPLE_HTML for cat in art_fetcher.CATEGORIES
    }
    routes["/browse.php"] = WEBSITE_BROWSE_HTML
    routes["/tag.php?tag_id=12&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=12&page=2"] = "<html>nothing more</html>"
    routes["/tag.php?tag_id=47&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=47&page=2"] = "<html>nothing more</html>"
    routes["/tag.php?tag_id=474&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=474&page=2"] = "<html>nothing more</html>"
    fetcher = FakeFetcher(routes=routes)
    # No subtypes passed -> no filter; all 3 mocked cats fetched.
    pool = art_fetcher.build_pool(fetcher)
    sources = {c["_source"] for c in pool}
    assert sources == {"eu", "website"}
    eu_count = sum(1 for c in pool if c["_source"] == "eu")
    web_count = sum(1 for c in pool if c["_source"] == "website")
    assert eu_count == 2 * len(art_fetcher.CATEGORIES)
    # 3 mocked cats, 2 cards each.
    assert web_count == 6


def test_build_pool_filters_website_cats_by_subtype() -> None:
    """When subtypes are supplied, only matching-name cats are fetched."""
    routes: dict[str, bytes | str] = {
        f"/{cat}": SAMPLE_HTML for cat in art_fetcher.CATEGORIES
    }
    # Three mocked cats: Aardvarks (no MTG match), Dinosaurs (Dinosaur is a
    # subtype), Big Cats (cat is a subtype).
    routes["/browse.php"] = WEBSITE_BROWSE_HTML
    routes["/tag.php?tag_id=12&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=12&page=2"] = "<html>nothing more</html>"
    routes["/tag.php?tag_id=47&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=47&page=2"] = "<html>nothing more</html>"
    routes["/tag.php?tag_id=474&page=1"] = WEBSITE_CAT_HTML
    routes["/tag.php?tag_id=474&page=2"] = "<html>nothing more</html>"
    fetcher = FakeFetcher(routes=routes)

    art_fetcher.build_pool(fetcher, subtypes=["dinosaur", "cat"])
    # Aardvark tag was skipped (browse.php fetched but tag.php skipped).
    # Verify we fetched only the matching two tag.php URLs.
    fetched_tag_urls = [
        u for u in fetcher.urls_fetched() if "tag.php?tag_id=" in u
    ]
    assert any("tag_id=47" in u for u in fetched_tag_urls)
    assert any("tag_id=474" in u for u in fetched_tag_urls)
    assert not any("tag_id=12" in u for u in fetched_tag_urls)


@pytest.mark.parametrize(
    ("tok", "expected_stems"),
    [
        ("cats", {"cats", "cat"}),                # regular -s plural
        ("foxes", {"foxes", "foxe", "fox"}),      # -es plural
        ("butterflies", {"butterflies", "butterfly", "butterflie"}),  # -ies → -y
        ("wolves", {"wolves", "wolf"}),           # irregular -ves
        ("mice", {"mice", "mouse"}),              # full irregular
        ("dragon", {"dragon"}),                   # singular, no stem
        ("ox", {"ox"}),                            # too short to strip
    ],
)
def test_stems_covers_plural_variants(tok: str, expected_stems: set[str]) -> None:
    """_stems returns every form we'll test the keyword set against."""
    actual = set(art_fetcher._stems(tok))
    assert expected_stems <= actual, (
        f"missing stems for {tok!r}: expected {expected_stems - actual}"
    )


def test_relevant_keywords_includes_every_subtype_token() -> None:
    """Every Scryfall subtype's tokens land in the keyword set."""
    subtypes = ["vampire", "eldrazi-spawn", "phyrexian"]
    keywords = art_fetcher._relevant_keywords(subtypes)
    assert "vampire" in keywords
    # Compound subtype slugs are split on '-' and each token is added.
    assert "eldrazi" in keywords
    assert "spawn" in keywords
    assert "phyrexian" in keywords


def test_relevant_keywords_includes_synonym_targets() -> None:
    """Synonym targets (e.g. 'gorilla' from ape→gorilla) land in keywords."""
    keywords = art_fetcher._relevant_keywords([])
    # 'ape' has synonyms gorilla, monkey in SYNONYMS.
    assert "gorilla" in keywords
    assert "monkey" in keywords
    # MTG-adjacent words are always present.
    assert "animal" in keywords
    assert "weapon" in keywords


def test_relevant_tags_keeps_subtype_matches() -> None:
    cats = [
        ("12", "Aardvarks"),
        ("47", "Dinosaurs"),
        ("474", "Big Cats"),
        ("999", "Star Wars"),
    ]
    out = art_fetcher.relevant_tags(cats, ["dinosaur", "cat"])
    names = {n for _, n in out}
    assert "Dinosaurs" in names  # plural matches singular subtype
    assert "Big Cats" in names    # word-level match
    assert "Star Wars" not in names
    assert "Aardvarks" not in names  # aardvark isn't an MTG subtype


def test_relevant_tags_drops_franchise_tags() -> None:
    """Franchise tags get dropped even though their names match an MTG keyword."""
    tags = [
        ("1", "Lion King"),         # lion matches Cat synonym
        ("2", "Donald Duck"),       # duck matches PW synonym
        ("3", "Dragon Ball"),       # dragon matches Dragon subtype
        ("4", "Star Wars"),         # broad franchise (would pollute many subtypes)
        ("5", "Disney"),            # broad franchise
        ("6", "Dragon"),            # legit
        ("7", "Lion"),              # legit
    ]
    out = art_fetcher.relevant_tags(tags, ["lion", "dragon"])
    names = {n for _, n in out}
    assert "Lion King" not in names
    assert "Donald Duck" not in names
    assert "Dragon Ball" not in names
    assert "Star Wars" not in names
    assert "Disney" not in names
    assert "Dragon" in names
    assert "Lion" in names


def test_franchise_skip_uses_case_insensitive_match() -> None:
    """Mixed-case tag names are skipped regardless of original casing."""
    tags = [
        ("1", "LION KING"),
        ("2", "Lion King"),
        ("3", "lion king"),
    ]
    out = art_fetcher.relevant_tags(tags, ["lion"])
    assert out == []


def test_subtypes_in_deck_extracts_from_type_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """subtypes_in_deck() returns the union of subtypes used by all deck cards
    plus the subtypes of every token the deck's cards can generate."""
    deck = {
        "commanders": [{"name": "Atraxa", "quantity": 1}],
        "cards": [
            {"name": "Llanowar Elves", "quantity": 1},
            {"name": "Goblin Chieftain", "quantity": 1},  # generates Goblin tokens
        ],
        "sideboard": [{"name": "Phyrexian Arena", "quantity": 1}],
    }
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(deck))

    # Bulk index mock: by_name has the main cards (with all_parts links);
    # by_id has the token records they reference.
    fake_by_name = {
        "atraxa": {"type_line": "Legendary Creature — Phyrexian Angel"},
        "llanowar elves": {"type_line": "Creature — Elf Druid"},
        "phyrexian arena": {"type_line": "Enchantment"},
        "goblin chieftain": {
            "type_line": "Creature — Goblin",
            "oracle_id": "gc",
            "all_parts": [
                {"id": "tok1", "name": "Soldier", "component": "token"},
            ],
        },
    }
    fake_by_id = {
        "tok1": {
            "id": "tok1",
            "name": "Soldier",
            "layout": "token",
            "type_line": "Token Creature — Soldier",
            "oracle_id": "soldier-oid",
        },
    }
    monkeypatch.setattr(
        "mtg_utils.deck.load_bulk_indexes",
        lambda _p: (fake_by_name, fake_by_id),
    )

    out = art_fetcher.subtypes_in_deck(deck_path, tmp_path / "fake-bulk")
    # Main-card subtypes
    assert "phyrexian" in out
    assert "angel" in out
    assert "elf" in out
    assert "druid" in out
    assert "goblin" in out
    # Card types
    assert "creature" in out
    assert "enchantment" in out
    # Token subtypes (Soldier from Goblin Chieftain's all_parts)
    assert "soldier" in out


# ---------------------------------------------------------------------------
# Name-keyed fetch (--by-name).
# ---------------------------------------------------------------------------


def test_fetch_by_name_writes_file_on_hit(tmp_path: Path) -> None:
    """A successful search yields <name-slug>.txt with the right header."""
    routes = {"/search": SAMPLE_HTML}
    fetcher = FakeFetcher(routes=routes)
    out_dir = tmp_path / "attributed"
    out_dir.mkdir()
    ok = art_fetcher.fetch_by_name(fetcher, "Vampire Bat Lord", out_dir)
    assert ok is True
    path = out_dir / "vampire-bat-lord.txt"
    assert path.is_file()
    head = path.read_text(encoding="utf-8").splitlines()[0]
    # The SAMPLE_HTML's two cards have widths 20 and 50; only the 20-wide
    # (Vampire Bat) fits the budget, so that's what gets written.
    assert "Vampire Bat" in head


def test_fetch_by_name_skips_when_no_fitting_hit(tmp_path: Path) -> None:
    """Search returns nothing → no file, returns False."""
    routes = {"/search": "<html>nothing here</html>"}
    fetcher = FakeFetcher(routes=routes)
    out_dir = tmp_path / "attributed"
    out_dir.mkdir()
    ok = art_fetcher.fetch_by_name(fetcher, "Definitely Not A Card", out_dir)
    assert ok is False
    assert not any(out_dir.iterdir())


def test_fetch_by_name_skips_existing_file(tmp_path: Path) -> None:
    """Existing <name-slug>.txt isn't clobbered; the fetch returns False."""
    out_dir = tmp_path / "attributed"
    out_dir.mkdir()
    pre = out_dir / "lightning-bolt.txt"
    pre.write_text("# Hand-curated, do not overwrite\n\nART\n")
    routes = {"/search": SAMPLE_HTML}
    fetcher = FakeFetcher(routes=routes)
    ok = art_fetcher.fetch_by_name(fetcher, "Lightning Bolt", out_dir)
    assert ok is False
    # Original content preserved.
    assert "Hand-curated" in pre.read_text(encoding="utf-8")


def test_fetch_by_name_overwrite_true_does_overwrite(tmp_path: Path) -> None:
    out_dir = tmp_path / "attributed"
    out_dir.mkdir()
    (out_dir / "vampire-bat.txt").write_text("# old\n\nold-art\n")
    routes = {"/search": SAMPLE_HTML}
    fetcher = FakeFetcher(routes=routes)
    ok = art_fetcher.fetch_by_name(fetcher, "Vampire Bat", out_dir, overwrite=True)
    assert ok is True
    text = (out_dir / "vampire-bat.txt").read_text(encoding="utf-8")
    assert "old-art" not in text


def test_fetch_by_name_empty_name_returns_false(tmp_path: Path) -> None:
    fetcher = FakeFetcher(routes={"/search": SAMPLE_HTML})
    assert art_fetcher.fetch_by_name(fetcher, "", tmp_path) is False


def test_distinct_card_names_walks_deck() -> None:
    """_distinct_card_names returns each name once, front-face only for DFC."""
    deck = {
        "commanders": [{"name": "Atraxa"}],
        "cards": [
            {"name": "Llanowar Elves"},
            {"name": "Llanowar Elves"},  # duplicate
            {"name": "Delver of Secrets // Insectile Aberration"},  # DFC
        ],
        "sideboard": [{"name": "Phyrexian Arena"}],
    }
    names = art_fetcher._distinct_card_names(deck)
    assert names == [
        "Atraxa",
        "Llanowar Elves",
        "Delver of Secrets",
        "Phyrexian Arena",
    ]


def test_alien_and_tolkien_are_not_skipped() -> None:
    """Per user preference, Alien (impossible to distinguish from generic
    alien) and Lord Of The Rings (user has LOTR MTG cards) stay in the pool.
    """
    tags = [
        ("1", "Alien"),
        ("2", "Lord Of The Rings / Tolkien"),
    ]
    out = art_fetcher.relevant_tags(tags, ["alien", "wizard"])
    names = {n for _, n in out}
    assert "Alien" in names
    assert "Lord Of The Rings / Tolkien" in names


def test_fetch_website_tags_decodes_html_entities() -> None:
    """Names like 'Wallace &amp; Gromit' come back HTML-decoded."""
    html_blob = (
        '<a href="tag.php?tag_id=212" onclick="">'
        '  Wallace &amp; Gromit  <span class="tag-count">(7)</span>'
        '</a>'
        '<a href="tag.php?tag_id=576" onclick="">'
        '  Blue&#039;s Clues  <span class="tag-count">(3)</span>'
        "</a>"
    )
    routes = {"/browse.php": html_blob}
    fetcher = FakeFetcher(routes=routes)
    cats = art_fetcher.fetch_website_tags(fetcher)
    by_id = dict(cats)
    assert by_id["212"] == "Wallace & Gromit"
    assert by_id["576"] == "Blue's Clues"


def test_relevant_tags_keeps_mtg_adjacent_parents() -> None:
    """'Animals (Other) (Land)' and 'Weapons (Swords)' parent categories stay."""
    cats = [
        ("1", "Animals (Other) (Land)"),
        ("2", "Weapons (Swords)"),
        ("3", "The Office"),
    ]
    out = art_fetcher.relevant_tags(cats, [])
    names = {n for _, n in out}
    assert "Animals (Other) (Land)" in names
    assert "Weapons (Swords)" in names
    assert "The Office" not in names


def test_write_art_website_header_uses_per_art_url(tmp_path: Path) -> None:
    """A website-source card's header points at the per-art URL + website FAQ."""
    card = {
        "_source": "website",
        "id": "100",
        "title": "Lion King",
        "artist": "Alice Author",
        "width": 8,
        "height": 3,
        "art": "  /\\___/\\\n ( o.o )\n  > ^ <",
        "source_path": "Big Cats",
        "url": "https://asciiart.website/art/100",
    }
    path = write_art(tmp_path, "lion", card)
    text = path.read_text()
    lines = text.splitlines()
    assert lines[0] == "# Lion King (by Alice Author)"
    assert lines[1] == "# Source: https://asciiart.website/art/100"
    # asciiart.website doesn't grant a blanket license; we say so honestly.
    assert "Personal-use" in lines[2]
    assert "no explicit license grant" in lines[2]


def test_fetch_tag_pages_respects_max_pages_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With MAX_PAGES_PER_TAG=2, only pages 1 and 2 are fetched even if more exist."""
    monkeypatch.setattr(art_fetcher, "MAX_PAGES_PER_TAG", 2)
    page2 = WEBSITE_CAT_HTML.replace('"100"', '"200"').replace('"101"', '"201"')
    page2 = page2.replace("art/100", "art/200").replace("art/101", "art/201")
    routes = {
        "/tag.php?tag_id=129&page=1": WEBSITE_CAT_HTML,
        "/tag.php?tag_id=129&page=2": page2,
        "/tag.php?tag_id=129&page=3": page2,  # would loop forever without cap
    }
    fetcher = FakeFetcher(routes=routes)
    cards = art_fetcher._fetch_tag_pages(fetcher, "129", "Lion")
    ids = sorted(c["id"] for c in cards)
    assert ids == ["100", "101", "200", "201"]
    # Cap was 2, so we never fetched page 3.
    assert len(fetcher.calls) == 2


def test_fetch_tag_pages_stops_when_no_new_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dedup-by-id loop terminates early when a page adds nothing new."""
    monkeypatch.setattr(art_fetcher, "MAX_PAGES_PER_TAG", 5)
    routes = {
        "/tag.php?tag_id=129&page=1": WEBSITE_CAT_HTML,
        # Page 2 repeats page 1 — no new IDs → loop stops immediately.
        "/tag.php?tag_id=129&page=2": WEBSITE_CAT_HTML,
    }
    fetcher = FakeFetcher(routes=routes)
    cards = art_fetcher._fetch_tag_pages(fetcher, "129", "Lion")
    assert sorted(c["id"] for c in cards) == ["100", "101"]
    # Page 1 + page 2 fetched; stopped because page 2 had no new IDs.
    assert len(fetcher.calls) == 2


# ---------------------------------------------------------------------------
# HttpFetcher retry behaviour (uses MagicMock on the private session).
# ---------------------------------------------------------------------------


def test_http_fetcher_retries_on_429(tmp_path: Path, monkeypatch) -> None:
    """A 429 followed by a 200 retries and succeeds."""
    monkeypatch.setattr(art_fetcher.time, "sleep", lambda _: None)
    from unittest.mock import MagicMock
    fetcher = HttpFetcher(cache_dir=tmp_path)
    fetcher._session = MagicMock()
    fetcher._session.get = MagicMock(side_effect=[
        MagicMock(status_code=429, content=b"slow down", raise_for_status=MagicMock()),
        MagicMock(status_code=200, content=b"ok", raise_for_status=MagicMock()),
    ])

    result = fetcher.fetch("https://x/y", "cached.bin", max_retries=2)
    assert result == b"ok"
    assert fetcher._session.get.call_count == 2


def test_http_fetcher_raises_after_exhausted_retries(tmp_path: Path, monkeypatch) -> None:
    """Persistent 429s eventually raise via raise_for_status."""
    monkeypatch.setattr(art_fetcher.time, "sleep", lambda _: None)
    from unittest.mock import MagicMock
    fetcher = HttpFetcher(cache_dir=tmp_path)

    def make_429() -> MagicMock:
        resp = MagicMock(status_code=429, content=b"slow down")
        resp.raise_for_status = MagicMock(
            side_effect=art_fetcher.requests.HTTPError("429")
        )
        return resp

    fetcher._session = MagicMock()
    fetcher._session.get = MagicMock(side_effect=[make_429() for _ in range(3)])

    with pytest.raises(art_fetcher.requests.HTTPError):
        fetcher.fetch("https://x/y", "cached.bin", max_retries=2)


def test_write_art_website_round_trips(tmp_path: Path, monkeypatch) -> None:
    """proxy_print._try_read_attributed parses the website header too."""
    from mtg_utils import proxy_print
    from mtg_utils.proxy_print import _try_read_attributed

    card = {
        "_source": "website",
        "id": "100",
        "title": "Lion King",
        "artist": "Alice Author",
        "width": 8,
        "height": 3,
        "art": "lion-art-marker",
        "source_path": "Big Cats",
        "url": "https://asciiart.website/art/100",
    }
    write_art(tmp_path, "lion", card)

    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    result = _try_read_attributed("lion")
    assert result is not None
    body, artist = result
    assert artist == "Alice Author"
    assert "lion-art-marker" in body
