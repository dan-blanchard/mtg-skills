"""Comprehensive Rules downloader.

Mirrors the ``download-bulk`` pattern: fetches the official Wizards of
the Coast MTG Comprehensive Rules TXT to the output directory, with a
24-hour freshness check that reuses an existing local copy instead of
re-downloading. Writes are atomic-rename so a crashed download cannot
leave a half-written file for ``rules-lookup`` to trip over.

Because the release cadence of the CR is irregular (a new version drops
alongside each set release or errata pass), we first GET the rules
landing page to discover the latest ``MagicCompRules 2026MMDD.txt``
download link, then fetch that. A locally-cached filename pattern
``comprehensive-rules-YYYYMMDD.txt`` lets ``rules-lookup`` find the
newest file without flags.
"""

from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

import click
import requests

# The listing page. ``requests`` with a browser UA is enough in normal
# networks; the MTG skills CLI is expected to run outside the sandbox.
_RULES_LANDING_URL = "https://magic.wizards.com/en/rules"

# Fallback: the current (Feb 2026) direct URL. If the landing-page
# discovery fails, we try this URL with the last-known filename pattern.
_FALLBACK_TXT_URL = (
    "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt"
)

# Match filenames like ``MagicCompRules 20260227.txt`` (the space may be
# URL-encoded as ``%20``) on the landing page and in download links.
_TXT_LINK_RE = re.compile(
    r"https?://[^\s\"'<>]+MagicCompRules(?:%20|\s)?(\d{8})\.txt",
    re.IGNORECASE,
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; mtg-skills rules-lawyer/0.1; "
    "+https://github.com/dan-blanchard/mtg-skills)"
)
FRESHNESS_SECONDS = 86400  # 24 hours — match download_bulk.

_LOCAL_GLOB = "comprehensive-rules*.txt"


def _find_existing(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.glob(_LOCAL_GLOB))
    return candidates[-1] if candidates else None


def _is_fresh(path: Path) -> bool:
    age = time.time() - path.stat().st_mtime
    return age < FRESHNESS_SECONDS


def _discover_latest_url(session: requests.Session) -> tuple[str, str] | None:
    """Scrape the landing page for the newest ``MagicCompRules*.txt`` link.

    Returns ``(url, yyyymmdd)`` or None if discovery failed. The CLI
    falls back to a hard-coded known-good URL when None is returned.
    """
    try:
        resp = session.get(_RULES_LANDING_URL, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    matches = _TXT_LINK_RE.findall(resp.text)
    if not matches:
        return None
    # Newest date wins (lexicographic == chronological for YYYYMMDD).
    newest = max(matches)
    # Rebuild the URL so we emit exactly what ``_TXT_LINK_RE`` matched.
    for m in _TXT_LINK_RE.finditer(resp.text):
        if m.group(1) == newest:
            return m.group(0), newest
    return None


def _atomic_write_bytes(path: Path, session: requests.Session, url: str) -> None:
    """Stream ``url`` into a temp file alongside ``path``, then rename.

    Cleans up the temp file if streaming raises, so a network failure
    mid-download can't leave an orphaned ``.name.tmp`` file behind
    (previous behaviour with ``delete=False``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — manual close to allow .replace after context exit
        mode="wb",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        with session.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
        tmp.close()
        tmp_path.replace(path)
    except BaseException:
        tmp.close()
        tmp_path.unlink(missing_ok=True)
        raise


def download_rules(
    output_dir: Path | None = None,
    existing_path: Path | None = None,
) -> Path:
    """Ensure a fresh local copy of the Comprehensive Rules TXT.

    Args:
        output_dir: Directory to hold / write the rules file. Defaults to
            the current working directory.
        existing_path: If supplied, skip discovery and freshness logic
            and just verify the given path exists.
    """
    if existing_path is not None:
        if not existing_path.exists():
            msg = f"Rules file not found: {existing_path}"
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

    discovered = _discover_latest_url(session)
    if discovered is not None:
        url, datestamp = discovered
    else:
        url = _FALLBACK_TXT_URL
        m = re.search(r"(\d{8})\.txt", url)
        datestamp = m.group(1) if m else "unknown"

    # If the newest-discovered file is the same as our existing one,
    # just touch the mtime so the freshness check passes next time.
    expected_name = f"comprehensive-rules-{datestamp}.txt"
    output_path = output_dir / expected_name
    if output_path.exists() and existing is not None and existing.samefile(output_path):
        output_path.touch()
        return output_path

    _atomic_write_bytes(output_path, session, url)
    return output_path


@click.command()
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory to download the rules file to.",
)
@click.option(
    "--existing",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to an existing rules file to reuse without network.",
)
def main(output_dir: Path | None, existing: Path | None) -> None:
    """Download or locate the MTG Comprehensive Rules TXT."""
    path = download_rules(output_dir=output_dir, existing_path=existing)
    click.echo(str(path))
