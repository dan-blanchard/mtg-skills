"""Fit and measure the noncreature-permanent and spell quality reads
(``mtg_utils._analysis.card_quality.noncreature_permanent`` / ``.spell``, ADR-0063)
on the guide pairs ``theme_pairs.py`` writes.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/quality_fit_noncreature.py \
        [PAIRS.json] [--type noncreature_permanent|spell] [--features a,b,...] [--l2 X]

PAIRS defaults to ``~/mtg/tuner-work/w41/pairs.json``; each type reads only its own
key. A pair is (guide add, an on-plan card the tuner ranked above it). Each pair
weighs ``guides naming the add / pairs of that add in its deck`` — a guide add
counts once per guide, however deep it sat on its page (a consensus add repeats
each pair once per guide, so the guide count is a pair's repeat count).

For each type it prints the two baselines on the same pairs (play-rate: the lower
EDHREC rank preferred; mana value: the cheaper preferred; a tie counts half), each
feature's share of pairs where it differs and how often the guide add has the
higher value, the leave-one-deck-out cross-validated pair accuracy of an L2
logistic regression on feature differences (no intercept: a pair is symmetric)
for each L2 strength, the full-data fit's weights (to hand-round into the
module's ``WEIGHTS``), the shipped ``WEIGHTS``' in-sample accuracy, and the
heaviest pairs the shipped read still orders wrong. Random folds would leak: the
pairs of one deck share its guide add. Play-rate and price are never features.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib

from mtg_utils._analysis.card_quality import noncreature_permanent, spell
from mtg_utils.card_pool import CardPool

MODULES = {"noncreature_permanent": noncreature_permanent, "spell": spell}
L2S = (0.3, 1.0, 3.0, 10.0, 30.0)


def load_pairs(path: pathlib.Path, typ: str) -> list[dict]:
    pairs = json.loads(path.read_text())[typ]
    repeats = collections.Counter(json.dumps(p, sort_keys=True) for p in pairs)
    per_add = collections.Counter((p["deck"], p["preferred"]) for p in pairs)
    guides: dict[tuple[str, str], int] = {}
    for blob, n in repeats.items():
        p = json.loads(blob)
        key = (p["deck"], p["preferred"])
        guides[key] = max(guides.get(key, 0), n)
    for p in pairs:
        key = (p["deck"], p["preferred"])
        p["w"] = guides[key] / per_add[key]
    return pairs


def baseline(pairs: list[dict], key: str) -> float:
    tot = acc = 0.0
    for p in pairs:
        a, b = p["features"][p["preferred"]][key], p["features"][p["other"]][key]
        tot += p["w"]
        acc += p["w"] * (1.0 if a < b else 0.5 if a == b else 0.0)
    return acc / tot


def accuracy(pairs: list[dict], score) -> float:
    """Weighted pair accuracy; a tie or an unread card counts half."""
    tot = acc = 0.0
    for p in pairs:
        a, b = score(p["preferred"]), score(p["other"])
        tot += p["w"]
        if a is None or b is None or abs(a - b) < 1e-9:
            acc += 0.5 * p["w"]
        elif a > b:
            acc += p["w"]
    return acc / tot if tot else float("nan")


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        if abs(m[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def logit_fit(x: list[list[float]], w: list[float], l2: float) -> list[float]:
    """Weighted L2 logistic regression on difference rows (every label 1), by
    Newton's method."""
    d = len(x[0]) if x else 0
    beta = [0.0] * d
    for _ in range(50):
        grad = [-l2 * b for b in beta]
        hess = [[l2 if i == j else 0.0 for j in range(d)] for i in range(d)]
        for row, wt in zip(x, w):
            z = sum(b * v for b, v in zip(beta, row))
            p = 1 / (1 + math.exp(-max(min(z, 30.0), -30.0)))
            nz = [i for i, v in enumerate(row) if v]
            for i in nz:
                grad[i] += wt * (1 - p) * row[i]
                for j in nz:
                    hess[i][j] += wt * p * (1 - p) * row[i] * row[j]
        step = _solve(hess, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max((abs(s) for s in step), default=0.0) < 1e-7:
            break
    return beta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "pairs",
        nargs="?",
        default=pathlib.Path.home() / "mtg/tuner-work/w41/pairs.json",
        type=pathlib.Path,
    )
    ap.add_argument("--type", choices=sorted(MODULES), action="append")
    ap.add_argument("--features", help="comma-separated subset to fit")
    ap.add_argument("--l2", type=float, help="the L2 the full fit uses")
    ap.add_argument("--worst", type=int, default=8)
    args = ap.parse_args()
    pool = CardPool.load(None)
    for typ in args.type or sorted(MODULES):
        mod = MODULES[typ]
        pairs = load_pairs(args.pairs, typ)
        memo: dict[str, dict[str, float] | None] = {}

        def feats(name: str, mod=mod, memo=memo) -> dict[str, float] | None:
            if name not in memo:
                rec = pool.by_name.get(name)
                memo[name] = None if rec is None else mod.features(rec)
            return memo[name]

        names = {n for p in pairs for n in (p["preferred"], p["other"])}
        unread = sorted(n for n in names if feats(n) is None)
        keys = sorted({k for n in names if (f := feats(n)) for k in f})
        if args.features:
            keys = args.features.split(",")
        decks = sorted({p["deck"] for p in pairs})
        total_w = sum(p["w"] for p in pairs)
        print(
            f"===== {typ}: {len(pairs)} pairs, weight {total_w:.0f}, "
            f"{len({p['preferred'] for p in pairs})} guide adds, {len(decks)} decks; "
            f"unread {unread}"
        )
        print(
            f"baselines: play-rate {baseline(pairs, 'rank'):.3f}  "
            f"mana value {baseline(pairs, 'cmc'):.3f}"
        )
        print("feature        differs  guide-add higher")
        for k in keys:
            cov = hi = 0.0
            for p in pairs:
                a, b = feats(p["preferred"]), feats(p["other"])
                if a is None or b is None or a.get(k, 0.0) == b.get(k, 0.0):
                    continue
                cov += p["w"]
                hi += p["w"] * (a.get(k, 0.0) > b.get(k, 0.0))
            if cov:
                print(f"  {k:12s}  {cov / total_w:6.2f}  {hi / cov:6.2f}")

        def rows(sub: list[dict]) -> tuple[list[list[float]], list[float]]:
            x, w = [], []
            for p in sub:
                a, b = feats(p["preferred"]), feats(p["other"])
                if a is not None and b is not None:
                    x.append([a.get(k, 0.0) - b.get(k, 0.0) for k in keys])
                    w.append(p["w"])
            return x, w

        def scorer(beta, keys=keys, feats=feats):
            def score(name: str) -> float | None:
                f = feats(name)
                return (
                    None
                    if f is None
                    else sum(b * f.get(k, 0.0) for b, k in zip(beta, keys))
                )

            return score

        for l2 in L2S:
            acc = 0.0
            for dk in decks:
                test = [p for p in pairs if p["deck"] == dk]
                beta = logit_fit(*rows([p for p in pairs if p["deck"] != dk]), l2)
                acc += accuracy(test, scorer(beta)) * sum(p["w"] for p in test)
            print(f"LODO l2={l2:<5} {acc / total_w:.3f}")
        l2 = args.l2 if args.l2 is not None else 3.0
        beta = logit_fit(*rows(pairs), l2)
        print(f"full fit (l2={l2}), in-sample {accuracy(pairs, scorer(beta)):.3f}:")
        print("  " + ", ".join(f"{k} {b:+.2f}" for k, b in zip(keys, beta)))
        shipped = mod.READ.weights
        if shipped:

            def ship(name: str, mod=mod) -> float | None:
                rec = pool.by_name.get(name)
                return None if rec is None else mod.READ.score(rec)

            print(f"shipped WEIGHTS in-sample {accuracy(pairs, ship):.3f}")
            wrong: collections.Counter = collections.Counter()
            for p in pairs:
                a, b = ship(p["preferred"]), ship(p["other"])
                if a is not None and b is not None and a <= b:
                    wrong[(p["preferred"], p["other"], a, b)] += p["w"]
            print("heaviest wrong pairs (guide add, read above it, scores, weight):")
            for (a, b, sa, sb), wt in wrong.most_common(args.worst):
                print(f"  {a} ({sa}) < {b} ({sb})  w={wt:.2f}")


if __name__ == "__main__":
    main()
