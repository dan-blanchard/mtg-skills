"""Wrapper around the phase-rs MTG rules engine.

Phase is invoked as a subprocess. We pin the upstream tag, build once into
a per-user cache, and shell out for every duel/commander run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

PHASE_TAG = "v0.1.19"
PHASE_REPO = "https://github.com/phase-rs/phase"

KNOWN_BINARIES = ("ai-duel", "ai-commander")


class PhaseNotInstalledError(RuntimeError):
    """Raised when the phase binary cannot be located."""


class PhasePrereqError(RuntimeError):
    """Raised when system prereqs (cargo, git) are missing."""


def cache_dir() -> Path:
    """Return the phase cache root: ``$MTG_SKILLS_CACHE_DIR/phase``
    or ``$HOME/.cache/mtg-skills/phase``.
    """
    base = os.environ.get("MTG_SKILLS_CACHE_DIR")
    if base:
        return Path(base) / "phase"
    return Path(os.environ["HOME"]) / ".cache" / "mtg-skills" / "phase"


def _repo_dir() -> Path:
    return cache_dir() / "phase.git"


def _release_dir() -> Path:
    return _repo_dir() / "target" / "release"


def find_binary(name: str) -> Path:
    """Locate a phase binary. Honors ``MTG_SKILLS_PHASE_BIN`` for ai-duel.

    For non-default binaries the env override is treated as the directory
    containing them. When the env override is set, the cache path is NOT
    consulted as a fallback — set the env, you're on your own.
    """
    env_override = os.environ.get("MTG_SKILLS_PHASE_BIN")
    if env_override:
        env_path = Path(env_override)
        if env_path.is_dir():
            candidate = env_path / name
        elif env_path.name == name:
            candidate = env_path
        else:
            candidate = env_path.parent / name
        if candidate.exists():
            return candidate
        raise PhaseNotInstalledError(
            f"Phase binary '{name}' not found at {candidate} "
            f"(resolved from MTG_SKILLS_PHASE_BIN={env_override}).\n"
            f"Run `playtest-install-phase` to build phase {PHASE_TAG}, or "
            f"unset MTG_SKILLS_PHASE_BIN to use the default cache path."
        )

    candidate = _release_dir() / name
    if candidate.exists():
        return candidate

    raise PhaseNotInstalledError(
        f"Phase binary '{name}' not found at {candidate}.\n"
        f"Run `playtest-install-phase` to build phase {PHASE_TAG} (~5-10 min)."
    )


def _ensure_prereqs() -> None:
    """Verify cargo and git are on PATH; raise with a clear message otherwise."""
    for tool in ("cargo", "git"):
        if shutil.which(tool) is None:
            raise PhasePrereqError(
                f"`{tool}` not found on PATH. "
                f"Install prereqs: cargo (rustup.rs) and git."
            )


def install_phase() -> None:
    """Clone, generate card data, and build the phase binaries we use."""
    _ensure_prereqs()
    repo = _repo_dir()
    repo.parent.mkdir(parents=True, exist_ok=True)

    if not repo.exists():
        subprocess.run(
            ["git", "clone", "--depth=1", "--branch", PHASE_TAG, PHASE_REPO, str(repo)],
            check=True,
        )

    subprocess.run(
        ["bash", "./scripts/setup.sh"],
        cwd=str(repo),
        check=True,
    )

    subprocess.run(
        ["cargo", "build", "--release", "--bin", "ai-duel", "--bin", "ai-commander"],
        cwd=str(repo),
        check=True,
    )

    version_file = cache_dir() / "version.txt"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    version_file.write_text(head + "\n")


DEFAULT_COVERAGE_THRESHOLD = 0.9


def _card_data_path() -> Path:
    return _repo_dir() / "client" / "public" / "card-data.json"


@lru_cache(maxsize=1)
def load_supported_card_names() -> frozenset[str]:
    """Load the set of card names phase implements (cached)."""
    path = _card_data_path()
    if not path.exists():
        raise PhaseNotInstalledError(
            f"phase card-data.json not found at {path}. Run `playtest-install-phase`.",
        )
    data = json.loads(path.read_text())
    return frozenset(c["name"] for c in data.get("cards", []))


def coverage_report(
    card_names: list[str],
    *,
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
) -> dict:
    """Classify a deck's phase coverage as full / warn / blocked.

    - ``full`` (100% supported): run silently.
    - ``warn`` (>= threshold but < 100%): run with a warning naming missing.
    - ``blocked`` (< threshold): refuse to run.
    """
    supported = load_supported_card_names()
    requested_set = set(card_names)
    missing = sorted(requested_set - supported)
    matched = len(requested_set) - len(missing)
    pct = matched / len(requested_set) if requested_set else 1.0

    if not missing:
        status = "full"
    elif pct >= threshold:
        status = "warn"
    else:
        status = "blocked"

    return {
        "status": status,
        "supported_pct": pct,
        "missing": missing,
        "requested": len(requested_set),
        "supported": matched,
    }
