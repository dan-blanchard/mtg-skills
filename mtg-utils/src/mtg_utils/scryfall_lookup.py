"""Card lookup against the card pool, with Scryfall's per-card endpoint as the
cache-miss fallback (ADR-0005 / ADR-0033).

``lookup_single`` and ``lookup_cards`` serve the bulk's own adapter record — the ONE
record shape every consumer reads (ADR-0046) — and only the single-card CLI mode prints
a terminal-sized projection of it (``display_fields``). The Scryfall fetch is strictly
the cache-miss path: a card newer than the last ``download-mtgjson``.
"""

import contextlib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import click
import requests

from mtg_utils._http import USER_AGENT
from mtg_utils._name_index import NameIndex
from mtg_utils._sidecar import atomic_write_json
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.card_pool import CardPool

__all__ = [
    "DISPLAY_FIELDS",
    "build_digest",
    "display_fields",
    "fetch_card",
    "lookup_cards",
    "lookup_single",
]

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
RATE_LIMIT_DELAY = 0.1

# The fields a terminal read of one card wants (``scryfall-lookup <name>`` and
# ``card-search --json``): a DISPLAY projection, never the hydration shape — hydration
# serves the full record, so a field can't go missing on one path and not the other.
DISPLAY_FIELDS = (
    "id",
    "name",
    "oracle_id",
    "printed_name",
    "flavor_name",
    "oracle_text",
    "mana_cost",
    "cmc",
    "type_line",
    "power",
    "toughness",
    "loyalty",
    "defense",
    "card_faces",
    "keywords",
    "colors",
    "color_identity",
    "produced_mana",
    "prices",
    "legalities",
    "arena_available",
    "rarity",
    "game_changer",
    "edhrec_rank",
)


def display_fields(card: dict) -> dict:
    """The terminal projection of a record: ``DISPLAY_FIELDS``, None where the card
    has no such field (so a table renderer can index every column), with a multi-face
    card's oracle text assembled from its faces."""
    result = {field: card.get(field) for field in DISPLAY_FIELDS}
    if result["oracle_text"] is None:
        result["oracle_text"] = get_oracle_text(card) or None
    return result


def fetch_card(name: str) -> dict | None:
    """Scryfall's per-card endpoint (fuzzy name): the cache-miss path for a card the
    bulk doesn't carry yet. The raw record (Scryfall's shape, which the MTGJSON adapter
    mirrors), or ``None`` on a 404."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})

        if resp.status_code == 404:
            return None

        resp.raise_for_status()
        return resp.json()
    finally:
        # Close so a batch lookup (one call per name) doesn't leak pooled sockets.
        session.close()


def lookup_single(
    name: str,
    bulk_path: Path | None = None,
    bulk_index: NameIndex | None = None,
) -> dict | None:
    """The record for *name*: from *bulk_index* (or the pool at *bulk_path*), else
    :func:`fetch_card`. ``None`` when neither knows the card."""
    if bulk_index is None and bulk_path is not None:
        bulk_index = CardPool.load(bulk_path).by_name

    if bulk_index is not None:
        card = bulk_index.get(name)
        if card:
            return card

    return fetch_card(name)


def _extract_names(data: list | dict) -> list[str]:
    """Extract card names from either a name list or parsed deck JSON.

    Thin compatibility shim: delegates to ``parse_deck.extract_deck_names``
    (the canonical implementation). Kept as an underscore-prefixed name
    inside this module because existing tests patch it by string path
    (``mtg_utils.scryfall_lookup._extract_names``).
    """
    from mtg_utils.parse_deck import extract_deck_names

    return extract_deck_names(data)


def _default_cache_dir() -> Path:
    """Return the default cache directory for hydrated card data.

    Uses ``$TMPDIR/scryfall-cache`` (falls back to the platform temp dir via
    ``tempfile.gettempdir()``). Agents and tests can override via
    ``--cache-dir``.
    """
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "scryfall-cache"


def _build_cache_key(content: str, bulk_path: Path | None) -> str:
    """Hash batch file content together with the bulk data file identity.

    The bulk data file is hashed by (mtime_ns, size) not content — it's
    ~500MB and content-hashing on every call is expensive. Mtime+size is
    sufficient because ``download-mtgjson`` rewrites the file on refresh,
    which changes mtime. Without including bulk_path, a bulk-data refresh
    would silently return stale hydrated data.
    """
    hasher = hashlib.sha256()
    hasher.update(content.encode())
    if bulk_path is not None:
        try:
            stat = bulk_path.stat()
            hasher.update(f"|bulk:{stat.st_mtime_ns}:{stat.st_size}".encode())
        except OSError:
            hasher.update(b"|bulk:missing")
    else:
        hasher.update(b"|bulk:none")
    return hasher.hexdigest()[:16]


# The keys only a parsed deck JSON carries (a cube JSON has ``cards`` alone).
_DECK_ZONE_KEYS = frozenset({"commanders", "sideboard", "companion", "format"})


def lookup_cards(
    names_path: Path,
    bulk_path: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[list[dict | None], Path, list[str]]:
    """Look up every card in *names_path*, returning (results, cache_path, names).

    Always writes the full hydrated results to a sha-keyed cache file so the
    caller can pass the absolute path downstream without re-hydrating. The
    cache key includes the bulk data file's mtime+size so refreshing bulk
    data invalidates the cache.

    Returns a 3-tuple so ``main()`` can build the digest envelope without
    re-reading and re-parsing the batch file.
    """
    # Guard against empty --cache-dir from a misconfigured shell var or
    # Click passing through an empty string.
    if cache_dir is None or str(cache_dir) in ("", "."):
        cache_dir = _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    content = names_path.read_text(encoding="utf-8")
    raw = json.loads(content)
    if isinstance(raw, dict) and _DECK_ZONE_KEYS & raw.keys():
        # A parsed deck hydrates itself through its sidecar (ADR-0046). A cube JSON
        # (``{cards, name, source, cube_format}``) is the cube bounded context's own
        # shape and still hydrates here — ADR-0046 scoped cube-wizard out.
        msg = (
            "scryfall-lookup --batch takes a JSON list of card names (or a cube "
            "JSON); a parsed deck hydrates itself — run `deck-hydrate <deck.json>` "
            "instead."
        )
        raise click.ClickException(msg)
    names = _extract_names(raw)

    cache_key = _build_cache_key(content, bulk_path)
    cache_path = (cache_dir / f"hydrated-{cache_key}.json").resolve()

    # Cache hit: reuse prior hydration for identical input + bulk data.
    # If the file exists but is corrupt (truncated write, disk full),
    # unlink it and fall through to recompute.
    if cache_path.exists():
        try:
            results = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            with contextlib.suppress(OSError):
                cache_path.unlink()
        else:
            return results, cache_path, names

    bulk_index = CardPool.load(bulk_path).by_name if bulk_path else None

    results: list[dict | None] = []
    for name in names:
        result = lookup_single(name, bulk_index=bulk_index)
        results.append(result)

    atomic_write_json(cache_path, results)
    return results, cache_path, names


def _classify_type(type_line: str | None) -> str:
    """Map a type_line to a coarse category for the digest."""
    if not type_line:
        return "other"
    if "Land" in type_line:
        return "lands"
    if "Creature" in type_line:
        return "creatures"
    if "Planeswalker" in type_line:
        return "planeswalkers"
    if "Instant" in type_line:
        return "instants"
    if "Sorcery" in type_line:
        return "sorceries"
    if "Artifact" in type_line:
        return "artifacts"
    if "Enchantment" in type_line:
        return "enchantments"
    return "other"


def _curve_bucket(cmc: float) -> str:
    """Bucket a CMC into the digest curve histogram."""
    if cmc <= 0:
        return "0"
    if cmc >= 7:
        return "7+"
    return str(int(cmc))


def build_digest(results: list[dict | None], names: list[str]) -> dict:
    """Compute a bounded-size digest of hydrated card data for sanity-checking.

    The digest is small (~400 bytes) regardless of deck size and exists so the
    agent can confirm hydration worked without Reading the full cache file.
    """
    categories: dict[str, int] = {
        "lands": 0,
        "creatures": 0,
        "instants": 0,
        "sorceries": 0,
        "artifacts": 0,
        "enchantments": 0,
        "planeswalkers": 0,
        "other": 0,
    }
    curve: dict[str, int] = {}
    total_cmc = 0.0
    nonland_count = 0
    missing: list[str] = []

    # strict=True so a length mismatch becomes a loud failure — the envelope
    # must not silently misrepresent card_count if hydration returned a
    # different number of entries than names_in.
    for name, card in zip(names, results, strict=True):
        if card is None:
            missing.append(name)
            continue
        category = _classify_type(card.get("type_line"))
        categories[category] = categories.get(category, 0) + 1
        if category != "lands":
            cmc = float(card.get("cmc") or 0)
            total_cmc += cmc
            nonland_count += 1
            bucket = _curve_bucket(cmc)
            curve[bucket] = curve.get(bucket, 0) + 1

    avg_cmc_nonland = round(total_cmc / nonland_count, 2) if nonland_count else 0.0

    # Drop zero-count categories to keep the envelope compact.
    non_empty_categories = {k: v for k, v in categories.items() if v > 0}

    return {
        "categories": non_empty_categories,
        "avg_cmc_nonland": avg_cmc_nonland,
        "curve": dict(sorted(curve.items())),
        "missing": missing,
    }


@click.command()
@click.argument("card_name", required=False)
@click.option("--batch", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--cache-dir", type=click.Path(path_type=Path), default=None)
def main(
    card_name: str | None,
    batch: Path | None,
    bulk_data: Path | None,
    cache_dir: Path | None,
) -> None:
    """Look up MTG card data from Scryfall."""
    if batch:
        results, cache_path, names = lookup_cards(
            batch, bulk_path=bulk_data, cache_dir=cache_dir
        )
        digest = build_digest(results, names)
        envelope = {
            "cache_path": str(cache_path),
            "card_count": len(results),
            "missing": digest.pop("missing"),
            "digest": digest,
        }
        click.echo(json.dumps(envelope, indent=2))
    elif card_name:
        result = lookup_single(card_name, bulk_path=bulk_data)
        if result:
            click.echo(json.dumps(display_fields(result), indent=2))
        else:
            click.echo(f"Card not found: {card_name}", err=True)
            raise SystemExit(1)
    else:
        click.echo("Provide a card name or --batch file.", err=True)
        raise SystemExit(1)
