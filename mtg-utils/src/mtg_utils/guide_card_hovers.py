"""guide-card-hovers / twohg-template: card-image hovers for a set guide page.

A 2HG prerelease guide (``twohg-template`` writes the blank one) is one HTML page
whose ``<script>`` holds ``const CARDS = {...};`` — card name -> image path — and
wraps every such name inside the ``.cols`` content region in a hover target that
shows the card. ``guide-card-hovers`` fills that map from the page's own text:

1. **Text.** The visible text of ``.cols`` — the same text nodes the page's script
   walks: links, headings, scripts and styles are skipped. Each text node is joined
   with a space, so a tag boundary never glues two words together (a table's
   rarity cell ``U`` beside ``Winter, Tormented Loner`` must not read "UWinter").
2. **Names.** Every card in the set is searched for by its full name and by each face
   name (an MDFC's or a prepare card's other half), with the page script's own
   word-boundary rule, longest name first — so "Bosh, Iron Golem" is one match, not
   also "Iron Golem". A face name that several cards share ("Vicious Verse" is a face
   of three) is ambiguous: it hovers only when ``--alias "FACE=CARD"`` says which
   card, and is otherwise reported and skipped. An alias key need not be a face name
   at all; any phrase the page uses can point at a card.
3. **Printing.** Per card, the printing ``CardPool.set_records`` lists (the lowest
   collector number in the set); its image is ``image_uris``' ``normal`` or, for a
   multi-face card, the front face's.
4. **Images.** Downloaded once into a shared cache
   ``<cache>/card-images/<scryfall-id>.jpg`` (``_http.cache_root()``), throttled
   between network fetches, then written to ``<out>/cards/<slug>.jpg`` (slug: the
   front face's name, ASCII-folded, lowercased, apostrophes dropped and every other
   non-alphanumeric run a ``-`` — ``names.slug``).
5. **Output.** ``<out>/<guide file name>`` with the map rewritten, and
   ``<out>/files.json`` — ``[{"path": "cards/<slug>.jpg"}, ...]``, the shape an
   Artifact publish's ``files`` takes with ``root`` set to ``<out>``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import click
from bs4 import BeautifulSoup
from bs4.element import PreformattedString

from mtg_utils._http import Fetcher, HttpFetcher, cache_root
from mtg_utils.card_images import image_urls
from mtg_utils.card_pool import CardPool
from mtg_utils.companion import _front_name
from mtg_utils.deck_cli import bulk_data_option, resolve_bulk_path
from mtg_utils.names import normalize_card_name, slug

__all__ = [
    "HoverResult",
    "build_hovers",
    "card_slug",
    "find_names",
    "guide_text",
    "image_url",
    "main",
    "read_template",
    "replace_cards_map",
    "template_main",
]

#: ``const CARDS = {...};`` in the page's hover script (``{}`` in the blank template).
_CARDS_MAP = re.compile(r"(const\s+CARDS\s*=\s*)\{.*?\}(\s*;)", re.DOTALL)

#: What the page's hover script never marks: links, headings, code, marks it made.
_SKIP_TAGS = ("a", "h2", "script", "style", "template", "footer")

#: A card image never changes once Scryfall serves it: keep cached ones a year.
_IMAGE_MAX_AGE_SECONDS = 365 * 86400


# --- Finding names ------------------------------------------------------------


def guide_text(html: str) -> str:
    """The text the page's hover script walks: ``.cols`` (else ``<body>``) minus
    links, headings, scripts, styles and the footer, one text node per chunk, joined
    with a space so no two tags' text runs together."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".cols") or soup.body or soup
    chunks = [
        str(s)
        for s in root.find_all(string=True)
        if s.find_parent(_SKIP_TAGS) is None
        and s.find_parent(class_="cn") is None
        and not isinstance(s, PreformattedString)  # not a comment / doctype
    ]
    return " ".join(chunks)


def _name_pattern(names: Iterable[str]) -> re.Pattern[str] | None:
    """The page script's matcher: longest name first, no word char or ``'`` on either
    side."""
    ordered = sorted(set(names), key=lambda n: (-len(n), n))
    if not ordered:
        return None
    alts = "|".join(re.escape(n) for n in ordered)
    return re.compile(rf"(?<![\w'])({alts})(?![\w'])")


def find_names(text: str, names: Iterable[str]) -> list[str]:
    """The *names* that occur in *text*, in order of first appearance. Matching is
    leftmost, longest first and non-overlapping, like the hover script's."""
    pattern = _name_pattern(names)
    if pattern is None:
        return []
    found: dict[str, None] = {}
    for m in pattern.finditer(text):
        found.setdefault(m.group(1), None)
    return list(found)


# --- Cards --------------------------------------------------------------------


def _card_key(record: dict) -> str:
    return record.get("oracle_id") or record.get("name", "")


def _faces(record: dict) -> list[str]:
    return [f["name"] for f in record.get("card_faces") or [] if f.get("name")]


def card_slug(record: dict) -> str:
    """``names.slug`` of the front face's ASCII-folded name: ``Lich's Relic`` ->
    ``lichs-relic``."""
    return slug(normalize_card_name(_front_name(record)))


def image_url(record: dict) -> str | None:
    """The ``normal`` image: ``image_uris``', else the front face's."""
    return (image_urls(record) or {}).get("normal")


def _search_names(cards: dict[str, dict]) -> dict[str, set[str]]:
    """name -> the card keys it can mean: each card's full name and face names."""
    out: dict[str, set[str]] = {}
    for key, rec in cards.items():
        for name in {rec.get("name", ""), *_faces(rec)} - {""}:
            out.setdefault(name, set()).add(key)
    return out


def _resolve_alias(target: str, cards: dict[str, dict]) -> str:
    """The card key an alias's CARD half names: a full name or a front-face name
    (case- and accent-insensitive, ``names.normalize_card_name``)."""
    want = normalize_card_name(target.strip())
    for key, rec in cards.items():
        if want in {
            normalize_card_name(rec.get("name", "")),
            normalize_card_name(_front_name(rec)),
        }:
            return key
    msg = f"--alias target {target!r} is not a card in this set"
    raise ValueError(msg)


# --- Output -------------------------------------------------------------------


def replace_cards_map(html: str, cards_map: dict[str, str]) -> str:
    """*html* with its ``const CARDS = {...};`` replaced by *cards_map* (JSON)."""
    if not _CARDS_MAP.search(html):
        msg = (
            "the page has no `const CARDS = {...};` map for the card hovers — start "
            "from `twohg-template`, whose hover script carries one"
        )
        raise ValueError(msg)
    body = json.dumps(cards_map, ensure_ascii=False)
    return _CARDS_MAP.sub(lambda m: f"{m.group(1)}{body}{m.group(2)}", html, count=1)


@dataclass
class HoverResult:
    cards_map: dict[str, str] = field(default_factory=dict)
    files: list[dict[str, str]] = field(default_factory=list)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    unused_aliases: list[str] = field(default_factory=list)
    no_image: list[str] = field(default_factory=list)

    @property
    def cards(self) -> int:
        """Distinct cards hovered: one image file each."""
        return len(self.files)


def build_hovers(
    guide: Path,
    set_cards: list[dict],
    *,
    out_dir: Path,
    fetcher: Fetcher,
    aliases: dict[str, str] | None = None,
    throttle: float = 0.1,
) -> HoverResult:
    """Fill *guide*'s card-hover map from *set_cards* (one printing per card, as
    ``CardPool.set_records`` lists them) and write the page, its card images and
    ``files.json`` under *out_dir*. Images come through *fetcher*, cached under
    ``<scryfall-id>.jpg`` and throttled by *throttle* seconds per network fetch.

    Raises ``ValueError`` when the page has no ``CARDS`` map or an alias names a card
    the set lacks."""
    html = guide.read_text(encoding="utf-8")
    replace_cards_map(html, {})  # fail before any download when there is no map

    cards = {_card_key(rec): rec for rec in set_cards}

    meaning = _search_names(cards)
    alias_keys = {
        name: _resolve_alias(target, cards) for name, target in (aliases or {}).items()
    }
    matched = find_names(guide_text(html), set(meaning) | set(alias_keys))

    result = HoverResult()
    chosen: dict[str, str] = {}  # matched name -> card key
    for name in matched:
        if name in alias_keys:
            chosen[name] = alias_keys[name]
        elif len(meaning[name]) == 1:
            chosen[name] = next(iter(meaning[name]))
        else:
            result.ambiguous[name] = sorted(cards[k]["name"] for k in meaning[name])
    result.unused_aliases = sorted(set(alias_keys) - set(matched))

    (out_dir / "cards").mkdir(parents=True, exist_ok=True)
    placed: dict[str, str] = {}  # card key -> "cards/<slug>.jpg"
    for name in sorted(chosen):
        key = chosen[name]
        rec = cards[key]
        if key not in placed:
            url = image_url(rec)
            if url is None:
                if rec.get("name", name) not in result.no_image:
                    result.no_image.append(rec.get("name", name))
                continue
            ident = rec.get("id") or f"{rec.get('set')}-{rec.get('collector_number')}"
            data = fetcher.fetch(url, f"{ident}.jpg", throttle=throttle)
            rel = f"cards/{card_slug(rec)}.jpg"
            (out_dir / rel).write_bytes(data)
            placed[key] = rel
        result.cards_map[name] = placed[key]

    result.files = [{"path": p} for p in sorted(set(placed.values()))]
    (out_dir / guide.name).write_text(
        replace_cards_map(html, result.cards_map), encoding="utf-8"
    )
    (out_dir / "files.json").write_text(
        json.dumps(result.files, indent=2) + "\n", encoding="utf-8"
    )
    return result


def _parse_aliases(values: tuple[str, ...]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for value in values:
        face, sep, card = value.partition("=")
        if not sep or not face.strip() or not card.strip():
            msg = f"--alias {value!r}: expected FACE=CARD"
            raise click.BadParameter(msg)
        aliases[face.strip()] = card.strip()
    return aliases


@click.command()
@click.argument("guide", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--set", "set_code", required=True, help="Set code, e.g. FRA.")
@click.option(
    "--out",
    "out_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output folder: the page, cards/*.jpg and files.json.",
)
@click.option(
    "--alias",
    "alias_values",
    multiple=True,
    metavar="FACE=CARD",
    help="Hover a name (e.g. a face several cards share) as CARD. Repeatable.",
)
@bulk_data_option
def main(
    guide: Path,
    set_code: str,
    out_dir: Path,
    alias_values: tuple[str, ...],
    bulk_data: Path | None,
) -> None:
    """Fill a guide page's card-image hover map from the set's card names in its
    text, download the images (cached), and write the page + files.json to OUT."""
    aliases = _parse_aliases(alias_values)
    pool = CardPool.load(resolve_bulk_path(bulk_data))
    set_cards = pool.set_records(set_code)
    if not set_cards:
        raise click.ClickException(f"no cards found for set {set_code!r}")
    images = cache_root() / "card-images"
    fetcher = HttpFetcher(images, max_age_seconds=_IMAGE_MAX_AGE_SECONDS)
    try:
        result = build_hovers(
            guide, set_cards, out_dir=out_dir, fetcher=fetcher, aliases=aliases
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"{len(result.cards_map)} names -> {result.cards} cards "
        f"(images cached in {images})"
    )
    for name, options in sorted(result.ambiguous.items()):
        click.echo(
            f"WARNING: skipped ambiguous name {name!r} (a face of "
            f'{", ".join(options)}); pass --alias "{name}=CARD"',
            err=True,
        )
    for name in result.unused_aliases:
        click.echo(f"WARNING: --alias {name!r} does not appear in the page", err=True)
    for name in result.no_image:
        click.echo(f"WARNING: no image for {name!r}; skipped", err=True)
    click.echo(f"Wrote {out_dir / guide.name}, {out_dir / 'files.json'}")


# --- The blank template -------------------------------------------------------


def read_template() -> str:
    """The blank 2HG guide page (``mtg_utils/data/twohg/template.html``)."""
    return (
        resources.files("mtg_utils.data.twohg")
        .joinpath("template.html")
        .read_text(encoding="utf-8")
    )


@click.command()
@click.argument("out", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--force", is_flag=True, help="Overwrite OUT if it exists.")
def template_main(out: Path, force: bool) -> None:  # noqa: FBT001 — a click flag
    """Write the blank 2HG prerelease guide page to OUT: the styles, header, the
    fixed section spine (each section says what goes in it) and the card-hover
    script with an empty CARDS map for guide-card-hovers to fill."""
    if out.exists() and not force:
        raise click.ClickException(f"{out} exists; pass --force to overwrite it")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(read_template(), encoding="utf-8")
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    main()
