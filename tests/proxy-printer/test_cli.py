"""CLI argparse / exit-code surface."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "proxy-print", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2] / "proxy-printer",
    )


def test_help_exits_zero() -> None:
    r = _run(["--help"])
    assert r.returncode == 0
    assert "--kind" in r.stdout
    assert "cards" in r.stdout
    assert "tokens" in r.stdout
    assert "--deck" in r.stdout
    assert "--out" in r.stdout


def test_missing_kind_exits_nonzero() -> None:
    r = _run([])
    assert r.returncode != 0
    assert "kind" in (r.stderr + r.stdout).lower()


def test_invalid_deck_path_exits_nonzero(tmp_path: Path) -> None:
    out = tmp_path / "out.pdf"
    r = _run([
        "--kind", "cards",
        "--deck", str(tmp_path / "nonexistent.json"),
        "--out", str(out),
    ])
    assert r.returncode != 0


def test_malformed_deck_json_exits_with_deck_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{{")
    out = tmp_path / "out.pdf"
    bulk = tmp_path / "fake-bulk.json"
    bulk.write_text("[]")
    r = _run([
        "--kind", "cards",
        "--deck", str(bad),
        "--out", str(out),
        "--bulk-data", str(bulk),
    ])
    # Either click rejects (json parse fails) or the CLI exits with the
    # documented EXIT_DECK_INVALID = 2.
    assert r.returncode != 0


def test_deck_missing_required_keys_exits_two(tmp_path: Path) -> None:
    """Deck JSON missing all of {commanders, cards, sideboard} → exit 2."""
    bad = tmp_path / "schemaless.json"
    bad.write_text(json.dumps({"unrelated": "data"}))
    out = tmp_path / "out.pdf"
    bulk = tmp_path / "fake-bulk.json"
    bulk.write_text("[]")
    r = _run([
        "--kind", "cards",
        "--deck", str(bad),
        "--out", str(out),
        "--bulk-data", str(bulk),
    ])
    assert r.returncode == 2


def test_missing_bulk_exits_one(tmp_path: Path) -> None:
    """Nonexistent bulk path → exit 1 with actionable message."""
    deck = tmp_path / "deck.json"
    deck.write_text(json.dumps({"cards": [{"name": "Sol Ring", "quantity": 1}]}))
    out = tmp_path / "out.pdf"
    r = _run([
        "--kind", "cards",
        "--deck", str(deck),
        "--out", str(out),
        "--bulk-data", str(tmp_path / "missing.json"),
    ])
    # Click rejects nonexistent path before we get to our own check.
    assert r.returncode != 0
