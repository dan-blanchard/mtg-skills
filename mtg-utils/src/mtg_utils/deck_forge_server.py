"""deck-forge backend hub — CLI entry point.

A local FastAPI process that owns canonical session state, hosts the deterministic
core (wrapping ``mtg_utils``), serves the browser SPA, and (in later milestones)
bridges the browser surface to the interactive Claude Code session-agent.

The app itself is assembled in ``mtg_utils._deck_forge.app.build_app`` from an
injected ``ForgeState``; ``create_app`` wires the production state (real bulk data).

Run with::

    deck-forge            # launch on the default port and open a browser
    deck-forge --no-open  # launch without opening a browser (e.g. for tests/CI)
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

import click
from fastapi import FastAPI

from mtg_utils._deck_forge.app import VERSION, build_app, busy_reporter
from mtg_utils._deck_forge.production import default_state, warm_at_launch

__all__ = ["VERSION", "create_app", "main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    """Build the production app (real bulk data when available), and start the
    launch warm (the signals index, then the commander-discovery caches) in the
    background so a first launch's one-time passes run with a progress meter in
    the page rather than inside the first request."""
    state = default_state()
    app = build_app(state, frontend_dist=frontend_dist)
    warm_at_launch(state, busy_reporter(state))
    return app


@click.command()
@click.option("--host", default=DEFAULT_HOST, show_default=True)
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int)
@click.option(
    "--open/--no-open",
    "open_browser",
    default=True,
    show_default=True,
    help="Open the build UI in a browser on startup.",
)
@click.option(
    "--frontend-dist",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the built SPA (defaults to ./frontend/dist).",
)
def main(
    host: str,
    port: int,
    frontend_dist: Path | None,
    *,
    open_browser: bool,
) -> None:
    """Launch the deck-forge backend hub."""
    import uvicorn  # deferred import so `--help` stays fast and import-light

    dist = frontend_dist or (Path.cwd() / "frontend" / "dist")
    app = create_app(frontend_dist=dist)
    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
