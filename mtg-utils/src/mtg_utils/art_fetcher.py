"""Fetch attributed ASCII art for every MTG subtype.

Pulls all subtype names from Scryfall's catalog endpoints, builds a
candidate pool from multiple ASCII art sources (asciiart.eu and Christopher
Johnson's collection at asciiart.website), picks the best fit per subtype
(target ~20x10, hard cap 30x13), and writes one attributed ``<subtype>.txt``
into the directory ``proxy_print`` reads from at render time.

**Sources.** Each ``Source`` carries its own URL builders, HTML parser, and
attribution-header formatter. Today's sources:

- ``asciiart.eu`` — category-page-driven, with an optional ``/search?q=``
  fallback. Reuse with attribution per its FAQ; artist's in-art signature
  is preserved verbatim.
- ``asciiart.website`` — Christopher Johnson's collection. Categories
  auto-discovered from ``browse.php``. Each cat.php page carries JSON-LD
  metadata (artist + URL per piece) plus inline ``<pre>`` art bodies. Each
  written file links back to the per-art URL so per-piece attribution is
  preserved.

A subtype with no acceptable art in any source is not an error; it falls
through to proxy_print's runtime fallback chain at render time.

Fail-loud: any HTTP error (Scryfall or art source) aborts the run with a
non-zero exit code.
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
WEBSITE_BASE = "https://asciiart.website"
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


# --- Polite-crawler throttle -----------------------------------------------

# asciiart.website rate-limits aggressive crawls. 0.4s/request keeps the
# crawler under their threshold during a cold full-pool build.
WEBSITE_THROTTLE_SEC = 0.4


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


# --- asciiart.eu card extractor --------------------------------------------

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
    """asciiart.eu category-page parser."""
    out: list[dict] = []
    for m in _CARD_RE.finditer(text):
        out.append({
            "_source": "eu",
            "id": m.group("id"),
            "title": html.unescape(m.group("title")),
            "artist": html.unescape(m.group("artist")),
            "height": int(m.group("height")),
            "width": int(m.group("width")),
            "art": html.unescape(m.group("art")).strip("\n"),
            "source_path": source_path,
        })
    return out


# --- asciiart.website card extractor ---------------------------------------

# Each cat.php page carries a CollectionPage JSON-LD with hasPart entries
# (name + url + author per piece) and inline <pre data-artwork-id="N"> blocks
# with the actual art body. We zip them by ID.

_WEBSITE_PRE_RE = re.compile(
    r'<pre[^>]*data-artwork-id="(?P<id>\d+)"[^>]*>(?P<art>.*?)</pre>',
    re.DOTALL,
)

_WEBSITE_JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)

_WEBSITE_BROWSE_RE = re.compile(
    r'href="cat\.php\?category_id=(?P<id>\d+)"[^>]*>\s*'
    r'(?P<name>[A-Za-z][^<\n]*?)\s*'
    r'<span class="category-count">\((?P<count>\d+)\)',
)


def _parse_cards_website(text: str, source_path: str) -> list[dict]:
    """asciiart.website cat.php page parser.

    Pulls per-piece metadata from the CollectionPage JSON-LD (name + url +
    author) and matches it to inline ``<pre data-artwork-id=N>`` art bodies
    by ID. Computes width/height from the art body itself (the JSON-LD on
    cat.php doesn't carry dimensions; those live on per-art pages).
    """
    # 1. Collect per-art metadata from JSON-LD.
    metadata: dict[str, dict] = {}
    for m in _WEBSITE_JSONLD_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "CollectionPage":
            continue
        for part in data.get("hasPart", []):
            url = part.get("url", "")
            # url like https://asciiart.website/art/123
            art_id = url.rsplit("/", 1)[-1] if "/art/" in url else ""
            if not art_id:
                continue
            author = (part.get("author") or {}).get("name", "")
            metadata[art_id] = {
                "title": part.get("name", ""),
                "artist": author,
                "url": url,
            }

    # 2. Extract art bodies + compute dimensions.
    out: list[dict] = []
    for m in _WEBSITE_PRE_RE.finditer(text):
        art_id = m.group("id")
        meta = metadata.get(art_id)
        if meta is None:
            continue
        body = html.unescape(m.group("art")).strip("\n")
        if not body:
            continue
        lines = body.splitlines()
        height = len(lines)
        width = max((len(line) for line in lines), default=0)
        out.append({
            "_source": "website",
            "id": art_id,
            "title": meta["title"],
            "artist": meta["artist"],
            "height": height,
            "width": width,
            "art": body,
            "source_path": source_path,
            "url": meta["url"],
        })
    return out


def fetch_website_categories(
    session: requests.Session, cache: Path
) -> list[tuple[str, str]]:
    """Auto-discover asciiart.website categories from browse.php.

    Returns ``[(category_id, name), ...]`` of every category the site
    lists (~635), with HTML entities decoded in names. Callers usually
    filter this through :func:`relevant_categories` before fetching the
    cat.php pages — the bulk of these are non-MTG (TV shows, brand
    logos, holidays, …).
    """
    path = cache / "asciiart-website-browse.html"
    raw = _fetch_cached(session, f"{WEBSITE_BASE}/browse.php", path)
    out: list[tuple[str, str]] = []
    for m in _WEBSITE_BROWSE_RE.finditer(raw.decode("utf-8")):
        name = html.unescape(m.group("name").strip())
        out.append((m.group("id"), name))
    return out


# --- Category filter -------------------------------------------------------

# Parent-category words that don't appear in any Scryfall subtype slug or
# synonym target, but reliably hold MTG-relevant content. Keep this list
# small and conservative.
_MTG_ADJACENT_WORDS: frozenset[str] = frozenset({
    "animal", "bird", "beast", "insect", "reptile", "monster",
    "weapon", "vehicle", "water", "ocean", "sea", "tree", "fish",
})


# asciiart.website category names whose tokens match an MTG keyword but
# whose content is a TV show / movie / cartoon character / brand — not
# representative of the MTG subtype. Without this denylist, "Lion King"
# pollutes the Lion subtype with Disney art, "Spider-Man" pollutes
# Spider, etc. Compared lowercase against the category name as-fetched.
#
# Trade-offs called out inline:
#  - "spider-man": MTG has Spider Hero subtype cards that would benefit
#    from this category; the simpler design is to skip and accept that
#    Spider Hero subtype falls through to creature.txt / _generic.
#
# We deliberately keep "Lord Of The Rings / Tolkien" — the user's decks
# include LOTR-set MTG cards and they prefer Tolkien art over generic
# fantasy art for Wizard / Elf / Dwarf when it scores well.
_FRANCHISE_SKIP_CATEGORIES: frozenset[str] = frozenset({
    # Cartoon characters whose names match an MTG subtype/synonym.
    "beavis and butt-head",
    "cartoon planet",
    "casper the friendly ghost",
    "donald duck",
    "felix the cat",
    "mickey mouse",
    "mighty mouse",
    "pink panther",
    "rocky and bullwinkle",
    "roger rabbit",
    "spongebob squarepants",
    "tiny toon adventures",
    # TV / movies / fictional franchises.
    "alien",                       # Ridley Scott Alien (MTG Alien uses /space/aliens).
    "beauty and the beast",
    "bear in the big blue house",
    "blue's clues",
    "buffy the vampire slayer",
    "charlie's angels",
    "crocodile dundee",
    "dragon ball",
    "fox and the hound",
    "ghostbusters",
    "land of the lustrous",
    "lion king",
    "little mermaid",
    "monkey island",
    "monsters inc.",
    "paddington bear",
    "ranger rick",
    "red dwarf",
    "sandra bullock",
    "sonic the hedgehog",
    "spider-man",                  # MTG Spider Hero subtype loses Marvel art (trade-off).
    "toy story",
    "vampire princess miyu",
    "wallace & gromit",
    # Brand-name overlaps.
    "red dog beer",
    "u.s. army corps of engineers",
    # Real-world landmarks (one image, doesn't represent any subtype).
    "eiffel tower",
    "leaning tower of pisa",
    "stonehenge",
    # Misc.
    "a fisherman's tale",
    "samurai shodown",
    "fairy tales",                 # too broad; usually anime art.
    "christmas (trees)",           # holiday-themed trees, not Treefolk.
})


def _relevant_keywords(subtypes: list[str]) -> set[str]:
    """Word set used to keep an asciiart.website category in the fetch list.

    Built from every Scryfall subtype slug (split on ``-``), every
    SYNONYMS target word, every card-type word from ``proxy_print``, and
    a small curated set of MTG-adjacent parent-category words.
    """
    words: set[str] = set(_MTG_ADJACENT_WORDS)
    # Card-type slugs (creature, artifact, enchantment, land, …).
    from mtg_utils.proxy_print import _CARD_TYPE_WORDS
    words.update(_CARD_TYPE_WORDS)
    for st in subtypes:
        for tok in st.split("-"):
            if tok:
                words.add(tok)
    for targets in SYNONYMS.values():
        for tok in targets:
            words.add(tok.lower())
    return words


# Irregular plurals → singular form. Extend as new MTG-relevant
# categories surface (the filter's job is to err on the side of keeping
# things — every false negative drops a whole asciiart.website page).
_IRREGULAR_PLURALS: dict[str, str] = {
    "mice": "mouse",
    "geese": "goose",
    "wolves": "wolf",
    "knives": "knife",
    "elves": "elf",
    "dwarves": "dwarf",
    "leaves": "leaf",
    "men": "man",
    "women": "woman",
    "children": "child",
    "oxen": "ox",
    "feet": "foot",
    "teeth": "tooth",
}


def _stems(tok: str) -> list[str]:
    """Return every possible singular form of ``tok`` we'll test in lookups.

    Covers the common English plural patterns plus a small list of
    irregulars. False positives are fine; false negatives drop whole
    asciiart.website pages.
    """
    out = [tok]
    if tok in _IRREGULAR_PLURALS:
        out.append(_IRREGULAR_PLURALS[tok])
    if len(tok) > 4 and tok.endswith("ies"):
        out.append(tok[:-3] + "y")          # butterflies → butterfly
    if len(tok) > 4 and tok.endswith("es"):
        out.append(tok[:-2])                # foxes → fox
    if len(tok) > 3 and tok.endswith("s"):
        out.append(tok[:-1])                # cats → cat, dogs → dog
    return out


def _category_matches(name: str, keywords: set[str]) -> bool:
    """Return True if any token in ``name`` matches a keyword.

    Match modes (any one suffices):
    * Direct: the token (or a plural-stem of it) is a keyword.
    * Long-prefix: a token ≥6 chars starts with a keyword ≥4 chars —
      catches ``rhinoceros`` → ``rhino`` and ``hippopotamus`` → ``hippo``
      where the site spells the full form but MTG uses the short subtype.
    """
    for tok in re.findall(r"[a-z]+", name.lower()):
        if any(s in keywords for s in _stems(tok)):
            return True
        if len(tok) >= 6:
            for kw in keywords:
                if len(kw) >= 4 and tok.startswith(kw):
                    return True
    return False


def relevant_categories(
    cats: list[tuple[str, str]], subtypes: list[str]
) -> list[tuple[str, str]]:
    """Filter ``cats`` to those whose names match an MTG keyword.

    A two-stage filter: first drop names listed in
    :data:`_FRANCHISE_SKIP_CATEGORIES` (TV / movie / brand pages whose
    titles match an MTG keyword but whose content is franchise art),
    then keep only names where a tokenized match against the keyword
    set succeeds.
    """
    keywords = _relevant_keywords(subtypes)
    return [
        (cid, name)
        for cid, name in cats
        if name.lower() not in _FRANCHISE_SKIP_CATEGORIES
        and _category_matches(name, keywords)
    ]


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
    # MTG planeswalker names -> closest class / signature creature.
    # Each PW maps to the visual concept that best represents them on
    # asciiart.eu (their creature type, signature class, or iconic motif).
    # Jokes / silver-bordered PWs without a coherent visual analog
    # (b.o.b., deb, ersta, inzerva, luxior, master, monopoly, svega,
    # szat, vronos) are intentionally omitted — they fall through to
    # the local catalog's _generic.txt.
    "abian": ["wizard"],
    "ajani": ["lion", "cat"],
    "aminatou": ["wizard", "cat"],
    "angrath": ["minotaur", "pirate"],
    "arlinn": ["werewolf", "wolf"],
    "ashiok": ["nightmare", "ghost"],
    "bahamut": ["dragon"],
    "basri": ["soldier", "knight"],
    "bolas": ["dragon"],
    "calix": ["wizard", "mage"],
    "chandra": ["mage", "wizard"],
    "comet": ["dog"],
    "dack": ["rogue"],
    "dakkon": ["assassin", "warrior"],
    "daretti": ["goblin"],
    "davriel": ["demon", "wizard"],
    "dellian": ["warrior", "soldier"],
    "dihada": ["vampire", "wizard"],
    "domri": ["barbarian"],
    "dovin": ["wizard"],
    "ellywick": ["bard", "musician"],
    "elminster": ["wizard"],
    "elspeth": ["knight"],
    "estrid": ["fairy"],
    "freyalise": ["elf"],
    "garruk": ["hunter", "warrior"],
    "gideon": ["knight"],
    "grist": ["insect", "beetle"],
    "guff": ["minotaur", "monk"],
    "huatli": ["warrior"],
    "jace": ["wizard", "mage"],
    "jared": ["warrior"],
    "jaya": ["wizard", "mage"],
    "jeska": ["warrior"],
    "kaito": ["ninja"],
    "karn": ["golem", "robot"],
    "kasmina": ["wizard"],
    "kaya": ["ghost", "assassin"],
    "kiora": ["mermaid"],
    "koth": ["dwarf", "warrior"],
    "liliana": ["necromancer", "witch"],
    "lolth": ["spider"],
    "lukka": ["soldier", "warrior"],
    "minsc": ["ranger", "hunter"],
    "mordenkainen": ["wizard"],
    "nahiri": ["warrior", "soldier"],
    "narset": ["monk"],
    "niko": ["warrior"],
    "nissa": ["druid"],
    "nixilis": ["demon"],
    "oko": ["faerie", "fairy"],
    "quintorius": ["elephant", "bard"],
    "ral": ["wizard"],
    "rowan": ["knight"],
    "saheeli": ["artificer"],
    "samut": ["warrior"],
    "sarkhan": ["dragon"],
    "serra": ["angel"],
    "sivitri": ["vampire", "dragon"],
    "sorin": ["vampire"],
    "tamiyo": ["wizard"],
    "tasha": ["wizard", "witch"],
    "teferi": ["wizard"],
    "teyo": ["knight"],
    "tezzeret": ["wizard"],
    "tibalt": ["devil"],
    "tyvar": ["elf"],
    "ugin": ["dragon"],
    "urza": ["wizard", "mage"],
    "venser": ["wizard"],
    "vivien": ["ranger", "hunter"],
    "vraska": ["gorgon"],
    "wanderer": ["samurai", "ninja"],
    "will": ["wizard", "mage"],
    "windgrace": ["panther", "cat"],
    "wrenn": ["dryad"],
    "xenagos": ["satyr"],
    "yanggu": ["dog"],
    "yanling": ["wizard"],
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
    session: requests.Session,
    url: str,
    path: Path,
    *,
    throttle: float = 0.0,
    max_retries: int = 2,
) -> bytes:
    """Return ``path`` contents, refreshing from ``url`` if stale/missing.

    Raises on HTTP error (fail-loud); only writes the cache on a 2xx.

    ``throttle`` sleeps before each *network* call (cache hits return
    immediately). On HTTP 429 the wait grows linearly between retries
    (5s, 10s, …) up to ``max_retries`` additional attempts; if all retries
    are 429 the final response is raised.
    """
    if _is_fresh(path):
        return path.read_bytes()
    for attempt in range(max_retries + 1):
        if throttle > 0:
            time.sleep(throttle)
        resp = session.get(url, timeout=30)
        status = getattr(resp, "status_code", 200)
        if status == 429 and attempt < max_retries:
            time.sleep(5.0 * (attempt + 1))
            continue
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return resp.content
    # Unreachable: the loop either returns or raises.
    msg = "exhausted retries without raising or returning"
    raise RuntimeError(msg)


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


def build_pool(
    session: requests.Session,
    cache: Path,
    *,
    subtypes: list[str] | None = None,
) -> list[dict]:
    """Download/refresh every category page from every source.

    Mines both asciiart.eu's hardcoded ``CATEGORIES`` list and the
    MTG-relevant subset of asciiart.website's auto-discovered categories.
    The asciiart.website source is rate-limited; we throttle 0.4s between
    requests there and retry on 429.

    ``subtypes`` is the Scryfall subtype list used to build the
    asciiart.website category filter (see :func:`relevant_categories`).
    If omitted, no filter applies and every discovered category is
    fetched — only useful in tests / debugging.
    """
    pool: list[dict] = []
    # Source 1: asciiart.eu — hardcoded curated category list.
    for cat in CATEGORIES:
        safe = cat.replace("/", "_")
        path = cache / f"asciiart-{safe}.html"
        raw = _fetch_cached(session, f"{ASCIIART_BASE}/{cat}", path)
        pool.extend(_parse_cards(raw.decode("utf-8"), cat))
    # Source 2: asciiart.website — auto-discovered numeric category IDs,
    # filtered down to names that contain an MTG-relevant word.
    cats = fetch_website_categories(session, cache)
    if subtypes is not None:
        cats = relevant_categories(cats, subtypes)
    for cat_id, cat_name in cats:
        path = cache / f"asciiart-website-cat-{cat_id}.html"
        raw = _fetch_cached(
            session,
            f"{WEBSITE_BASE}/cat.php?category_id={cat_id}",
            path,
            throttle=WEBSITE_THROTTLE_SEC,
        )
        pool.extend(_parse_cards_website(raw.decode("utf-8"), cat_name))
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
    """Write ``card`` to ``out_dir/<key>.txt`` with a per-source attribution header.

    Both sources use the same 3-line header shape that ``proxy_print``'s
    ``_try_read_attributed`` parses:

        # <title> (by <artist>)
        # Source: <url>
        # Used with attribution per <terms-url>

    The source URL and terms-url differ by source.
    """
    title = card["title"] or "Untitled"
    artist = card["artist"] or "unknown"
    source_kind = card.get("_source", "eu")
    if source_kind == "website":
        # asciiart.website does NOT grant blanket reuse with attribution
        # (its "FAQ" page is an archived 1994 usenet doc, not a site
        # license). We credit the artist anyway and treat this as
        # personal-use printing of MTG proxies.
        src_url = card.get("url") or f"{WEBSITE_BASE}/cat.php"
        license_note = (
            "Personal-use proxy; artist credited "
            "(no explicit license grant from source)."
        )
    else:
        src = card["source_path"]
        src_url = f"{ASCIIART_BASE}/{src}"
        license_note = f"Used with attribution per {ASCIIART_BASE}/faq"
    header = (
        f"# {title} (by {artist})\n"
        f"# Source: {src_url}\n"
        f"# {license_note}\n"
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

    log("Building candidate pool from asciiart.eu + asciiart.website...")
    pool = build_pool(session, cache, subtypes=subtypes)
    log(f"  parsed {len(pool)} cards across both sources")

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
