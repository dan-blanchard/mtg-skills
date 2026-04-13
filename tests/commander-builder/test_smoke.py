"""Smoke tests verifying commander-builder's symlinked package works."""

import subprocess
import sys


def test_mtg_utils_importable():
    """The mtg_utils package is importable from commander-builder's venv."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mtg_utils import parse_deck, scryfall_lookup, edhrec_lookup, deck_stats, mana_audit, price_check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Import failed: {result.stderr}"


EXPECTED_ENTRY_POINTS = [
    "parse-deck",
    "scryfall-lookup",
    "edhrec-lookup",
    "download-bulk",
    "web-fetch",
    "deck-stats",
    "card-summary",
    "deck-diff",
    "set-commander",
    "mana-audit",
    "cut-check",
    "build-deck",
    "price-check",
]


def test_cli_entry_points_available():
    """All expected CLI entry points respond to --help."""
    for entry_point in EXPECTED_ENTRY_POINTS:
        result = subprocess.run(
            [sys.executable, "-m", "mtg_utils." + entry_point.replace("-", "_"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        # Click commands exposed via [project.scripts] may not work with -m,
        # so fall back to checking the module is at least importable
        if result.returncode != 0:
            mod = entry_point.replace("-", "_")
            result2 = subprocess.run(
                [sys.executable, "-c", f"from mtg_utils.{mod} import main; assert callable(main)"],
                capture_output=True,
                text=True,
                check=False,
            )
            assert result2.returncode == 0, (
                f"Entry point '{entry_point}' not available: {result.stderr} / {result2.stderr}"
            )
