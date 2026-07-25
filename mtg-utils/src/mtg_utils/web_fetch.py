"""Web page fetcher for strategy articles — fallback when WebFetch returns JS shells."""

import re

import click
import requests

from mtg_utils._http import BROWSER_HEADERS, _fetch_with_curl

# Re-exported for existing importers (cubecobra_fetch.py) — the shared
# implementations now live in mtg_utils._http; see its module docstring.
__all__ = ["BROWSER_HEADERS", "_fetch_with_curl", "fetch_page", "main"]


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace into readable text."""
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    # Convert common block elements to newlines
    text = re.sub(r"<(?:p|div|br|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_page(url: str) -> str:
    """Fetch a web page and return its text content.

    Tries Python requests first with browser-like headers. If that fails
    with a 403 (common with TLS fingerprinting), falls back to curl which
    uses the system's native TLS stack.

    Args:
        url: The URL to fetch.

    Returns:
        Stripped text content of the page.
    """
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    resp = session.get(url, timeout=30)

    if resp.status_code == 403:
        # TLS fingerprinting block — fall back to curl
        html = _fetch_with_curl(url)
    else:
        resp.raise_for_status()
        html = resp.text

    return _strip_html(html)


@click.command()
@click.argument("url")
@click.option(
    "--max-length",
    type=int,
    default=None,
    help="Truncate output to this many characters.",
)
def main(url: str, max_length: int | None) -> None:
    """Fetch a web page and print its text content."""
    text = fetch_page(url)
    if max_length and len(text) > max_length:
        text = text[:max_length] + "\n\n[Truncated]"
    click.echo(text)
