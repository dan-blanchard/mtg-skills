"""Scryfall bulk data downloader."""

import time
from pathlib import Path

import click
import requests

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"
USER_AGENT = "commander-utils/0.1.0"
FRESHNESS_SECONDS = 86400  # 24 hours


def _find_existing(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.glob("default-cards*.json"))
    return candidates[-1] if candidates else None


def _is_fresh(path: Path) -> bool:
    age = time.time() - path.stat().st_mtime
    return age < FRESHNESS_SECONDS


def download_bulk(
    output_dir: Path | None = None,
    existing_path: Path | None = None,
) -> Path:
    if existing_path is not None:
        if not existing_path.exists():
            msg = f"Bulk data file not found: {existing_path}"
            raise FileNotFoundError(msg)
        return existing_path

    if output_dir is None:
        output_dir = Path.cwd()

    output_dir.mkdir(parents=True, exist_ok=True)

    existing = _find_existing(output_dir)
    if existing and _is_fresh(existing):
        return existing

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    meta_resp = session.get(SCRYFALL_BULK_URL)
    meta_resp.raise_for_status()
    meta = meta_resp.json()

    download_uri = None
    for entry in meta.get("data", []):
        if entry.get("type") == "default_cards":
            download_uri = entry["download_uri"]
            break

    if not download_uri:
        msg = "Could not find default_cards bulk data URI"
        raise RuntimeError(msg)

    output_path = output_dir / "default-cards.json"

    with session.get(download_uri, stream=True) as resp:
        resp.raise_for_status()
        with output_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    return output_path


@click.command()
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to download bulk data to.",
)
@click.option(
    "--existing",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to an existing bulk data file to reuse.",
)
def main(output_dir: Path | None, existing: Path | None):
    """Download or locate Scryfall bulk data."""
    path = download_bulk(output_dir=output_dir, existing_path=existing)
    click.echo(str(path))
