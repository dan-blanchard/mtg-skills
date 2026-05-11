"""Fetch attributed ASCII art from asciiart.eu for every MTG subtype.

Pulls all subtype names from Scryfall's catalog endpoints, builds a
candidate pool by downloading asciiart.eu category pages (cached on disk
with a 7-day TTL matching the Scryfall bulk), picks the best fit per
subtype (target ~20x10, hard cap 30x13), and writes one attributed
``<subtype>.txt`` into the directory ``proxy_print`` reads from at render
time.

asciiart.eu's FAQ grants reuse with attribution provided the artist's
initials / signature are preserved. Each written file carries a 3-line
header with title, source URL, and a link to the FAQ; the art body
itself is copied verbatim so embedded artist marks survive.

Fail-loud: any HTTP error (Scryfall or asciiart.eu) aborts the run with
a non-zero exit code. A subtype with no acceptable art is not an error;
it's simply left out of the catalog and proxy_print's runtime fallback
chain handles the render.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

import click
import requests

from mtg_utils.proxy_print import attributed_art_dir, slug

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


# --- Endpoints -------------------------------------------------------------

SCRYFALL_BASE = "https://api.scryfall.com"
ASCIIART_BASE = "https://www.asciiart.eu"
USER_AGENT = "mtg-utils/art-fetcher"

SCRYFALL_CATALOGS: tuple[str, ...] = (
    "creature-types",
    "planeswalker-types",
    "land-types",
    "artifact-types",
    "enchantment-types",
    "spell-types",
)


# --- Geometry --------------------------------------------------------------

TARGET_W, TARGET_H = 20, 10
MAX_W, MAX_H = 30, 13


# --- Cache freshness -------------------------------------------------------

CACHE_MAX_AGE_DAYS = 7
FRESHNESS_SECONDS = CACHE_MAX_AGE_DAYS * 86400


# --- Exit codes ------------------------------------------------------------

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_BAD_CACHE = 2


# --- asciiart.eu category list --------------------------------------------

# Pool we always mine. Subtypes that miss the pool fall through to the
# site's /search endpoint, so this list doesn't need to be exhaustive —
# extend it as new gaps are discovered.
CATEGORIES: tuple[str, ...] = (
    # Animals
    "animals/bats", "animals/bears", "animals/beavers",
    "animals/birds-land", "animals/birds-water", "animals/bisons",
    "animals/camels", "animals/cats", "animals/cows", "animals/deer",
    "animals/dogs", "animals/dolphins", "animals/elephants",
    "animals/fish", "animals/frogs", "animals/horses",
    "animals/marsupials", "animals/monkeys", "animals/moose",
    "animals/other-land", "animals/other-water", "animals/rabbits",
    "animals/rhinoceros", "animals/scorpions", "animals/spiders",
    "animals/wolves",
    "animals/insects/ants", "animals/insects/bees",
    "animals/insects/beetles", "animals/insects/butterflies",
    "animals/insects/caterpillars", "animals/insects/cockroaches",
    "animals/insects/other", "animals/insects/snails",
    "animals/insects/worms",
    "animals/reptiles/alligators", "animals/reptiles/dinosaurs",
    "animals/reptiles/lizards", "animals/reptiles/snakes",
    "animals/reptiles/turtles",
    "animals/rodents/mice", "animals/rodents/other",
    # Mythology — most subcategories map to a creature subtype.
    "mythology/centaurs", "mythology/devils", "mythology/dragons",
    "mythology/fairies", "mythology/ghosts", "mythology/gryphon",
    "mythology/mermaids", "mythology/monsters", "mythology/phoenix",
    "mythology/skeletons", "mythology/unicorns",
    # Plants — Plant, Fungus, Treefolk subtypes.
    "plants/bonsai-trees", "plants/cactus", "plants/flowers",
    "plants/leaf", "plants/mushroom", "plants/roses",
    # Religion — Angel, Cleric, Monk subtypes.
    "religion/angels", "religion/saints",
    # Space — Alien, Spacecraft, Astronaut.
    "space/aliens", "space/astronauts", "space/spaceships", "space/planets",
    # Nature — Land subtypes (Mountain, Island, Desert) + Cloud / Storm flavor.
    "nature/mountains", "nature/islands", "nature/deserts",
    "nature/landscapes", "nature/waterfall", "nature/clouds",
    "nature/lightning",
    # People — Human fallback + occupations as class subtypes (Knight,
    # Wizard, …).
    "people/men", "people/women", "people/faces", "people/famous",
    "people/babies",
    "people/occupations/knights", "people/occupations/kings",
    "people/occupations/wizards", "people/occupations/vikings",
    "people/occupations/cowboys", "people/occupations/clowns",
    "people/occupations/police",
    # Weapons — Equipment subtype variations + Soldier.
    "weapons/swords", "weapons/axes", "weapons/bows-and-arrows",
    "weapons/shields", "weapons/soldiers",
    # Buildings — Land flavor (castle, temple, bridge).
    "buildings-and-places/castles", "buildings-and-places/temple",
    "buildings-and-places/bridges",
    # Electronics — Robot / Construct artifact creatures.
    "electronics/robots",
    # Music — Bard subtype.
    "music/musicians", "music/musical-instruments",
)


# --- Card extractor --------------------------------------------------------

_CARD_RE = re.compile(
    r'<div class="card art-card[^"]*"[^>]*?'
    r'data-id="(?P<id>[^"]+)"[^>]*?'
    r'data-title="(?P<title>[^"]*)"[^>]*?'
    r'data-artist="(?P<artist>[^"]*)"[^>]*?'
    r'data-height="(?P<height>\d+)"[^>]*?'
    r'data-width="(?P<width>\d+)"[^>]*?>'
    r'.*?<div class="art-card__ascii">(?P<art>.*?)</div>',
    re.DOTALL,
)


def _parse_cards(text: str, source_path: str) -> list[dict]:
    out: list[dict] = []
    for m in _CARD_RE.finditer(text):
        out.append({
            "id": m.group("id"),
            "title": html.unescape(m.group("title")),
            "artist": html.unescape(m.group("artist")),
            "height": int(m.group("height")),
            "width": int(m.group("width")),
            "art": html.unescape(m.group("art")).strip("\n"),
            "source_path": source_path,
        })
    return out


# --- Synonyms --------------------------------------------------------------

# subtype slug -> ordered list of extra query terms to try after the
# subtype's own name. Add entries when a subtype's literal name doesn't
# match anything on asciiart.eu but a related term would.
SYNONYMS: dict[str, list[str]] = {
    # Animals whose archive entry uses a different/related word
    "ape": ["gorilla", "monkey"],
    "aurochs": ["bull", "buffalo"],
    "boar": ["pig", "hog"],
    "elk": ["moose", "deer"],
    "hamster": ["hampster"],
    "ox": ["bull", "cow"],
    "raccoon": ["racoon"],
    "seal": ["walrus"],
    "weasel": ["ferret"],
    # Fantasy / generic mappings
    "berserker": ["barbarian"],
    "brushwagg": ["plant"],
    "construct": ["robot"],
    "horror": ["monster"],
    "homunculus": ["imp"],
    "incarnation": ["spirit"],
    "kavu": ["lizard"],
    "lhurgoyf": ["monster"],
    "moonfolk": ["wizard"],
    "rebel": ["soldier"],
    "scout": ["ranger"],
    "shaman": ["sorcerer"],
    "spacecraft": ["spaceship"],
    "warlock": ["wizard"],
    "zombie": ["skeleton"],
    # MTG planeswalker names -> closest class / signature creature
    "ajani": ["lion", "cat"],
    "ashiok": ["nightmare"],
    "basri": ["soldier"],
    "bolas": ["dragon"],
    "chandra": ["mage", "wizard"],
    "dack": ["rogue"],
    "daretti": ["goblin"],
    "domri": ["barbarian"],
    "elspeth": ["knight"],
    "estrid": ["fairy"],
    "freyalise": ["elf"],
    "garruk": ["hunter", "warrior"],
    "gideon": ["knight"],
    "huatli": ["warrior"],
    "jace": ["wizard", "mage"],
    "kaito": ["ninja"],
    "karn": ["golem"],
    "kasmina": ["wizard"],
    "kaya": ["ghost", "assassin"],
    "kiora": ["mermaid"],
    "liliana": ["necromancer", "witch"],
    "narset": ["monk"],
    "nissa": ["druid"],
    "nixilis": ["demon"],
    "oko": ["faerie", "fairy"],
    "ral": ["wizard"],
    "rowan": ["knight"],
    "saheeli": ["artificer"],
    "samut": ["warrior"],
    "sarkhan": ["dragon"],
    "sorin": ["vampire"],
    "tamiyo": ["wizard"],
    "teferi": ["wizard"],
    "tezzeret": ["wizard"],
    "tibalt": ["devil"],
    "ugin": ["dragon"],
    "urza": ["wizard", "mage"],
    "venser": ["wizard"],
    "vivien": ["ranger", "hunter"],
    "vraska": ["gorgon"],
    "windgrace": ["panther", "cat"],
    "wrenn": ["dryad"],
    "xenagos": ["satyr"],
    "zariel": ["devil"],
}


# Slugs we never write a file for: MTG-only mechanics, frame markers,
# named planes, common articles. proxy_print's runtime fallback handles
# render for these.
SKIP_SUBTYPES: frozenset[str] = frozenset({
    # Meta / supertype words (proxy_print already filters these via
    # _ART_SKIP_WORDS; listed here for safety in case Scryfall returns them)
    "token", "legendary", "snow", "tribal", "basic", "ongoing",
    "world", "host",
    # MTG-only structural / object subtypes with no representational art
    "attraction", "background", "blood", "bobblehead", "case", "class",
    "clue", "contraption", "food", "gold", "incubator", "lesson", "map",
    "powerstone", "role", "saga", "shard", "treasure",
    # Plane / setting names (Plane card subtypes)
    "alara", "belenon", "dominaria", "equilor", "fabacin", "gallifrey",
    "innistrad", "ir", "ixalan", "kaldheim", "kamigawa", "karsus",
    "kephalai", "lorwyn", "luvion", "mercadia", "mirrodin", "mongseng",
    "moag", "muraganda", "phyrexia", "pyrulea", "rath", "ravnica",
    "regatha", "segovia", "serra", "shadowmoor", "shandalar", "tarkir",
    "theros", "ulgrotha", "vryn", "wildfire", "xerex", "zendikar",
    # Setting metadata / convention markers
    "amsterdam", "chicago", "magiccon", "new", "vegas",
    # Stop-words
    "and", "of", "the",
})


# --- HTTP with cache -------------------------------------------------------

def _is_fresh(path: Path) -> bool:
    return path.is_file() and (time.time() - path.stat().st_mtime) < FRESHNESS_SECONDS


def _cache_root(cache_dir: Path) -> Path:
    root = cache_dir / "ascii-art-fetcher"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _fetch_cached(
    session: requests.Session, url: str, path: Path
) -> bytes:
    """Return ``path`` contents, refreshing from ``url`` if stale/missing.

    Raises on HTTP error (fail-loud); only writes the cache on a 2xx.
    """
    if _is_fresh(path):
        return path.read_bytes()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    return resp.content


def _fetch_cached_json(
    session: requests.Session, url: str, path: Path
) -> dict:
    return json.loads(_fetch_cached(session, url, path).decode("utf-8"))


# --- Pool builders ---------------------------------------------------------

def fetch_subtypes(session: requests.Session, cache: Path) -> list[str]:
    """Return every MTG subtype slug, lowercased, deduped, sorted."""
    seen: set[str] = set()
    for catalog in SCRYFALL_CATALOGS:
        url = f"{SCRYFALL_BASE}/catalog/{catalog}"
        path = cache / f"scryfall-{catalog}.json"
        data = _fetch_cached_json(session, url, path)
        for name in data.get("data", []):
            seen.add(slug(name))
    return sorted(seen)


def build_pool(session: requests.Session, cache: Path) -> list[dict]:
    """Download/refresh every category page and parse out art cards."""
    pool: list[dict] = []
    for cat in CATEGORIES:
        safe = cat.replace("/", "_")
        path = cache / f"asciiart-{safe}.html"
        raw = _fetch_cached(session, f"{ASCIIART_BASE}/{cat}", path)
        pool.extend(_parse_cards(raw.decode("utf-8"), cat))
    return pool


def search_pool(session: requests.Session, cache: Path, query: str) -> list[dict]:
    """Fall back to asciiart.eu's /search?q= endpoint for a single query."""
    safe = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "x"
    path = cache / f"asciiart-search-{safe}.html"
    url = f"{ASCIIART_BASE}/search?q={urllib.parse.quote_plus(query)}"
    raw = _fetch_cached(session, url, path)
    return _parse_cards(raw.decode("utf-8"), f"search?q={query}")


# --- Selection -------------------------------------------------------------

def _fits(card: dict) -> bool:
    return card["width"] <= MAX_W and card["height"] <= MAX_H


def _score(card: dict) -> float:
    """Lower is better. Bias toward TARGET; mildly penalize too-small."""
    w, h = card["width"], card["height"]
    return (
        abs(w - TARGET_W)
        + abs(h - TARGET_H) * 2
        + max(0, TARGET_W - w) * 1.5
        + max(0, TARGET_H - h) * 1.5
    )


def _title_matches(card: dict, query: str) -> bool:
    pat = re.compile(rf"\b{re.escape(query)}\b", re.I)
    return bool(pat.search(card["title"]))


def queries_for(subtype: str) -> list[str]:
    return [subtype, *SYNONYMS.get(subtype, [])]


def select(queries: Iterable[str], pool: list[dict]) -> dict | None:
    """Return the best in-budget card matching any query, or None."""
    for q in queries:
        hits = [c for c in pool if _fits(c) and _title_matches(c, q)]
        if hits:
            return min(hits, key=_score)
    return None


# --- Writer ----------------------------------------------------------------

def write_art(out_dir: Path, key: str, card: dict) -> Path:
    title = card["title"] or "Untitled"
    artist = card["artist"] or "unknown"
    src = card["source_path"]
    src_url = f"{ASCIIART_BASE}/{src}" if not src.startswith("search?") else f"{ASCIIART_BASE}/{src}"
    header = (
        f"# {title} (by {artist})\n"
        f"# Source: {src_url}\n"
        f"# Used with attribution per {ASCIIART_BASE}/faq\n"
        "\n"
    )
    path = out_dir / f"{key}.txt"
    path.write_text(header + card["art"] + "\n", encoding="utf-8")
    return path


# --- Driver ----------------------------------------------------------------

def run(
    *,
    cache_dir: Path,
    out_dir: Path,
    search_fallback: bool = True,
    limit: int | None = None,
    log: Callable[[str], None] = lambda _s: None,
) -> tuple[int, int, int, list[str]]:
    """Drive the whole pipeline.

    Returns ``(written, skipped, missing, missing_keys)``.
    """
    cache = _cache_root(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    log("Fetching Scryfall subtype catalogs...")
    subtypes = fetch_subtypes(session, cache)
    if limit is not None:
        subtypes = subtypes[:limit]
    log(f"  {len(subtypes)} subtype slugs")

    log(f"Building candidate pool ({len(CATEGORIES)} categories)...")
    pool = build_pool(session, cache)
    log(f"  parsed {len(pool)} cards")

    written = 0
    skipped = 0
    missing_keys: list[str] = []

    for st in subtypes:
        if st in SKIP_SUBTYPES:
            skipped += 1
            continue
        queries = queries_for(st)
        card = select(queries, pool)
        if card is None and search_fallback:
            extra = search_pool(session, cache, st)
            card = select(queries, extra)
        if card is None:
            missing_keys.append(st)
            continue
        write_art(out_dir, st, card)
        written += 1

    log(
        f"\nWrote {written} files, skipped {skipped} mechanic/plane subtypes, "
        f"{len(missing_keys)} have no fitting art (proxy_print will fall back)."
    )
    return written, skipped, len(missing_keys), missing_keys


# --- CLI -------------------------------------------------------------------

_DEFAULT_CACHE = Path(os.environ.get("MTG_SKILLS_CACHE_DIR") or "/tmp")


@click.command()
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=_DEFAULT_CACHE,
    show_default=True,
    help=(
        "Root cache directory. HTTP responses are stored under "
        "<cache-dir>/ascii-art-fetcher/ with a 7-day TTL."
    ),
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Where to write attributed art .txt files (read by proxy_print). "
        "Defaults to $MTG_SKILLS_CACHE_DIR/attributed-art."
    ),
)
@click.option(
    "--search-fallback/--no-search-fallback",
    default=True,
    show_default=True,
    help="If a subtype misses the cached pool, try asciiart.eu /search.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Process only the first N Scryfall subtypes (testing).",
)
@click.option(
    "--report-missing",
    is_flag=True,
    help="Print every subtype slug that had no in-budget match.",
)
def main(
    cache_dir: Path,
    out_dir: Path | None,
    search_fallback: bool,
    limit: int | None,
    report_missing: bool,
) -> None:
    """Populate the attributed-art catalog from asciiart.eu."""
    if out_dir is None:
        out_dir = attributed_art_dir()
    try:
        _written, _skipped, _missing, missing_keys = run(
            cache_dir=cache_dir,
            out_dir=out_dir,
            search_fallback=search_fallback,
            limit=limit,
            log=lambda s: click.echo(s, err=True),
        )
    except requests.HTTPError as e:
        click.echo(f"ERROR: HTTP {e.response.status_code} from {e.request.url}", err=True)
        sys.exit(EXIT_FETCH_FAILED)
    except requests.RequestException as e:
        click.echo(f"ERROR: network failure: {e}", err=True)
        sys.exit(EXIT_FETCH_FAILED)
    except (json.JSONDecodeError, OSError) as e:
        click.echo(f"ERROR: cache or parse failure: {e}", err=True)
        sys.exit(EXIT_BAD_CACHE)

    if report_missing and missing_keys:
        for key in missing_keys:
            click.echo(key)


if __name__ == "__main__":
    main()
