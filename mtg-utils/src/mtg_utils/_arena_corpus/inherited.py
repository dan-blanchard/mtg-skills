"""``--resanitize-inherited``: the corpus's own files, re-scrubbed.

The public corpus's files predate parts of the scrubber (real deck ids, deck
names, GPU lines). The fork cleans them in its first commit: each
``corpus/*.log.gz`` goes through the pinned scrubber and the second pass, then
the checks that need no raw session (patterns, fields, the denylist, this
machine's names — no harvest: no raw text of these sessions exists), the signal
check as old file against new file, the re-scrub and size checks. A file is
rewritten (gzip mtime 0, no name) only when its content changed, and its
manifest ``sha256`` and ``size_bytes`` with it; nothing is written unless every
file passes (or ``keep_going``), as an export.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import shutil
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mtg_utils._arena_corpus.corpus import MANIFEST, commit
from mtg_utils._arena_corpus.export import MAX_GZ_BYTES, SignalReport, _canon, _mb
from mtg_utils._arena_corpus.redact import second_pass
from mtg_utils._arena_corpus.scrub import SCRUB_PIN, Scrubber
from mtg_utils._arena_corpus.verify import (
    Finding,
    MachineFacts,
    Term,
    check_fields,
    check_patterns,
    check_terms,
    machine_terms,
)

__all__ = ["CHECKS", "Inherited", "InheritedOutcome", "render", "resanitize"]

CHECKS = ("patterns", "fields", "user-denylist", "signal", "rescrub", "size")


@dataclass
class Inherited:
    name: str
    old_size: int = 0
    size: int = 0
    sha256: str = ""
    changed: bool = False
    passed: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    redactions: Counter[str] = field(default_factory=Counter)
    staged: Path | None = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.findings and not self.problems

    @property
    def failed(self) -> list[str]:
        return [c for c in CHECKS if c not in self.passed]


@dataclass
class InheritedOutcome:
    files: list[Inherited]
    written: list[str] = field(default_factory=list)
    #: Rewritten files the manifest has no entry for.
    unlisted: list[str] = field(default_factory=list)
    commit: str | None = None

    @property
    def failed(self) -> list[Inherited]:
        return [f for f in self.files if not f.ok]


def _check(v: Inherited, name: str, findings: list[Finding]) -> None:
    if findings:
        v.findings += findings
    else:
        v.passed.append(name)


def recheck(
    path: Path,
    scrubber: Scrubber,
    work: Path,
    *,
    signal_report: SignalReport | None,
    terms: Sequence[Term],
) -> Inherited:
    v = Inherited(path.name)
    start = time.monotonic()
    old = gzip.decompress(path.read_bytes()).decode("utf-8")
    v.old_size = len(old.encode())
    new, v.redactions = second_pass(scrubber(old))
    data = new.encode()
    v.size, v.sha256, v.changed = (
        len(data),
        hashlib.sha256(data).hexdigest(),
        new != old,
    )
    _check(v, "patterns", check_patterns(new))
    _check(v, "fields", check_fields(new))
    _check(v, "user-denylist", check_terms(new, terms, "user-denylist"))
    if signal_report is None:
        pass
    elif not v.changed:
        v.passed.append("signal")  # the same bytes read the same
    else:
        plain = work / path.name.removesuffix(".gz")
        plain.write_bytes(data)
        try:
            same = _canon(signal_report(path)) == _canon(signal_report(plain))
        finally:
            plain.unlink()
        if same:
            v.passed.append("signal")
        else:
            v.problems.append("signal: arena-crosscheck reads the new file differently")
    if scrubber(new) == new:
        v.passed.append("rescrub")
    else:
        v.problems.append("rescrub: the scrubber would still change this file")
    packed = gzip.compress(data, mtime=0)
    if len(packed) <= MAX_GZ_BYTES:
        v.passed.append("size")
    else:
        v.problems.append(f"size: {len(packed):,} bytes gzipped, over 10 MiB")
    if v.ok and v.changed:
        v.staged = work / path.name
        v.staged.write_bytes(packed)
    v.seconds = time.monotonic() - start
    return v


def update_manifest(corpus: Path, rows: dict[str, tuple[str, int]]) -> list[str]:
    """Rewrite each listed file's ``sha256`` and ``size_bytes``; the file names
    the manifest has no entry for."""
    path = corpus / MANIFEST
    text, missing = path.read_text(), []
    for filename, (sha, size) in rows.items():
        entry = re.compile(
            r'(filename\s*=\s*"' + re.escape(filename) + r'"\n'
            r'sha256\s*=\s*)"[0-9a-f]*"(\nsize_bytes\s*=\s*)\d+'
        )
        text, n = entry.subn(rf'\g<1>"{sha}"\g<2>{size}', text)
        if not n:
            missing.append(filename)
    path.write_text(text)
    return missing


def resanitize(
    corpus: Path,
    scrubber: Scrubber,
    work: Path,
    *,
    signal_report: SignalReport | None = None,
    machine: MachineFacts | None = None,
    denylist: Sequence[Term] = (),
    dry_run: bool = False,
    keep_going: bool = False,
    do_commit: bool = False,
    progress: Callable[[str], None] = lambda _line: None,
) -> InheritedOutcome:
    terms = [*denylist, *machine_terms(machine or MachineFacts())]
    paths = sorted((corpus / "corpus").glob("*.log.gz"))
    out = InheritedOutcome([])
    for i, path in enumerate(paths, 1):
        v = recheck(path, scrubber, work, signal_report=signal_report, terms=terms)
        out.files.append(v)
        verdict = ("changes" if v.changed else "unchanged") + (
            "" if v.ok else f", FAIL: {', '.join(v.failed)}"
        )
        progress(f"[{i}/{len(paths)}] {v.name}: {verdict} ({v.seconds:.0f}s)")
    if dry_run or (out.failed and not keep_going):
        return out
    rows = {}
    for v in out.files:
        if v.ok and v.staged is not None:
            shutil.copyfile(v.staged, corpus / "corpus" / v.name)
            rows[v.name.removesuffix(".gz")] = (v.sha256, v.size)
            out.written.append(v.name)
    if rows:
        out.unlisted = update_manifest(corpus, rows)
        if do_commit:
            message = (
                f"Re-sanitize inherited sessions with manasight-parser {SCRUB_PIN}\n\n"
                + "".join(f"- {n}\n" for n in out.written)
            )
            files = [f"corpus/{n}" for n in out.written] + [MANIFEST]
            out.commit = commit(corpus, files, message)
    return out


def render(out: InheritedOutcome, *, dry_run: bool) -> str:
    w = max([len(v.name) for v in out.files] + [4])
    lines = [f"{'file':{w}} {'old':>6} {'new':>6} {'time':>5}  verdict"]
    for v in out.files:
        verdict = "changes" if v.changed else "unchanged"
        verdict += " PASS" if v.ok else " FAIL: " + ", ".join(v.failed)
        lines.append(
            f"{v.name:{w}} {_mb(v.old_size):>6} {_mb(v.size):>6} "
            f"{v.seconds:>4.0f}s  {verdict}"
        )
        lines += [f"    ! {f}" for f in v.findings]
        lines += [f"    ! {p}" for p in v.problems]
    changed = sum(v.changed for v in out.files)
    lines += [
        "",
        (
            f"{len(out.files)} inherited file(s): {changed} change, "
            f"{len(out.files) - len(out.failed)} pass, {len(out.failed)} fail. "
            "Harvest not run: no raw text of these sessions exists."
        ),
    ]
    if dry_run:
        lines.append("Dry run: nothing written.")
    elif out.failed and not out.written:
        lines.append("Nothing written: a file failed (--keep-going writes the rest)")
    else:
        lines.append(f"Rewrote {len(out.written)} file(s) and their manifest rows.")
        if out.unlisted:
            lines.append("Not in the manifest: " + ", ".join(out.unlisted))
        if out.commit:
            lines.append(f"Committed {out.commit} locally (unsigned); not pushed.")
    return "\n".join(lines) + "\n"
