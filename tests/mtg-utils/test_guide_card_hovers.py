"""guide-card-hovers / twohg-template: a guide page's card-hover map and images."""

import json
import re

import pytest
from click.testing import CliRunner

from mtg_utils.guide_card_hovers import (
    build_hovers,
    card_slug,
    find_names,
    guide_text,
    image_url,
    read_template,
    replace_cards_map,
    template_main,
)
from mtg_utils.testkit import test_card, test_printing

SET = "tst"


def _printing(name, number):
    """A real card as one printing in the test set, with a fake image URL."""
    pid = f"id-{number}"
    return {
        **test_printing(name, SET, number),
        "id": pid,
        "image_uris": {"normal": f"https://img.test/{pid}.jpg"},
    }


def _fictional(name, faces, number):
    """A synthetic multi-face card (obviously fictional) — for the face-name
    ambiguity machinery, which no pair of real cards exercises."""
    pid = f"id-{number}"
    return {
        "name": " // ".join(faces),
        "oracle_id": f"oracle-{name}",
        "set": SET,
        "collector_number": number,
        "promo": False,
        "id": pid,
        "card_faces": [
            {"name": f, "image_uris": {"normal": f"https://img.test/{pid}-{i}.jpg"}}
            for i, f in enumerate(faces)
        ],
    }


def _page(body):
    return (
        "<title>Test guide</title><h2>Lightning Bolt heading</h2>"
        f'<div class="cols">{body}</div>'
        "<footer>Gray Merchant of Asphodel in the footer</footer>"
        "<script>\n(() => {\n  const CARDS = {};\n})();\n</script>"
    )


class FakeFetcher:
    """A dict-backed ``_http.Fetcher``: a cache key it holds is a hit; anything else
    is a "network" fetch, recorded in ``urls`` with the throttle it was asked for."""

    def __init__(self):
        self.cache: dict[str, bytes] = {}
        self.urls: list[str] = []
        self.throttles: list[float] = []

    def fetch(self, url, cache_key, *, throttle=0.0, max_retries=2):
        if cache_key not in self.cache:
            self.urls.append(url)
            self.throttles.append(throttle)
            self.cache[cache_key] = f"image bytes for {url}".encode()
        return self.cache[cache_key]

    def fetch_uncached(self, url, *, throttle=0.0):
        raise NotImplementedError

    def post_form(self, url, *, form_fields, throttle=0.0, max_retries=2):
        raise NotImplementedError


@pytest.fixture
def printings():
    """One printing per card, as ``CardPool.set_records`` lists a set."""
    return [
        _printing("Lightning Bolt", "12"),
        _printing("Murder", "40"),
        _printing("Bosh, Iron Golem", "200"),
        _printing("Iron Golem", "201"),
        {
            **test_printing("Bonecrusher Giant // Stomp", SET, "90"),
            "id": "id-90",
            "card_faces": [
                {**face, "image_uris": {"normal": f"https://img.test/id-90-{i}.jpg"}}
                for i, face in enumerate(
                    test_card("Bonecrusher Giant // Stomp")["card_faces"]
                )
            ],
        },
        _printing("Gray Merchant of Asphodel", "70"),
        _fictional("zzyx", ["Zzyx Testwing", "Shared Refrain"], "301"),
        _fictional("qqor", ["Qqor Testmaw", "Shared Refrain"], "302"),
    ]


# --- Text and names ------------------------------------------------------------------


def test_guide_text_spaces_tags_and_skips_links_headings_footer():
    html = _page(
        '<table><tr><td class="r">U</td><td><span class="card">Murder</span>'
        '</td></tr></table><a href="#">Iron Golem</a>'
    )
    text = guide_text(html)
    assert "UMurder" not in text
    assert re.search(r"U\s+Murder", text)
    assert "Iron Golem" not in text  # a link
    assert "heading" not in text  # an <h2>
    assert "footer" not in text
    assert "CARDS" not in text  # the script
    assert find_names(text, ["Murder", "Iron Golem"]) == ["Murder"]


def test_find_names_longest_first_and_word_boundaries():
    text = "Bosh, Iron Golem hits hard. Iron Golem too. Murderous Rider isn't Murder's."
    names = ["Iron Golem", "Bosh, Iron Golem", "Murder"]
    # Bosh's name is one match (not also "Iron Golem"); the later lone "Iron Golem"
    # is its own; "Murderous" and "Murder's" are not Murder.
    assert find_names(text, names) == ["Bosh, Iron Golem", "Iron Golem"]
    assert find_names("Only Bosh, Iron Golem here.", names) == ["Bosh, Iron Golem"]
    assert find_names("nothing", []) == []


# --- Image, slug ---------------------------------------------------------------------


def test_image_url_and_slug(printings):
    giant = next(p for p in printings if p["name"].startswith("Bonecrusher"))
    assert image_url(giant) == "https://img.test/id-90-0.jpg"
    assert card_slug(giant) == "bonecrusher-giant"
    assert card_slug(test_card("Bosh, Iron Golem")) == "bosh-iron-golem"
    assert card_slug({"name": "Lich's Relic"}) == "lichs-relic"
    assert card_slug({"name": "Émeric's Testwing"}) == "emerics-testwing"
    assert image_url({"name": "No Art"}) is None


# --- The map ---------------------------------------------------------------------------


def test_replace_cards_map():
    html = _page("")
    out = replace_cards_map(html, {"Émeric": "cards/emeric.jpg"})
    assert 'const CARDS = {"Émeric": "cards/emeric.jpg"};' in out
    # A filled map is replaced again, not appended to.
    again = replace_cards_map(out, {})
    assert "const CARDS = {};" in again
    assert "emeric" not in again
    with pytest.raises(ValueError, match="const CARDS"):
        replace_cards_map("<p>no script</p>", {})


# --- End to end --------------------------------------------------------------------------


def _guide(tmp_path, body):
    path = tmp_path / "guide.html"
    path.write_text(_page(body), encoding="utf-8")
    return path


BODY = (
    '<table><tr><td class="r">U</td><td><span class="card">Lightning Bolt</span>'
    "</td></tr></table>"
    "<p>Bosh, Iron Golem and Murder; Stomp is the adventure half. "
    "Shared Refrain is on two cards. Zzyx Testwing too.</p>"
)


def test_build_hovers_end_to_end(tmp_path, printings):
    guide = _guide(tmp_path, BODY)
    out = tmp_path / "out"
    fetcher = FakeFetcher()
    result = build_hovers(guide, printings, out_dir=out, fetcher=fetcher, throttle=0.5)
    assert result.cards_map == {
        "Bosh, Iron Golem": "cards/bosh-iron-golem.jpg",
        "Lightning Bolt": "cards/lightning-bolt.jpg",
        "Murder": "cards/murder.jpg",
        "Stomp": "cards/bonecrusher-giant.jpg",
        "Zzyx Testwing": "cards/zzyx-testwing.jpg",
    }
    # "Shared Refrain" is a face of two cards and no alias says which: skipped.
    assert result.ambiguous == {
        "Shared Refrain": [
            "Qqor Testmaw // Shared Refrain",
            "Zzyx Testwing // Shared Refrain",
        ]
    }
    # Gray Merchant (footer only) and Iron Golem (inside Bosh's name) are not matched.
    assert "https://img.test/id-201.jpg" not in fetcher.urls
    assert len(fetcher.urls) == result.cards == 5
    assert set(fetcher.throttles) == {0.5}  # every network fetch is throttled

    written = (out / "guide.html").read_text(encoding="utf-8")
    m = re.search(r"const CARDS = (\{.*?\});", written)
    assert m
    assert json.loads(m.group(1)) == result.cards_map
    assert json.loads((out / "files.json").read_text()) == [
        {"path": "cards/bonecrusher-giant.jpg"},
        {"path": "cards/bosh-iron-golem.jpg"},
        {"path": "cards/lightning-bolt.jpg"},
        {"path": "cards/murder.jpg"},
        {"path": "cards/zzyx-testwing.jpg"},
    ]
    assert (out / "cards" / "murder.jpg").read_bytes() == (
        b"image bytes for https://img.test/id-40.jpg"
    )
    assert "id-40.jpg" in fetcher.cache  # cached by Scryfall id


def test_alias_resolves_ambiguous_face_and_reuses_cache(tmp_path, printings):
    guide = _guide(tmp_path, BODY)
    fetcher = FakeFetcher()
    build_hovers(guide, printings, out_dir=tmp_path / "a", fetcher=fetcher)
    fetcher.urls.clear()
    result = build_hovers(
        guide,
        printings,
        out_dir=tmp_path / "b",
        # The CARD half folds case and accents, like any typed-in card name.
        aliases={"Shared Refrain": "QQÖR testmaw", "Not In Page": "Murder"},
        fetcher=fetcher,
    )
    assert result.cards_map["Shared Refrain"] == "cards/qqor-testmaw.jpg"
    assert result.ambiguous == {}
    assert result.unused_aliases == ["Not In Page"]
    # Only the newly-needed card is fetched; the other five are cache hits.
    assert fetcher.urls == ["https://img.test/id-302-0.jpg"]
    assert result.cards == 6


def test_alias_to_unknown_card_and_missing_map_fail(tmp_path, printings):
    guide = _guide(tmp_path, BODY)
    with pytest.raises(ValueError, match="not a card in this set"):
        build_hovers(
            guide,
            printings,
            out_dir=tmp_path / "o",
            aliases={"Shared Refrain": "Nonexistent Card"},
            fetcher=FakeFetcher(),
        )
    bare = tmp_path / "bare.html"
    bare.write_text('<div class="cols">Murder</div>', encoding="utf-8")
    fetcher = FakeFetcher()
    with pytest.raises(ValueError, match="const CARDS"):
        build_hovers(bare, printings, out_dir=tmp_path / "o", fetcher=fetcher)
    assert fetcher.urls == []  # failed before any download


# --- The template ------------------------------------------------------------------------


SECTIONS = {
    "winning": "What's winning",
    "pairing": "Team pairing",
    "x2": "The ×2 cards",
    "gotchas": "Downgrades &amp; gotchas",
    "rules": "Rules that win games",
    "bombs": "Bombs",
    "removal": "Removal",
    "checklist": "Build hour checklist",
}


def test_template_has_spine_placeholders_and_empty_map():
    html = read_template()
    assert html.count("const CARDS") == 1
    assert "const CARDS = {};" in html
    assert "{{SET_NAME}}" in html
    assert "{{DATE}}" in html
    assert '<div class="cols">' in html
    assert '<footer id="sources">' in html
    positions = []
    for sid, heading in SECTIONS.items():
        m = re.search(rf'<section id="{sid}">\s*<h2>{re.escape(heading)}', html)
        assert m, sid
        positions.append(m.start())
    assert positions == sorted(positions)  # the fixed order
    # The x2 section holds a table with the rarity column.
    x2 = html[html.index('<section id="x2">') : html.index('<section id="gotchas">')]
    assert "<table>" in x2
    assert '<td class="r">' in x2
    # The blank page is a valid input to the map rewrite.
    filled = replace_cards_map(html, {"Murder": "cards/murder.jpg"})
    assert 'const CARDS = {"Murder": "cards/murder.jpg"};' in filled


def test_template_cli_writes_and_refuses_overwrite(tmp_path):
    out = tmp_path / "guide.html"
    runner = CliRunner()
    result = runner.invoke(template_main, [str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") == read_template()

    out.write_text("edited", encoding="utf-8")
    result = runner.invoke(template_main, [str(out)])
    assert result.exit_code != 0
    assert "--force" in result.output
    assert out.read_text(encoding="utf-8") == "edited"

    result = runner.invoke(template_main, [str(out), "--force"])
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") == read_template()
