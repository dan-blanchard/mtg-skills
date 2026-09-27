"""thread-extract: a browser-saved shreddit page read into a transcript."""

import json
import shutil
import struct
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.thread_extract import (
    extract_thread,
    image_size,
    main,
    parse_thread,
    render_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_thread_min.html"


@pytest.fixture
def thread():
    return parse_thread(FIXTURE.read_text(encoding="utf-8"), source="fixture")


def _jpeg(width: int, height: int, size: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x00" * 3
    head = b"\xff\xd8" + app0 + sof0
    return head + b"\x00" * (size - len(head))


def _png(width: int, height: int, size: int) -> bytes:
    head = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
    )
    return head + b"\x00" * (size - len(head))


def _webp(width: int, height: int, size: int) -> bytes:
    head = (
        b"RIFF"
        + struct.pack("<I", size - 8)
        + b"WEBPVP8X"
        + struct.pack("<I", 10)
        + b"\x00" * 4
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )
    return head + b"\x00" * (size - len(head))


@pytest.fixture
def saved_page(tmp_path):
    """The fixture page with a ``_files`` folder of fake saved media beside it."""
    page = tmp_path / "reddit_thread_min.html"
    shutil.copy(FIXTURE, page)
    files = tmp_path / "reddit_thread_min_files"
    files.mkdir()
    (files / "bob-pool.jpeg").write_bytes(_jpeg(4032, 3024, 120_000))
    (files / "post-photo.jpeg").write_bytes(_jpeg(640, 480, 60_000))
    (files / "unreferenced-full.png").write_bytes(_png(800, 600, 90_000))
    (files / "later.webp").write_bytes(_webp(300, 200, 40_000))
    (files / "ad-thumb.jpg").write_bytes(b"\x00" * 80_000)  # an ad's thumbnail
    (files / "sidebar-ad.jpg").write_bytes(b"\x00" * 50_000)  # a sidebar ad
    (files / "sidebar-art.png").write_bytes(b"\x00" * 45_000)  # chrome only
    (files / "header-mark.png").write_bytes(b"\x00" * 45_000)  # chrome only
    (files / "alice-avatar.png").write_bytes(b"\x00" * 5_000)  # tiny
    (files / "tiny.jpeg").write_bytes(b"\x00" * 1_000)
    (files / "script.js").write_bytes(b"\x00" * 200_000)  # not an image
    return page


def test_post_fields(thread):
    assert thread.title == "Went 9-0 at the Fictional Open"
    assert thread.author == "fictional_op"
    assert thread.subreddit == "r/examplelimited"
    assert thread.reported_comments == 9
    assert thread.post_images == ["post-photo.jpeg"]
    # Source line breaks are spaces; list items are one bullet line each.
    assert thread.body == (
        "My pool was mostly blue removal.\n\n"
        "- Two copies of Imaginary Bolt\n"
        "- One Pretend Dragon"
    )


def test_comments_depth_age_and_body(thread):
    got = [(c.author, c.depth, c.age) for c in thread.comments]
    assert got == [
        ("fictional_alice", 0, "3h ago"),
        ("fictional_bob", 1, "2h ago"),
        ("fictional_alice", 2, "1h ago"),
        ("fictional_carol", 0, "30m ago"),
    ]
    alice = thread.comments[0]
    assert alice.body == (
        "Congrats! The [[Pretend Dragon]] is a bomb.\n\n"
        "Second paragraph\nwith a line break."
    )
    bob = thread.comments[1]
    assert bob.images == ["bob-pool.jpeg"]
    assert "[image: bob-pool.jpeg]" in bob.body
    # A nested reply's body never leaks into its parent's.
    assert "Nice pull" not in bob.body
    assert thread.comments[3].collapsed is True
    assert not thread.comments[0].collapsed


def test_ads_bots_and_chrome_are_excluded(thread):
    text = render_text(thread)
    # Card-link replies: mtgcf by name, the other by its link-list body.
    assert thread.dropped_bot_replies == 2
    assert all(c.author not in {"mtgcf", "fictional_linkbot"} for c in thread.comments)
    for noise in ("ZapCola", "SuperWidget", "Upvote", "Reply", "Share", "(SF)"):
        assert noise not in text


def test_collapsed_note_counts_missing_replies(thread):
    # 6 comments are in the page (2 of them bots), 9 reported, 2 behind a stub.
    assert "reports 9 comments; 6 are in the saved page" in thread.collapsed_note
    assert "3 are missing (2 behind 'more replies' buttons)" in thread.collapsed_note


def test_render_text_indents_by_depth(thread):
    lines = render_text(thread).splitlines()
    assert "- fictional_alice (3h ago):" in lines
    assert "  - fictional_bob (2h ago):" in lines
    assert "    - fictional_alice (1h ago):" in lines
    assert "      Nice pull." in lines
    assert "- fictional_carol (30m ago) [collapsed]:" in lines


def test_image_listing_filters_and_sorts(saved_page):
    thread = extract_thread(saved_page)
    names = [Path(i.path).name for i in thread.images]
    assert names == [
        "bob-pool.jpeg",
        "unreferenced-full.png",
        "post-photo.jpeg",
        "later.webp",
    ]
    by_name = {Path(i.path).name: i for i in thread.images}
    assert all(Path(i.path).is_absolute() for i in thread.images)
    assert (by_name["bob-pool.jpeg"].width, by_name["bob-pool.jpeg"].height) == (
        4032,
        3024,
    )
    assert (by_name["unreferenced-full.png"].width, by_name["later.webp"].height) == (
        800,
        200,
    )
    assert by_name["bob-pool.jpeg"].shown_in == ["comment:fictional_bob"]
    assert by_name["post-photo.jpeg"].shown_in == ["post"]
    assert by_name["unreferenced-full.png"].shown_in == []


def test_max_images_and_missing_folder(saved_page, tmp_path):
    assert len(extract_thread(saved_page, max_images=2).images) == 2
    lone = tmp_path / "lone" / "page.html"
    lone.parent.mkdir()
    shutil.copy(FIXTURE, lone)
    assert extract_thread(lone).images == []


def test_image_size_unknown_format(tmp_path):
    junk = tmp_path / "junk.jpeg"
    junk.write_bytes(b"not an image")
    assert image_size(junk) is None


def test_not_a_reddit_page():
    with pytest.raises(ValueError, match="shreddit-post"):
        parse_thread("<html><body><p>hi</p></body></html>")


def test_cli_text_and_json(saved_page):
    runner = CliRunner()
    result = runner.invoke(main, [str(saved_page)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("# Went 9-0 at the Fictional Open")
    assert "Images:" in result.output
    assert str(saved_page.parent / "reddit_thread_min_files" / "bob-pool.jpeg") in (
        result.output
    )

    result = runner.invoke(main, ["--json", "--max-images", "1", str(saved_page)])
    assert result.exit_code == 0, result.output
    (data,) = json.loads(result.output)
    assert data["title"] == "Went 9-0 at the Fictional Open"
    assert len(data["comments"]) == 4
    assert data["comments"][2]["depth"] == 2
    assert len(data["images"]) == 1
    assert data["collapsed_note"]


def test_cli_rejects_non_reddit_page(tmp_path):
    page = tmp_path / "plain.html"
    page.write_text("<html><body>hello</body></html>")
    result = CliRunner().invoke(main, [str(page)])
    assert result.exit_code != 0
    assert "shreddit-post" in result.output
