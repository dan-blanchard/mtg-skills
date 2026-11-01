"""Fit and measure a theme-STRENGTH read (``THEME_WEIGHTS``) on two pair sources
the tuner's order did not choose (the 2026-10-31 night grilling).

    cd mtg-utils && uv run python ../docs/plans/precon-audit/strength_fit_noncreature.py \
        [--type noncreature_permanent|spell] [--features a,b,...] [--set existing|theme]

* **A** (``~/mtg/tuner-work/w41/pairs-cuts.json``): a guide's add against that same
  guide's cut of the same card type; each pair weighs its ``weight`` (the guides
  naming the add).
* **B** (``~/mtg/tuner-work/w41/pairs-live.json``, ``theme_pairs.py`` over the LIVE
  play-rate order's page dumps): a guide add against each on-plan non-guide card
  the live order put above it on the same theme page; weighted as
  ``quality_fit_noncreature.load_pairs`` does (each guide add once per guide).

Each source is normalised to total weight 1 before an A∪B fit, so neither
dominates. Every accuracy is leave-one-deck-out (the deck's pairs, in both
sources, are out of the fit that scores them): fitted on A, B or A∪B, scored on A
and on B, so the off-diagonal cells are the cross-source check. The baselines are
play-rate (the lower EDHREC rank preferred, unranked worst) and mana value on the
same pairs; a tie or an unread card counts half. Play-rate and price are never
features.

``--set existing`` fits the module's live ``features`` (the ADR-0063 job-blend
read); ``--set theme`` (the default) its ``THEME_READ``'s features. ``--fit``
picks the source the full fit (the weights to hand-round) is fitted on. The spell
read runs from ``strength_fit_spell.py``.

Output, noncreature permanents (2026-10-31 night). The job-blend features
refit (``--set existing``) fail source A::

    source A: 1757 pairs, 293 guide adds, 25 decks | play-rate 0.530  mana value 0.456
    source B: 6377 pairs, 129 guide adds, 22 decks | play-rate 0.000  mana value 0.450
    LODO l2=3.0   fit A -> A 0.451 B 0.474 | fit B -> A 0.475 B 0.534 | fit A+B -> A 0.473 B 0.532
    LODO l2=30.0  fit A -> A 0.458 B 0.510 | fit B -> A 0.496 B 0.574 | fit A+B -> A 0.475 B 0.544

so new features (forward selection over ~35 candidates read off the trees, then
cut to the legible ones; the 11 the selection kept reach A 0.682 / B 0.681)::

    feature        A:differs guide-higher | B:differs guide-higher
      abilities        0.68   0.48       |   0.68   0.37
      cheap            0.37   0.54       |   0.32   0.54
      damage           0.06   0.83       |   0.06   0.82
      library_top      0.25   0.19       |   0.19   0.25
      multiplier       0.09   0.92       |   0.14   0.53
      protection       0.15   0.72       |   0.12   0.49
      ramp             0.37   0.38       |   0.33   0.36
    LODO l2=1.0   fit A -> A 0.657 B 0.605 | fit B -> A 0.642 B 0.570 | fit A+B -> A 0.656 B 0.609
    LODO l2=3.0   fit A -> A 0.656 B 0.602 | fit B -> A 0.642 B 0.564 | fit A+B -> A 0.658 B 0.610
    LODO l2=10.0  fit A -> A 0.650 B 0.602 | fit B -> A 0.636 B 0.561 | fit A+B -> A 0.661 B 0.603
    LODO l2=30.0  fit A -> A 0.645 B 0.597 | fit B -> A 0.616 B 0.585 | fit A+B -> A 0.660 B 0.602
    A+B full fit (l2=3.0): weight (standardised = weight x sd)
      abilities      -0.18  (-0.19)
      cheap          +0.37  (+0.16)
      damage         +1.29  (+0.26)
      library_top    -1.30  (-0.39)
      multiplier     +0.65  (+0.13)
      protection     +0.44  (+0.07)
      ramp           -0.98  (-0.21)
    THEME_WEIGHTS in-sample on A: 0.677
    THEME_WEIGHTS in-sample on B: 0.630

Dropping the four decks with the most pairs (Planeswalker Party, Enduring
Enchantments, Animated Army, Virtue and Valor) the A+B fit still scores A 0.618 /
B 0.639. Every B guide add is also an A guide add (B's pairs differ only in the
other card), so the cross-source cells share the preferred side; and a card
recurs across decks (Parallel Lives in several), which leave-one-deck-out does
not hold out.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from quality_fit_noncreature import accuracy, load_pairs, logit_fit  # noqa: E402

from mtg_utils._analysis.card_quality import noncreature_permanent, spell  # noqa: E402
from mtg_utils.card_pool import CardPool  # noqa: E402

MODULES = {"noncreature_permanent": noncreature_permanent, "spell": spell}
WORK = pathlib.Path.home() / "mtg/tuner-work/w41"
L2S = (1.0, 3.0, 10.0, 30.0)
UNRANKED = 10**9


def load_sources(typ: str) -> dict[str, list[dict]]:
    a = json.loads((WORK / "pairs-cuts.json").read_text())[typ]
    for p in a:
        p["w"] = float(p["weight"])
    b = load_pairs(WORK / "pairs-live.json", typ)
    out = {"A": a, "B": b}
    for pairs in out.values():
        total = sum(p["w"] for p in pairs)
        for p in pairs:
            p["wn"] = p["w"] / total
    return out


def main(default_type: str | None = None, default_fit: str = "A+B") -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=sorted(MODULES), action="append")
    ap.add_argument("--features", help="comma-separated subset to fit")
    ap.add_argument("--set", choices=("existing", "theme"), default="theme")
    ap.add_argument("--l2", type=float, default=3.0, help="the L2 the full fit uses")
    ap.add_argument("--fit", choices=("A", "B", "A+B"), default=default_fit)
    ap.add_argument("--worst", type=int, default=10)
    args = ap.parse_args()
    pool = CardPool.load(None)
    for typ in args.type or [default_type or "noncreature_permanent"]:
        mod = MODULES[typ]
        theme = getattr(mod, "THEME_READ", None)
        featfn = (
            mod.features if args.set == "existing" or theme is None else theme.features
        )
        src = load_sources(typ)
        memo: dict[str, dict[str, float] | None] = {}

        def feats(name: str, memo=memo, featfn=featfn) -> dict[str, float] | None:
            if name not in memo:
                rec = pool.by_name.get(name)
                memo[name] = None if rec is None else featfn(rec)
            return memo[name]

        def rank(name: str) -> int:
            rec = pool.by_name.get(name) or {}
            return rec.get("edhrec_rank") or UNRANKED

        def cmc(name: str) -> float:
            return float((pool.by_name.get(name) or {}).get("cmc") or 0.0)

        names = {
            n for s in src.values() for p in s for n in (p["preferred"], p["other"])
        }
        unread = sorted(n for n in names if feats(n) is None)
        keys = sorted({k for n in names if (f := feats(n)) for k in f})
        if args.features:
            keys = args.features.split(",")
        print(f"===== {typ} ({args.set} features); unread {len(unread)}: {unread[:12]}")
        for s, pairs in src.items():
            decks = {p["deck"] for p in pairs}
            adds = {(p["deck"], p["preferred"]) for p in pairs}
            pr = accuracy(pairs, lambda n: -rank(n))
            mv = accuracy(pairs, lambda n: -cmc(n))
            print(
                f"source {s}: {len(pairs)} pairs, {len(adds)} guide adds, "
                f"{len(decks)} decks | play-rate {pr:.3f}  mana value {mv:.3f}"
            )
        print("feature        A:differs guide-higher | B:differs guide-higher")
        for k in keys:
            cells = []
            for pairs in src.values():
                tot = sum(p["w"] for p in pairs)
                cov = hi = 0.0
                for p in pairs:
                    a, b = feats(p["preferred"]), feats(p["other"])
                    if a is None or b is None or a.get(k, 0.0) == b.get(k, 0.0):
                        continue
                    cov += p["w"]
                    hi += p["w"] * (a.get(k, 0.0) > b.get(k, 0.0))
                cells.append(f"{cov / tot:6.2f} {hi / cov if cov else 0:6.2f}")
            print(f"  {k:14s} {cells[0]}       | {cells[1]}")

        def rows(sub: list[dict]) -> tuple[list[list[float]], list[float]]:
            x, w = [], []
            for p in sub:
                a, b = feats(p["preferred"]), feats(p["other"])
                if a is not None and b is not None:
                    x.append([a.get(k, 0.0) - b.get(k, 0.0) for k in keys])
                    w.append(p["wn"] * 1000)
            return x, w

        def scorer(beta):
            def score(name: str) -> float | None:
                f = feats(name)
                if f is None:
                    return None
                return sum(b * f.get(k, 0.0) for b, k in zip(beta, keys))

            return score

        decks = sorted({p["deck"] for s in src.values() for p in s})
        fits = {"A": ("A",), "B": ("B",), "A+B": ("A", "B")}
        for l2 in L2S:
            line = []
            for fname, train in fits.items():
                acc = {s: 0.0 for s in src}
                for dk in decks:
                    tr = [p for s in train for p in src[s] if p["deck"] != dk]
                    beta = logit_fit(*rows(tr), l2)
                    for s, pairs in src.items():
                        test = [p for p in pairs if p["deck"] == dk]
                        if test:
                            wt = sum(p["w"] for p in test)
                            acc[s] += accuracy(test, scorer(beta)) * wt
                tot = {s: sum(p["w"] for p in src[s]) for s in src}
                line.append(
                    f"fit {fname:3s} -> A {acc['A'] / tot['A']:.3f} B {acc['B'] / tot['B']:.3f}"
                )
            print(f"LODO l2={l2:<5} " + "  |  ".join(line))
        x, w = rows([p for s in fits[args.fit] for p in src[s]])
        beta = logit_fit(x, w, args.l2)
        sd = [
            statistics.pstdev([f.get(k, 0.0) for n in names if (f := feats(n))]) or 1.0
            for k in keys
        ]
        print(
            f"{args.fit} full fit (l2={args.l2}): weight (standardised = weight x sd)"
        )
        for k, b, s in zip(keys, beta, sd):
            print(f"  {k:14s} {b:+.2f}  ({b * s:+.2f})")
        shipped = getattr(mod, "THEME_WEIGHTS", None)
        if shipped and args.set == "theme":

            def ship(name: str) -> float | None:
                f = feats(name)
                return None if f is None else sum(shipped[k] * f[k] for k in shipped)

            for s, pairs in src.items():
                print(f"THEME_WEIGHTS in-sample on {s}: {accuracy(pairs, ship):.3f}")
            for s, pairs in src.items():
                fixes: collections.Counter = collections.Counter()
                wrong: collections.Counter = collections.Counter()
                for p in pairs:
                    a, b = ship(p["preferred"]), ship(p["other"])
                    if a is None or b is None:
                        continue
                    pr_wrong = rank(p["preferred"]) > rank(p["other"])
                    if a > b and pr_wrong:
                        fixes[
                            (p["preferred"], p["other"], round(a, 2), round(b, 2))
                        ] += p["w"]
                    if a <= b:
                        wrong[
                            (p["preferred"], p["other"], round(a, 2), round(b, 2))
                        ] += p["w"]
                print(f"[{s}] heaviest pairs play-rate gets wrong and the read right:")
                for (a, b, sa, sb), wt in fixes.most_common(args.worst):
                    print(f"  {a} ({sa}) > {b} ({sb})  w={wt:.2f}")
                print(f"[{s}] heaviest pairs the read still gets wrong:")
                for (a, b, sa, sb), wt in wrong.most_common(args.worst):
                    print(f"  {a} ({sa}) <= {b} ({sb})  w={wt:.2f}")


if __name__ == "__main__":
    main()
