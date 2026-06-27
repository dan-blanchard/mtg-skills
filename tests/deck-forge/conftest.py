"""Shared deck-forge test fixtures.

The single fixture here keeps the suite network-free. Since the phase-rs bump
decoupled card-data from the cargo build (it now ships in the release tarball),
``build_sidecar`` / ``production.ensure_card_ir`` reach card-data via
``_phase.ensure_card_data``, which downloads the tag-versioned tarball when the
cache is cold. deck-forge launch + the ``ensure_card_ir`` tests exercise that
path, so without a guard the suite would hit the network. Mirror the
``tests/mtg-utils/conftest.py`` guard: short-circuit ``ensure_card_data`` to
"cached-or-raise" so callers degrade to the regex path exactly as before the
download was wired in.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _block_card_data_download(monkeypatch):
    from mtg_utils import _phase

    real_path = _phase._card_data_path

    def _cached_only() -> Path:
        cached = real_path()
        if cached.exists():
            return cached
        raise RuntimeError(
            "card-data download blocked in tests (no network); the tag-versioned "
            f"cache at {cached} is absent."
        )

    monkeypatch.setattr(_phase, "ensure_card_data", _cached_only)
