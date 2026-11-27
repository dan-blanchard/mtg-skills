"""The export pipeline, per archived session: gunzip, the Manasight scrubber, the
second pass (``redact``), the checks (``verify`` plus the signal, re-scrub, size
and name checks), gzip into a private staging folder. Only when every selected
session passes (or ``--keep-going``) are the passing files copied into the
corpus clone and added to its manifest. Fail closed: a file that fails any check
is never written.
"""

from __future__ import annotations

import fnmatch
import gzip
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mtg_utils._arena_corpus import naming
from mtg_utils._arena_corpus.corpus import (
    MANIFEST,
    ManifestEntry,
    State,
    append_manifest,
    check_commit_identity,
    commit,
    export_message,
    manifest_entries,
)
from mtg_utils._arena_corpus.redact import second_pass
from mtg_utils._arena_corpus.scrub import Scrubber
from mtg_utils._arena_corpus.verify import (
    Finding,
    Harvest,
    MachineFacts,
    Term,
    check_fields,
    check_patterns,
    check_terms,
    harvest,
    machine_terms,
)

__all__ = [
    "MAX_GZ_BYTES",
    "Exporter",
    "Outcome",
    "Session",
    "SignalReport",
    "Verdict",
    "export",
    "find_sessions",
    "render",
    "render_verify",
    "verify_file",
]

#: The corpus's limit on one compressed file (its ``check-log-sanitization``).
MAX_GZ_BYTES = 10 * 1024 * 1024

#: Every check a session goes through, in order.
CHECKS = (
    "harvest",
    "patterns",
    "user-denylist",
    "fields",
    "signal",
    "rescrub",
    "size",
    "name",
)

#: A signal report for a log file: ``arena-crosscheck``'s report in production.
SignalReport = Callable[[Path], dict]


@dataclass(frozen=True)
class Session:
    path: Path
    #: ``<account>/<file>``: names the account, so only the state file keeps it.
    key: str

    @property
    def label(self) -> str:
        """How the table names its source: the archive timestamp alone."""
        return self.path.name.split("-", 1)[0]


def find_sessions(archive: Path, only: str | None = None) -> list[Session]:
    """The archive's sessions, oldest archive timestamp first."""
    paths = sorted(archive.glob("*/*.log.gz"), key=lambda p: (p.name, p.parent.name))
    sessions = [Session(p, f"{p.parent.name}/{p.name}") for p in paths]
    if only:
        sessions = [
            s
            for s in sessions
            if fnmatch.fnmatch(s.path.name, only) or fnmatch.fnmatch(s.key, only)
        ]
    return sessions


@dataclass
class Verdict:
    session: Session
    name: str | None = None
    date: str | None = None
    size: int = 0
    gz_size: int = 0
    sha256: str = ""
    games: int | None = None
    cards: int | None = None
    passed: list[str] = field(default_factory=list)
    #: Offending values (printed masked).
    findings: list[Finding] = field(default_factory=list)
    #: Failures that carry no value: a signal difference, a re-scrub change.
    problems: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    #: Name pieces too short to search (listed in ``skipped`` by class).
    short: int = 0
    redactions: Counter[str] = field(default_factory=Counter)
    staged: Path | None = None
    #: Why it isn't exported though it passed (already in the corpus).
    note: str | None = None

    @property
    def ok(self) -> bool:
        return not self.findings and not self.problems

    @property
    def failed(self) -> list[str]:
        return [c for c in CHECKS if c not in self.passed]


@dataclass
class Exporter:
    scrubber: Scrubber
    #: A private (mode 700) folder for the staged files.
    work: Path
    signal_report: SignalReport | None = None
    machine: MachineFacts = field(default_factory=MachineFacts)
    denylist: Sequence[Term] = ()
    #: Identifiers harvested from other sessions (of this run and every one
    #: exported before): each session is checked against all of them.
    pool: list[Term] = field(default_factory=list)

    def harvest(self, session: Session) -> Harvest:
        return harvest(_read(session), self.machine)

    def process(
        self, session: Session, taken: set[str], own: Harvest | None = None
    ) -> Verdict:
        v = Verdict(session)
        try:
            raw = _read(session)
            final, v.redactions = second_pass(self.scrubber(raw))
        except (OSError, UnicodeDecodeError, RuntimeError) as exc:
            v.problems.append(f"scrub: {type(exc).__name__}: {exc}")
            return v
        data = final.encode()
        v.size, v.sha256 = len(data), hashlib.sha256(data).hexdigest()
        try:
            start = naming.session_start(final, session.path.name)
        except ValueError as exc:
            v.problems.append(f"name: {exc}")
            return v
        v.date = f"{start:%Y-%m-%d}"
        base = naming.base_name(start, naming.suffix_of(naming.match_events(final)))
        v.name = naming.unique_name(base, taken)
        taken.add(v.name)

        h = own or harvest(raw, self.machine)
        v.skipped, v.short = list(h.skipped), h.short
        if h.short:
            v.skipped.append(
                f"{h.short} name piece(s) under 4 characters not searched alone"
            )
        terms = Harvest()
        terms.merge(h.terms)
        terms.merge(self.pool)
        self._check(v, "harvest", check_terms(final, terms.terms, "harvest"))
        self._check(v, "patterns", check_patterns(final))
        self._check(
            v, "user-denylist", check_terms(final, self.denylist, "user-denylist")
        )
        self._check(v, "fields", check_fields(final))
        plain = self.work / v.name.removesuffix(".gz")
        plain.write_bytes(data)
        try:
            self._signal(v, session.path, plain)
        finally:
            plain.unlink()
        try:
            unchanged = self.scrubber(final) == final
        except RuntimeError as exc:
            unchanged = False
            v.problems.append(f"rescrub: {type(exc).__name__}: {exc}")
        if unchanged:
            v.passed.append("rescrub")
        elif not any(p.startswith("rescrub") for p in v.problems):
            v.problems.append("rescrub: the scrubber would still change this file")
        packed = gzip.compress(data, mtime=0)
        v.gz_size = len(packed)
        if v.gz_size <= MAX_GZ_BYTES:
            v.passed.append("size")
        else:
            v.problems.append(f"size: {v.gz_size:,} bytes gzipped, over 10 MiB")
        if naming.CORPUS_NAME.match(v.name) and session.path.parent.name not in v.name:
            v.passed.append("name")
        else:
            v.problems.append("name: breaks the corpus's naming rule")
        if v.ok:
            v.staged = self.work / v.name
            v.staged.write_bytes(packed)
        return v

    @staticmethod
    def _check(v: Verdict, name: str, findings: list[Finding]) -> None:
        if findings:
            v.findings += findings
        else:
            v.passed.append(name)

    def _signal(self, v: Verdict, raw: Path, scrubbed: Path) -> None:
        if self.signal_report is None:
            v.skipped.append("signal check skipped (--skip-signal-check)")
            return
        before, after = self.signal_report(raw), self.signal_report(scrubbed)
        v.games = after.get("games")
        v.cards = len(
            {
                r.get("card")
                for r in (*after.get("resolutions", ()), *after.get("triggers", ()))
            }
            - {None}
        )
        if _canon(before) == _canon(after):
            v.passed.append("signal")
            return
        v.problems.append(
            "signal: arena-crosscheck reads the scrubbed log differently "
            f"(games {before.get('games')} -> {after.get('games')}, "
            f"resolutions {len(before.get('resolutions', ()))} -> "
            f"{len(after.get('resolutions', ()))}, triggers "
            f"{len(before.get('triggers', ()))} -> {len(after.get('triggers', ()))})"
        )


def _read(session: Session) -> str:
    return gzip.decompress(session.path.read_bytes()).decode("utf-8")


def _canon(report: dict) -> str:
    return json.dumps(report, sort_keys=True, default=str)


@dataclass
class Outcome:
    verdicts: list[Verdict]
    #: Sessions the state file says are already exported.
    already: int = 0
    written: list[str] = field(default_factory=list)
    commit: str | None = None

    @property
    def failed(self) -> list[Verdict]:
        return [v for v in self.verdicts if not v.ok]


def export(
    sessions: Sequence[Session],
    exporter: Exporter,
    corpus: Path,
    state: State,
    *,
    dry_run: bool = False,
    keep_going: bool = False,
    do_commit: bool = False,
) -> Outcome:
    """Scrub and check every session not yet exported; unless ``dry_run``, write
    the passing ones into ``corpus`` (all of them only when every one passed,
    or with ``keep_going``), record them in ``state``, and commit if asked."""
    entries = manifest_entries(corpus)
    taken = {p.name for p in (corpus / "corpus").glob("*.log.gz")}
    taken |= {f"{e.filename}.gz" for e in entries}
    known = {e.sha256: e.filename for e in entries}
    if do_commit and not dry_run:
        check_commit_identity(corpus)  # before anything is written
    todo = [s for s in sessions if s.key not in state.exported]
    out = Outcome([], already=len(sessions) - len(todo))
    # the pooled harvest: every session is checked against every other's names
    harvests = {}
    for session in todo:
        try:
            harvests[session.key] = exporter.harvest(session)
        except (OSError, UnicodeDecodeError):
            continue  # process() reports the unreadable file
        exporter.pool += harvests[session.key].terms
    for session in todo:
        v = exporter.process(session, taken, harvests.get(session.key))
        if v.ok and v.sha256 in known:
            v.note = f"already in the corpus as {known[v.sha256]}"
        out.verdicts.append(v)
    if dry_run or (out.failed and not keep_going):
        return out
    new = []
    for v in out.verdicts:
        if not v.ok or v.note or v.staged is None or v.name is None:
            continue
        shutil.copyfile(v.staged, corpus / "corpus" / v.name)
        new.append(
            ManifestEntry(v.name.removesuffix(".gz"), v.sha256, v.size, v.date or "")
        )
        state.exported[v.session.key] = {"name": v.name, "sha256": v.sha256}
        out.written.append(v.name)
    if new:
        append_manifest(corpus, new)
        state.save()
        if do_commit:
            names = [e.filename for e in new]
            files = [f"corpus/{f}" for f in out.written] + [MANIFEST]
            out.commit = commit(corpus, files, export_message(names))
    return out


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f}M"


def render(out: Outcome, *, dry_run: bool) -> str:
    """The per-file table (offending values masked) and a summary."""
    w = max([len(v.name or "-") for v in out.verdicts] + [7])
    lines = [
        (
            f"{'source':16} {'session':{w}} {'date':10} {'size':>6} {'gz':>5} "
            f"{'games':>5} {'cards':>5} {'short':>5}  verdict"
        )
    ]
    for v in out.verdicts:
        verdict = (
            f"PASS ({len(v.passed)}/{len(CHECKS)})"
            if v.ok
            else "FAIL: " + ", ".join(v.failed)
        )
        if v.note:
            verdict += f" — {v.note}, not written"
        lines.append(
            f"{v.session.label:16} {v.name or '-':{w}} {v.date or '-':10} "
            f"{_mb(v.size):>6} {_mb(v.gz_size):>5} "
            f"{'-' if v.games is None else v.games:>5} "
            f"{'-' if v.cards is None else v.cards:>5} {v.short:>5}  {verdict}"
        )
        lines += [f"    ! {f}" for f in v.findings]
        lines += [f"    ! {p}" for p in v.problems]
        lines += [
            f"    second pass: {n}x {reason}" for reason, n in v.redactions.items()
        ]
        lines += [f"    skipped: {s}" for s in v.skipped]
    passed = sum(v.ok for v in out.verdicts)
    lines.append("")
    lines.append(
        f"{len(out.verdicts)} session(s) checked: {passed} pass, "
        f"{len(out.failed)} fail; {out.already} already exported (state file)."
    )
    if dry_run:
        lines.append("Dry run: nothing written to the corpus.")
    elif out.failed and not out.written:
        lines.append("Nothing written: a session failed (--keep-going writes the rest)")
    else:
        lines.append(f"Wrote {len(out.written)} file(s) to the corpus.")
        if out.commit:
            lines.append(f"Committed {out.commit} locally; not pushed.")
    return "\n".join(lines) + "\n"


def verify_file(
    path: Path,
    machine: MachineFacts,
    denylist: Sequence[Term],
    pool: Sequence[Term] = (),
) -> tuple[int, list[Finding]]:
    """The checks that need no raw text, on an already published file: patterns,
    fields, the denylist, this machine's names and the pooled harvest."""
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    text = data.decode("utf-8", errors="replace")
    findings = check_patterns(text) + check_fields(text)
    findings += check_terms(text, denylist, "user-denylist")
    findings += check_terms(text, machine_terms(machine), "machine")
    findings += check_terms(text, pool, "pool")
    return len(data), findings


def render_verify(results: Sequence[tuple[Path, int, list[Finding]]]) -> str:
    lines = []
    for path, size, findings in results:
        status = "clean" if not findings else f"{len(findings)} finding(s)"
        lines.append(f"{path.name:60} {_mb(size):>6}  {status}")
        lines += [f"    ! {f}" for f in findings]
    dirty = sum(bool(f) for _, _, f in results)
    lines.append("")
    lines.append(f"{len(results)} file(s) verified: {dirty} with findings.")
    return "\n".join(lines) + "\n"
