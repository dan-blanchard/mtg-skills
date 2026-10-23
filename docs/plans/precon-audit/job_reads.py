"""Measure the job-quality reads (``mtg_utils._analysis.job_quality``) against
play-rate and the 25 precon upgrade guides (docs/plans/precon-audit-2026-10-18.md,
eighth pass).

    cd mtg-utils && uv run python ../docs/plans/precon-audit/job_reads.py ROOT [JOB ...]

ROOT holds decks/<Name>/deck.json and articles/<Name>.md (may be a symlink to this
directory). JOB is one of the read's jobs (interaction, protection, ramp,
card_draw, board_wipe); default all. For each job, over the commander-legal nonland
cards the read scores: Spearman of the score against -log10(EDHREC rank); the
guides' adds the read scores, as a percentile among the cards of their deck's
color identity, by score and by play-rate; and in each precon the deck's scored
cards ordered by score, how many of the bottom two are guide cuts, against
play-rate and mana value. Play-rate is the yardstick only.
"""
import bisect, json, math, pathlib, re, statistics, sys

from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils._analysis.job_quality import READS, job_score
from mtg_utils.card_pool import CardPool


def norm(n):
    n = n.split("//")[0].strip().strip("*").strip()
    return re.sub(r"\s+", " ", n).lower()


def parse_table(md, header):
    rows = {}
    sec = md.split(f"## {header}", 1)
    if len(sec) < 2:
        return rows
    for line in sec[1].split("\n## ", 1)[0].splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| card"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3:
            for name in re.split(r"\s*(?:;|/(?!/))\s*", cells[0]):
                if name.strip():
                    rows[norm(name.strip())] = name.strip()
    return rows


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0] * len(v)
        for r, i in enumerate(order):
            out[i] = r
        return out
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs); mx = sum(rx) / n; my = sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return cov / ((sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5)


def main(root, jobs):
    pool = CardPool.load(None)
    cards = {}
    for rec in pool.by_name.values():
        if (rec.get("legalities") or {}).get("commander") != "legal" or not rec.get("edhrec_rank"):
            continue
        if "Land" in (rec.get("type_line") or "").split("//")[0]:
            continue
        cards[rec["name"]] = rec
    decks = sorted((root / "decks").iterdir())
    for job in jobs:
        scored = {n: s for n, r in cards.items() if (s := job_score(r, job)) is not None}
        play = {n: -math.log10(cards[n]["edhrec_rank"]) for n in scored}
        names = list(scored)
        print(f"== {job}: {len(names)} cards scored, Spearman vs play-rate "
              f"{spearman([scored[n] for n in names], [play[n] for n in names]):.3f}")
        pct = {"score": [], "play-rate": []}; hits = {"score": 0, "play-rate": 0, "mana value": 0}; ncut = nmem = 0
        for d in decks:
            md = (root / "articles" / f"{d.name}.md").read_text()
            cuts, adds = parse_table(md, "Recommended cuts"), parse_table(md, "Recommended adds")
            deck = json.load(open(d / "deck.json"))
            colors = set()
            for e in deck["commanders"]:
                colors |= set(pool.by_name[e["name"]].get("color_identity") or [])
            mem = [c["name"] for c in deck["cards"] if c["name"] in scored]
            if len(mem) >= 3:
                nmem += len(mem); ncut += sum(norm(m) in cuts for m in mem)
                for label, key in (("score", scored.get), ("play-rate", play.get),
                                   ("mana value", lambda m: -effective_mana_value(cards[m]))):
                    hits[label] += sum(norm(m) in cuts for m in sorted(mem, key=key)[:2])
            ident = [n for n in names if set(cards[n].get("color_identity") or []) <= colors]
            by_score = sorted(scored[n] for n in ident); by_play = sorted(play[n] for n in ident)
            for name in adds.values():
                if name in scored and name in ident:
                    pct["score"].append(bisect.bisect_left(by_score, scored[name]) / len(by_score))
                    pct["play-rate"].append(bisect.bisect_left(by_play, play[name]) / len(by_play))
        for k, v in pct.items():
            if v:
                print(f"   guide adds by {k}: n={len(v)} median percentile {statistics.median(v):.2f}, "
                      f"top decile {sum(x >= 0.9 for x in v) / len(v):.2f}")
        print(f"   cut side: {ncut} guide cuts among {nmem} deck members; bottom-2 hits {hits}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), sys.argv[2:] or sorted(READS))
