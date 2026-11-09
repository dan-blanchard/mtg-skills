"""``arena-crosscheck``: MTG Arena's game logs against phase's parse (ADR-0064).

Arena's rules engine logs what every spell and ability did. This reads those logs
(the archive under ``/Users/Shared/mtg-arena-logs`` plus your live ``Player.log`` /
``Player-prev.log``, or the files given), pairs each resolution and fired trigger with
phase's parse of the same ability, and reports where they disagree. A developer audit:
it needs logs and Arena's card database, so it never runs in CI. Every finding is a
lead to check with ``/rules-lawyer`` before it is called a misparse.

    arena-crosscheck                      # archive + live logs, markdown summary
    arena-crosscheck --json out.json      # also the full report
    arena-crosscheck --no-save-report     # skip <archive>/reports/<PHASE_TAG>.json
    arena-crosscheck game1.log game2.log.gz --no-archive --no-live
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mtg_utils._arena_crosscheck.check import Checker, crosscheck, load_ignores
from mtg_utils._arena_crosscheck.report import (
    ARCHIVE,
    render_markdown,
    report_path,
    write_report,
)
from mtg_utils._phase import PHASE_TAG
from mtg_utils.arena_card_db import CardText, find_card_db, player_log_path


def log_paths(given: list[Path], archive: Path | None, *, live: bool) -> list[Path]:
    """The logs to read: those given, the archive's (oldest first), then the live
    pair. A game in more than one is read once."""
    paths = list(given)
    if archive is not None and archive.is_dir():
        paths += sorted(archive.glob("*/*.log.gz"), key=lambda p: p.name)
    log = player_log_path()
    if live and log is not None:
        paths += [p for p in (log.with_name("Player-prev.log"), log) if p.is_file()]
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arena-crosscheck", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "logs", nargs="*", type=Path, help="Player.log files (.log or .log.gz)"
    )
    parser.add_argument(
        "--archive", type=Path, default=ARCHIVE, help=f"log archive (default {ARCHIVE})"
    )
    parser.add_argument(
        "--no-archive", action="store_true", help="don't read the archive"
    )
    parser.add_argument(
        "--no-live", action="store_true", help="don't read this account's live logs"
    )
    parser.add_argument(
        "--card-db", type=Path, help="Arena's Raw_CardDatabase (default: found)"
    )
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument(
        "--no-save-report",
        action="store_true",
        help="don't save it as <archive>/reports/<PHASE_TAG>.json (the regression "
        "baseline; saved whenever the archive exists)",
    )
    args = parser.parse_args(argv)

    db = args.card_db or find_card_db()
    if db is None:
        parser.error("no Arena card database found; pass --card-db")
    paths = log_paths(
        args.logs,
        None if args.no_archive else args.archive,
        live=not args.no_live,
    )
    if not paths:
        parser.error("no logs to read")
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils.card_pool import CardPool

    pool = CardPool.load(None)
    checker = Checker(CardText(db), pool.by_name.get, trees_for, load_ignores())
    report = crosscheck(paths, checker, PHASE_TAG)
    sys.stdout.write(render_markdown(report))
    if args.json:
        write_report(report, args.json)
    if not args.no_save_report and args.archive.is_dir():
        print(f"\nSaved {write_report(report, report_path(args.archive, PHASE_TAG))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
