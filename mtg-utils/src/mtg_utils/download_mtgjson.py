"""MTGJSON card-data downloader (AllPrintings + AllPricesToday).

MTGJSON ``AllPrintings`` is the card-data source of record (ADR-0033). ``bulk_loader``
translates it to the Scryfall-shaped record the rest of the code reads; prices come from
``AllPricesToday`` (joined by uuid). Scryfall's HTTP API stays a thin per-card fallback.

Mirrors ``download-bulk``: a cache-dir default, 24h freshness, an eager sidecar build so
the first script call after a download doesn't pay the parse + translate cost. The two
files arrive gzip-compressed (~174 MB + ~5 MB) and are stream-decompressed to JSON.
"""

from __future__ import annotations

import contextlib
import os
import time
import zlib
from pathlib import Path

import click
import requests

from mtg_utils._mtgjson.load import ALLPRICES_NAME, ALLPRINTINGS_NAME
from mtg_utils.bulk_loader import build_sidecar

MTGJSON_BASE = "https://mtgjson.com/api/v5"
USER_AGENT = "mtg-skills/0.1.0"
FRESHNESS_SECONDS = 86400  # 24 hours
_FILES = (ALLPRINTINGS_NAME, ALLPRICES_NAME)


def default_mtgjson_dir() -> Path:
    """The durable MTGJSON cache dir (mirrors ``default_bulk_path``'s roots)."""
    root = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if root:
        return Path(root) / "mtgjson"
    home = os.environ.get("HOME")
    if home:
        return Path(home) / ".cache" / "mtg-skills" / "mtgjson"
    return Path("/tmp/mtgjson")


def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < FRESHNESS_SECONDS


def _download_gz(session: requests.Session, url: str, dest: Path) -> None:
    """Stream a ``.json.gz`` and decompress to *dest* (atomic, memory-friendly)."""
    decomp = zlib.decompressobj(wbits=31)  # 31 = gzip header + decompress
    tmp = dest.with_name(dest.name + ".tmp")
    with session.get(url, stream=True) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(decomp.decompress(chunk))
            f.write(decomp.flush())
    tmp.replace(dest)


def download_mtgjson(output_dir: Path | None = None) -> Path:
    """Download AllPrintings + AllPricesToday; return the AllPrintings path."""
    output_dir = output_dir or default_mtgjson_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    printings = output_dir / ALLPRINTINGS_NAME

    if all(_is_fresh(output_dir / f) for f in _FILES):
        return printings

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    for fname in _FILES:
        _download_gz(session, f"{MTGJSON_BASE}/{fname}.gz", output_dir / fname)

    # Eagerly build the translated sidecar (non-fatal on error; load_bulk_cards
    # rebuilds lazily). This is where the MTGJSON → Scryfall-shape translation runs.
    with contextlib.suppress(OSError):
        build_sidecar(printings)

    return printings


@click.command()
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to download MTGJSON data to (default: the mtg-skills cache).",
)
def main(output_dir: Path | None) -> None:
    """Download MTGJSON AllPrintings + AllPricesToday (the card-data source)."""
    path = download_mtgjson(output_dir=output_dir)
    click.echo(str(path))
