"""Shared helpers: JSON envelope, markdown rendering."""

from __future__ import annotations

import time
from typing import Any

SCHEMA_VERSION = 1


def envelope(
    *,
    mode: str,
    engine: str,
    engine_version: str,
    seed: int | None,
    format_: str | None,
    card_coverage: dict | None,
    results: dict,
    warnings: list[str] | None = None,
    duration_s: float,
) -> dict[str, Any]:
    """Build the schema-v1 JSON envelope wrapping any playtest result."""
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "engine": engine,
        "engine_version": engine_version,
        "seed": seed,
        "format": format_,
        "card_coverage": card_coverage,
        "results": results,
        "warnings": warnings or [],
        "duration_s": round(duration_s, 2),
        "generated_at": int(time.time()),
    }
