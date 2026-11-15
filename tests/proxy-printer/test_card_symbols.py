"""Tests for :mod:`mtg_utils.card_symbols`: the SVG reader, the symbol set's
measuring and drawing, and its behavior when a symbol can't be fetched.

The SVGs here are small hand-written ones in the shapes Scryfall's symbol files
use; no test fetches a real one.
"""

from __future__ import annotations

import math

import pytest
import requests
from _fake_fetcher import FakeFetcher

from mtg_utils.card_symbols import (
    NO_SYMBOLS,
    SvgError,
    SymbolSet,
    find_symbols,
    parse_svg,
    symbol_file_name,
)
from mtg_utils.proxy_print import PAGE_SIZES, compute_layout

CIRCLE_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
    "<g fill='none'><circle fill='#CAC5C0' cx='50' cy='50' r='50'/>"
    "<path d='M10 10h80v80H10z' fill='#0D0F0F'/></g></svg>"
)
WIDE_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 100'>"
    "<path d='M0 0h200v100H0z'/></svg>"
)


def fixed_width(text: str, _font: str, size: float) -> float:
    return len(text) * size * 0.6


def _endpoints(shape):
    return [seg[-2:] for seg in shape.segments if seg[0] != "Z"]


# --- Symbol codes ----------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ("{W}", "W"),
        ("{T}", "T"),
        ("{10}", "10"),
        ("{W/U}", "WU"),
        ("{2/W}", "2W"),
        ("{G/U/P}", "GUP"),
        ("{½}", "HALF"),
        ("{∞}", "INFINITY"),
    ],
)
def test_symbol_file_name(code, name):
    assert symbol_file_name(code) == name


def test_find_symbols_collects_distinct_codes():
    assert find_symbols(["{2}{W/U}{W/U}", "{T}: Add {G}.", "no symbols"]) == {
        "{2}",
        "{W/U}",
        "{T}",
        "{G}",
    }


# --- SVG reading -----------------------------------------------------------


def test_parse_reads_view_box_and_shapes_in_order():
    symbol = parse_svg(CIRCLE_SVG)
    assert (symbol.width, symbol.height) == (100, 100)
    circle, square = symbol.shapes
    assert circle.fill == pytest.approx((0xCA / 255, 0xC5 / 255, 0xC0 / 255))
    assert square.fill == pytest.approx((0x0D / 255, 0x0F / 255, 0x0F / 255))
    assert _endpoints(square) == [(10, 10), (90, 10), (90, 90), (10, 90)]


def test_circle_becomes_four_quarter_curves_on_the_circle():
    circle = parse_svg(CIRCLE_SVG).shapes[0]
    curves = [seg for seg in circle.segments if seg[0] == "C"]
    assert len(curves) == 4
    for seg in curves:
        assert math.hypot(seg[5] - 50, seg[6] - 50) == pytest.approx(50)


def test_relative_commands_and_implicit_lineto():
    shape = parse_svg(
        "<svg viewBox='0 0 10 10'><path d='m1 1 2 0 0 2-2 0z'/></svg>"
    ).shapes[0]
    assert _endpoints(shape) == [(1, 1), (3, 1), (3, 3), (1, 3)]


def test_smooth_curve_mirrors_the_previous_handle():
    shape = parse_svg(
        "<svg viewBox='0 0 10 10'><path d='M0 0C1 0 2 1 2 2S3 4 4 4'/></svg>"
    ).shapes[0]
    assert shape.segments[2] == ("C", 2, 3, 3, 4, 4, 4)


def test_arc_with_run_together_flags_ends_at_its_endpoint():
    shape = parse_svg(
        "<svg viewBox='0 0 10 10'><path d='M0 5a5 5 0 015 5'/></svg>"
    ).shapes[0]
    assert shape.segments[-1][-2:] == pytest.approx((5, 10))


def test_group_transform_and_fill_are_inherited():
    symbol = parse_svg(
        "<svg viewBox='0 0 10 10'><g transform='translate(0 -1)' fill='#fff'>"
        "<path d='M1 2h3'/></g></svg>"
    )
    assert symbol.shapes[0].fill == (1.0, 1.0, 1.0)
    assert _endpoints(symbol.shapes[0]) == [(1, 1), (4, 1)]


def test_fill_none_without_stroke_draws_nothing():
    with pytest.raises(SvgError, match="no drawable shapes"):
        parse_svg("<svg viewBox='0 0 1 1'><path fill='none' d='M0 0h1'/></svg>")


def test_fill_rule_is_read_from_the_group():
    symbol = parse_svg(
        "<svg viewBox='0 0 1 1'><g fill-rule='evenodd'><path d='M0 0h1v1z'/></g></svg>"
    )
    assert symbol.shapes[0].even_odd is True


@pytest.mark.parametrize(
    "svg",
    [
        "not xml",
        "<svg><path d='M0 0h1'/></svg>",  # no viewBox
        "<svg viewBox='0 0 1 1'><rect width='1' height='1'/></svg>",
        "<svg viewBox='0 0 1 1'><path d='M0 0Q1 1 2 2'/></svg>",
        "<svg viewBox='0 0 1 1'><g transform='rotate(45)'><path d='M0 0h1'/></g></svg>",
        "<svg viewBox='0 0 1 1'><path fill='red' d='M0 0h1'/></svg>",
    ],
)
def test_unsupported_svg_raises(svg):
    with pytest.raises(SvgError):
        parse_svg(svg)


# --- Loading ---------------------------------------------------------------


def test_load_fetches_each_code_once_by_file_name():
    fetcher = FakeFetcher(routes={"/WU.svg": CIRCLE_SVG, "/T.svg": CIRCLE_SVG})
    symbols = SymbolSet.load(["{W/U}", "{T}", "{T}"], fetcher)
    assert "{W/U}" in symbols
    assert "{T}" in symbols
    assert sorted(call.cache_key for call in fetcher.calls) == ["T.svg", "WU.svg"]


class _FailingFetcher:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def fetch(self, url, cache_key, **_kwargs) -> bytes:
        self.calls += 1
        raise self.error


def test_load_offline_stops_after_one_failure_and_holds_nothing(capsys):
    fetcher = _FailingFetcher(requests.ConnectionError("down"))
    symbols = SymbolSet.load(["{W}", "{U}", "{B}"], fetcher)
    assert len(symbols) == 0
    assert fetcher.calls == 1
    assert "printing them as text" in capsys.readouterr().err


def test_load_skips_a_symbol_scryfall_has_no_image_for(capsys):
    class Fetcher:
        def fetch(self, url, cache_key, **_kwargs) -> bytes:
            if "/NOPE.svg" in url:
                raise requests.HTTPError("404")
            return CIRCLE_SVG.encode()

    symbols = SymbolSet.load(["{NOPE}", "{W}"], Fetcher())
    assert "{W}" in symbols
    assert "{NOPE}" not in symbols
    assert "{NOPE}" in capsys.readouterr().err


def test_load_skips_an_unreadable_svg_and_never_fetches_a_non_file_code():
    fetcher = FakeFetcher(routes={"/W.svg": "<svg/>", "/U.svg": CIRCLE_SVG})
    symbols = SymbolSet.load(["{W}", "{U}", "{../x}"], fetcher)
    assert "{U}" in symbols
    assert "{W}" not in symbols
    assert len(fetcher.calls) == 2


def test_default_load_is_offline_under_tests():
    # The conftest replaces the production fetcher, so this never hits the network.
    assert len(SymbolSet.load(["{W}"])) == 0


# --- Measuring -------------------------------------------------------------


def test_held_symbol_measures_as_its_image_not_its_text():
    symbols = SymbolSet({"{T}": parse_svg(CIRCLE_SVG)})
    plain = fixed_width("{T}: Add ", "Helvetica", 10)
    assert symbols.measure("{T}: Add ", "Helvetica", 10, fixed_width) < plain
    # A square symbol at size 10: 9.5 tall and wide, plus a 0.8 gap.
    assert symbols.measure("{T}", "Helvetica", 10, fixed_width) == pytest.approx(10.3)


def test_symbol_width_follows_the_view_box_aspect():
    symbols = SymbolSet({"{100}": parse_svg(WIDE_SVG)})
    assert symbols.measure("{100}", "Helvetica", 10, fixed_width) == pytest.approx(19.8)


def test_symbol_not_held_measures_as_text():
    symbols = SymbolSet({"{T}": parse_svg(CIRCLE_SVG)})
    assert symbols.measure("{Q}", "Helvetica", 10, fixed_width) == fixed_width(
        "{Q}", "Helvetica", 10
    )
    assert NO_SYMBOLS.measure("{T}", "Helvetica", 10, fixed_width) == fixed_width(
        "{T}", "Helvetica", 10
    )


# --- Layout ----------------------------------------------------------------


def _layout(card, symbols):
    page_w, page_h = PAGE_SIZES["letter"]
    return compute_layout(
        card,
        0,
        page_w=page_w,
        page_h=page_h,
        is_token=False,
        measure_width=fixed_width,
        symbols=symbols,
    )


def test_layout_wraps_oracle_text_at_the_symbols_drawn_width():
    card = {
        "name": "Mana Machine",
        "type_line": "Artifact",
        "mana_cost": "{2}",
        "oracle_text": " ".join(["{W}{U}{B}{R}{G}"] * 12),
    }
    square = parse_svg(CIRCLE_SVG)
    symbols = SymbolSet({f"{{{c}}}": square for c in "WUBRG2"})
    as_text = _layout(card, NO_SYMBOLS)
    as_images = _layout(card, symbols)
    # Images are narrower than "{W}" text, so the same words take fewer lines.
    assert len(as_images.oracle_lines) < len(as_text.oracle_lines)
    # The layout keeps the {CODE} form; drawing swaps in the images.
    assert as_images.mana_cost_text == "{2}"
    assert " ".join(as_images.oracle_lines) == card["oracle_text"]


# --- Drawing ---------------------------------------------------------------


class _RecordingCanvas:
    """Just enough of reportlab's Canvas to record what ``draw_text`` emits."""

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def stringWidth(self, text, font, size):  # noqa: N802 — reportlab's name
        return fixed_width(text, font, size)

    def setFont(self, font, size):  # noqa: N802
        self.ops.append(("font", font, size))

    def drawString(self, x, y, text):  # noqa: N802
        self.ops.append(("text", round(x, 3), y, text))

    def saveState(self):  # noqa: N802
        self.ops.append(("save",))

    def restoreState(self):  # noqa: N802
        self.ops.append(("restore",))

    def translate(self, x, y):
        self.ops.append(("translate", round(x, 3), round(y, 3)))

    def scale(self, x, y):
        self.ops.append(("scale", round(x, 4), round(y, 4)))

    def beginPath(self):  # noqa: N802
        return _RecordingPath()

    def setFillColorRGB(self, *rgb):  # noqa: N802
        pass

    def setStrokeColorRGB(self, *rgb):  # noqa: N802
        pass

    def setLineWidth(self, width):  # noqa: N802
        pass

    def drawPath(self, path, *, stroke, fill, fillMode):  # noqa: N802, N803
        self.ops.append(("path", len(path.ops), stroke, fill, fillMode))


class _RecordingPath:
    def __init__(self) -> None:
        self.ops: list[tuple] = []

    def moveTo(self, *a):  # noqa: N802
        self.ops.append(("M", *a))

    def lineTo(self, *a):  # noqa: N802
        self.ops.append(("L", *a))

    def curveTo(self, *a):  # noqa: N802
        self.ops.append(("C", *a))

    def close(self):
        self.ops.append(("Z",))


def test_draw_text_places_text_and_symbols_left_to_right():
    symbols = SymbolSet({"{T}": parse_svg(CIRCLE_SVG)})
    c = _RecordingCanvas()
    symbols.draw_text(c, 100, 50, "{T}: Add {Q}.", "Helvetica", 10)
    # The symbol sits 1.4 below the baseline, 9.5 tall, flipped to the canvas's
    # y-up axis; the text starts after its 10.3 advance.
    assert ("translate", 100, 50 - 1.4 + 9.5) in c.ops
    assert ("scale", 0.095, -0.095) in c.ops
    assert ("text", 110.3, 50, ": Add {Q}.") in c.ops
    # Circle then square, both filled, non-zero winding.
    assert [op for op in c.ops if op[0] == "path"] == [
        ("path", 6, 0, 1, 1),
        ("path", 5, 0, 1, 1),
    ]


def test_draw_text_right_aligned_ends_at_x():
    symbols = SymbolSet({"{2}": parse_svg(CIRCLE_SVG)})
    c = _RecordingCanvas()
    symbols.draw_text(c, 200, 50, "{2}{2}", "Helvetica-Bold", 10, align_right=True)
    starts = [op[1] for op in c.ops if op[0] == "translate"]
    assert starts == pytest.approx([200 - 20.6, 200 - 10.3])


def test_no_symbols_draws_plain_text():
    c = _RecordingCanvas()
    NO_SYMBOLS.draw_text(c, 10, 20, "{T}: Add {G}.", "Helvetica", 7)
    assert c.ops == [("font", "Helvetica", 7), ("text", 10, 20, "{T}: Add {G}.")]
