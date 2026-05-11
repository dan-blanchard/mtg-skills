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
from typing import TYPE_CHECKING, Protocol

import click
import requests

from mtg_utils.deck import slug
from mtg_utils.proxy_print import attributed_art_dir

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

# TARGET is what we'd ideally pick — the size proxy_print renders most
# legibly. MAX is the hard cap; proxy_print's fixed ~125pt art region
# (Courier-Bold) can render up to ~22 lines at min-font 5.5pt, so we
# can afford to admit taller pieces. MAX_H=18 unlocks subtypes like
# Elf (asciiart.website's narrowest in-budget Elf is 21x18) that the
# old 14-line cap excluded by 1-4 lines.
TARGET_W, TARGET_H = 20, 10
MAX_W, MAX_H = 30, 18


# --- Cache freshness -------------------------------------------------------

CACHE_MAX_AGE_DAYS = 7
FRESHNESS_SECONDS = CACHE_MAX_AGE_DAYS * 86400


# --- Polite-crawler throttle -----------------------------------------------

# asciiart.website rate-limits aggressive crawls. 0.4s/request keeps the
# crawler under their threshold during a cold full-pool build.
WEBSITE_THROTTLE_SEC = 0.4


# --- asciiart.website search API ------------------------------------------

# Hardcoded "secret" the site's JS embeds in search.php and ships in
# /api/search2api.php POSTs. Not a real secret — public client-side
# constant. If the site rotates it, our integration breaks loud (search
# returns {status: "error"}) and this constant needs a one-line bump.
WEBSITE_SEARCH_SECRET = (
    "fgjO83fk45mflskJGos1ko2KBVjJBS59j3J9sjJ93j02jla93jfjgnsjd8h82lkjasfJF893j11Kkksjak"
)


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
    "animals/bats",
    "animals/bears",
    "animals/beavers",
    "animals/birds-land",
    "animals/birds-water",
    "animals/bisons",
    "animals/camels",
    "animals/cats",
    "animals/cows",
    "animals/deer",
    "animals/dogs",
    "animals/dolphins",
    "animals/elephants",
    "animals/fish",
    "animals/frogs",
    "animals/horses",
    "animals/marsupials",
    "animals/monkeys",
    "animals/moose",
    "animals/other-land",
    "animals/other-water",
    "animals/rabbits",
    "animals/rhinoceros",
    "animals/scorpions",
    "animals/spiders",
    "animals/wolves",
    "animals/insects/ants",
    "animals/insects/bees",
    "animals/insects/beetles",
    "animals/insects/butterflies",
    "animals/insects/caterpillars",
    "animals/insects/cockroaches",
    "animals/insects/other",
    "animals/insects/snails",
    "animals/insects/worms",
    "animals/reptiles/alligators",
    "animals/reptiles/dinosaurs",
    "animals/reptiles/lizards",
    "animals/reptiles/snakes",
    "animals/reptiles/turtles",
    "animals/rodents/mice",
    "animals/rodents/other",
    # Mythology — most subcategories map to a creature subtype.
    "mythology/centaurs",
    "mythology/devils",
    "mythology/dragons",
    "mythology/fairies",
    "mythology/ghosts",
    "mythology/gryphon",
    "mythology/mermaids",
    "mythology/monsters",
    "mythology/phoenix",
    "mythology/skeletons",
    "mythology/unicorns",
    # Plants — Plant, Fungus, Treefolk subtypes.
    "plants/bonsai-trees",
    "plants/cactus",
    "plants/flowers",
    "plants/leaf",
    "plants/mushroom",
    "plants/roses",
    # Religion — Angel, Cleric, Monk subtypes.
    "religion/angels",
    "religion/saints",
    # Space — Alien, Spacecraft, Astronaut.
    "space/aliens",
    "space/astronauts",
    "space/spaceships",
    "space/planets",
    # Nature — Land subtypes (Mountain, Island, Desert) + Cloud / Storm flavor.
    "nature/mountains",
    "nature/islands",
    "nature/deserts",
    "nature/landscapes",
    "nature/waterfall",
    "nature/clouds",
    "nature/lightning",
    # People — Human fallback + occupations as class subtypes (Knight,
    # Wizard, …).
    "people/men",
    "people/women",
    "people/faces",
    "people/famous",
    "people/babies",
    "people/occupations/knights",
    "people/occupations/kings",
    "people/occupations/wizards",
    "people/occupations/vikings",
    "people/occupations/cowboys",
    "people/occupations/clowns",
    "people/occupations/police",
    # Weapons — Equipment subtype variations + Soldier.
    "weapons/swords",
    "weapons/axes",
    "weapons/bows-and-arrows",
    "weapons/shields",
    "weapons/soldiers",
    # Buildings — Land flavor (castle, temple, bridge).
    "buildings-and-places/castles",
    "buildings-and-places/temple",
    "buildings-and-places/bridges",
    # Electronics — Robot / Construct artifact creatures.
    "electronics/robots",
    # Music — Bard subtype.
    "music/musicians",
    "music/musical-instruments",
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
        out.append(
            {
                "_source": "eu",
                "id": m.group("id"),
                "title": html.unescape(m.group("title")),
                "artist": html.unescape(m.group("artist")),
                "height": int(m.group("height")),
                "width": int(m.group("width")),
                # Normalize line endings: asciiart.eu's HTML serves \r\n
                # (and sometimes bare \r), which would silently break the
                # byte-identical body comparison against on-disk files
                # (write_text emits \n). Use splitlines() — it handles every
                # line-terminator form — then rejoin with \n.
                "art": "\n".join(html.unescape(m.group("art")).splitlines()).strip(
                    "\n"
                ),
                "source_path": source_path,
            }
        )
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

_WEBSITE_TAG_RE = re.compile(
    r'href="tag\.php\?tag_id=(?P<id>\d+)"[^>]*>\s*'
    r"(?P<name>[A-Za-z][^<\n]*?)\s*"
    r'<span class="tag-count">\((?P<count>\d+)\)',
)


# Pagination cap. We run with the asciiart.website narrowest-sort
# cookie set, so each page 1 already contains the 20 smallest pieces —
# the ones most likely to fit our 30x14 budget. Pages 2+ have
# progressively wider pieces, which our _fits filter would mostly
# reject. Cold-fetch shrinks from ~300 to ~185 page requests.
# Bump this if a specific subtype is consistently missing and page 1
# of its tag has no in-budget candidates.
MAX_PAGES_PER_TAG = 1


def _parse_cards_website(text: str, source_path: str) -> list[dict]:
    """asciiart.website tag.php (and cat.php) page parser.

    Pulls per-piece metadata from the CollectionPage JSON-LD (name + url
    + author) and matches it to inline ``<pre data-artwork-id=N>`` art
    bodies by ID. Computes width/height from the art body itself with
    each line right-stripped — many asciiart.website pieces are padded
    with trailing whitespace that would falsely push them over our
    width cap.
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
        # Right-strip each line so trailing whitespace doesn't inflate width.
        lines = [line.rstrip() for line in body.splitlines()]
        body = "\n".join(lines)
        height = len(lines)
        width = max((len(line) for line in lines), default=0)
        out.append(
            {
                "_source": "website",
                "id": art_id,
                "title": meta["title"],
                "artist": meta["artist"],
                "height": height,
                "width": width,
                "art": body,
                "source_path": source_path,
                "url": meta["url"],
            }
        )
    return out


def _fetch_tag_pages(
    fetcher: Fetcher,
    tag_id: str,
    tag_name: str,
) -> list[dict]:
    """Fetch every page of one asciiart.website tag, deduped by art id.

    Pages are 20 entries each; we walk page=1, 2, 3, … until a page
    yields no new ids (or :data:`MAX_PAGES_PER_TAG` is hit).
    """
    pool: list[dict] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES_PER_TAG + 1):
        url = f"{WEBSITE_BASE}/tag.php?tag_id={tag_id}&page={page}"
        raw = fetcher.fetch(
            url,
            f"asciiart-website-tag-{tag_id}-p{page}.html",
            throttle=WEBSITE_THROTTLE_SEC,
        )
        cards = _parse_cards_website(raw.decode("utf-8"), tag_name)
        new = [c for c in cards if c["id"] not in seen]
        if not new:
            break
        seen.update(c["id"] for c in new)
        pool.extend(new)
    return pool


def fetch_website_tags(fetcher: Fetcher) -> list[tuple[str, str]]:
    """Auto-discover asciiart.website tags from browse.php?show=tags.

    Returns ``[(tag_id, name), ...]`` of every tag the site lists
    (~1148), with HTML entities decoded in names. Tags are more granular
    than categories and map closer to MTG concepts — e.g. "Lion" is a
    dedicated tag distinct from the "Lion King" tag, "Panther" is
    separate from "Pink Panther", and the 89-piece "Dragon" tag is
    distinct from the 6-piece "Dragon Ball" tag.

    Callers usually filter this through :func:`relevant_tags` before
    fetching the tag.php pages.
    """
    raw = fetcher.fetch(
        f"{WEBSITE_BASE}/browse.php?show=tags",
        "asciiart-website-browse-tags.html",
    )
    out: list[tuple[str, str]] = []
    for m in _WEBSITE_TAG_RE.finditer(raw.decode("utf-8")):
        name = html.unescape(m.group("name").strip())
        out.append((m.group("id"), name))
    return out


def _refresh_website_csrf(fetcher: Fetcher) -> str:
    """Fetch a fresh CSRF token from asciiart.website's API.

    The matching PHPSESSID cookie is captured by the fetcher's internal
    session and travels with subsequent ``post_form`` calls.
    """
    raw = fetcher.fetch_uncached(f"{WEBSITE_BASE}/api/refresh_csrf.php")
    return json.loads(raw.decode("utf-8"))["csrf_token"]


def _parse_website_search(data: dict, query: str) -> list[dict]:
    """Translate the search API's artwork records to the candidate-pool shape.

    asciiart.website's search endpoint returns ``{status, artworks: [{
    id, art, title, artist_name, ...}]}``. We compute width/height from
    the art body (right-stripped per line so trailing whitespace doesn't
    inflate width — same rule as :func:`_parse_cards_website`).
    """
    cards: list[dict] = []
    for art in data.get("artworks", []) or []:
        body = art.get("art") or ""
        # Normalise to LF and right-strip each line.
        lines = [line.rstrip() for line in body.replace("\r\n", "\n").split("\n")]
        body = "\n".join(lines).strip("\n")
        if not body:
            continue
        lines_nonempty = body.splitlines()
        height = len(lines_nonempty)
        width = max((len(line) for line in lines_nonempty), default=0)
        art_id = str(art.get("id") or "")
        cards.append(
            {
                "_source": "website",
                "id": art_id,
                "title": art.get("title") or "Untitled",
                "artist": art.get("artist_name") or art.get("artist") or "unknown",
                "height": height,
                "width": width,
                "art": body,
                "source_path": f"search?q={query}",
                "url": f"{WEBSITE_BASE}/art/{art_id}",
            }
        )
    return cards


def search_pool_website(
    fetcher: Fetcher,
    query: str,
    *,
    csrf_token: str,
) -> list[dict]:
    """POST to asciiart.website's search API; return parsed candidate cards.

    Multi-word queries reliably return zero — the site's search matches
    tag names rather than full titles. Callers should split card names
    into individual words and try each.

    Sort order ``narrowest`` is hardcoded: our budget caps width at 30,
    so narrow-first pieces are the ones most likely to fit. (``shortest``
    sounds attractive but tends to surface 60+-wide x 4-tall strips
    that fail the width cap; narrowest favours pieces closer to our
    20x10 target shape.) Without a sort, the default-ordered results
    rarely fit.
    """
    raw = fetcher.post_form(
        f"{WEBSITE_BASE}/api/search2api.php",
        form_fields={
            "q": query,
            "csrf_token": csrf_token,
            "secret": WEBSITE_SEARCH_SECRET,
            "sort_order": "narrowest",
        },
        throttle=WEBSITE_THROTTLE_SEC,
    )
    data = json.loads(raw.decode("utf-8"))
    if data.get("status") != "success":
        return []
    return _parse_website_search(data, query)


# --- Category filter -------------------------------------------------------

# Parent-category words that don't appear in any Scryfall subtype slug or
# synonym target, but reliably hold MTG-relevant content. Keep this list
# small and conservative.
_MTG_ADJACENT_WORDS: frozenset[str] = frozenset(
    {
        "animal",
        "bird",
        "beast",
        "insect",
        "reptile",
        "monster",
        "weapon",
        "vehicle",
        "water",
        "ocean",
        "sea",
        "tree",
        "fish",
    }
)


# asciiart.website tag names that are franchise/media-property pollutants —
# their tokens look MTG-relevant but their content is licensed media
# (Disney characters, Star Wars, anime). Tags are far more granular than
# categories (a clean "Lion" tag exists separately from "Lion King"), so
# this list is much smaller than the category-equivalent would be.
# Compared lowercase against the tag name as-fetched.
#
# We deliberately KEEP "Lord Of The Rings / Tolkien" — the user has
# LOTR-set MTG cards and prefers Tolkien art for Wizard / Elf / Dwarf
# when it scores well. We deliberately KEEP "Alien" because there's only
# one Alien tag (mix of generic alien and Ridley Scott Alien), and
# they're visually indistinguishable.
# asciiart.website tags we force-keep even when the keyword filter would
# drop them. Use when the user has MTG cards from a licensed franchise
# whose tag name doesn't otherwise match an MTG subtype word — Tolkien's
# "Lord Of The Rings / Tolkien" tag has no MTG-subtype tokens but the
# user owns LOTR-set MTG cards (Wizard, Elf, Dwarf creatures) that
# benefit from Tolkien art when it scores well.
_FORCE_KEEP_TAGS: frozenset[str] = frozenset(
    {
        "lord of the rings / tolkien",
    }
)


_FRANCHISE_SKIP_TAGS: frozenset[str] = frozenset(
    {
        # Broad media-property tags. These pollute many subtypes at once
        # because they collect every piece from a vast franchise universe.
        "disney",
        "pixar",
        "anime",
        "manga",
        "star wars",
        # Specific franchise tags whose names match an MTG keyword.
        "lion king",
        "little mermaid",
        "dragon ball",
        "donald duck",
        "toy story",
        "ghostbusters",
        "beauty and the beast",
    }
)


def _relevant_keywords(subtypes: list[str]) -> set[str]:
    """Word set used to keep an asciiart.website category in the fetch list.

    Built from every Scryfall subtype slug (split on ``-``), every
    SYNONYMS target word, every card-type word from ``proxy_print``, and
    a small curated set of MTG-adjacent parent-category words.
    """
    words: set[str] = set(_MTG_ADJACENT_WORDS)
    # Card-type slugs (creature, artifact, enchantment, land, …).
    from mtg_utils.deck import CARD_TYPE_WORDS

    words.update(CARD_TYPE_WORDS)
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
        out.append(tok[:-3] + "y")  # butterflies → butterfly
    if len(tok) > 4 and tok.endswith("es"):
        out.append(tok[:-2])  # foxes → fox
    if len(tok) > 3 and tok.endswith("s"):
        out.append(tok[:-1])  # cats → cat, dogs → dog
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


def relevant_tags(
    tags: list[tuple[str, str]], subtypes: list[str]
) -> list[tuple[str, str]]:
    """Filter ``tags`` to those whose names map to an MTG concept.

    Three-stage filter, in order:
    1. Drop names in :data:`_FRANCHISE_SKIP_TAGS` (Disney, Star Wars,
       etc. — broad media franchises that would pollute generic subtype
       renderings).
    2. Force-keep names in :data:`_FORCE_KEEP_TAGS` regardless of
       keyword match (e.g. Tolkien — user has LOTR-set MTG cards).
    3. Keep names whose tokens (or plural-stems / long-prefix variants)
       are in the MTG keyword set built from subtypes + synonyms +
       card-types + MTG-adjacent words.
    """
    keywords = _relevant_keywords(subtypes)
    out: list[tuple[str, str]] = []
    for tid, name in tags:
        lowered = name.lower()
        if lowered in _FRANCHISE_SKIP_TAGS:
            continue
        if lowered in _FORCE_KEEP_TAGS or _category_matches(name, keywords):
            out.append((tid, name))
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
SKIP_SUBTYPES: frozenset[str] = frozenset(
    {
        # Meta / supertype words (proxy_print already filters these via
        # _ART_SKIP_WORDS; listed here for safety in case Scryfall returns them)
        "token",
        "legendary",
        "snow",
        "tribal",
        "basic",
        "ongoing",
        "world",
        "host",
        # MTG-only structural / object subtypes with no representational art
        "attraction",
        "background",
        "blood",
        "bobblehead",
        "case",
        "class",
        "clue",
        "contraption",
        "food",
        "gold",
        "incubator",
        "lesson",
        "map",
        "powerstone",
        "role",
        "saga",
        "shard",
        "treasure",
        # Plane / setting names (Plane card subtypes)
        "alara",
        "belenon",
        "dominaria",
        "equilor",
        "fabacin",
        "gallifrey",
        "innistrad",
        "ir",
        "ixalan",
        "kaldheim",
        "kamigawa",
        "karsus",
        "kephalai",
        "lorwyn",
        "luvion",
        "mercadia",
        "mirrodin",
        "mongseng",
        "moag",
        "muraganda",
        "phyrexia",
        "pyrulea",
        "rath",
        "ravnica",
        "regatha",
        "segovia",
        "serra",
        "shadowmoor",
        "shandalar",
        "tarkir",
        "theros",
        "ulgrotha",
        "vryn",
        "wildfire",
        "xerex",
        "zendikar",
        # Setting metadata / convention markers
        "amsterdam",
        "chicago",
        "magiccon",
        "new",
        "vegas",
        # Stop-words
        "and",
        "of",
        "the",
    }
)


# --- Fetcher ---------------------------------------------------------------


class Fetcher(Protocol):
    """Seam for HTTP-with-cache.

    A ``Fetcher`` returns the bytes for a URL, caching them under
    ``cache_key`` for :data:`FRESHNESS_SECONDS`. The interface owns
    freshness, retry, throttle, and disk-write — callers only know
    "give me the bytes for this URL, please."

    Two adapters live behind this seam: :class:`HttpFetcher` (production,
    backed by ``requests.Session``) and ``FakeFetcher`` (test-only, in
    ``tests/proxy-printer/_fake_fetcher.py``, dict-backed).
    """

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        """Return cached bytes for ``url``, fetching if stale/missing.

        ``cache_key`` is a flat filename (the fetcher resolves it under
        its own cache root). ``throttle`` sleeps before each *network*
        call (cache hits return immediately). On HTTP 429 / connection
        error, the fetcher retries with linear backoff (5s, 10s, …) up
        to ``max_retries`` additional attempts; if all retries fail the
        final exception is raised (fail-loud).
        """
        ...

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        """GET without caching. Used for short-lived resources like CSRF
        tokens that must be fresh on every call."""
        ...

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        """POST a form-encoded body. Never cached (POST responses depend
        on session state). Retry / throttle behaviour mirrors ``fetch``."""
        ...


class HttpFetcher:
    """Production :class:`Fetcher`. Wraps a private ``requests.Session``."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        user_agent: str = USER_AGENT,
        cookies: dict[str, dict[str, str]] | None = None,
    ) -> None:
        """``cache_dir`` is the on-disk cache root (auto-created).
        ``cookies`` maps domain → {name: value} for cookies that must
        be pre-set (e.g. asciiart.website's sort-order cookie).
        """
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir = cache_dir
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        if cookies:
            for domain, by_name in cookies.items():
                for name, value in by_name.items():
                    self._session.cookies.set(name, value, domain=domain)

    def fetch(
        self,
        url: str,
        cache_key: str,
        *,
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        path = self._cache_dir / cache_key
        if path.is_file() and (time.time() - path.stat().st_mtime) < FRESHNESS_SECONDS:
            return path.read_bytes()
        for attempt in range(max_retries + 1):
            if throttle > 0:
                time.sleep(throttle)
            try:
                resp = self._session.get(url, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt < max_retries:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise
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

    def fetch_uncached(self, url: str, *, throttle: float = 0.0) -> bytes:
        if throttle > 0:
            time.sleep(throttle)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def post_form(
        self,
        url: str,
        *,
        form_fields: dict[str, str],
        throttle: float = 0.0,
        max_retries: int = 2,
    ) -> bytes:
        for attempt in range(max_retries + 1):
            if throttle > 0:
                time.sleep(throttle)
            try:
                resp = self._session.post(url, data=form_fields, timeout=30)
            except (requests.ConnectionError, requests.Timeout):
                if attempt < max_retries:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                raise
            status = getattr(resp, "status_code", 200)
            if status == 429 and attempt < max_retries:
                time.sleep(5.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.content
        msg = "exhausted retries without raising or returning"
        raise RuntimeError(msg)


# --- Pool builders ---------------------------------------------------------


def fetch_subtypes(fetcher: Fetcher) -> list[str]:
    """Return every MTG subtype slug, lowercased, deduped, sorted."""
    seen: set[str] = set()
    for catalog in SCRYFALL_CATALOGS:
        url = f"{SCRYFALL_BASE}/catalog/{catalog}"
        raw = fetcher.fetch(url, f"scryfall-{catalog}.json")
        data = json.loads(raw.decode("utf-8"))
        for name in data.get("data", []):
            seen.add(slug(name))
    return sorted(seen)


def build_pool(
    fetcher: Fetcher,
    *,
    subtypes: list[str] | None = None,
) -> list[dict]:
    """Download/refresh every collection page from every source.

    Mines both asciiart.eu's hardcoded ``CATEGORIES`` list and the
    MTG-relevant subset of asciiart.website's auto-discovered **tags**
    (the tag taxonomy is more granular than categories and avoids
    franchise-pollution issues — a clean "Lion" tag is distinct from
    "Lion King"). The asciiart.website source is rate-limited; we
    throttle 0.4s between requests there and retry on 429.

    ``subtypes`` is the Scryfall subtype list used to build the
    asciiart.website tag filter (see :func:`relevant_tags`). If omitted,
    no filter applies and every discovered tag is fetched — only useful
    in tests / debugging.
    """
    pool: list[dict] = []
    # Source 1: asciiart.eu — hardcoded curated category list.
    for cat in CATEGORIES:
        safe = cat.replace("/", "_")
        raw = fetcher.fetch(f"{ASCIIART_BASE}/{cat}", f"asciiart-{safe}.html")
        pool.extend(_parse_cards(raw.decode("utf-8"), cat))
    # Source 2: asciiart.website — auto-discovered numeric tag IDs,
    # filtered down to names that contain an MTG-relevant word. Each tag
    # is paginated; we walk all pages so large tags (Dragon=89,
    # Angel=62, Lion=43) yield their full content.
    tags = fetch_website_tags(fetcher)
    if subtypes is not None:
        tags = relevant_tags(tags, subtypes)
    for tag_id, tag_name in tags:
        pool.extend(_fetch_tag_pages(fetcher, tag_id, tag_name))
    return pool


def search_pool(fetcher: Fetcher, query: str) -> list[dict]:
    """Fall back to asciiart.eu's /search?q= endpoint for a single query."""
    safe = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "x"
    url = f"{ASCIIART_BASE}/search?q={urllib.parse.quote_plus(query)}"
    raw = fetcher.fetch(url, f"asciiart-search-{safe}.html")
    return _parse_cards(raw.decode("utf-8"), f"search?q={query}")


# --- Selection -------------------------------------------------------------


def _fits(card: dict) -> bool:
    return card["width"] <= MAX_W and card["height"] <= MAX_H


# Common English function words. Any of these appearing as a whole
# token in an art body signals a baked-in caption ("Beauty and the
# Beast", "Long live the King"). Artist initials ("ldb", "mrf") and
# onomatopoeia ("vvvv", "wWw", "qp") do not collide with this set.
_CAPTION_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "was",
        "you",
        "but",
        "not",
        "his",
        "her",
        "all",
        "out",
        "who",
        "with",
        "from",
        "this",
        "that",
        "into",
        "over",
        "they",
        "them",
        "have",
        "has",
        "had",
        "will",
        "would",
        "could",
        "should",
        "your",
        "ours",
        "their",
        "what",
        "when",
        "where",
        "why",
        "how",
        "off",
        "now",
        "yet",
    }
)


def _has_caption_text(card: dict) -> bool:
    """True if the art body contains baked-in English-language text.

    Two signals, OR'd together:

    1. **Title echo** — the body contains a 4+ character word from the
       piece's title. Most captioned art repeats its title verbatim
       (e.g. asciiart.website's "Beauty And The Beast" piece bakes
       "Beauty and the Beast" into the body).
    2. **Stopword** — the body contains an English function word from
       :data:`_CAPTION_STOPWORDS`. Catches captions like "Long live
       the king" even when they don't echo the title.

    Cached on the card dict so the regex/lookup runs at most once per
    candidate across multiple ``select`` queries.
    """
    cached = card.get("_caption_checked")
    if cached is not None:
        return cached
    body = card.get("art") or ""
    body_lo = body.lower()
    body_tokens = set(re.findall(r"[a-z]+", body_lo))
    result = False
    title = card.get("title") or ""
    for tok in re.findall(r"[A-Za-z]{4,}", title):
        if tok.lower() in body_tokens:
            result = True
            break
    if not result and body_tokens & _CAPTION_STOPWORDS:
        result = True
    card["_caption_checked"] = result
    return result


def _eligible(card: dict) -> bool:
    """Geometry + caption filter combined. Used by every selection path."""
    return _fits(card) and not _has_caption_text(card)


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
    pat = re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)
    return bool(pat.search(card["title"]))


def _title_matches_stem(card: dict, query: str) -> bool:
    """Like :func:`_title_matches` but tries every plural/singular stem of
    ``query`` (via :func:`_stems`) so morphological variants in the title
    still match.

    Used by the asciiart.website per-word fallback in :func:`fetch_by_name`:
    a query of ``"Elves"`` should accept a piece titled ``"Elf piece"`` —
    the artist tagged it ``"Elves"`` and the title is the singular form.
    Without stem matching the title-match check would over-reject. With
    plain :func:`_title_matches` only, an exact word-boundary form is
    required which leaks artist-alias matches (``"Master"`` matching a
    piece titled ``"Sail Boat"`` because the artist is "Master Mitch").
    """
    title = card.get("title") or ""
    for stem in _stems(query.lower()):
        pat = re.compile(rf"\b{re.escape(stem)}\b", re.IGNORECASE)
        if pat.search(title):
            return True
    return False


def queries_for(subtype: str) -> list[str]:
    return [subtype, *SYNONYMS.get(subtype, [])]


def select(queries: Iterable[str], pool: list[dict]) -> dict | None:
    """Return the best in-budget card matching any query, or None."""
    for q in queries:
        hits = [c for c in pool if _eligible(c) and _title_matches(c, q)]
        if hits:
            return min(hits, key=_score)
    return None


# --- Name-keyed fetch ------------------------------------------------------


def _load_existing_bodies(out_dir: Path) -> set[str]:
    """Return the set of art bodies (post-header) of every .txt in ``out_dir``.

    Used by :func:`fetch_by_name` to dedupe: if a candidate's body is
    already in the catalog under a different slug (typically a subtype
    file written by the pass-1 sweep), don't write a redundant name-keyed
    copy. Avoids the case where ``goblin-bombardment.txt`` and
    ``goblin.txt`` end up with byte-identical content.
    """
    bodies: set[str] = set()
    for p in out_dir.glob("*.txt"):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        # Files have a 3-line `#`-prefixed header followed by a blank
        # line, then the body. Strip via header-line count for robustness.
        lines = text.splitlines()
        body_start = 0
        for i, line in enumerate(lines):
            if i < 3 and line.startswith("#"):
                continue
            if line.strip() == "":
                body_start = i + 1
                break
            body_start = i
            break
        bodies.add("\n".join(lines[body_start:]).strip("\n"))
    return bodies


def fetch_by_name(
    fetcher: Fetcher,
    name: str,
    out_dir: Path,
    *,
    overwrite: bool = False,
    website_csrf: str | None = None,
    existing_bodies: set[str] | None = None,
) -> bool:
    """Try to fetch art for a specific card *name* via two-source search.

    Writes ``<name-slug>.txt`` into ``out_dir`` if an in-budget hit
    exists; skips silently when no source returns anything fitting.
    Returns True iff a file was written.

    Search order:
    1. ``asciiart.eu /search?q=<full name>`` — handles most multi-word
       MTG names because the engine matches across full titles.
    2. If step 1 returns no fitting hits AND ``website_csrf`` is
       provided, split ``name`` into whole words (≥4 chars) and search
       each on ``asciiart.website``. The website's search matches **tag
       names**, which collide with artist aliases (e.g. ``"Master"``
       matches Christian Garbs's "Master Mitch" tag on a Sail Boat
       piece). We therefore require the query word to appear in each
       candidate's title — same word-boundary check :func:`select` uses
       for the asciiart.eu subtype pool.

    Dedupe: if ``existing_bodies`` is supplied and the chosen piece's
    body is already present in the catalog under another slug, skip
    writing. This is what prevents ``goblin-bombardment.txt`` from
    ending up byte-identical to a pre-existing ``goblin.txt`` — the
    differentiation pass at render time would buy us nothing.

    ``overwrite=False`` skips names whose ``<name-slug>.txt`` already
    exists (avoids clobbering hand-curated files or earlier runs).
    ``website_csrf`` is ``None`` when the caller doesn't want
    asciiart.website fallback — keeps the function callable with no
    extra session setup.
    """
    if not name:
        return False
    name_slug = slug(name)
    out_path = out_dir / f"{name_slug}.txt"
    if not overwrite and out_path.is_file():
        return False

    # Pass 1: asciiart.eu full-name search.
    pool = search_pool(fetcher, name)
    fitting = [c for c in pool if _eligible(c)]

    # Pass 2: per-word fallback on asciiart.website.
    if not fitting and website_csrf:
        for word in name.split():
            if len(word) < 4:
                continue
            web_pool = search_pool_website(fetcher, word, csrf_token=website_csrf)
            web_fitting = [
                c for c in web_pool if _eligible(c) and _title_matches_stem(c, word)
            ]
            if web_fitting:
                fitting = web_fitting
                break

    if not fitting:
        return False
    chosen = min(fitting, key=_score)
    if existing_bodies is not None:
        chosen_body = (chosen.get("art") or "").strip("\n")
        if chosen_body in existing_bodies:
            return False
        existing_bodies.add(chosen_body)
    write_art(out_dir, name_slug, chosen)
    return True


def _distinct_card_names(deck: dict) -> list[str]:
    """Return every distinct card name in the deck, front-face only for DFC."""
    seen: set[str] = set()
    ordered: list[str] = []
    for section in ("commanders", "cards", "sideboard"):
        for entry in deck.get(section) or []:
            name = entry.get("name") or ""
            if " // " in name:
                name = name.split(" // ")[0]
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


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
    header = f"# {title} (by {artist})\n# Source: {src_url}\n# {license_note}\n\n"
    path = out_dir / f"{key}.txt"
    path.write_text(header + card["art"] + "\n", encoding="utf-8")
    return path


# --- Driver ----------------------------------------------------------------


def subtypes_in_deck(deck_path: Path, bulk_path: Path) -> set[str]:
    """Return the subtype + card-type slugs used by every card in the deck
    AND every token the deck's cards generate.

    Pulls each card's ``type_line`` from the Scryfall bulk index for the
    main cards, then walks ``all_parts`` (via :func:`discover_tokens`) so
    a deck whose cards generate Soldier / Spirit / Treasure tokens fetches
    those subtypes too. This is what ``fetch-art --from-deck`` uses to
    fetch only the tags a specific deck (cards + tokens) needs.
    """
    from mtg_utils.deck import (
        discover_tokens,
        hydrate,
        load_bulk_indexes,
        split_type_line,
        walk_cards,
    )

    deck = json.loads(deck_path.read_text())
    by_name, by_id = load_bulk_indexes(bulk_path)
    needed: set[str] = set()

    def _add_type_line(type_line: str) -> None:
        types, subs = split_type_line(type_line)
        for s in subs:
            needed.add(slug(s))
        for t in types:
            needed.add(slug(t))

    # Main cards (commanders + cards + sideboard).
    for name, _qty in walk_cards(deck, include_sideboard=True, copies=1):
        card = by_name.get(name.lower())
        if not card:
            continue
        _add_type_line(hydrate(card).get("type_line") or "")

    # Tokens generated by those cards (via Scryfall all_parts).
    for record in discover_tokens(deck, by_name, by_id, log_warn=lambda _s: None):
        token = record["token"]
        _add_type_line(hydrate(token).get("type_line") or "")

    return needed


def run(
    *,
    cache_dir: Path,
    out_dir: Path,
    search_fallback: bool = True,
    limit: int | None = None,
    deck_path: Path | None = None,
    bulk_path: Path | None = None,
    by_name: bool = False,
    log: Callable[[str], None] = lambda _s: None,
) -> tuple[int, int, int, list[str]]:
    """Drive the whole pipeline.

    Returns ``(written, skipped, missing, missing_keys)``.

    When ``deck_path`` is set, the subtype list is narrowed to just the
    subtypes the deck actually uses (resolved against the Scryfall bulk
    at ``bulk_path``, which defaults to proxy_print's discovery rule).

    When ``by_name`` is also True, after the subtype fetch the driver
    walks every distinct card name in the deck and runs an additional
    asciiart.eu /search?q=<name> for each. In-budget hits are written as
    ``<name-slug>.txt`` — these are what proxy_print's differentiation
    pass picks up when multiple distinct-name cards land on the same
    type-keyed art file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    fetcher: Fetcher = HttpFetcher(
        cache_dir=cache_dir / "ascii-art-fetcher",
        # asciiart.website respects a `toolbar_settings` cookie that pins
        # the sort order. Pre-set it to "narrowest" so each tag.php page
        # lists its smallest pieces first — most subtypes have a fitting
        # (≤30 wide) candidate on page 1 alone, so we rarely need to
        # paginate deeply. URL-encoded {"sortOrder":"narrowest"} —
        # matches the Set-Cookie shape the site emits when the user picks
        # the option in the toolbar.
        cookies={
            "asciiart.website": {
                "toolbar_settings": "%7B%22sortOrder%22%3A%22narrowest%22%7D",
            },
        },
    )

    log("Fetching Scryfall subtype catalogs...")
    subtypes = fetch_subtypes(fetcher)
    if limit is not None:
        subtypes = subtypes[:limit]
    log(f"  {len(subtypes)} subtype slugs")

    if deck_path is not None:
        from mtg_utils.bulk_loader import default_bulk_path

        resolved_bulk = bulk_path or default_bulk_path()
        if resolved_bulk is None or not resolved_bulk.is_file():
            msg = (
                "--from-deck requires Scryfall bulk data; pass --bulk-data "
                "or run download-bulk first"
            )
            raise FileNotFoundError(msg)
        log(f"Filtering to subtypes used by {deck_path.name}...")
        needed = subtypes_in_deck(deck_path, resolved_bulk)
        subtypes = [s for s in subtypes if s in needed]
        log(f"  narrowed to {len(subtypes)} deck-relevant subtypes")

    log("Building candidate pool from asciiart.eu + asciiart.website...")
    pool = build_pool(fetcher, subtypes=subtypes)
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
            extra = search_pool(fetcher, st)
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

    if by_name and deck_path is not None:
        log(f"Fetching name-keyed art for cards in {deck_path.name}...")
        deck = json.loads(deck_path.read_text())
        names = _distinct_card_names(deck)
        # One CSRF refresh for the whole batch — the session cookie
        # persists in the fetcher, so all subsequent post_form calls
        # reuse it.
        try:
            csrf = _refresh_website_csrf(fetcher)
        except (requests.RequestException, ValueError, KeyError) as e:
            log(f"  (warning: asciiart.website CSRF refresh failed: {e}; eu-only)")
            csrf = None
        # Snapshot of existing art bodies — fetch_by_name uses this to
        # avoid writing a name-keyed file that's byte-identical to an
        # already-cataloged piece under another slug.
        existing_bodies = _load_existing_bodies(out_dir)
        n_written = 0
        n_skipped_existing = 0
        for name in names:
            name_slug = slug(name)
            if (out_dir / f"{name_slug}.txt").is_file():
                n_skipped_existing += 1
                continue
            if fetch_by_name(
                fetcher,
                name,
                out_dir,
                website_csrf=csrf,
                existing_bodies=existing_bodies,
            ):
                n_written += 1
        log(
            f"  Wrote {n_written} name-keyed files "
            f"(skipped {n_skipped_existing} already cached, "
            f"{len(names) - n_written - n_skipped_existing} had no fitting art)."
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
    "--from-deck",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help=(
        "Parsed deck JSON. When set, the fetch is narrowed to subtypes "
        "actually used by cards in the deck — typically ~30 tags vs ~185 "
        "for a full sweep. Cuts a cold fetch from ~108s to ~15s."
    ),
)
@click.option(
    "--bulk-data",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help=(
        "Scryfall bulk JSON path (only used with --from-deck). Defaults "
        "to the cached default-cards.json proxy_print discovers."
    ),
)
@click.option(
    "--by-name",
    is_flag=True,
    help=(
        "After the subtype fetch, also try asciiart.eu /search?q=<name> "
        "for each distinct card name in --from-deck. Hits are written as "
        "<name-slug>.txt — what proxy_print's differentiation pass picks "
        "up when multiple distinct-name cards share a type-keyed art file. "
        "Most card names miss (asciiart sites are concept-keyed, not "
        "card-keyed); the few hits are worth the extra search calls. "
        "Requires --from-deck."
    ),
)
@click.option(
    "--report-missing",
    is_flag=True,
    help="Print every subtype slug that had no in-budget match.",
)
def main(
    cache_dir: Path,
    out_dir: Path | None,
    search_fallback: bool,  # noqa: FBT001 — click injects as a keyword arg at runtime
    limit: int | None,
    from_deck: Path | None,
    bulk_data: Path | None,
    by_name: bool,  # noqa: FBT001 — click injects as a keyword arg at runtime
    report_missing: bool,  # noqa: FBT001 — click injects as a keyword arg at runtime
) -> None:
    """Populate the attributed-art catalog from asciiart.eu + asciiart.website.

    Default mode fetches every MTG subtype (~185 tags, ~108s cold).
    With --from-deck, fetches only the subtypes that the given deck uses
    (~30 tags, ~15s cold) — recommended for the typical proxy-printing
    workflow. Add --by-name to also fetch by card name for the
    differentiation pass.
    """
    if by_name and from_deck is None:
        click.echo("ERROR: --by-name requires --from-deck", err=True)
        sys.exit(EXIT_FETCH_FAILED)
    if out_dir is None:
        out_dir = attributed_art_dir()
    try:
        _written, _skipped, _missing, missing_keys = run(
            cache_dir=cache_dir,
            out_dir=out_dir,
            search_fallback=search_fallback,
            limit=limit,
            deck_path=from_deck,
            bulk_path=bulk_data,
            by_name=by_name,
            log=lambda s: click.echo(s, err=True),
        )
    except requests.HTTPError as e:
        click.echo(
            f"ERROR: HTTP {e.response.status_code} from {e.request.url}",
            err=True,
        )
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
