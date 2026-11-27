"""``arena-log-export``: archived MTG Arena logs, sanitized for a public log corpus
(ADR-0067).

Each archived session (``/Users/Shared/mtg-arena-logs/<account>/*.log.gz``, read
only) goes through the Manasight scrubber the corpus itself uses, then a second
pass for what it misses (the login line's display name, the Steam ID, any
``Name#12345``), then fail-closed checks: every identifier harvested from the
session's own raw text and this machine's names gone, no handle / email / JWT /
home path / Steam ID left, the owner's denylist, every name field the
placeholder, ``arena-crosscheck`` reading the same games, the scrubber leaving
the file unchanged. Passing files are gzipped into the corpus clone's
``corpus/`` and added to its manifest. A developer tool that reads private
data: never run in CI.

    arena-log-export --install-scrub                  # once: cargo install the scrubber
    arena-log-export --corpus ~/clone --dry-run       # scrub + verify, write nothing
    arena-log-export --corpus ~/clone --commit        # write + one local commit
    arena-log-export --verify-only ~/clone/corpus     # check already published files

This tool never pushes: publishing is a separate, deliberate `git push` from the
corpus clone, and a pull request on the corpus's own site.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from mtg_utils._arena_corpus.corpus import (
    CommitRefusedError,
    State,
    check_commit_identity,
    check_corpus,
    load_pool,
    private_dir,
    save_pool,
)
from mtg_utils._arena_corpus.export import (
    Exporter,
    SignalReport,
    export,
    find_sessions,
    render,
    render_verify,
    verify_file,
)
from mtg_utils._arena_corpus.inherited import render as render_inherited
from mtg_utils._arena_corpus.inherited import resanitize
from mtg_utils._arena_corpus.scrub import (
    ScrubError,
    binary_scrubber,
    file_sha256,
    find_scrub,
    install_scrub,
    is_pinned,
)
from mtg_utils._arena_corpus.verify import (
    MachineFacts,
    SelfTestError,
    load_denylist,
    self_test,
)
from mtg_utils._arena_crosscheck.report import ARCHIVE

#: Where the private files live: the state file, the denylist, staging.
PRIVATE = Path.home() / "mtg" / "arena-log-corpus" / "private"


def _signal_report() -> SignalReport:
    """``arena-crosscheck``'s report for one log file (its Python API)."""
    from mtg_utils._arena_crosscheck.check import checker_for, crosscheck
    from mtg_utils._phase import PHASE_TAG
    from mtg_utils.arena_card_db import CardText, find_card_db
    from mtg_utils.card_pool import CardPool

    db = find_card_db()
    if db is None:
        raise SystemExit(
            "no Arena card database found for the signal check "
            "(set MTG_SKILLS_ARENA_CARD_DB, or pass --skip-signal-check)"
        )
    checker = checker_for(CardText(db), CardPool.load(None))
    return lambda path: crosscheck([path], checker, PHASE_TAG)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arena-log-export",
        description=__doc__.split("\n\n")[0],
        epilog="Never pushes: publishing is a separate, deliberate git push from "
        "the corpus clone.",
    )
    parser.add_argument(
        "--corpus", type=Path, help="the local clone of the corpus fork"
    )
    parser.add_argument(
        "--archive", type=Path, default=ARCHIVE, help=f"log archive (default {ARCHIVE})"
    )
    parser.add_argument(
        "--only", help="only sessions whose archive file (or <account>/<file>) matches"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scrub and verify into a private temp folder; write nothing",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="write the sessions that pass even when another fails, and exit 0 "
        "(a failing file is never written)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="make one local, UNSIGNED git commit in the corpus clone, refused "
        "unless the clone's author is a <id>+<login>@users.noreply.github.com "
        "address (a signature would tie the corpus to a key whose identity this "
        "tool cannot vet); never pushes",
    )
    parser.add_argument(
        "--resanitize-inherited",
        action="store_true",
        help="re-scrub the corpus's own corpus/*.log.gz with the pinned scrubber "
        "and the second pass, check them, and rewrite the ones that change "
        "(with their manifest rows)",
    )
    parser.add_argument(
        "--skip-signal-check",
        action="store_true",
        help="don't compare arena-crosscheck's report on the raw and scrubbed logs",
    )
    parser.add_argument("--scrub-bin", type=Path, help="the scrub binary to use")
    parser.add_argument(
        "--install-scrub",
        action="store_true",
        help="cargo install the pinned manasight-parser scrub, then exit",
    )
    parser.add_argument(
        "--verify-only",
        type=Path,
        metavar="DIR",
        help="check the *.log.gz / *.log files in DIR (patterns, name fields, "
        "denylist, this machine's names) and exit",
    )
    parser.add_argument(
        "--private-dir",
        type=Path,
        default=PRIVATE,
        help=f"state file, denylist, pooled harvest and staging (mode 700, outside "
        f"the corpus clone; default {PRIVATE})",
    )
    args = parser.parse_args(argv)

    if args.install_scrub:
        try:
            print(f"Installed {install_scrub()}")
        except ScrubError as exc:
            parser.error(str(exc))
        return 0

    if args.corpus is not None:
        clone = args.corpus.resolve()
        mine = args.private_dir.expanduser().resolve()
        if mine == clone or clone in mine.parents:
            parser.error(
                f"--private-dir {mine} is inside the corpus clone: its state file "
                "names the account and must never be committed"
            )
    private = private_dir(args.private_dir)
    deny_path = private / "denylist.txt"
    denylist = load_denylist(deny_path)
    if deny_path.is_file():
        print(f"denylist: {deny_path} ({len(denylist)} term(s))", file=sys.stderr)
    else:
        print(f"denylist: none (no {deny_path})", file=sys.stderr)
    machine = MachineFacts.read()
    if args.verify_only:
        files = sorted(
            [*args.verify_only.glob("*.log.gz"), *args.verify_only.glob("*.log")]
        )
        pool = load_pool(private)
        print(f"pooled harvest: {len(pool)} identifier(s)", file=sys.stderr)
        results = [(p, *verify_file(p, machine, denylist, pool)) for p in files]
        sys.stdout.write(render_verify(results))
        return 1 if any(f for _, _, f in results) else 0

    if args.corpus is None:
        parser.error("--corpus is required (or --install-scrub / --verify-only)")
    no_denylist = (
        ""
        if deny_path.is_file()
        else ("no user denylist: only harvested names are searched\n")
    )
    try:
        check_corpus(args.corpus)
        binary = find_scrub(args.scrub_bin)
        if not is_pinned(binary):
            print(
                f"WARNING: {binary} is not the scrub --install-scrub built "
                f"(sha256 {file_sha256(binary)[:12]}…); trusting it only if it "
                "passes the self-test",
                file=sys.stderr,
            )
        scrubber = binary_scrubber(binary)
        self_test(scrubber)  # every run: cheap, and it catches a broken scrub
    except (ValueError, ScrubError, SelfTestError) as exc:
        parser.error(str(exc))
    if args.dry_run and args.commit:
        parser.error("--dry-run writes nothing, so there is nothing to --commit")
    if args.commit:
        try:
            who = check_commit_identity(args.corpus)
        except CommitRefusedError as exc:
            parser.error(str(exc))
        print(f"commits will be authored as {who}, unsigned", file=sys.stderr)
    signal = None if args.skip_signal_check else _signal_report()
    if args.resanitize_inherited:
        with tempfile.TemporaryDirectory(dir=private, prefix="staging-") as work:
            try:
                redo = resanitize(
                    args.corpus,
                    scrubber,
                    Path(work),
                    signal_report=signal,
                    machine=machine,
                    denylist=denylist,
                    dry_run=args.dry_run,
                    keep_going=args.keep_going,
                    do_commit=args.commit,
                    progress=lambda line: print(line, file=sys.stderr, flush=True),
                )
            except CommitRefusedError as exc:
                parser.error(str(exc))
        sys.stdout.write(render_inherited(redo, dry_run=args.dry_run) + no_denylist)
        return 1 if redo.failed and not args.keep_going else 0
    sessions = find_sessions(args.archive, args.only)
    if not sessions:
        parser.error(f"no archived sessions in {args.archive}")
    state = State.load(private / "exported.json")
    pool = load_pool(private)
    with tempfile.TemporaryDirectory(dir=private, prefix="staging-") as work:
        exporter = Exporter(scrubber, Path(work), signal, machine, denylist, pool)
        try:
            out = export(
                sessions,
                exporter,
                args.corpus,
                state,
                dry_run=args.dry_run,
                keep_going=args.keep_going,
                do_commit=args.commit,
            )
        except CommitRefusedError as exc:
            parser.error(str(exc))
    if out.written:
        save_pool(private, exporter.pool)
    sys.stdout.write(render(out, dry_run=args.dry_run) + no_denylist)
    return 1 if out.failed and not args.keep_going else 0


if __name__ == "__main__":
    sys.exit(main())
