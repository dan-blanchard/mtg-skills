"""Fit and measure the creature theme-strength read on two pair sources.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/strength_fit_creature.py \\
        ~/mtg/tuner-work/w41/pairs-cuts.json ~/mtg/tuner-work/w41/pairs-live.json \\
        [--cache FEATS.json] [--keys k1,k2,...] [--screen 1]

The theme-strength read (``card_quality.creature.THEME_READ``) is fitted on two
pair sources the reads-first order didn't choose, design 25 only:

- A, ``pairs-cuts.json``: a guide's add against the same guide's cut of a
  creature. Weighted ``weight`` (the guides naming the add) over the add's pairs.
- B, ``pairs-live.json`` (``theme_pairs.py`` over ``pages-live/``): a guide add
  against each on-plan creature the LIVE play-rate order ranked above it on the
  same theme page. Weighted by ``quality_fit_creature.weights_of``.

Each source's weights sum to one. Play-rate prefers the lower EDHREC rank
(unranked worst); on B it scores 0 by construction (every pair is one it got
wrong), so B's real bar is chance, 0.5. Pairwise L2 logistic regression without
intercept on standardized feature differences, leave-one-deck-out by deck
(both sources' pairs of the held-out deck dropped from training). Columns:
train -> scored, so ``AB->B`` is fitted on both and scored on B, ``A->B`` the
cross-source check. ``--screen 1`` prints every candidate's univariate accuracy
per source; ``--keys`` fits one set. Forward selection and its nested
estimate are ``strength_select_creature.py`` (numpy) over ``--cache``'s file.

Output, 2026-10-31::

    source A: pairs 3565 | decks 24 | adds 310 | play-rate 0.574 | mana value 0.566
    source B: pairs 6627 | decks 24 | adds 160 | play-rate 0.000 | mana value 0.487

    step 1: the ADR-0063 quality features, refitted
      lambda | A->A  B->B  AB->A AB->B | A->B  B->A
      0.03   | 0.618 0.505 0.606 0.453 | 0.469 0.439
      fit A: standardised [defender -0.14, dies -0.12, engines +0.17, evasion +0.14, ramp +0.06, share -0.36]
      fit B: standardised [defender +0.15, dies +0.01, engines +0.14, evasion +0.07, ramp -0.04, share +0.15]

    step 2: the theme-strength features (creature.theme_features)
      lambda | A->A  B->B  AB->A AB->B | A->B  B->A
      0.01   | 0.664 0.605 0.667 0.616 | 0.601 0.662
      0.03   | 0.664 0.606 0.668 0.616 | 0.606 0.664
      0.1    | 0.663 0.608 0.665 0.616 | 0.598 0.663
      fit A:  standardised [cost -0.29, legendary +0.30, tutor +0.32, board_static +0.30, attack_trigger +0.15, evasion +0.15]
      fit B:  standardised [cost -0.08, legendary +0.24, tutor +0.34, board_static +0.17, attack_trigger +0.26, evasion +0.09]
      fit AB: standardised [cost -0.19, legendary +0.28, tutor +0.33, board_static +0.23, attack_trigger +0.21, evasion +0.12]
              per unit     [cost -0.099, legendary +0.611, tutor +2.429, board_static +0.609, attack_trigger +0.711, evasion +0.548]

    shipped THEME_READ (hand-rounded THEME_WEIGHTS), in sample: A 0.681 | B 0.647
    selection inside the LODO loop (strength_select_creature.py nested 6): A 0.616 | B 0.537

Step 1's features split by source (``share`` cheaper-per-ability on A, dearer
on B) and fall below chance on B when fitted on both. Step 2's six agree in sign
on both sources' own fits. The six were chosen by forward selection over the 56
candidates of :func:`candidates` seeing every deck, hence the nested line. The
shipped read is weakest on MultiverseReforged_FRC (A 0.28 against play-rate's
0.95: a polymorph deck's adds are big flip targets) and TimeyWimey_WHO (0.26).
"""

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from quality_fit_creature import candidates as old_candidates  # noqa: E402
from quality_fit_creature import fit, weights_of  # noqa: E402

from mtg_utils._analysis.card_quality import creature  # noqa: E402
from mtg_utils._analysis.job_quality import READS as JOB_READS  # noqa: E402
from mtg_utils._analysis.job_quality._common import activation_mana, cast_cost  # noqa: E402
from mtg_utils._analysis.signal_trees import signal_trees_for  # noqa: E402
from mtg_utils._card_ir.crosswalk import (  # noqa: E402
    INCREASE_QTY_MODS,
    activated_ability_units,
    amount_is_scaling,
    replacement_qty_mod,
)
from mtg_utils.card_classify import card_pt_int  # noqa: E402
from mtg_utils.card_pool import CardPool  # noqa: E402

UNRANKED = 10**9


def load_pairs(cuts_path, live_path):
    """Both sources' creature pairs as ``(source, deck, preferred, other, w)``,
    each source's weights summing to 1. Source A (cuts): every guide add counts
    once per guide naming it, split over its pairs. Source B (live): the old
    ``weights_of`` (guides naming the add / the add's pairs in its deck)."""
    a = json.load(open(cuts_path))["creature"]
    n = collections.Counter((p["deck"], p["preferred"]) for p in a)
    wa = [p["weight"] / n[(p["deck"], p["preferred"])] for p in a]
    b = json.load(open(live_path))["creature"]
    wb = weights_of(b)
    out = []
    for src, ps, ws in (("A", a, wa), ("B", b, wb)):
        tot = sum(ws)
        out += [
            (src, p["deck"], p["preferred"], p["other"], wi / tot)
            for p, wi in zip(ps, ws)
        ]
    return out


def accuracy(pairs, key):
    """Weighted share of pairs where ``key`` puts the preferred card higher; a
    tie or an unread card (``None``) counts half."""
    s = t = 0.0
    for _src, _dk, pref, other, w in pairs:
        a, b = key(pref), key(other)
        t += w
        if a is None or b is None or a == b:
            s += w / 2
        elif a > b:
            s += w
    return s / t if t else float("nan")


class Design:
    """Standardized feature vectors over ``keys`` for every card name."""

    def __init__(self, feats, keys):
        self.keys = keys
        vals = {k: [f[k] for f in feats.values() if f] for k in keys}
        mu = {k: sum(v) / len(v) for k, v in vals.items()}
        self.sd = {
            k: (sum((x - mu[k]) ** 2 for x in v) / len(v)) ** 0.5 or 1.0
            for k, v in vals.items()
        }
        self.vec = {
            n: [(f[k] - mu[k]) / self.sd[k] for k in keys]
            for n, f in feats.items()
            if f
        }

    def rows(self, pairs):
        return [
            ([x - y for x, y in zip(self.vec[pref], self.vec[other])], w)
            for _s, _d, pref, other, w in pairs
            if pref in self.vec and other in self.vec
        ]

    def score_fn(self, beta):
        return lambda n: (
            sum(b * x for b, x in zip(beta, self.vec[n])) if n in self.vec else None
        )

    def lodo(self, train, test, lam):
        """Leave-one-deck-out: for each deck, fit on ``train`` without it and
        score ``test``'s pairs of that deck. Unread pairs count half."""
        right = total = 0.0
        for dk in sorted({p[1] for p in test}):
            rows = self.rows([p for p in train if p[1] != dk])
            beta = fit(rows, lam)
            sub = [p for p in test if p[1] == dk]
            w = sum(p[4] for p in sub)
            right += accuracy(sub, self.score_fn(beta)) * w
            total += w
        return right / total

    def weights(self, train, lam):
        beta = fit(self.rows(train), lam)
        return beta, {k: b / self.sd[k] for k, b in zip(self.keys, beta)}


def report(pairs, feats, keys, lams=(0.01, 0.03, 0.1)):
    design = Design(feats, keys)
    a = [p for p in pairs if p[0] == "A"]
    b = [p for p in pairs if p[0] == "B"]
    print(f"keys {keys}")
    print("  lambda | A->A  B->B  AB->A AB->B | A->B  B->A")
    for lam in lams:
        print(
            f"  {lam:<6} | {design.lodo(a, a, lam):.3f} {design.lodo(b, b, lam):.3f} "
            f"{design.lodo(pairs, a, lam):.3f} {design.lodo(pairs, b, lam):.3f} | "
            f"{design.lodo(a, b, lam):.3f} {design.lodo(b, a, lam):.3f}",
            flush=True,
        )
    for name, train in (("A", a), ("B", b), ("AB", pairs)):
        beta, w = design.weights(train, 0.03)
        std = ", ".join(f"{k} {x:+.2f}" for k, x in zip(keys, beta))
        unit = ", ".join(f"{k} {x:+.3f}" for k, x in w.items())
        print(f"  fit {name}: standardised [{std}]\n          per unit [{unit}]")


def main(argv):
    cuts, live = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    opts = dict(zip(argv[2::2], argv[3::2]))
    pairs = load_pairs(cuts, live)
    names = sorted({p[2] for p in pairs} | {p[3] for p in pairs})
    cache = pathlib.Path(opts["--cache"]) if "--cache" in opts else None
    if cache and cache.exists():
        stored = json.loads(cache.read_text())
    else:
        pool = CardPool.load(None)
        recs = {n: pool.by_name.get(n) for n in names}
        missing = [n for n, r in recs.items() if r is None]
        if missing:
            print("missing from pool:", missing[:10])
        stored = {
            "feats": {
                n: (
                    None
                    if r is None or (c := candidates(r)) is None
                    else {
                        **c,
                        **{
                            f"t_{k}": v
                            for k, v in (creature.theme_features(r) or {}).items()
                        },
                    }
                )
                for n, r in recs.items()
            },
            "rank": {n: (r or {}).get("edhrec_rank") for n, r in recs.items()},
            "score": {
                n: (creature.THEME_READ.score(r) if r else None)
                for n, r in recs.items()
            },
        }
        if cache:
            cache.write_text(json.dumps(stored))
    feats, rank, score = stored["feats"], stored["rank"], stored["score"]
    unread = [n for n, f in feats.items() if f is None]
    a = [p for p in pairs if p[0] == "A"]
    b = [p for p in pairs if p[0] == "B"]
    for src, sub in (("A", a), ("B", b)):
        print(
            f"source {src}: pairs {len(sub)} | decks {len({p[1] for p in sub})} | "
            f"adds {len({(p[1], p[2]) for p in sub})} | "
            f"play-rate {accuracy(sub, lambda n: -(rank[n] or UNRANKED)):.3f} | "
            f"mana value {accuracy(sub, lambda n: -feats[n]['mv'] if feats[n] else None):.3f}"
        )
    print(f"cards {len(names)}, unread {len(unread)}: {unread[:10]}")
    if "--screen" in opts:
        print("univariate (higher preferred): feature  A  B  | share of cards nonzero")
        for k in sorted(next(f for f in feats.values() if f)):
            nz = sum(1 for f in feats.values() if f and f[k]) / len(feats)
            print(
                f"  {k:18s} {accuracy(a, lambda n, k=k: feats[n][k] if feats[n] else None):.3f} "
                f"{accuracy(b, lambda n, k=k: feats[n][k] if feats[n] else None):.3f}  | {nz:.2f}"
            )
        return
    if "--keys" in opts:
        report(pairs, feats, opts["--keys"].split(","))
        return
    print("\nstep 1: the ADR-0063 quality features, refitted")
    report(pairs, feats, sorted(creature.WEIGHTS))
    print("\nstep 2: the theme-strength features (creature.theme_features)")
    report(pairs, feats, [f"t_{k}" for k in creature.THEME_WEIGHTS])
    print("\nshipped THEME_READ (hand-rounded THEME_WEIGHTS), in sample:")
    print(
        f"  A {accuracy(a, lambda n: score[n]):.3f} | B {accuracy(b, lambda n: score[n]):.3f}"
    )
    print("  per deck: A read / play-rate | B read")
    for dk in sorted({p[1] for p in pairs}):
        sa = [p for p in a if p[1] == dk]
        sb = [p for p in b if p[1] == dk]
        line = f"   {dk:26s} "
        line += (
            f"{accuracy(sa, lambda n: score[n]):.2f} / {accuracy(sa, lambda n: -(rank[n] or UNRANKED)):.2f}"
            if sa
            else "  -  /  - "
        )
        line += f" | {accuracy(sb, lambda n: score[n]):.2f}" if sb else " |  -"
        print(line)
    wrong, fixed = collections.Counter(), collections.Counter()
    for src, dk, pref, other, w in pairs:
        s_p, s_o = score[pref], score[other]
        if s_p is None or s_o is None or s_p == s_o:
            continue
        if s_p < s_o:
            wrong[(src, dk, pref, other, s_p, s_o)] += w
        elif src == "A" and (rank[pref] or UNRANKED) > (rank[other] or UNRANKED):
            fixed[(dk, pref, other, s_p, s_o, rank[pref], rank[other])] += w
    print("  heaviest wrong pairs (weight: source, deck, preferred, other, scores):")
    for k, v in wrong.most_common(12):
        print(f"   {v:.4f}  {k}")
    print(
        "  heaviest source-A pairs play-rate gets wrong and the read right (deck, add, cut, scores, ranks):"
    )
    for k, v in fixed.most_common(15):
        print(f"   {v:.4f}  {k}")


def candidates(card):
    """The shipped quality features, the ones the ADR-0063 fit rejected, and
    the strength candidates designed for this fit."""
    base = old_candidates(card)
    if base is None:
        return None
    trees = signal_trees_for(card, bulk=card)
    units = [u for t in trees for u in t.units if u.origin != "synth"]
    effects = [e for u in units for e in u.effects]
    trig = [u for u in units if u.origin == "trigger" and u.effects]
    acts = [u for t in trees for u in activated_ability_units(t) if u.effects]
    events = {u.trigger_event for u in trig}
    jobs = {j: r.score(card) is not None for j, r in JOB_READS.items()}
    power = card_pt_int(card, "power")
    tough = card_pt_int(card, "toughness")
    mv = cast_cost(card)
    doubler = any(
        u.origin == "replacement"
        and (q := replacement_qty_mod(u.node)) is not None
        and q[0] in INCREASE_QTY_MODS
        for u in units
    )
    return {
        **base,
        "power": float(min(power, 12)),
        "toughness": float(min(tough, 12)),
        "power_per_mv": power / max(mv, 1.0),
        "cheap": float(mv <= 2),
        "big": float(mv >= 6),
        "triggers": float(min(len(trig), 4)),
        "activated": float(min(len(acts), 4)),
        "free_act": float(any(activation_mana(u) == 0 for u in acts)),
        "attack_trig": float(bool(events & {"attacks", "entersorattacks"})),
        "combat_dmg_trig": float("deals_damage" in events),
        "cast_trig": float(bool(events & {"cast_spell", "spellcastorcopy"})),
        "phase_trig": float("phase" in events),
        "scaling": float(
            any(
                amount_is_scaling(e.node) or amount_is_scaling(e.node, "count")
                for e in effects
            )
        ),
        "doubler": float(doubler),
        "kw_n": float(min(len(trees[0].card_keywords), 5)),
        **{f"job_{j}": float(v) for j, v in jobs.items()},
        "any_job": float(any(jobs.values())),
        "counters": float(any(e.concept == "place_counter" for e in effects)),
        "pump": float(any(e.concept == "pump" for e in effects)),
        "untap": float(any(e.concept == "tap_untap" for e in effects)),
        "extra_phase": float(any(e.concept == "extra_phase" for e in effects)),
        "copy": float(
            any(
                e.concept in ("copy_token", "copy_spell", "become_copy")
                for e in effects
            )
        ),
        "removal_fx": float(
            any(
                e.concept in ("destroy", "bounce", "fight", "gain_control")
                for e in effects
            )
        ),
        "tokens_fx": float(
            any(
                e.concept
                in ("make_token", "copy_token", "investigate", "amass", "populate")
                for e in effects
            )
        ),
        "card_adv": float(
            any(
                e.concept
                in (
                    "draw",
                    "investigate",
                    "exile_top",
                    "grant_cast_permission",
                    "cast_from_zone",
                    "dig",
                    "tutor",
                )
                for e in effects
            )
        ),
        "mill_self": float(any(e.concept == "mill" for e in effects)),
        "concept_n": float(min(len({e.concept for e in effects}), 8)),
    }


if __name__ == "__main__":
    main(sys.argv[1:])
