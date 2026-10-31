"""Fit and measure the creature quality read (``mtg_utils._analysis.card_quality.creature``)
on the guide pairs ``theme_pairs.py`` writes (ADR-0063's method, after ADR-0060's
``job_reads.py``).

    cd mtg-utils && uv run python ../docs/plans/precon-audit/quality_fit_creature.py PAIRS.json [--select]

PAIRS.json is ``theme_pairs.py``'s output (``~/mtg/tuner-work/w41/pairs.json``);
only its ``"creature"`` pairs are read. Each pair (guide add, on-plan card the
reads-first order put above it) is weighted by the guides naming the add / the
add's pairs in its deck, so every guide add counts once per guide.

Prints, as weighted pair accuracy (a tie or an unread card counts half):

- the baselines: play-rate (lower EDHREC rank preferred) and mana value (cheaper
  preferred);
- a pairwise logistic regression (L2, no intercept, on standardized feature
  differences) under leave-one-deck-out cross-validation, for a grid of L2
  strengths;
- the full-data fit's weights in feature units (what ``WEIGHTS`` rounds);
- the shipped read (``READ.score``, hand-rounded ``WEIGHTS``) on the same pairs, per
  deck beside play-rate, and the heaviest pairs it gets wrong.

``--select`` runs the feature-selection pass instead: greedy forward selection by
leave-one-deck-out accuracy over :func:`candidates` (the shipped features plus the
ones the fit rejected). It is optimistic (the selection sees the folds).
"""

import collections
import json
import math
import pathlib
import sys

from mtg_utils._analysis.card_quality import creature
from mtg_utils._analysis.job_quality import READS as JOB_READS
from mtg_utils._analysis.job_quality._common import cast_cost
from mtg_utils._analysis.signal_trees import signal_trees_for
from mtg_utils._card_ir.crosswalk import (
    PROTECTIVE_KEYWORDS,
    normalised_keyword_name,
    static_mode_tag,
    tag_of,
)
from mtg_utils.card_classify import card_pt_int
from mtg_utils.card_pool import CardPool

COMBAT_KW = {"deathtouch", "lifelink", "firststrike", "doublestrike", "trample", "vigilance"}


def candidates(card):
    """The shipped features plus every candidate the fit rejected."""
    feats = creature.features(card)
    if feats is None:
        return None
    trees = signal_trees_for(card, bulk=card)
    front = trees[0]
    units = [u for t in trees for u in t.units if u.origin != "synth"]
    kws = {normalised_keyword_name(k) for k in front.card_keywords}
    mv = cast_cost(card)
    pt = card_pt_int(card, "power") + card_pt_int(card, "toughness")
    self_modes = {
        static_mode_tag(sd)
        for u in units
        for sd in u.static_defs()
        if tag_of(getattr(sd, "affected", None)) == "SelfRef"
    }
    concepts = {c.concept for u in units for c in u.effects}
    return {
        **feats,
        "abilities": float(min(len({creature._ability_key(u) for u in units if creature._is_ability(u)}), 6)),
        "mv": float(min(mv, 9)),
        "pt": float(min(pt, 20)),
        "body": pt / max(mv, 1.0),
        "flying": float("flying" in kws),
        "combat_kw": float(len(kws & COMBAT_KW)),
        "protect": float(bool(kws & (PROTECTIVE_KEYWORDS | {"hexprooffrom"}))),
        "uncounterable": float("CantBeCountered" in self_modes),
        "flash": float("flash" in kws),
        "draw": float("draw" in concepts),
        "tokens": float(bool(concepts & {"make_token", "copy_token"})),
        "impulse": float(bool(concepts & {"exile_top", "cast_from_zone", "grant_cast_permission"})),
        "etb": float(any(u.origin == "trigger" and u.effects and u.trigger_event in ("enters", "entersorattacks") for u in units)),
        "others_static": float(any(
            tag_of(getattr(sd, "affected", None)) != "SelfRef"
            for u in units if u.origin == "static" for sd in u.static_defs()
        )),
        "replacement": float(any(u.origin == "replacement" for u in units)),
        "legendary": float("Legendary" in front.card_supertypes),
        "other_jobs": float(sum(r.score(card) is not None for j, r in JOB_READS.items() if j != "ramp")),
    }


def weights_of(pairs):
    """Per-pair weight: guides naming the add / the add's pairs in its deck."""
    n = collections.Counter((p["deck"], p["preferred"]) for p in pairs)
    dup = collections.Counter(
        (p["deck"], p["avenue"], p["preferred"], p["other"], p["pos_other"]) for p in pairs
    )
    guides = collections.defaultdict(int)
    for k, v in dup.items():
        guides[(k[0], k[2])] = max(guides[(k[0], k[2])], v)
    return [guides[(p["deck"], p["preferred"])] / n[(p["deck"], p["preferred"])] for p in pairs]


def accuracy(pairs, w, key):
    """Weighted share of pairs where ``key`` puts the guide add higher; a tie or
    an unreadable card (``None``) counts half."""
    s = t = 0.0
    for p, wi in zip(pairs, w):
        a, b = key(p, p["preferred"]), key(p, p["other"])
        t += wi
        if a is None or b is None or a == b:
            s += wi / 2
        elif a > b:
            s += wi
    return s / t


def solve(a, b):
    """Gaussian elimination with partial pivoting: a x = b."""
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
                if f:
                    for k in range(c, n + 1):
                        m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def fit(rows, lam):
    """Weighted L2 logistic regression without intercept on ``rows`` of
    (difference vector, weight), label 1: P(add above other) = sigmoid(beta . d),
    symmetric by construction. Newton's method."""
    d = len(rows[0][0])
    beta = [0.0] * d
    tw = sum(w for _, w in rows)
    for _ in range(30):
        g = [-lam * b for b in beta]
        h = [[(-lam if i == j else 0.0) for j in range(d)] for i in range(d)]
        for x, w in rows:
            z = sum(bi * xi for bi, xi in zip(beta, x))
            pr = 1 / (1 + math.exp(-max(-30, min(30, z))))
            ww = w / tw
            for i in range(d):
                if x[i]:
                    g[i] += ww * (1 - pr) * x[i]
                    for j in range(d):
                        if x[j]:
                            h[i][j] -= ww * pr * (1 - pr) * x[i] * x[j]
        step = solve([[-v for v in row] for row in h], g)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return beta


class Design:
    """The pairs' standardized feature differences over ``keys``."""

    def __init__(self, pairs, w, feats, keys):
        self.keys = keys
        vals = {k: [f[k] for f in feats.values() if f] for k in keys}
        mu = {k: sum(v) / len(v) for k, v in vals.items()}
        self.sd = {k: (sum((x - mu[k]) ** 2 for x in v) / len(v)) ** 0.5 or 1.0 for k, v in vals.items()}
        vec = {n: [(f[k] - mu[k]) / self.sd[k] for k in keys] for n, f in feats.items() if f}
        self.data = [
            (p, wi, [a - b for a, b in zip(vec[p["preferred"]], vec[p["other"]])])
            for p, wi in zip(pairs, w)
            if p["preferred"] in vec and p["other"] in vec
        ]
        self.unread = sum(w) - sum(wi for _, wi, _ in self.data)

    def lodo(self, lam):
        """Leave-one-deck-out accuracy; unread pairs count half."""
        right = total = 0.0
        for dk in sorted({p["deck"] for p, _, _ in self.data}):
            beta = fit([(x, wi) for p, wi, x in self.data if p["deck"] != dk], lam)
            for p, wi, x in self.data:
                if p["deck"] == dk:
                    z = sum(b * xi for b, xi in zip(beta, x))
                    total += wi
                    right += wi if z > 0 else (wi / 2 if z == 0 else 0)
        return (right + self.unread / 2) / (total + self.unread)

    def weights(self, lam):
        """The full-data fit, in feature units."""
        beta = fit([(x, wi) for _, wi, x in self.data], lam)
        return {k: b / self.sd[k] for k, b in zip(self.keys, beta)}


def select(pairs, w, feats):
    keys = sorted(next(f for f in feats.values() if f))
    chosen, best = [], 0.0
    while len(chosen) < len(keys):
        trial = {k: Design(pairs, w, feats, chosen + [k]).lodo(0.03) for k in keys if k not in chosen}
        k, a = max(trial.items(), key=lambda kv: kv[1])
        print(f"+{k:16s} {a:.3f}", flush=True)
        if a <= best + 0.002:
            break
        chosen.append(k)
        best = a
    print("selected", chosen, f"{best:.3f}")


def main(path, selecting):
    pairs = json.load(open(path))["creature"]
    w = weights_of(pairs)
    pool = CardPool.load(None)
    names = sorted({p["preferred"] for p in pairs} | {p["other"] for p in pairs})
    read = candidates if selecting else creature.features
    feats = {n: read(pool.by_name[n]) for n in names}
    unread = [n for n, f in feats.items() if f is None]
    print(f"pairs {len(pairs)} | guide adds {len({p['preferred'] for p in pairs})} "
          f"({len({(p['deck'], p['preferred']) for p in pairs})} deck-adds) "
          f"| decks {len({p['deck'] for p in pairs})} | weight {sum(w):.0f} "
          f"| cards {len(names)}, unread {len(unread)} {unread[:8]}")
    print(f"baseline play-rate  {accuracy(pairs, w, lambda p, n: -p['features'][n]['rank']):.3f}")
    print(f"baseline mana value {accuracy(pairs, w, lambda p, n: -p['features'][n]['cmc']):.3f}")
    if selecting:
        select(pairs, w, feats)
        return
    design = Design(pairs, w, feats, sorted(creature.WEIGHTS))
    for lam in (0.003, 0.01, 0.03, 0.1, 0.3):
        print(f"LODO CV lambda={lam:<6} read {design.lodo(lam):.3f}")
    print("full fit (lambda 0.03), weight per feature unit (shipped WEIGHTS beside):")
    for k, b in sorted(design.weights(0.03).items(), key=lambda kb: -abs(kb[1])):
        print(f"   {k:10s} {b:+.3f}   {creature.WEIGHTS[k]:+.2f}")

    score = {n: creature.READ.score(pool.by_name[n]) for n in names}
    print(f"shipped read (hand-rounded WEIGHTS), in-sample: "
          f"{accuracy(pairs, w, lambda p, n: score[n]):.3f}")
    print("per deck (read / play-rate):")
    for dk in sorted({p["deck"] for p in pairs}):
        sub = [(p, wi) for p, wi in zip(pairs, w) if p["deck"] == dk]
        ps, ws = [p for p, _ in sub], [wi for _, wi in sub]
        print(f"   {dk:26s} {accuracy(ps, ws, lambda p, n: score[n]):.2f} / "
              f"{accuracy(ps, ws, lambda p, n: -p['features'][n]['rank']):.2f}")
    wrong = collections.Counter()
    for p, wi in zip(pairs, w):
        a, b = score[p["preferred"]], score[p["other"]]
        if a is not None and b is not None and a < b:
            wrong[(p["deck"], p["preferred"], p["other"], a, b)] += wi
    print("heaviest wrong pairs (weight: deck, add, other, add score, other score):")
    for k, v in wrong.most_common(12):
        print(f"   {v:.3f}  {k}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), "--select" in sys.argv[2:])
