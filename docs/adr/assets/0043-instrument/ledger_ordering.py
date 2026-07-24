"""Ledger ordering score — the within-class instrument (Rate v2.1 acceptance).

Derived entirely from the frozen verdict ledger (no new adjudication cost,
no invented absolutes): over each panel deck and each pair-row class that
contains at least one adjudicated SURVIVOR and one adjudicated KILL among
the deck's ranked pool candidates, the fraction of (survivor, kill) pairs
the production sort orders correctly (survivor above kill). Closes the
protocol blindness iteration-4 exposed: recall/drift cannot see
within-class reordering; this can.

Usage:
  MTG_STUDY_POOLS=<pools> uv run python ledger_ordering.py <label>
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import COMMANDERS, POOLS, sort_key  # noqa: E402

DUR = Path(__file__).parent
PANEL_SLUGS = {
    "krenko-mob-boss", "teysa-karlov", "talrand-sky-summoner", "the-ur-dragon",
    "zaxara-the-exemplary", "sythis-harvests-hand", "urza-lord-high-artificer",
    "muldrotha-the-gravetide", "isshin-two-heavens-as-one", "niv-mizzet-parun",
}


def norm(n: str) -> str:
    return n.split(" // ")[0].strip().casefold()


def score(pools_dir: Path | None = None) -> dict:
    pools = pools_dir or POOLS
    ledger = json.loads((DUR / "verdict-ledger.json").read_text())
    per_class: list[dict] = []
    for _, slug in COMMANDERS:
        if slug not in PANEL_SLUGS:
            continue
        rows = [
            json.loads(x)
            for x in (pools / f"{slug}.jsonl").read_text().splitlines()
        ]
        rows.sort(key=sort_key)
        rank = {norm(r["name"]): i for i, r in enumerate(rows)}
        pairs_of = {norm(r["name"]): set(r.get("pairs") or []) for r in rows}
        verdicts = {}
        for key, v in ledger.items():
            s, card = key.split("||", 1)
            if s == slug and card in rank:
                verdicts[card] = v["survives"]
        by_class: dict[str, list[str]] = {}
        for card in verdicts:
            for pid in pairs_of.get(card) or ():
                by_class.setdefault(pid, []).append(card)
        for pid, cards in sorted(by_class.items()):
            surv = [c for c in cards if verdicts[c]]
            kill = [c for c in cards if not verdicts[c]]
            if not surv or not kill:
                continue
            good = sum(1 for s_ in surv for k in kill if rank[s_] < rank[k])
            per_class.append(
                {
                    "slug": slug,
                    "row": pid,
                    "n_surv": len(surv),
                    "n_kill": len(kill),
                    "pairs": len(surv) * len(kill),
                    "correct": good,
                }
            )
    total_pairs = sum(c["pairs"] for c in per_class)
    total_good = sum(c["correct"] for c in per_class)
    return {
        "classes": per_class,
        "total_pairs": total_pairs,
        "correct": total_good,
        "ordering_score": total_good / total_pairs if total_pairs else None,
    }


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "unlabeled"
    res = score()
    print(f"== ledger ordering score [{label}] ==")
    for c in res["classes"]:
        print(
            f"  {c['slug']:28} {c['row']:40} "
            f"{c['correct']}/{c['pairs']} (S{c['n_surv']}/K{c['n_kill']})"
        )
    print(
        f"TOTAL: {res['correct']}/{res['total_pairs']} = "
        f"{res['ordering_score']:.3f}" if res["total_pairs"] else "TOTAL: n/a"
    )
    out = DUR / "ordering-scores.jsonl"
    with out.open("a") as f:
        f.write(
            json.dumps(
                {
                    "label": label,
                    "ordering_score": res["ordering_score"],
                    "total_pairs": res["total_pairs"],
                    "correct": res["correct"],
                }
            )
            + "\n"
        )
    print(f"recorded -> {out}")
