"""Card symbols ({W}, {T}, {2/U}, …) drawn as Scryfall's symbol images.

Scryfall publishes one SVG per symbol at ``svgs.scryfall.io/card-symbols/``.
:class:`SymbolSet` fetches the ones a print run needs through the shared Scryfall
client (``_scryfall``) into ``<cache>/scryfall/card-symbols/``, parses each into
filled outlines, and draws them on a reportlab canvas. Text that mixes words and
symbols is measured and drawn through the set (:meth:`SymbolSet.measure`,
:meth:`SymbolSet.draw_text`), so the wrap a layout computes and the line the canvas
draws agree.

A symbol the set does not hold (offline, an unknown code, an SVG feature the
parser does not read) is measured and drawn as its ``{CODE}`` text, so a missing
symbol never drops text from a card.

The SVG reader covers what Scryfall's symbol files use (surveyed over all 84):
``<g>`` (``fill`` / ``stroke`` / ``fill-rule`` inheritance, ``translate`` /
``scale`` / ``matrix`` transforms), ``<circle>`` and ``<path>`` with the M L H V
C S A Z commands. Anything else raises :class:`SvgError`.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import requests

from mtg_utils import _scryfall
from mtg_utils._scryfall import ScryfallClient

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

    from mtg_utils._http import Fetcher

SYMBOL_URL = "https://svgs.scryfall.io/card-symbols/{name}.svg"

#: One ``{CODE}`` symbol in a mana cost or oracle text.
SYMBOL_RE = re.compile(r"\{[^{}\s]+\}")

#: Symbol images never change once published; a year keeps the cache from
#: re-fetching on every print run.
_CACHE_SECONDS = 365 * 24 * 3600

#: The two codes whose file name is not the code with ``/`` removed.
_FILE_NAMES = {"½": "HALF", "∞": "INFINITY"}

# A symbol's height and drop below the baseline, as fractions of the font size
# of the text it sits in, and the gap left after it.
_HEIGHT = 0.95
_DROP = 0.14
_GAP = 0.08

MeasureWidth = Callable[[str, str, float], float]
Color = tuple[float, float, float]
Matrix = tuple[float, float, float, float, float, float]
# A path segment in absolute coordinates: ("M", x, y), ("L", x, y),
# ("C", x1, y1, x2, y2, x, y) or ("Z",).
Segment = tuple


class SvgError(ValueError):
    """An SVG uses something the symbol reader does not handle."""


@dataclass(frozen=True, slots=True)
class Shape:
    """One filled and/or stroked outline of a symbol."""

    segments: tuple[Segment, ...]
    fill: Color | None
    stroke: Color | None
    even_odd: bool


@dataclass(frozen=True, slots=True)
class Symbol:
    """A parsed symbol: its view box size and the shapes drawn inside it."""

    width: float
    height: float
    shapes: tuple[Shape, ...]


#: The symbol cache's directory under the Scryfall cache.
SYMBOLS_SUBDIR = "card-symbols"


def symbols_dir() -> Path:
    """Where fetched symbol SVGs are cached."""
    return _scryfall.cache_dir() / SYMBOLS_SUBDIR


def symbol_file_name(code: str) -> str:
    """``{W/U}`` -> ``WU``: the stem of Scryfall's SVG file for a symbol."""
    inner = code.strip("{}")
    return _FILE_NAMES.get(inner, inner.replace("/", ""))


def find_symbols(texts: Iterable[str]) -> set[str]:
    """Every distinct ``{CODE}`` in *texts*."""
    return {code for text in texts for code in SYMBOL_RE.findall(text)}


# --- SVG reading -----------------------------------------------------------

_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_TRANSFORM = re.compile(r"(\w+)\s*\(([^)]*)\)")
_ARG_COUNT = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "A": 7, "Z": 0}


def _compose(outer: Matrix, inner: Matrix) -> Matrix:
    """The matrix that applies *inner* first, then *outer*."""
    a, b, c, d, e, f = outer
    g, h, i, j, k, m = inner
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * m + e,
        b * k + d * m + f,
    )


def _apply(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _parse_transform(text: str | None) -> Matrix:
    matrix = _IDENTITY
    for name, raw in _TRANSFORM.findall(text or ""):
        args = [float(n) for n in _NUMBER.findall(raw)]
        if name == "translate" and len(args) in (1, 2):
            step: Matrix = (1.0, 0.0, 0.0, 1.0, args[0], args[1] if args[1:] else 0.0)
        elif name == "scale" and len(args) in (1, 2):
            step = (args[0], 0.0, 0.0, args[-1], 0.0, 0.0)
        elif name == "matrix" and len(args) == 6:
            step = (args[0], args[1], args[2], args[3], args[4], args[5])
        else:
            raise SvgError(f"unsupported transform: {name}({raw})")
        matrix = _compose(matrix, step)
    return matrix


def _parse_color(text: str | None, inherited: Color | None) -> Color | None:
    if text is None:
        return inherited
    text = text.strip().lower()
    if text == "none":
        return None
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        text = "#" + "".join(ch * 2 for ch in text[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return (
            int(text[1:3], 16) / 255,
            int(text[3:5], 16) / 255,
            int(text[5:7], 16) / 255,
        )
    raise SvgError(f"unsupported color: {text}")


def _path_commands(d: str) -> Iterator[tuple[str, list[float]]]:
    """Yield ``(command letter, arguments)`` for each command in a path's ``d``,
    one per repetition of an implicitly repeated command."""
    pos = 0
    command = ""
    while True:
        while pos < len(d) and d[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(d):
            return
        if d[pos].isalpha():
            command = d[pos]
            pos += 1
            if command.upper() not in _ARG_COUNT:
                raise SvgError(f"unsupported path command: {command}")
            if command in "Zz":
                yield command, []
                continue
        elif not command or command in "Zz":
            raise SvgError("path data does not start with a command")
        args: list[float] = []
        for index in range(_ARG_COUNT[command.upper()]):
            while pos < len(d) and d[pos] in " \t\r\n,":
                pos += 1
            # An arc's two flags are single digits that may run together ("01").
            if command in "Aa" and index in (3, 4):
                if pos >= len(d) or d[pos] not in "01":
                    raise SvgError("malformed arc flag")
                args.append(float(d[pos]))
                pos += 1
                continue
            match = _NUMBER.match(d, pos)
            if match is None:
                raise SvgError(f"malformed path data near offset {pos}")
            args.append(float(match.group()))
            pos = match.end()
        yield command, args
        # After a moveto, repeated coordinate pairs are implicit linetos.
        if command == "M":
            command = "L"
        elif command == "m":
            command = "l"


def _arc_to_curves(
    x0: float,
    y0: float,
    rx: float,
    ry: float,
    rotation_deg: float,
    x1: float,
    y1: float,
    *,
    large: bool,
    sweep: bool,
) -> list[Segment]:
    """An SVG elliptical arc as cubic Béziers (SVG 1.1 appendix F.6)."""
    if (x0, y0) == (x1, y1):
        return []
    if rx == 0 or ry == 0:
        return [("L", x1, y1)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    xp = cos_phi * dx + sin_phi * dy
    yp = -sin_phi * dx + cos_phi * dy
    scale = (xp / rx) ** 2 + (yp / ry) ** 2
    if scale > 1:
        rx *= math.sqrt(scale)
        ry *= math.sqrt(scale)
    num = (rx * ry) ** 2 - (rx * yp) ** 2 - (ry * xp) ** 2
    den = (rx * yp) ** 2 + (ry * xp) ** 2
    coef = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp, cyp = coef * rx * yp / ry, -coef * ry * xp / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x0 + x1) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y0 + y1) / 2
    theta = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    delta = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx) - theta
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi

    def point(angle: float) -> tuple[float, float]:
        ex, ey = rx * math.cos(angle), ry * math.sin(angle)
        return cx + cos_phi * ex - sin_phi * ey, cy + sin_phi * ex + cos_phi * ey

    def tangent(angle: float) -> tuple[float, float]:
        ex, ey = -rx * math.sin(angle), ry * math.cos(angle)
        return cos_phi * ex - sin_phi * ey, sin_phi * ex + cos_phi * ey

    pieces = max(1, math.ceil(abs(delta) / (math.pi / 2) - 1e-9))
    step = delta / pieces
    handle = 4 / 3 * math.tan(step / 4)
    out: list[Segment] = []
    for i in range(pieces):
        a0, a1 = theta + i * step, theta + (i + 1) * step
        (sx, sy), (ex, ey) = point(a0), point(a1)
        (t0x, t0y), (t1x, t1y) = tangent(a0), tangent(a1)
        out.append(
            (
                "C",
                sx + handle * t0x,
                sy + handle * t0y,
                ex - handle * t1x,
                ey - handle * t1y,
                ex,
                ey,
            )
        )
    return out


def _path_segments(d: str) -> list[Segment]:
    """A path's ``d`` as absolute M / L / C / Z segments."""
    out: list[Segment] = []
    x = y = start_x = start_y = 0.0
    last_ctrl: tuple[float, float] | None = None
    for command, args in _path_commands(d):
        relative = command.islower()
        kind = command.upper()
        ox, oy = (x, y) if relative else (0.0, 0.0)
        ctrl: tuple[float, float] | None = None
        if kind == "Z":
            out.append(("Z",))
            x, y = start_x, start_y
        elif kind == "M":
            x, y = ox + args[0], oy + args[1]
            start_x, start_y = x, y
            out.append(("M", x, y))
        elif kind == "L":
            x, y = ox + args[0], oy + args[1]
            out.append(("L", x, y))
        elif kind == "H":
            x = ox + args[0]
            out.append(("L", x, y))
        elif kind == "V":
            y = oy + args[0]
            out.append(("L", x, y))
        elif kind in "CS":
            if kind == "C":
                x1, y1 = ox + args[0], oy + args[1]
                rest = args[2:]
            else:
                # Smooth curve: the first handle mirrors the previous one.
                x1, y1 = (
                    (2 * x - last_ctrl[0], 2 * y - last_ctrl[1])
                    if last_ctrl
                    else (x, y)
                )
                rest = args
            x2, y2 = ox + rest[0], oy + rest[1]
            x, y = ox + rest[2], oy + rest[3]
            out.append(("C", x1, y1, x2, y2, x, y))
            ctrl = (x2, y2)
        else:  # "A"
            end_x, end_y = ox + args[5], oy + args[6]
            out.extend(
                _arc_to_curves(
                    x,
                    y,
                    args[0],
                    args[1],
                    args[2],
                    end_x,
                    end_y,
                    large=bool(args[3]),
                    sweep=bool(args[4]),
                )
            )
            x, y = end_x, end_y
        last_ctrl = ctrl
    return out


def _circle_segments(cx: float, cy: float, r: float) -> list[Segment]:
    return [
        ("M", cx + r, cy),
        *_arc_to_curves(cx + r, cy, r, r, 0, cx - r, cy, large=False, sweep=True),
        *_arc_to_curves(cx - r, cy, r, r, 0, cx + r, cy, large=False, sweep=True),
        ("Z",),
    ]


def _transformed(segments: list[Segment], matrix: Matrix) -> tuple[Segment, ...]:
    out: list[Segment] = []
    for seg in segments:
        coords: list[float] = []
        for i in range(1, len(seg), 2):
            coords.extend(_apply(matrix, seg[i], seg[i + 1]))
        out.append((seg[0], *coords))
    return tuple(out)


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


@dataclass(frozen=True, slots=True)
class _Style:
    fill: Color | None = (0.0, 0.0, 0.0)  # SVG's default fill is black
    stroke: Color | None = None
    even_odd: bool = False
    matrix: Matrix = _IDENTITY

    def inherit(self, element: ET.Element) -> _Style:
        rule = element.get("fill-rule")
        return _Style(
            fill=_parse_color(element.get("fill"), self.fill),
            stroke=_parse_color(element.get("stroke"), self.stroke),
            even_odd=self.even_odd if rule is None else rule == "evenodd",
            matrix=_compose(self.matrix, _parse_transform(element.get("transform"))),
        )


def _collect(element: ET.Element, parent: _Style, shapes: list[Shape]) -> None:
    style = parent.inherit(element)
    tag = _tag(element)
    if tag in {"svg", "g"}:
        for child in element:
            _collect(child, style, shapes)
        return
    if tag == "path":
        segments = _path_segments(element.get("d") or "")
    elif tag == "circle":
        segments = _circle_segments(
            float(element.get("cx") or 0),
            float(element.get("cy") or 0),
            float(element.get("r") or 0),
        )
    elif tag in {"title", "desc", "defs", "metadata"}:
        return
    else:
        raise SvgError(f"unsupported element: <{tag}>")
    if segments and (style.fill is not None or style.stroke is not None):
        shapes.append(
            Shape(
                segments=_transformed(segments, style.matrix),
                fill=style.fill,
                stroke=style.stroke,
                even_odd=style.even_odd,
            )
        )


def parse_svg(text: str | bytes) -> Symbol:
    """Parse one symbol SVG. Raises :class:`SvgError` on anything unsupported."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise SvgError(f"not well-formed XML: {e}") from e
    box = [float(n) for n in _NUMBER.findall(root.get("viewBox") or "")]
    if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
        raise SvgError("missing or malformed viewBox")
    shapes: list[Shape] = []
    origin = _Style(matrix=(1.0, 0.0, 0.0, 1.0, -box[0], -box[1]))
    _collect(root, origin, shapes)
    if not shapes:
        raise SvgError("no drawable shapes")
    return Symbol(width=box[2], height=box[3], shapes=tuple(shapes))


# --- The set a print run draws with ----------------------------------------


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


class SymbolSet:
    """The parsed symbols a print run can draw, keyed by ``{CODE}``."""

    def __init__(self, symbols: dict[str, Symbol] | None = None) -> None:
        self._symbols = dict(symbols or {})

    @classmethod
    def load(cls, codes: Iterable[str], fetcher: Fetcher | None = None) -> SymbolSet:
        """Fetch (or read from cache) and parse the SVG for each code.

        Never raises for a symbol it cannot get: an unknown code or an unreadable
        SVG is left out with a warning, and the first network failure stops the
        fetching (so an offline run warns once and prints ``{CODE}`` text).
        """
        if fetcher is None:
            fetcher = ScryfallClient(SYMBOLS_SUBDIR, max_age_seconds=_CACHE_SECONDS)
        symbols: dict[str, Symbol] = {}
        for code in sorted(set(codes)):
            name = symbol_file_name(code)
            if not re.fullmatch(r"[A-Z0-9]+", name):
                continue
            try:
                raw = fetcher.fetch(SYMBOL_URL.format(name=name), f"{name}.svg")
            except requests.HTTPError:
                _warn(f"no symbol image for {code}; printing it as text")
                continue
            except (requests.RequestException, OSError) as e:
                _warn(f"cannot fetch card symbols ({e}); printing them as text")
                break
            try:
                symbols[code] = parse_svg(raw)
            except SvgError as e:
                _warn(f"cannot read the symbol image for {code} ({e})")
        return cls(symbols)

    def __contains__(self, code: object) -> bool:
        return code in self._symbols

    def __len__(self) -> int:
        return len(self._symbols)

    def _advance(self, code: str, size: float) -> float:
        symbol = self._symbols[code]
        return size * _HEIGHT * symbol.width / symbol.height + size * _GAP

    def _runs(self, text: str) -> Iterator[tuple[str, bool]]:
        """*text* as ``(piece, is_drawn_symbol)`` runs, in order."""
        pos = 0
        for match in SYMBOL_RE.finditer(text):
            if match.group() not in self._symbols:
                continue
            if match.start() > pos:
                yield text[pos : match.start()], False
            yield match.group(), True
            pos = match.end()
        if pos < len(text):
            yield text[pos:], False

    def measure(
        self, text: str, font: str, size: float, measure_width: MeasureWidth
    ) -> float:
        """The width of *text* with every held symbol drawn as its image."""
        return sum(
            self._advance(piece, size) if drawn else measure_width(piece, font, size)
            for piece, drawn in self._runs(text)
        )

    def measurer(self, measure_width: MeasureWidth) -> MeasureWidth:
        """A ``measure_width`` that accounts for this set's symbols."""

        def measure(text: str, font: str, size: float) -> float:
            return self.measure(text, font, size, measure_width)

        return measure

    def draw(self, c: Canvas, code: str, x: float, y: float, height: float) -> None:
        """Draw one symbol with its bottom-left corner at ``(x, y)``."""
        symbol = self._symbols[code]
        k = height / symbol.height
        c.saveState()
        # SVG's y axis points down; the canvas's points up.
        c.translate(x, y + height)
        c.scale(k, -k)
        for shape in symbol.shapes:
            path = c.beginPath()
            for seg in shape.segments:
                if seg[0] == "M":
                    path.moveTo(seg[1], seg[2])
                elif seg[0] == "L":
                    path.lineTo(seg[1], seg[2])
                elif seg[0] == "C":
                    path.curveTo(*seg[1:])
                else:
                    path.close()
            if shape.fill is not None:
                c.setFillColorRGB(*shape.fill)
            if shape.stroke is not None:
                c.setStrokeColorRGB(*shape.stroke)
                c.setLineWidth(1)
            c.drawPath(
                path,
                stroke=int(shape.stroke is not None),
                fill=int(shape.fill is not None),
                fillMode=0 if shape.even_odd else 1,
            )
        c.restoreState()

    def draw_text(
        self,
        c: Canvas,
        x: float,
        y: float,
        text: str,
        font: str,
        size: float,
        *,
        align_right: bool = False,
    ) -> None:
        """Draw *text* on baseline *y*, held symbols as images. *x* is the left
        edge, or the right edge when *align_right*."""
        if align_right:
            x -= self.measure(text, font, size, c.stringWidth)
        c.setFont(font, size)
        for piece, drawn in self._runs(text):
            if drawn:
                self.draw(c, piece, x, y - size * _DROP, size * _HEIGHT)
                x += self._advance(piece, size)
            else:
                c.drawString(x, y, piece)
                x += c.stringWidth(piece, font, size)


#: The set with no symbols: everything measures and draws as plain text.
NO_SYMBOLS = SymbolSet()
