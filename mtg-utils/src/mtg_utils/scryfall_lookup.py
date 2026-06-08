"""Scryfall card lookup against bulk data with API fallback."""

import contextlib
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import click
import requests

from mtg_utils._name_index import NameIndex, build_name_index, keep_cheaper
from mtg_utils._sidecar import atomic_write_json
from mtg_utils.bulk_loader import load_bulk_cards
from mtg_utils.card_classify import (
    SKIP_LAYOUTS,
    get_oracle_text,
    has_copy_limit_exemption,
)

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
USER_AGENT = "commander-utils/0.1.0"
RATE_LIMIT_DELAY = 0.1

CARD_FIELDS = [
    "name",
    "oracle_id",
    "printed_name",
    "flavor_name",
    "oracle_text",
    "mana_cost",
    "cmc",
    "type_line",
    "keywords",
    "colors",
    "color_identity",
    "produced_mana",
    "prices",
    "legalities",
    "rarity",
    "game_changer",
]

RARITY_ORDER = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "mythic": 3,
    "special": 2,
    "bonus": 2,
}

# Digital-only Arena draft sets whose rarities reflect limited design,
# not Arena wildcard cost.  Reprints in these sets are excluded from the
# Arena rarity index so the "real" printing's rarity wins.  E.g.,
# Lightning Bolt is common in J21 (for draft) but uncommon on Arena
# (STA/FCA — the actual wildcard cost).
_DRAFT_RARITY_SETS = frozenset({"j21", "jmp", "ajmp"})


def _load_bulk_index(bulk_path: Path) -> NameIndex:
    """Load bulk data into a folding name index, keeping the cheapest printing.

    Keyed by canonical name, every DFC face, and Arena printed_name / flavor_name
    (NFKD-folded for diacritic- and case-robust lookups) via the shared name-index core.
    When printings share a key the cheapest USD one wins — a priced printing beats a
    price-less one.
    """
    return build_name_index(
        load_bulk_cards(bulk_path),
        reduce=keep_cheaper,
        prefilter=lambda card: card.get("layout") not in SKIP_LAYOUTS,
    )


def _keep_lowest_rarity(existing: dict, new: dict) -> dict:
    """Arena acquisition-cost reducer: a card's wildcard cost is the LOWEST rarity among
    its legal printings, so the lower ``RARITY_ORDER`` rank wins."""
    existing_rank = RARITY_ORDER.get(existing.get("rarity", "rare"), 2)
    new_rank = RARITY_ORDER.get(new.get("rarity", "rare"), 2)
    return new if new_rank < existing_rank else existing


def build_rarity_index(
    bulk_path: Path,
    legality_key: str,
    *,
    arena_only: bool = False,
) -> NameIndex:
    """Build a folding ``name -> {rarity, exempt_from_4cap}`` index.

    For Arena formats, a card's wildcard cost equals its lowest rarity among
    printings available in that format.  When *arena_only* is True, only
    printings that exist on Arena (``"arena" in games``) are considered.

    Some digital-only Arena sets (J21, JMP, AJMP) assign rarities for
    draft/limited purposes that don't match the wildcard cost Arena
    charges.  Reprints in these sets are excluded from rarity
    consideration so that the "real" Arena printing's rarity wins.
    Non-reprints (cards exclusive to these sets) are kept because they
    have no alternative printing to defer to.

    ``exempt_from_4cap`` is True for cards whose oracle text opts out of the
    standard 4-copy limit ("A deck can have any number of cards named X"
    or "A deck can have up to N cards named X"). Arena normally treats
    ownership of 4 copies as infinite because no legal deck can need a
    5th, but that substitution does not apply to exempt cards — a deck
    can legitimately want 17 Hare Apparent.
    """

    def _legal(card: dict) -> bool:
        if card.get("layout") in SKIP_LAYOUTS:
            return False
        if card.get("legalities", {}).get(legality_key) not in ("legal", "restricted"):
            return False
        if arena_only and "arena" not in (card.get("games") or []):
            return False
        # Reprints in digital-only draft sets carry limited-design rarities that don't
        # reflect Arena's wildcard cost; defer to the real printing.
        return not (
            arena_only
            and card.get("set", "") in _DRAFT_RARITY_SETS
            and card.get("reprint", False)
        )

    def _rarity(card: dict) -> dict:
        rarity = card.get("rarity", "rare")
        return {
            "rarity": "rare" if rarity in ("special", "bonus") else rarity,
            "exempt_from_4cap": has_copy_limit_exemption(card),
        }

    return build_name_index(
        load_bulk_cards(bulk_path),
        reduce=_keep_lowest_rarity,
        value=_rarity,
        prefilter=_legal,
    )


def _extract_fields(card: dict) -> dict:
    result = {field: card.get(field) for field in CARD_FIELDS}
    if result["oracle_text"] is None:
        result["oracle_text"] = get_oracle_text(card) or None
    return result


def _api_lookup(name: str) -> dict | None:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    time.sleep(RATE_LIMIT_DELAY)
    resp = session.get(SCRYFALL_NAMED_URL, params={"fuzzy": name})

    if resp.status_code == 404:
        return None

    resp.raise_for_status()
    return _extract_fields(resp.json())


def lookup_single(
    name: str,
    bulk_path: Path | None = None,
    bulk_index: NameIndex | None = None,
) -> dict | None:
    if bulk_index is None and bulk_path is not None:
        bulk_index = _load_bulk_index(bulk_path)

    if bulk_index is not None:
        card = bulk_index.get(name.lower())
        if card:
            return _extract_fields(card)

    return _api_lookup(name)


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
    sufficient because ``download-bulk`` rewrites the file on refresh,
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

    bulk_index = _load_bulk_index(bulk_path) if bulk_path else None

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
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Card not found: {card_name}", err=True)
            raise SystemExit(1)
    else:
        click.echo("Provide a card name or --batch file.", err=True)
        raise SystemExit(1)
