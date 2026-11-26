"""Fetch a cube list from CubeCobra.

Priority order: cubeJSON endpoint (richest — has mainboard/maybeboard split,
designer tags, per-card overrides, Scryfall IDs) → cubelist (plain newline
names) → CSV. Which clients CubeCobra refuses (HTTP 403) has changed over
time, so a request is tried as this tool's own client first, then with browser
headers, then through curl; a refusal is reported as one, never as a missing
cube.

Both the card list and overview metadata (description, tags, designer
intent) are fetched when using the JSON endpoint — the overview is embedded
in the cubeJSON response.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click
import requests

from mtg_utils._http import BROWSER_HEADERS, USER_AGENT, _fetch_with_curl

CUBECOBRA_JSON_URL = "https://cubecobra.com/cube/api/cubeJSON/{cube_id}"
CUBECOBRA_LIST_URL = "https://cubecobra.com/cube/api/cubelist/{cube_id}"
CUBECOBRA_CSV_URL = "https://cubecobra.com/cube/download/csv/{cube_id}"

# cubecobra cube id is the segment right after the route keyword (/overview/<id>,
# /list/<id>, …); a trailing sub-page (/analysis/<id>/typal) is ignored by .search.
# The one exception is the download route, which inserts a format segment first
# (/download/csv/<id>), so skip a known format token before the id. The previous
# non-greedy `(?:/[^/?]+)*?` matched the FEWEST segments and so bound the id to the
# format token ("csv") for download URLs.
_CUBE_ID_FROM_URL = re.compile(
    r"cubecobra\.com/cube/(?:list|overview|playtest|blog|download|api|analysis)"
    r"(?:/(?:csv|xml|forge|plaintext|mtgo|cubecobra|json))?"
    r"/(?P<cube_id>[a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


def extract_cube_id(raw: str) -> str:
    """Extract a CubeCobra cube ID from a raw ID or full URL."""
    raw = raw.strip()
    if "://" not in raw and "/" not in raw:
        return raw
    match = _CUBE_ID_FROM_URL.search(raw)
    if match:
        return match.group("cube_id")
    # Fall back to last path segment, stripping query.
    last = raw.rstrip("/").rsplit("/", 1)[-1]
    return last.split("?", 1)[0]


# Tried in order. CubeCobra answered 403 to a browser User-Agent and 200 to a
# plain client on 2026-11-25; the reverse held when this tool was written.
_HEADER_SETS: tuple[dict[str, str], ...] = (
    {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
    BROWSER_HEADERS,
)


def _fetch_text(url: str) -> str:
    """GET a URL, as each client identity in turn, then through curl.

    A 403 moves on to the next identity; a 404 is a missing cube. CubeCobra
    has also returned an HTML shell with HTTP 200 for a missing ID, so a
    response that is an HTML page is rejected: as a refusal when every
    identity was refused, as a missing cube otherwise.
    """
    session = requests.Session()
    text: str | None = None
    for headers in _HEADER_SETS:
        resp = session.get(url, headers=headers, timeout=30)
        if resp.status_code == 403:
            continue
        if resp.status_code == 404:
            msg = f"CubeCobra has no such cube (HTTP 404) for {url}"
            raise RuntimeError(msg)
        resp.raise_for_status()
        text = resp.text
        break
    refused = text is None
    if text is None:
        text = _fetch_with_curl(url)

    if text.lstrip().lower().startswith(("<!doctype", "<html")):
        if refused:
            msg = f"CubeCobra refused the request (HTTP 403) for {url}"
        else:
            msg = f"CubeCobra returned an HTML page (likely cube not found) for {url}"
        raise RuntimeError(msg)
    return text


def fetch_json(cube_id: str) -> dict:
    """Fetch the cubeJSON endpoint and parse it."""
    raw = _fetch_text(CUBECOBRA_JSON_URL.format(cube_id=cube_id))
    return json.loads(raw)


def fetch_cubelist(cube_id: str) -> str:
    """Fetch the plain-text name list endpoint."""
    return _fetch_text(CUBECOBRA_LIST_URL.format(cube_id=cube_id))


def fetch_csv(cube_id: str) -> str:
    """Fetch the CSV download endpoint."""
    return _fetch_text(CUBECOBRA_CSV_URL.format(cube_id=cube_id))


@click.command()
@click.argument("cube_ref")
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(),
    show_default=True,
    help="Directory to write the fetched files into.",
)
@click.option(
    "--format",
    "preferred_format",
    type=click.Choice(["json", "csv", "list"]),
    default="json",
    show_default=True,
    help="Preferred format. Falls back through json → csv → list on error.",
)
def main(cube_ref: str, output_dir: Path, preferred_format: str) -> None:
    """Fetch a cube from CubeCobra. Accepts a cube ID or a CubeCobra URL."""
    cube_id = extract_cube_id(cube_ref)
    output_dir.mkdir(parents=True, exist_ok=True)

    attempts = {
        "json": (preferred_format == "json", fetch_json, f"{cube_id}.json", "json"),
        "csv": (preferred_format == "csv", fetch_csv, f"{cube_id}.csv", "csv"),
        "list": (preferred_format == "list", fetch_cubelist, f"{cube_id}.txt", "list"),
    }
    order = [preferred_format] + [
        f for f in ("json", "csv", "list") if f != preferred_format
    ]

    errors: list[str] = []
    for fmt in order:
        _, fetcher, filename, kind = attempts[fmt]
        try:
            data = fetcher(cube_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fmt}: {exc}")
            continue

        out_path = (output_dir / filename).resolve()
        if isinstance(data, dict):
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        else:
            out_path.write_text(data, encoding="utf-8")

        click.echo(f"cubecobra-fetch: {kind} saved to {out_path}")
        if isinstance(data, dict):
            # v2 nests mainboard under `cards`; v1 has it at top level.
            cards_block = (
                data.get("cards") if isinstance(data.get("cards"), dict) else None
            )
            mainboard = (
                cards_block.get("mainboard", [])
                if cards_block
                else data.get("mainboard") or []
            )
            click.echo(
                f"  cube: {data.get('name', '?')} ({len(mainboard)} mainboard cards)"
            )
            if data.get("description"):
                desc = data["description"].strip().splitlines()[0][:120]
                click.echo(f"  description: {desc}")
        click.echo(f"Full JSON: {out_path}")
        return

    # All attempts failed.
    click.echo("cubecobra-fetch: all endpoints failed:", err=True)
    for err in errors:
        click.echo(f"  · {err}", err=True)
    raise click.ClickException("could not fetch cube from CubeCobra")
