"""Render printable PDF proxies for an MTG deck.

Two modes selected by ``--kind``:

* ``cards``  — one proxy per copy of every card in the deck.
* ``tokens`` — one proxy per distinct token kind (deduped by ``oracle_id``)
  produced by the deck.

Both modes share a single render template:
name banner / ASCII art / type banner / oracle text / P/T. Card data is pulled
from the Scryfall bulk file; ASCII art is keyed by card subtype (with
card-type and ultimate-generic fallbacks) from the on-disk catalog at
``mtg_utils/data/card_art/``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import click

from mtg_utils.bulk_loader import default_bulk_path
from mtg_utils.deck import (
    CARD_TYPE_WORDS,
    discover_tokens,
    hydrate,
    load_bulk_indexes,
    slug,
    split_type_line,
    walk_cards,
)

if TYPE_CHECKING:

    from reportlab.pdfgen.canvas import Canvas


# --- Geometry --------------------------------------------------------------

PAGE_SIZES = {
    # (width_pts, height_pts) — reportlab uses points (1in = 72pt).
    "letter": (8.5 * 72, 11.0 * 72),
    "a4": (210 / 25.4 * 72, 297 / 25.4 * 72),
}

CARD_W = 2.5 * 72  # 2.5"
CARD_H = 3.5 * 72  # 3.5"
GRID_COLS = 3
GRID_ROWS = 3
PER_PAGE = GRID_COLS * GRID_ROWS

PAD = 0.10 * 72  # inner padding
BANNER_H = 14
BANNER_FILL = 0.92  # light gray
BANNER_GAP = 3
PT_BOX_W = 0.55 * 72
PT_BOX_H = 14
ART_MIN_H = 40
ORACLE_MAX_H_FRAC = 0.60  # of body height

# --- Bulk freshness --------------------------------------------------------

BULK_MAX_AGE_DAYS = 7

# --- Exit codes ------------------------------------------------------------

EXIT_OK = 0
EXIT_BULK_MISSING = 1
EXIT_DECK_INVALID = 2
EXIT_OUTPUT_UNWRITABLE = 3
EXIT_RENDER_FAILED = 4


# --- Slug normalization ----------------------------------------------------

# Words that should never become art-lookup keys (they're meta-types or
# decorations on top of an actual card type).
_ART_SKIP_WORDS = frozenset({
    "token", "legendary", "snow", "tribal", "basic", "ongoing", "world",
    "host",
})

# --- Art catalog -----------------------------------------------------------

# The attributed catalog holds ASCII art the user has fetched from
# asciiart.eu (or similar) with a 3-line ``#``-prefixed header noting title,
# source, and license. When a piece is found here it overrides the local
# catalog and its artist is rendered in the proxy's lower-left footer.
def attributed_art_dir() -> Path:
    """Return the attributed-catalog root: ``$MTG_SKILLS_CACHE_DIR/attributed-art``
    or ``$HOME/.cache/mtg-skills/attributed-art``.
    """
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "attributed-art"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "attributed-art"

# Header line shape: ``# Title (by Artist Name (signature))``
_ATTRIBUTED_BY_RE = re.compile(
    r"\(by\s+(?P<name>[^()]+?)(?:\s*\([^)]+\))?\s*\)\s*$"
)


def _art_dir() -> resources.abc.Traversable:
    return resources.files("mtg_utils.data.card_art")


def _try_read_art(key: str) -> str | None:
    """Read art for ``key`` from the local catalog, or None if missing."""
    if not key:
        return None
    art_root = _art_dir()
    candidate = art_root / f"{key}.txt"
    try:
        if not candidate.is_file():
            return None
        return candidate.read_text(encoding="utf-8").strip("\n")
    except (FileNotFoundError, OSError):
        return None


def _try_read_attributed(key: str) -> tuple[str, str] | None:
    """Read attributed art for ``key`` from :func:`attributed_art_dir`.

    Returns ``(art_body, artist_name)`` or None if not found / unparseable.
    The file format is::

        # <title> (by <artist name>[ (<signature>)])
        # Source: <url>
        # Used with attribution per <url>

        <art body…>

    Header lines are stripped before returning ``art_body``; the artist's
    name is extracted from the first header line so the renderer can credit
    them on the printed proxy.
    """
    root = attributed_art_dir()
    if not key or not root.exists():
        return None
    candidate = root / f"{key}.txt"
    try:
        if not candidate.is_file():
            return None
        text = candidate.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None

    lines = text.splitlines()
    first_header = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            if not first_header:
                first_header = line
            body_start = i + 1
        elif line.strip() == "" and body_start == i:
            # consume a single blank separator after the header
            body_start = i + 1
            break
        else:
            break

    body = "\n".join(lines[body_start:]).strip("\n")
    if not body:
        return None

    artist = ""
    m = _ATTRIBUTED_BY_RE.search(first_header)
    if m:
        artist = m.group("name").strip()
    return body, artist


def lookup_art(type_line: str) -> tuple[str, str, str, str]:
    """Resolve ASCII art for a card by type line.

    Returns ``(art, tier, key, credit)`` where:
    * ``art`` is the multi-line ASCII string (already stripped of leading/
      trailing newlines).
    * ``tier`` is one of ``"subtype" | "card-type" | "generic"``.
    * ``key`` is the slug that hit (e.g., ``"vampire"``, ``"creature"``,
      ``"_generic"``).
    * ``credit`` is the artist's name when the piece came from the
      attributed catalog, otherwise ``""``.

    Lookup chain (first hit wins). For each slug we try the attributed
    catalog first, then the local catalog:
      1. Each subtype slug from the type line, in order.
      2. Each card-type slug (filtering meta words like Token / Legendary).
      3. ``_generic.txt`` ultimate fallback (local only).
    """
    types, subs = split_type_line(type_line)

    for sub in subs:
        if sub in _ART_SKIP_WORDS:
            continue
        s = slug(sub)
        att = _try_read_attributed(s)
        if att is not None:
            return att[0], "subtype", s, att[1]
        art = _try_read_art(s)
        if art is not None:
            return art, "subtype", s, ""

    for t in types:
        if t in _ART_SKIP_WORDS or t not in CARD_TYPE_WORDS:
            continue
        s = slug(t)
        att = _try_read_attributed(s)
        if att is not None:
            return att[0], "card-type", s, att[1]
        art = _try_read_art(s)
        if art is not None:
            return art, "card-type", s, ""

    art = _try_read_art("_generic")
    if art is None:
        # Catalog missing the ultimate fallback — emergency stub so we never
        # crash mid-render.
        art = "         ?\n        ???\n         ?"
    return art, "generic", "_generic", ""


# --- Layout primitives -----------------------------------------------------


def _slot_xy(slot: int, page_w: float, page_h: float) -> tuple[float, float]:
    """Return (x, y) of the slot's lower-left corner."""
    grid_w = GRID_COLS * CARD_W
    grid_h = GRID_ROWS * CARD_H
    margin_x = (page_w - grid_w) / 2
    margin_y = (page_h - grid_h) / 2
    col = slot % GRID_COLS
    row_top = slot // GRID_COLS
    x = margin_x + col * CARD_W
    y = page_h - margin_y - (row_top + 1) * CARD_H
    return x, y


def _color_tag(card: dict) -> str:
    cs = card.get("colors") or card.get("color_indicator") or []
    if not cs:
        return "C"
    return "".join(f"{{{c}}}" for c in cs)


def _wrap(
    text: str,
    font: str,
    size: float,
    max_w: float,
    measure_width: Callable[[str, str, float], float],
) -> list[str]:
    """Word-wrap ``text`` to ``max_w``, preserving \\n paragraph breaks.

    Uses ``measure_width(text, font, size)`` for font metrics — pass
    ``Canvas.stringWidth`` in production, a fake in tests.
    """
    out: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            out.append("")
            continue
        current = ""
        for word in paragraph.split():
            tentative = f"{current} {word}".strip()
            if not current or measure_width(tentative, font, size) <= max_w:
                current = tentative
            else:
                out.append(current)
                current = word
        if current:
            out.append(current)
    return out


def _fit_oracle(
    text: str,
    font: str,
    max_w: float,
    max_h: float,
    *,
    measure_width: Callable[[str, str, float], float],
    lo: float,
    hi: float,
    leading_ratio: float = 1.18,
) -> tuple[float, list[str]]:
    """Pick the largest font size in [lo, hi] whose wrapped text fits."""
    size = hi
    while size >= lo:
        lines = _wrap(text, font, size, max_w, measure_width)
        leading = size * leading_ratio
        if len(lines) * leading <= max_h:
            return size, lines
        size -= 0.25
    return lo, _wrap(text, font, lo, max_w, measure_width)


def _fit_art(
    art: str, max_w: float, max_h: float, *, lo: float = 5.5, hi: float = 8.0
) -> tuple[float, float, list[str]]:
    """Pick the largest Courier-Bold size where art fits w x h."""
    art_lines = art.splitlines() or [""]
    art_w_chars = max((len(line) for line in art_lines), default=1)
    art_h_lines = len(art_lines)
    size = hi
    while size >= lo:
        char_w = size * 0.6
        leading = size  # 1.0 leading reads cleanly for ASCII
        if art_w_chars * char_w <= max_w and art_h_lines * leading <= max_h:
            return size, leading, art_lines
        size -= 0.25
    return lo, lo, art_lines


def _draw_banner(
    c: Canvas, x: float, y: float, w: float, h: float, *, fill: float = BANNER_FILL
) -> None:
    c.setFillGray(fill)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.3)
    c.rect(x, y, w, h, stroke=1, fill=1)
    c.setFillGray(0)  # reset


# --- Card / token render ---------------------------------------------------


# --- Layout vs emission ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProxyLayout:
    """Pre-computed positions, sizes, and content strings for one card proxy.

    Everything ``_draw_proxy`` needs to *emit* a card lives here. The
    geometry math + font fitting + art lookup all happen in
    :func:`compute_layout`; ``_draw_proxy`` just translates this struct
    into canvas calls.

    Test seam: callers (and tests) can build a ``ProxyLayout`` with a
    fake ``measure_width`` callable and assert on every field without
    touching reportlab.
    """

    # Outer cell origin (CARD_W × CARD_H constant).
    x: float
    y: float

    # Name banner.
    name_banner_y: float
    name_text: str
    name_text_size: float
    name_centered: bool   # True for tokens; False for cards (left-aligned)
    mana_cost_text: str   # "" for tokens

    # P/T box (omitted from emission when pt_text == "").
    pt_text: str
    pt_box_x: float
    pt_box_y: float

    # Footer slot — token "from: X" or "art by X". Already truncated to fit.
    footer_text: str
    footer_y: float

    # Art region.
    art_lines: list[str]
    art_size: float
    art_leading: float
    art_x: float
    art_y_top: float
    art_tier: str
    art_key: str

    # Type banner.
    type_banner_y: float
    type_text: str
    type_text_size: float
    color_tag: str

    # Oracle (oracle_lines empty when card has no oracle text).
    oracle_lines: list[str]
    oracle_size: float
    oracle_leading: float
    oracle_top: float
    oracle_bottom: float


# ``measure_width(text, font, size) -> width_in_points``. In production,
# bind to ``Canvas.stringWidth``. In tests, pass a fake. This is the
# only piece of reportlab the layout phase needs.
MeasureWidth = Callable[[str, str, float], float]


def compute_layout(
    card: dict,
    slot: int,
    *,
    page_w: float,
    page_h: float,
    is_token: bool,
    sources: list[str] | None,
    measure_width: MeasureWidth,
) -> ProxyLayout:
    """Pure(ish) layout computation. No drawing — only measurement.

    Returns a :class:`ProxyLayout` carrying every position, font size,
    wrapped text, and content string the emit phase needs. ``measure_width``
    is the only seam to a real canvas (font metrics).
    """
    x, y = _slot_xy(slot, page_w, page_h)

    name = card.get("name") or "?"
    if " // " in name:
        name = name.split(" // ")[0]
    type_line = card.get("type_line") or ""
    if " // " in type_line:
        type_line = type_line.split(" // ")[0]
    oracle = card.get("oracle_text") or ""
    mana_cost = "" if is_token else (card.get("mana_cost") or "")
    color_tag = _color_tag(card)
    power, toughness = card.get("power"), card.get("toughness")
    loyalty = card.get("loyalty")

    inner_w = CARD_W - 2 * PAD

    # ---- Name banner -------------------------------------------------------
    name_banner_y = y + CARD_H - PAD - BANNER_H
    cost_w = measure_width(mana_cost, "Helvetica-Bold", 9.5) if mana_cost else 0
    if is_token:
        name_size = 9.5
        while name_size >= 6.0 and measure_width(name, "Helvetica-Bold", name_size) > inner_w - 6:
            name_size -= 0.25
        name_centered = True
    else:
        name_max_w = inner_w - cost_w - 8
        name_size = 9.5
        while name_size >= 6.0 and measure_width(name, "Helvetica-Bold", name_size) > name_max_w:
            name_size -= 0.25
        name_centered = False

    # ---- P/T box -----------------------------------------------------------
    pt_text = ""
    if power is not None and toughness is not None:
        pt_text = f"{power} / {toughness}"
    elif loyalty is not None:
        pt_text = f"L: {loyalty}"
    pt_box_y = y + PAD
    pt_box_x = x + CARD_W - PAD - PT_BOX_W
    footer_h = PT_BOX_H if pt_text else 0

    # ---- Footer slot (token source > artist credit) -----------------------
    footer_text = ""
    if is_token and sources:
        footer_text = (
            f"from: {sources[0]}" if len(sources) == 1
            else f"from: {len(sources)} cards"
        )
    footer_avail_w = inner_w - (PT_BOX_W + 6) if pt_text else inner_w
    if footer_text:
        while (
            measure_width(footer_text, "Helvetica-Oblique", 6) > footer_avail_w
            and len(footer_text) > 8
        ):
            footer_text = footer_text[:-2] + "…"

    # ---- Body math: oracle probe → art floor → compensation ---------------
    body_top = name_banner_y - BANNER_GAP
    body_bottom = pt_box_y + footer_h + BANNER_GAP
    body_h = body_top - body_bottom

    if oracle:
        probe_size = 7.5
        probe_lines = _wrap(oracle, "Helvetica", probe_size, inner_w, measure_width)
        probe_h = len(probe_lines) * probe_size * 1.18
        oracle_max_h = min(probe_h + 4, body_h * ORACLE_MAX_H_FRAC)
    else:
        oracle_max_h = 0

    type_banner_h = BANNER_H - 1
    art_h = body_h - oracle_max_h - type_banner_h - BANNER_GAP
    if oracle_max_h > 0:
        art_h -= BANNER_GAP
    art_h = max(art_h, ART_MIN_H)
    used = art_h + oracle_max_h + type_banner_h + BANNER_GAP * (
        2 if oracle_max_h > 0 else 1
    )
    if used > body_h:
        oracle_max_h = max(0, oracle_max_h - (used - body_h))

    # ---- Art region --------------------------------------------------------
    art_top = body_top
    art_bottom = art_top - art_h
    art_text_raw, tier, key, art_credit = lookup_art(type_line)
    art_size, art_leading, art_lines = _fit_art(art_text_raw, inner_w, art_h)
    char_w = art_size * 0.6
    block_h = len(art_lines) * art_leading
    block_w = max((len(line) for line in art_lines), default=1) * char_w
    art_x = x + (CARD_W - block_w) / 2
    art_y_top = art_bottom + (art_h + block_h) / 2 - art_size

    # Artist credit takes the footer slot only when no token source is there.
    if art_credit and not footer_text:
        cred_text = f"art by {art_credit}"
        while (
            measure_width(cred_text, "Helvetica-Oblique", 6) > footer_avail_w
            and len(cred_text) > 12
        ):
            cred_text = cred_text[:-2] + "…"
        footer_text = cred_text

    # ---- Type banner -------------------------------------------------------
    type_banner_y = art_bottom - BANNER_GAP - type_banner_h
    tag_w = measure_width(color_tag, "Helvetica-Bold", 7.5)
    type_max_w = inner_w - tag_w - 10
    type_size = 8.0
    while (
        type_size >= 6.0
        and measure_width(type_line, "Helvetica-Bold", type_size) > type_max_w
    ):
        type_size -= 0.25

    # ---- Oracle region -----------------------------------------------------
    if oracle and oracle_max_h > 0:
        oracle_top = type_banner_y - BANNER_GAP
        oracle_bottom = pt_box_y + footer_h + BANNER_GAP
        avail_h = oracle_top - oracle_bottom
        size, lines = _fit_oracle(
            oracle, "Helvetica", inner_w, avail_h,
            measure_width=measure_width, lo=5.5, hi=7.5,
        )
        leading = size * 1.18
    else:
        oracle_top = oracle_bottom = 0.0
        size, lines, leading = 0.0, [], 0.0

    return ProxyLayout(
        x=x, y=y,
        name_banner_y=name_banner_y,
        name_text=name, name_text_size=name_size,
        name_centered=name_centered, mana_cost_text=mana_cost,
        pt_text=pt_text, pt_box_x=pt_box_x, pt_box_y=pt_box_y,
        footer_text=footer_text, footer_y=pt_box_y + 4,
        art_lines=art_lines, art_size=art_size, art_leading=art_leading,
        art_x=art_x, art_y_top=art_y_top, art_tier=tier, art_key=key,
        type_banner_y=type_banner_y,
        type_text=type_line, type_text_size=type_size, color_tag=color_tag,
        oracle_lines=lines, oracle_size=size, oracle_leading=leading,
        oracle_top=oracle_top, oracle_bottom=oracle_bottom,
    )


def _draw_proxy(
    c: Canvas,
    slot: int,
    card: dict,
    *,
    page_w: float,
    page_h: float,
    is_token: bool,
    sources: list[str] | None = None,
) -> tuple[str, str]:
    """Render one card or token into ``slot``. Returns (art_tier, art_key)."""
    layout = compute_layout(
        card, slot,
        page_w=page_w, page_h=page_h,
        is_token=is_token, sources=sources,
        measure_width=c.stringWidth,
    )
    _emit_proxy(c, layout)
    return layout.art_tier, layout.art_key


def _emit_proxy(c: Canvas, layout: ProxyLayout) -> None:
    """Translate ``layout`` into reportlab canvas calls. No measurement, no math.

    Every position and size has already been decided in
    :func:`compute_layout`.
    """
    inner_x = layout.x + PAD
    inner_w = CARD_W - 2 * PAD

    # Outer cell border (cut line).
    c.setLineWidth(0.6)
    c.setStrokeColorRGB(0, 0, 0)
    c.rect(layout.x, layout.y, CARD_W, CARD_H, stroke=1, fill=0)

    # Name banner.
    _draw_banner(c, inner_x, layout.name_banner_y, inner_w, BANNER_H)
    name_text_y = layout.name_banner_y + 4
    c.setFont("Helvetica-Bold", layout.name_text_size)
    if layout.name_centered:
        c.drawCentredString(inner_x + inner_w / 2, name_text_y, layout.name_text)
    else:
        c.drawString(inner_x + 3, name_text_y, layout.name_text)
        if layout.mana_cost_text:
            c.setFont("Helvetica-Bold", 9.5)
            c.drawRightString(inner_x + inner_w - 3, name_text_y, layout.mana_cost_text)

    # P/T box.
    if layout.pt_text:
        c.setLineWidth(0.4)
        c.rect(layout.pt_box_x, layout.pt_box_y, PT_BOX_W, PT_BOX_H, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(
            layout.pt_box_x + PT_BOX_W / 2, layout.pt_box_y + 3.5, layout.pt_text
        )

    # Footer slot (token source or art credit).
    if layout.footer_text:
        c.setFont("Helvetica-Oblique", 6)
        c.drawString(inner_x, layout.footer_y, layout.footer_text)

    # Art body.
    c.setFont("Courier-Bold", layout.art_size)
    cy = layout.art_y_top
    for line in layout.art_lines:
        c.drawString(layout.art_x, cy, line)
        cy -= layout.art_leading

    # Type banner.
    type_banner_h = BANNER_H - 1
    _draw_banner(c, inner_x, layout.type_banner_y, inner_w, type_banner_h)
    type_text_y = layout.type_banner_y + 3
    c.setFont("Helvetica-Bold", layout.type_text_size)
    c.drawString(inner_x + 3, type_text_y, layout.type_text)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(inner_x + inner_w - 3, type_text_y, layout.color_tag)

    # Oracle text.
    if layout.oracle_lines:
        c.setFont("Helvetica", layout.oracle_size)
        cy = layout.oracle_top - layout.oracle_size
        for line in layout.oracle_lines:
            if cy < layout.oracle_bottom:
                break
            c.drawString(inner_x, cy, line)
            cy -= layout.oracle_leading



# --- PDF builder -----------------------------------------------------------


def build_pdf(
    out_path: Path,
    items: list[tuple[dict, list[str] | None]],
    *,
    page_size: str,
    is_token: bool,
    title: str,
    coverage: list[dict] | None = None,
) -> None:
    from reportlab.pdfgen import canvas

    page_w, page_h = PAGE_SIZES[page_size]
    c = canvas.Canvas(str(out_path), pagesize=(page_w, page_h))
    c.setTitle(title)

    for i, (card, sources) in enumerate(items):
        slot = i % PER_PAGE
        if i > 0 and slot == 0:
            c.showPage()
        tier, key = _draw_proxy(
            c,
            slot,
            card,
            page_w=page_w,
            page_h=page_h,
            is_token=is_token,
            sources=sources,
        )
        if coverage is not None:
            coverage.append({
                "name": card.get("name"),
                "tier": tier,
                "key": key,
            })

    c.showPage()
    c.save()


# --- Bulk-data discovery ---------------------------------------------------


def _bulk_is_fresh(path: Path) -> bool:
    import time
    age_s = time.time() - path.stat().st_mtime
    return age_s < BULK_MAX_AGE_DAYS * 86400


# --- CLI -------------------------------------------------------------------


def _log_warn(msg: str) -> None:
    click.echo(f"WARN: {msg}", err=True)


@click.command()
@click.option(
    "--kind",
    required=True,
    type=click.Choice(["cards", "tokens"]),
    help="Which PDF to render.",
)
@click.option(
    "--deck",
    "deck_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Parsed deck JSON (parse-deck output schema).",
)
@click.option(
    "--out",
    "out_path",
    required=True,
    type=click.Path(path_type=Path),
    help="Output PDF path.",
)
@click.option(
    "--bulk-data",
    "bulk_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Scryfall bulk JSON (auto-resolved if omitted).",
)
@click.option(
    "--page-size",
    type=click.Choice(["letter", "a4"]),
    default="letter",
    show_default=True,
)
@click.option("--copies", type=int, default=1, show_default=True)
@click.option(
    "--include-sideboard/--no-sideboard",
    default=True,
    help="Cards mode only; whether to include the sideboard.",
)
@click.option(
    "--report-art-coverage",
    is_flag=True,
    help="Tokens mode only; emit per-token JSON to stderr showing which catalog tier hit.",
)
def main(
    kind: str,
    deck_path: Path,
    out_path: Path,
    bulk_path: Path | None,
    page_size: str,
    copies: int,
    include_sideboard: bool,
    report_art_coverage: bool,
) -> None:
    # Resolve bulk path
    if bulk_path is None:
        bulk_path = default_bulk_path()
    if bulk_path is None or not bulk_path.is_file():
        click.echo(
            "ERROR: Scryfall bulk data not found. Run `download-bulk` first.",
            err=True,
        )
        sys.exit(EXIT_BULK_MISSING)
    if not _bulk_is_fresh(bulk_path):
        click.echo(
            f"ERROR: bulk data at {bulk_path} is older than "
            f"{BULK_MAX_AGE_DAYS} days. Run `download-bulk` to refresh.",
            err=True,
        )
        sys.exit(EXIT_BULK_MISSING)

    # Load deck
    try:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        click.echo(f"ERROR: cannot read deck JSON: {e}", err=True)
        sys.exit(EXIT_DECK_INVALID)

    if not isinstance(deck, dict) or not any(
        k in deck for k in ("commanders", "cards", "sideboard")
    ):
        click.echo(
            "ERROR: deck JSON must have at least one of "
            "{commanders, cards, sideboard}. Run `parse-deck` first.",
            err=True,
        )
        sys.exit(EXIT_DECK_INVALID)

    # Output path writability
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        click.echo(f"ERROR: cannot create output dir {out_path.parent}: {e}", err=True)
        sys.exit(EXIT_OUTPUT_UNWRITABLE)

    # Build indexes (this is the slow step)
    by_name, by_id = load_bulk_indexes(bulk_path)

    items: list[tuple[dict, list[str] | None]] = []

    if kind == "cards":
        for name, qty in walk_cards(
            deck, include_sideboard=include_sideboard, copies=copies
        ):
            src = by_name.get(name.lower())
            if src is None:
                _log_warn(f"missing from bulk: {name}")
                continue
            hydrated = hydrate(src)
            for _ in range(qty):
                items.append((hydrated, None))
        title = f"MTG Card Proxies — {deck_path.name}"
    else:  # tokens
        groups = discover_tokens(deck, by_name, by_id, log_warn=_log_warn)
        for group in groups:
            for _ in range(copies):
                items.append((group["token"], group["sources"]))
        title = f"MTG Token Proxies — {deck_path.name}"

    if not items:
        click.echo("ERROR: no items to render.", err=True)
        sys.exit(EXIT_RENDER_FAILED)

    coverage: list[dict] | None = [] if (report_art_coverage and kind == "tokens") else None

    try:
        build_pdf(
            out_path,
            items,
            page_size=page_size,
            is_token=(kind == "tokens"),
            title=title,
            coverage=coverage,
        )
    except Exception as e:  # noqa: BLE001 — surface any reportlab error
        click.echo(f"ERROR: rendering failed: {e}", err=True)
        sys.exit(EXIT_RENDER_FAILED)

    if coverage:
        for entry in coverage:
            click.echo(json.dumps(entry), err=True)

    click.echo(str(out_path))


if __name__ == "__main__":
    main()
