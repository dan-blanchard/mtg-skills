"""The crosscheck report: rows, a summary, markdown, and the per-pin regression diff.

A report is saved per phase pin as ``<archive>/reports/<PHASE_TAG>.json``, so a run
under a new pin can list what its parse changed against the same logged games
(:func:`diff_reports`, :func:`render_changes`; ``bump-phase-pin``'s step 9).
Rows are keyed by game and their order in it, which the same logs reproduce exactly.
"""

from __future__ import annotations

import collections
import json
from collections.abc import Sequence
from pathlib import Path

__all__ = [
    "ARCHIVE",
    "build_report",
    "diff_reports",
    "load_report",
    "render_changes",
    "render_markdown",
    "report_path",
    "write_report",
]

#: Where the Arena logs are archived, one folder per account, with the reports.
ARCHIVE = Path("/Users/Shared/mtg-arena-logs")

#: Statuses that are findings to look at.
RESOLUTION_FINDINGS = ("arena-extra", "phase-extra")
TRIGGER_FINDINGS = ("mismatch",)


def _keyed(rows: Sequence[dict]) -> list[dict]:
    per_game: collections.Counter = collections.Counter()
    out = []
    for row in rows:
        game = tuple(row["game"])
        out.append({**row, "key": f"{game[0]}#{game[1]}#{per_game[game]}"})
        per_game[game] += 1
    return out


def build_report(
    resolutions: Sequence[dict],
    triggers: Sequence[dict],
    games: Sequence[tuple[str, int]],
    phase_tag: str,
) -> dict:
    resolutions, triggers = _keyed(resolutions), _keyed(triggers)
    checks: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for row in resolutions:
        if row["status"] == "ignored":
            continue  # an Arena mistake, checked and recorded
        for c in row.get("checks", ()):
            checks[c["check"]][0 if c["ok"] else 1] += 1
    return {
        "schema": 1,
        "phase_tag": phase_tag,
        "games": len(games),
        "summary": {
            "resolutions": dict(collections.Counter(r["status"] for r in resolutions)),
            "triggers": dict(collections.Counter(t["status"] for t in triggers)),
            "checks": {
                k: {"pass": v[0], "fail": v[1]} for k, v in sorted(checks.items())
            },
        },
        "resolutions": resolutions,
        "triggers": triggers,
    }


def _findings(report: dict) -> list[str]:
    lines = []
    for r in report["resolutions"]:
        if r["status"] == "ignored":
            continue
        failed = [c for c in r.get("checks", ()) if not c["ok"]]
        if r["status"] in RESOLUTION_FINDINGS or failed:
            what = (
                f"Arena did {r['unexplained']}"
                if r["status"] == "arena-extra"
                else f"phase predicts {r.get('unseen')} Arena didn't log"
                if r["status"] == "phase-extra"
                else ""
            )
            fails = "; ".join(
                f"{c['check']}: phase {c['expected']}, Arena {c['observed']}"
                for c in failed
            )
            lines.append(
                f"- **{r['card']}** ({r['kind']}): {r.get('arena_text') or '(spell)'} "
                f"— {'; '.join(x for x in (what, fails) if x)}"
            )
    for t in report["triggers"]:
        if t["status"] in TRIGGER_FINDINGS:
            lines.append(
                f"- **{t['card']}** trigger: {t['arena_text']} — phase watches "
                f"`{t['phase_event']}`, Arena logged {t['events']}"
            )
    return lines


def _counts(counts: dict[str, int]) -> list[str]:
    return [f"- {k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def render_markdown(report: dict) -> str:
    s = report["summary"]
    out = [
        f"# Arena crosscheck — phase {report['phase_tag']}, {report['games']} games",
        "",
        "## Resolutions",
        *_counts(s["resolutions"]),
        "",
        "## Strict checks",
        *(f"- {k}: {v['pass']} pass, {v['fail']} fail" for k, v in s["checks"].items()),
        "",
        "## Triggers",
        *_counts(s["triggers"]),
        "",
        "## Findings (check each with /rules-lawyer before calling it a misparse)",
        *(_findings(report) or ["- none"]),
    ]
    rows = (*report["resolutions"], *report["triggers"])
    unsure = [r for r in rows if r["status"] == "unsure-pairing"]
    if unsure:
        out += ["", "## Unsure pairings (not scored)"]
        out += [
            f"- **{r['card']}**: Arena `{r.get('arena_text')}` ~ phase "
            f"`{r.get('phase_text')}` ({r.get('pairing_score')})"
            for r in unsure
        ]
    rebalanced = sorted(
        {r["card"] for r in rows if "rebalanced" in r.get("warnings", ())}
    )
    if rebalanced:
        out += [
            "",
            "Rebalanced cards compared against the paper parse: "
            + ", ".join(rebalanced),
        ]
    return "\n".join(out) + "\n"


def write_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    return path


def report_path(archive: Path, phase_tag: str) -> Path:
    """Where the report for ``phase_tag`` is kept: the regression baseline."""
    return archive / "reports" / f"{phase_tag}.json"


def load_report(path: Path) -> dict:
    return json.loads(path.read_text())


def _verdict(row: dict) -> dict:
    failed = sorted(c["check"] for c in row.get("checks", ()) if not c["ok"])
    return {"status": row["status"], "failed": failed}


def diff_reports(old: dict, new: dict) -> list[dict]:
    """The rows whose verdict changed between two reports over the same games: a
    status that flipped, or checks that newly pass or fail."""
    changes = []
    for section in ("resolutions", "triggers"):
        before = {r["key"]: _verdict(r) for r in old.get(section, ())}
        for row in new.get(section, ()):
            prior, now = before.get(row["key"]), _verdict(row)
            if prior is None or prior == now:
                continue
            changes.append(
                {
                    "section": section,
                    "key": row["key"],
                    "card": row.get("card"),
                    "arena_text": row.get("arena_text"),
                    "before": prior,
                    "after": now,
                }
            )
    return changes


def _verdict_text(verdict: dict) -> str:
    failed = verdict["failed"]
    return verdict["status"] + (f" (failed: {', '.join(failed)})" if failed else "")


def render_changes(changes: Sequence[dict]) -> list[str]:
    """One markdown line per :func:`diff_reports` change, old verdict then new."""
    return [
        f"- **{c['card']}** ({c['section']}): {c.get('arena_text') or '(spell)'} — "
        f"{_verdict_text(c['before'])} → {_verdict_text(c['after'])}"
        for c in changes
    ]
