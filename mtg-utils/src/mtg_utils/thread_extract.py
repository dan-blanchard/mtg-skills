"""thread-extract: read a browser-saved Reddit thread into a transcript.

A Cmd+S-saved new-Reddit ("shreddit") comments page carries the post and every
comment the browser had loaded as custom elements: one ``<shreddit-post>`` (title,
author and timestamp as attributes, the self-text under ``[slot=text-body]``) and one
``<shreddit-comment>`` per comment (``author`` / ``depth`` / ``created`` attributes,
the body under ``[slot=comment]``, the relative age in the ``<time>`` of
``[slot=commentMeta]``). This module reads exactly those and nothing else, so the
page's chrome ("Reply", "Share", vote buttons, the sidebar) never reaches the text.

Dropped on purpose:

* **Ads** — anything under ``shreddit-comments-page-ad`` / ``shreddit-comment-tree-ads``
  / ``shreddit-sidebar-ad`` / ``shreddit-ad-post`` (promoted posts); their thumbnails
  are left out of the image list too.
* **Card-fetcher bot replies** — a comment whose body is only a list of card links
  (Scryfall / Gatherer links with no prose around them), such as r/magicTCG's
  ``mtgcf`` bot answering ``[[Card Name]]``. ``mtgcf`` is also dropped by name, since
  it is the one such bot these threads carry; the link-list test catches the others
  (and an ``mtgcf`` reply whose author was since deleted).

Collapsed and not-yet-loaded replies are not in a saved page at all: only the
"N more replies" buttons are. The output says how many comments the post reports
against how many the page holds (``collapsed_note``), so a reader knows to expand the
thread and save again when it matters.

Images: the browser saves a page's media beside it in ``<stem>_files/``. The listing
keeps JPEG / PNG / WEBP files of at least 30 KB (smaller ones are avatars, icons and
emoji), leaves out ad thumbnails and sidebar/header chrome, sorts by size (largest
first — the deck photos), and says which post or comment shows each one. Pixel sizes
come from the file headers; no imaging library is needed.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

import click
from bs4 import BeautifulSoup, NavigableString, Tag

__all__ = [
    "Comment",
    "SavedImage",
    "Thread",
    "extract_thread",
    "image_size",
    "list_images",
    "main",
    "parse_thread",
    "render_text",
]

#: Ad containers (and promoted posts) in a saved shreddit page.
AD_TAGS = frozenset(
    {
        "shreddit-comments-page-ad",
        "shreddit-comment-tree-ads",
        "shreddit-sidebar-ad",
        "shreddit-ad-post",
    }
)

#: Card-fetcher bots dropped by author. ``mtgcf`` ("Keeper of the Mox" flair) answers
#: ``[[Card Name]]`` on r/magicTCG with a list of card links and nothing else.
BOT_AUTHORS = frozenset({"mtgcf"})

#: Hosts a card-fetcher bot's links point at.
_CARD_LINK_HOSTS = ("scryfall.com", "scryfall.io", "gatherer.wizards.com")

#: Smallest saved image worth listing; below this are avatars, icons and emoji.
MIN_IMAGE_BYTES = 30_000

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_CHROME_NAME = re.compile(r"avatar|icon|headshot|emoji|banner|logo", re.IGNORECASE)
_BLOCK_TAGS = frozenset(
    {
        "p",
        "ul",
        "ol",
        "blockquote",
        "pre",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "tr",
        "figure",
    }
)


@dataclass
class Comment:
    author: str
    age: str
    created: str
    depth: int
    body: str
    images: list[str] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class SavedImage:
    path: str
    bytes: int
    width: int | None = None
    height: int | None = None
    shown_in: list[str] = field(default_factory=list)


@dataclass
class Thread:
    source: str
    title: str
    subreddit: str
    author: str
    created: str
    score: str
    body: str
    post_images: list[str]
    reported_comments: int | None
    comments: list[Comment]
    dropped_bot_replies: int
    collapsed_note: str
    images: list[SavedImage] = field(default_factory=list)


# --- Parsing ------------------------------------------------------------------


def _in_ad(tag: Tag) -> bool:
    return tag.name in AD_TAGS or tag.find_parent(AD_TAGS) is not None


def _local_images(el: Tag) -> list[str]:
    """The saved-folder file names the ``<img>`` elements under *el* show."""
    names: list[str] = []
    for img in el.find_all("img"):
        name = _saved_name(str(img.get("src") or ""))
        if name and name not in names:
            names.append(name)
    return names


def _saved_name(ref: str) -> str | None:
    """The file name inside a ``<stem>_files/`` folder that *ref* points at."""
    ref = unquote(ref)
    if "_files/" not in ref:
        return None
    name = ref.rsplit("_files/", 1)[1].split("?", 1)[0].split("#", 1)[0]
    return name or None


def _block_text(el: Tag | None) -> str:
    """*el*'s text with paragraphs, list items and line breaks kept as lines, and each
    image replaced by an ``[image: <file>]`` marker."""
    if el is None:
        return ""
    el = BeautifulSoup(str(el), "html.parser")  # work on a copy
    for script in el.find_all(["script", "style", "template"]):
        script.decompose()
    # HTML whitespace: a source newline is a space; only the markers below break lines.
    for s in el.find_all(string=True):
        if s.find_parent("pre") is None:
            s.replace_with(NavigableString(re.sub(r"\s+", " ", str(s))))
    for img in el.find_all("img"):
        name = _saved_name(str(img.get("src") or "")) or str(img.get("alt") or "image")
        img.replace_with(NavigableString(f"[image: {name}]"))
    for br in el.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for li in el.find_all("li"):
        for p in li.find_all("p"):  # "<li><p>text</p></li>" is one bullet line
            p.insert_after(NavigableString(" "))
            p.unwrap()
        li.insert(0, NavigableString("- "))
        li.insert_after(NavigableString("\n"))
    for block in el.find_all(_BLOCK_TAGS):
        block.insert_after(NavigableString("\n\n"))
    lines = [" ".join(line.split()) for line in el.get_text().splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_card_link_list(body: Tag | None) -> bool:
    """A body made only of card links: at least two links to a card database and at
    most a few words of anything else ("All cards", a dash between links)."""
    if body is None:
        return False
    links = body.find_all("a")
    card_links = [
        a
        for a in links
        if (urlparse(str(a.get("href") or "")).hostname or "").endswith(
            _CARD_LINK_HOSTS
        )
    ]
    if len(card_links) < 2:
        return False
    rest = BeautifulSoup(str(body), "html.parser")
    for a in rest.find_all("a"):
        a.decompose()
    words = [w for w in rest.get_text(" ").split() if re.search(r"\w", w)]
    return len(words) <= 5


def _own(comment: Tag, slot: str) -> Tag | None:
    """*comment*'s own ``[slot=<slot>]`` element (not one of a nested reply's)."""
    for el in comment.find_all(attrs={"slot": slot}):
        if el.find_parent("shreddit-comment") is comment:
            return el
    return None


def _time_text(el: Tag | None) -> str:
    if el is None:
        return ""
    time = el.find("time")
    return time.get_text(strip=True) if time else ""


def _to_int(value: object) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None


def _find_post(soup: BeautifulSoup) -> Tag | None:
    posts = [p for p in soup.find_all("shreddit-post") if not _in_ad(p)]
    for post in posts:
        if post.get("view-context") == "CommentsPage":
            return post
    return posts[0] if posts else None


def _hidden_reply_count(soup: BeautifulSoup) -> int:
    """Replies sitting behind "N more replies" buttons in the saved page."""
    total = 0
    for stub in soup.select("faceplate-partial.more-comments-partial"):
        number = stub.find("faceplate-number")
        n = _to_int(number.get("number")) if number else None
        if n is None:
            m = re.search(r"(\d+)\s+more repl", stub.get_text(" "))
            n = int(m.group(1)) if m else 0
        total += n
    return total


def parse_thread(html: str | BeautifulSoup, source: str = "") -> Thread:
    """The post and comments of one saved shreddit page (no image listing)."""
    soup = (
        html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "html.parser")
    )
    post = _find_post(soup)
    if post is None:
        msg = "no <shreddit-post> found — is this a saved new-Reddit comments page?"
        raise ValueError(msg)

    title_el = post.find(attrs={"slot": "title"})
    title = str(post.get("post-title") or "") or (
        title_el.get_text(" ", strip=True) if title_el else ""
    )
    text_body = post.find("shreddit-post-text-body")
    body_el = (
        text_body.find(attrs={"slot": "text-body"}) if text_body else None
    ) or text_body
    media = post.find(attrs={"slot": "post-media-container"})
    post_images = _local_images(media) if media else []
    if body_el is not None:
        post_images += [n for n in _local_images(body_el) if n not in post_images]

    comments: list[Comment] = []
    dropped = 0
    visible = 0
    for c in soup.find_all("shreddit-comment"):
        if _in_ad(c):
            continue
        visible += 1
        author = str(c.get("author") or "")
        body = _own(c, "comment")
        if author in BOT_AUTHORS or _is_card_link_list(body):
            dropped += 1
            continue
        text = _block_text(body)
        if not text and (c.has_attr("is-comment-deleted") or author == "[deleted]"):
            text = "[deleted]"
        comments.append(
            Comment(
                author=author,
                age=_time_text(_own(c, "commentMeta")),
                created=str(c.get("created") or ""),
                depth=_to_int(c.get("depth")) or 0,
                body=text,
                images=_local_images(body) if body else [],
                collapsed=c.has_attr("collapsed"),
            )
        )

    tree = soup.find("shreddit-comment-tree")
    reported = _to_int(tree.get("totalcomments")) if tree else None
    if reported is None:
        reported = _to_int(post.get("comment-count"))
    return Thread(
        source=source,
        title=title,
        subreddit=str(post.get("subreddit-prefixed-name") or ""),
        author=str(post.get("author") or ""),
        created=str(post.get("created-timestamp") or ""),
        score=str(post.get("score") or ""),
        body=_block_text(body_el),
        post_images=post_images,
        reported_comments=reported,
        comments=comments,
        dropped_bot_replies=dropped,
        collapsed_note=_collapsed_note(reported, visible, _hidden_reply_count(soup)),
    )


def _collapsed_note(reported: int | None, visible: int, stubs: int) -> str:
    base = (
        "Collapsed and unloaded replies are not in a saved page; expand them in the "
        "browser and save again to include them."
    )
    if reported is None:
        return f"{visible} comments are in the saved page. {base}"
    if reported <= visible:
        return (
            f"All {reported} comments the post reports are in the saved page "
            "(nothing collapsed)."
        )
    behind = f" ({stubs} behind 'more replies' buttons)" if stubs else ""
    return (
        f"The post reports {reported} comments; {visible} are in the saved page, so "
        f"{reported - visible} are missing{behind}. {base}"
    )


# --- Saved images -------------------------------------------------------------


def _tag_saved_names(tag: Tag) -> set[str]:
    """The saved file names *tag*'s attributes reference (``src``, ``srcset``, …)."""
    names: set[str] = set()
    for value in tag.attrs.values():
        text = " ".join(value) if isinstance(value, list) else str(value)
        if "_files/" not in text:
            continue
        names.update(
            name for part in re.split(r"[\s,]+", text) if (name := _saved_name(part))
        )
    return names


def _image_refs(soup: BeautifulSoup) -> dict[str, set[str]]:
    """saved file name -> where the page references it: ``post``, ``comment:<author>``,
    ``ad`` or ``chrome`` (header, sidebar, anything else)."""
    refs: dict[str, set[str]] = {}
    for tag in soup.find_all(name=True):
        names = _tag_saved_names(tag)
        if not names:
            continue
        if _in_ad(tag):
            where = "ad"
        elif (c := tag.find_parent("shreddit-comment")) is not None:
            where = f"comment:{c.get('author') or ''}"
        elif tag.name == "shreddit-post" or tag.find_parent("shreddit-post"):
            where = "post"
        else:
            where = "chrome"
        for name in names:
            refs.setdefault(name, set()).add(where)
    return refs


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) read from a PNG / JPEG / WEBP header, or None."""
    try:
        with path.open("rb") as fh:
            head = fh.read(64)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
                w, h = struct.unpack(">II", head[16:24])
                return w, h
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                return _webp_size(head)
            if head[:2] == b"\xff\xd8":
                fh.seek(2)
                return _jpeg_size(fh)
    except (OSError, struct.error):
        return None
    return None


def _webp_size(head: bytes) -> tuple[int, int] | None:
    chunk = head[12:16]
    if chunk == b"VP8X":
        w = int.from_bytes(head[24:27], "little") + 1
        h = int.from_bytes(head[27:30], "little") + 1
        return w, h
    if chunk == b"VP8 ":
        w, h = struct.unpack("<HH", head[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def _jpeg_size(fh) -> tuple[int, int] | None:  # noqa: ANN001 — a binary file handle
    while True:
        marker = fh.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        kind = marker[1]
        if kind in {0xD8, 0x01} or 0xD0 <= kind <= 0xD7:
            continue
        (length,) = struct.unpack(">H", fh.read(2))
        if 0xC0 <= kind <= 0xCF and kind not in {0xC4, 0xC8, 0xCC}:
            h, w = struct.unpack(">xHH", fh.read(5))
            return w, h
        fh.seek(length - 2, 1)


def list_images(
    html_path: Path,
    refs: dict[str, set[str]] | None = None,
    *,
    limit: int | None = None,
) -> list[SavedImage]:
    """The content images saved beside *html_path* in ``<stem>_files/``, largest
    first. *refs* (``_image_refs``) drops ad thumbnails and chrome-only images and
    says where each kept one is shown."""
    folder = html_path.with_name(html_path.stem + "_files")
    if not folder.is_dir():
        return []
    refs = refs or {}
    found: list[SavedImage] = []
    for f in folder.iterdir():
        if not f.is_file() or f.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        size = f.stat().st_size
        where = refs.get(f.name, set())
        if (
            size < MIN_IMAGE_BYTES
            or "ad" in where
            or where == {"chrome"}
            or _CHROME_NAME.search(f.name)
        ):
            continue
        dims = image_size(f)
        found.append(
            SavedImage(
                path=str(f.resolve()),
                bytes=size,
                width=dims[0] if dims else None,
                height=dims[1] if dims else None,
                shown_in=sorted(where - {"chrome"}),
            )
        )
    found.sort(key=lambda i: (-i.bytes, i.path))
    return found[:limit] if limit is not None else found


def extract_thread(html_path: Path, *, max_images: int | None = None) -> Thread:
    """Parse the saved page at *html_path* and list its saved images."""
    html = html_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    thread = parse_thread(soup, source=str(html_path.resolve()))
    refs = _image_refs(soup)
    thread.images = list_images(html_path, refs, limit=max_images)
    return thread


# --- Output -------------------------------------------------------------------


def _indent(text: str, pad: str) -> str:
    return "\n".join(f"{pad}{line}" if line else "" for line in text.splitlines())


def render_text(thread: Thread) -> str:
    """A readable transcript: the post, the comments indented by depth, then the
    saved images with absolute paths."""
    out = [f"# {thread.title}"]
    meta = [
        thread.subreddit,
        f"u/{thread.author}" if thread.author else "",
        thread.created,
    ]
    if thread.score:
        meta.append(f"score {thread.score}")
    if thread.reported_comments is not None:
        meta.append(f"{thread.reported_comments} comments reported")
    out.append(" · ".join(m for m in meta if m))
    out.append(f"Source: {thread.source}")
    out.append("")
    if thread.body:
        out += [thread.body, ""]
    if thread.post_images:
        out += [f"[post images: {', '.join(thread.post_images)}]", ""]
    dropped = (
        f"; {thread.dropped_bot_replies} card-link bot replies dropped"
        if thread.dropped_bot_replies
        else ""
    )
    out.append(f"## Comments ({len(thread.comments)} shown{dropped})")
    for c in thread.comments:
        pad = "  " * c.depth
        age = f" ({c.age})" if c.age else ""
        flag = " [collapsed]" if c.collapsed else ""
        out.append(f"{pad}- {c.author}{age}{flag}:")
        out.append(_indent(c.body, pad + "  "))
    out += ["", f"Note: {thread.collapsed_note}", "", "Images:"]
    if not thread.images:
        out.append("  (none saved)")
    for img in thread.images:
        dims = f", {img.width}x{img.height}" if img.width else ""
        where = f"  [{', '.join(img.shown_in)}]" if img.shown_in else ""
        out.append(f"  {img.path}  ({img.bytes // 1024} KB{dims}){where}")
    return "\n".join(out)


@click.command()
@click.argument(
    "pages",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--json", "as_json", is_flag=True, help="Emit the structure as JSON.")
@click.option(
    "--max-images",
    type=click.IntRange(min=0),
    default=None,
    help="List at most N saved images per page (largest first).",
)
def main(
    pages: tuple[Path, ...],
    as_json: bool,  # noqa: FBT001 — a click flag
    max_images: int | None,
) -> None:
    """Read browser-saved (Cmd+S) Reddit thread pages into a transcript: the post,
    each comment with author / age / depth, and the saved images' absolute paths.
    Ads, card-fetcher bot replies and page chrome are left out."""
    threads = []
    for page in pages:
        try:
            threads.append(extract_thread(page, max_images=max_images))
        except ValueError as exc:
            raise click.ClickException(f"{page}: {exc}") from exc
    if as_json:
        click.echo(
            json.dumps([asdict(t) for t in threads], indent=2, ensure_ascii=False)
        )
        return
    click.echo("\n\n".join(render_text(t) for t in threads))


if __name__ == "__main__":
    main()
