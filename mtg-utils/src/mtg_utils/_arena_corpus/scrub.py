"""The Manasight scrubber: the pinned ``manasight-parser`` ``scrub`` binary.

The public corpus checks every log it is sent with this binary (its
``check-log-sanitization`` workflow), so a file is first scrubbed with the same
tool. ``arena-log-export --install-scrub`` builds it once with ``cargo install``
into ``<cache root>/manasight-scrub/<SCRUB_PIN>/``, the way
``playtest-install-phase`` builds phase. In tests the scrubber is a plain callable.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from mtg_utils._http import cache_root

__all__ = [
    "SCRUB_PIN",
    "ScrubError",
    "Scrubber",
    "binary_scrubber",
    "file_sha256",
    "find_scrub",
    "install_command",
    "install_scrub",
    "is_pinned",
    "pinned_binary",
    "scrub_root",
]

#: The ``manasight-parser`` release whose ``scrub`` (the strictest, "corpus"
#: profile) sanitizes every exported log.
SCRUB_PIN = "0.8.1"

#: Raw log text in, scrubbed log text out.
Scrubber = Callable[[str], str]


class ScrubError(RuntimeError):
    """The scrubber is missing, can't be built, or failed on a log."""


def scrub_root() -> Path:
    """Where the pinned scrubber is installed (``cargo install --root``)."""
    return cache_root() / "manasight-scrub" / SCRUB_PIN


def install_command(root: Path) -> list[str]:
    return [
        "cargo",
        "install",
        "manasight-parser",
        "--version",
        SCRUB_PIN,
        "--features",
        "tailer",
        "--bin",
        "scrub",
        "--locked",
        "--root",
        str(root),
    ]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(binary: Path) -> Path:
    """Where the install keeps the binary's sha256, beside it."""
    return binary.with_name(binary.name + ".sha256")


def install_scrub(run: Callable[..., object] = subprocess.run) -> Path:
    """Build the pinned ``scrub`` into :func:`scrub_root` and record its sha256
    beside it (``scrub.sha256``); the binary's path."""
    if shutil.which("cargo") is None:
        raise ScrubError("`cargo` not found on PATH; install Rust from rustup.rs")
    root = scrub_root()
    root.mkdir(parents=True, exist_ok=True)
    run(install_command(root), check=True)
    binary = root / "bin" / "scrub"
    if not binary.is_file():
        raise ScrubError(f"cargo install finished but {binary} is missing")
    _record(binary).write_text(file_sha256(binary) + "\n")
    return binary


def pinned_binary() -> Path:
    return scrub_root() / "bin" / "scrub"


def is_pinned(binary: Path) -> bool:
    """Whether ``binary`` is byte for byte the one ``--install-scrub`` built."""
    record = _record(pinned_binary())
    return record.is_file() and record.read_text().strip() == file_sha256(binary)


def find_scrub(override: Path | None = None) -> Path:
    """The scrubber to run: ``override`` (``--scrub-bin``; the caller warns when
    it isn't :func:`is_pinned` and relies on the self-test), else the install,
    refused unless its sha256 matches the one recorded when it was built. Never
    a ``scrub`` on PATH: its version is unknown."""
    if override is not None:
        if not override.is_file():
            raise ScrubError(f"scrub binary not found at {override}")
        return override
    binary = pinned_binary()
    hint = (
        "run `arena-log-export --install-scrub` (cargo install of "
        f"manasight-parser {SCRUB_PIN}), or pass --scrub-bin"
    )
    if not binary.is_file():
        raise ScrubError(f"scrub binary not found at {binary}: {hint}")
    if not _record(binary).is_file():
        raise ScrubError(f"{binary} has no recorded sha256: {hint}")
    if not is_pinned(binary):
        raise ScrubError(
            f"{binary} differs from the binary --install-scrub built "
            f"(sha256 mismatch): {hint}"
        )
    return binary


def binary_scrubber(binary: Path) -> Scrubber:
    """A :data:`Scrubber` that pipes the text through ``binary`` (stdin to stdout)."""

    def scrub(text: str) -> str:
        done = subprocess.run(
            [str(binary)], input=text.encode(), capture_output=True, check=False
        )
        if done.returncode != 0:
            err = done.stderr.decode(errors="replace").strip()
            raise ScrubError(f"{binary} exited {done.returncode}: {err[:300]}")
        return done.stdout.decode()

    return scrub
