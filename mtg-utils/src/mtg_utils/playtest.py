"""Playtest entry points: goldfish, match, gauntlet, draft, install-phase.

Each command is a self-contained Click entry point. They share helpers from
``_playtest_common`` (output rendering) and ``_phase`` (Rust-engine wrapper).
"""

from __future__ import annotations

import click


@click.command()
def goldfish_main() -> None:
    """Solo deck simulator (mulligan, curve, color-screw, combo timing)."""
    click.echo("goldfish: not yet implemented")


@click.command()
def match_main() -> None:
    """AI vs AI batch (phase-rs)."""
    click.echo("match: not yet implemented")


@click.command()
def gauntlet_main() -> None:
    """Cube archetype-gauntlet round-robin (phase-rs)."""
    click.echo("gauntlet: not yet implemented")


@click.command()
def draft_main() -> None:
    """Heuristic cube draft + per-deck goldfish."""
    click.echo("draft: not yet implemented")


@click.command()
def install_phase_main() -> None:
    """One-time install of the phase-rs binaries we wrap."""
    click.echo("install-phase: not yet implemented")
