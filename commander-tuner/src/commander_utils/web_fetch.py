"""Web page fetcher for strategy articles — fallback when WebFetch returns JS shells."""

import re
import subprocess

import click
import requests

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Avoid Brotli — requests can't decode it without extra dependencies
    "Accept-Encoding": "gzip, deflate",
}


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


def _fetch_with_curl(url: str) -> str:
    """Fetch via curl — bypasses TLS fingerprinting that blocks requests."""
    result = subprocess.run(
        [
            "curl",
            "-sL",
            "-H",
            f"User-Agent: {BROWSER_HEADERS['User-Agent']}",
            "-H",
            f"Accept: {BROWSER_HEADERS['Accept']}",
            "-H",
            f"Accept-Language: {BROWSER_HEADERS['Accept-Language']}",
            "--compressed",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        msg = f"curl failed with exit code {result.returncode}: {result.stderr}"
        raise RuntimeError(msg)
    return result.stdout


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
def main(url: str, max_length: int | None):
    """Fetch a web page and print its text content."""
    text = fetch_page(url)
    if max_length and len(text) > max_length:
        text = text[:max_length] + "\n\n[Truncated]"
    click.echo(text)
