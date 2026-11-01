# /// script
# dependencies = ["numpy"]
# ///
"""Feature selection for the creature theme-strength read, and its honest
(nested) accuracy: ``strength_fit_creature.py``'s fit, vectorized.

    uv run docs/plans/precon-audit/strength_select_creature.py FEATS.json \\
        ~/mtg/tuner-work/w41/pairs-cuts.json ~/mtg/tuner-work/w41/pairs-live.json \\
        greedy | nested MAXK | keys k1,k2,...

FEATS.json is ``strength_fit_creature.py --cache``'s file (every candidate
feature per card). The pairs and weights are that script's (each source's
weights sum to one). Standardized features, L2 0.03, pairwise logistic
regression without intercept.

- ``greedy``: forward selection over every candidate, by the combined fit's
  leave-one-deck-out accuracy, the objective min(A - play-rate's 0.574, B - 0.5)
  plus their mean, stopping when a step adds under 0.002.
- ``nested MAXK``: the same selection (at most MAXK features) run inside the
  leave-one-deck-out loop, each held-out deck scored by the features chosen
  without it: the selection's own optimism taken out.
- ``keys``: one feature set's six accuracies (A->A, B->B, AB->A, AB->B, A->B,
  B->A).
"""

import collections
import json
import sys

import numpy as np

PLAY_RATE_A = 0.574  # play-rate's accuracy on source A (strength_fit_creature.py)


def weights_of(pairs):
    n = collections.Counter((p["deck"], p["preferred"]) for p in pairs)
    dup = collections.Counter(
        (p["deck"], p["avenue"], p["preferred"], p["other"], p["pos_other"])
        for p in pairs
    )
    g = collections.defaultdict(int)
    for k, v in dup.items():
        g[(k[0], k[2])] = max(g[(k[0], k[2])], v)
    return [
        g[(p["deck"], p["preferred"])] / n[(p["deck"], p["preferred"])] for p in pairs
    ]


feats = json.load(open(sys.argv[1]))["feats"]
a = json.load(open(sys.argv[2]))["creature"]
n = collections.Counter((p["deck"], p["preferred"]) for p in a)
wa = np.array([p["weight"] / n[(p["deck"], p["preferred"])] for p in a])
b = json.load(open(sys.argv[3]))["creature"]
wb = np.array(weights_of(b))
P = [(0, p["deck"], p["preferred"], p["other"]) for p in a] + [
    (1, p["deck"], p["preferred"], p["other"]) for p in b
]
src = np.array([p[0] for p in P])
W = np.concatenate([wa / wa.sum(), wb / wb.sum()])
decks = sorted({p[1] for p in P})
deck = np.array([decks.index(p[1]) for p in P])
names = sorted(n for n, f in feats.items() if f)
keys_all = sorted(next(iter(f for f in feats.values() if f)))
X = np.array([[feats[nm][k] for k in keys_all] for nm in names])
X = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1)
idx = {nm: i for i, nm in enumerate(names)}
D = X[[idx[p[2]] for p in P]] - X[[idx[p[3]] for p in P]]


def fit(dm, w, lam=0.03):
    beta = np.zeros(dm.shape[1])
    w = w / w.sum()
    for _ in range(30):
        pr = 1 / (1 + np.exp(-np.clip(dm @ beta, -30, 30)))
        g = dm.T @ (w * (1 - pr)) - lam * beta
        h = (dm * (w * pr * (1 - pr))[:, None]).T @ dm + lam * np.eye(len(beta))
        step = np.linalg.solve(h, g)
        beta += step
        if np.abs(step).max() < 1e-7:
            break
    return beta


def acc(z, w):
    return (w * ((z > 0) + 0.5 * (z == 0))).sum() / w.sum()


def lodo(cols, train_src, test_src, mask=None):
    dm = D[:, cols]
    right = tot = 0.0
    for d in range(len(decks)):
        if mask is not None and not mask[d]:
            continue
        tr = (deck != d) & np.isin(src, train_src)
        if mask is not None:
            tr &= mask[deck]
        te = (deck == d) & (src == test_src)
        if te.any():
            right += acc(dm[te] @ fit(dm[tr], W[tr]), W[te]) * W[te].sum()
            tot += W[te].sum()
    return right / tot


def greedy(mask=None, verbose=False, maxk=10):
    chosen, best = [], -1.0
    while len(chosen) < maxk:
        trial = {}
        for k in keys_all:
            if k not in chosen and not k.startswith("t_"):  # t_: the shipped set
                cols = [keys_all.index(c) for c in [*chosen, k]]
                ea = lodo(cols, [0, 1], 0, mask) - PLAY_RATE_A
                eb = lodo(cols, [0, 1], 1, mask) - 0.5
                trial[k] = (min(ea, eb) + (ea + eb) / 2, ea, eb)
        k, (s, ea, eb) = max(trial.items(), key=lambda kv: kv[1][0])
        if verbose:
            print(
                f"+{k:16s} obj {s:.4f}  A {ea + PLAY_RATE_A:.3f}  B {eb + 0.5:.3f}",
                flush=True,
            )
        if s <= best + 0.002:
            break
        chosen.append(k)
        best = s
    return chosen


def main(mode, arg):
    if mode == "greedy":
        print("chosen", greedy(verbose=True))
    elif mode == "nested":
        res = {0: [0.0, 0.0], 1: [0.0, 0.0]}
        for d in range(len(decks)):
            mask = np.ones(len(decks), bool)
            mask[d] = False
            chosen = greedy(mask=mask, maxk=int(arg))
            cols = [keys_all.index(c) for c in chosen]
            beta = fit(D[deck != d][:, cols], W[deck != d])
            for s in (0, 1):
                te = (deck == d) & (src == s)
                if te.any():
                    res[s][0] += acc(D[te][:, cols] @ beta, W[te]) * W[te].sum()
                    res[s][1] += W[te].sum()
            print(decks[d], chosen, flush=True)
        print(f"nested A {res[0][0] / res[0][1]:.3f} B {res[1][0] / res[1][1]:.3f}")
    elif mode == "keys":
        cols = [keys_all.index(c) for c in arg.split(",")]
        print(
            f"AB->A {lodo(cols, [0, 1], 0):.3f} AB->B {lodo(cols, [0, 1], 1):.3f} "
            f"A->A {lodo(cols, [0], 0):.3f} B->B {lodo(cols, [1], 1):.3f} "
            f"A->B {lodo(cols, [0], 1):.3f} B->A {lodo(cols, [1], 0):.3f}"
        )


if __name__ == "__main__":
    main(sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None)
