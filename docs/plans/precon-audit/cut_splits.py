"""The guide cuts the tuner protects, split two ways over the 25 precons — the
measurement behind backlog (g) and "The remaining tuner levers"
(docs/plans/precon-audit-2026-10-18.md, 2026-10-24).

Usage (ROOT laid out as for misses.py: ROOT/decks/<Name>/deck.json, the guide
summary at ROOT/articles/<Name>.md, budgets.json and the Spellbook cache):

    cd mtg-utils && uv run python ../docs/plans/precon-audit/cut_splits.py ROOT
    (add --from-json to re-read ROOT/cut_splits.json instead of tuning)

Tunes each precon once, one at a time (the misses.py settings), records every
nonland card's cut-side facts and the cut order ``cut_candidates`` gave, and
writes ROOT/cut_splits.json; ``--from-json`` re-reads that file instead. Prints:

1. The commander-lane cards no cut tier reaches, guide-cut rate by carer /
   feeder, template role or none, and play-rate (premium: EDHREC rank <= 200;
   <1500; >1500).
2. The off-lane cards (rank <= 1500) no tier but the popular one reaches, by
   whether they serve a viable avenue, hold a template role, whether that role
   is at or below its floor, and premium. The popular tier's rows are those
   with viable=False and premium=False.
"""

import collections
import fcntl
import functools
import json
import pathlib
import sys
import tempfile

from mtg_utils._tuner.classify import PREMIUM_RANK as PREMIUM
from mtg_utils._tuner.classify import UPGRADE_RANK as POPULAR

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import misses as M  # noqa: E402


def dump(root: pathlib.Path) -> dict:
    from mtg_utils import card_search, combo_search
    from mtg_utils._tuner import swaps as S
    from mtg_utils._tuner.tune import TuneParams, tune
    from mtg_utils.bulk_loader import default_bulk_path
    from mtg_utils.deck_cli import acquire_for_cli
    from mtg_utils.hydrated_deck import HydratedDeck

    M.cache_spellbook(root / "spellbook-cache", combo_search)
    cap: dict = {}
    orig = S.cut_candidates

    def recording(classes, **kw):
        cap["classes"], cap["kw"] = classes, kw
        ranked = orig(classes, **kw)
        cap["rank"] = [(reason, c.name) for reason, c in ranked]
        return ranked

    S.cut_candidates = recording
    out = {}
    for d in sorted((root / "decks").iterdir()):
        name = d.name
        md = (root / "articles" / f"{name}.md").read_text()
        g_cuts = set(M.parse_table(md, "Recommended cuts"))
        hd = acquire_for_cli(d / "deck.json", None)
        res = tune(
            hd,
            search_fn=functools.partial(card_search.search_cards, default_bulk_path()),
            params=TuneParams(budget=M.budget_for(root, name), max_swaps=M.MAX_SWAPS),
            combos_fn=lambda deck, hd=hd: combo_search.combo_search(
                HydratedDeck.from_parsed(deck, by_name=hd.by_name)
            ),
        )
        f = res["scorecard"]["focus"]
        rows = []
        for c in cap["classes"]:
            if c.bucket in ("land", "commander"):
                continue
            rows.append(
                dict(
                    name=c.name,
                    rank=c.edhrec_rank,
                    roles=list(c.roles),
                    guide_cut=M.norm(c.name) in g_cuts,
                    lane=c.name in (f.get("commander_lane_cards") or []),
                    carer=c.name in (f.get("commander_lane_carers") or []),
                    viable=[
                        a["label"]
                        for a in f["viable_avenues"]
                        if c.name in a.get("cards", [])
                        or c.name in a.get("carer_cards", [])
                    ],
                )
            )
        budgets = {
            k: {kk: v.get(kk) for kk in ("current", "min", "max")}
            for k, v in cap["kw"]["budgets"].items()
        }
        out[name] = dict(rows=rows, budgets=budgets, cut_rank=cap["rank"])
        print(name, len(rows), file=sys.stderr)
    return out


def lane_splits(data: dict) -> None:
    st = collections.Counter()
    for o in data.values():
        ranked = {n for _r, n in o["cut_rank"]}
        for r in o["rows"]:
            if not r["lane"] or r["name"] in ranked:
                continue
            rank = r["rank"] or 10**9
            play = (
                "prem" if rank <= PREMIUM else ("<1500" if rank <= POPULAR else ">1500")
            )
            k = (
                "carer" if r["carer"] else "feeder",
                "role" if r["roles"] else "norole",
                play,
            )
            st[k, r["guide_cut"]] += 1
    print("Commander-lane cards no cut tier reaches: guide cuts / cards")
    for k in sorted({k for k, _ in st}):
        g, n = st[k, True], st[k, False]
        print(f"  {k}  {g}/{g + n} = {g / max(1, g + n):.2f}")


def popular_splits(data: dict) -> None:
    st = collections.Counter()
    for o in data.values():
        # The popular tier is what this split measures: count its cards as unreached.
        ranked = {n for r, n in o["cut_rank"] if r != "popular_upgrade"}
        b = o["budgets"]
        for r in o["rows"]:
            if r["name"] in ranked or r["lane"] or r["carer"]:
                continue
            if (r["rank"] or 10**9) > POPULAR:
                continue
            short = any(x in b and b[x]["current"] <= b[x]["min"] for x in r["roles"])
            k = (bool(r["viable"]), bool(r["roles"]), short, r["rank"] <= PREMIUM)
            st[k, r["guide_cut"]] += 1
    print("Off-lane cards (rank <= 1500) only the popular tier reaches:")
    total = [0, 0]
    for k in sorted({k for k, _ in st}):
        g, n = st[k, True], st[k, False]
        if not k[0] and not k[3]:
            total[0] += g
            total[1] += g + n
        print(
            f"  viable={k[0]!s:5} roles={k[1]!s:5} short={k[2]!s:5} premium={k[3]!s:5}"
            f"  guide {g:3d} / {g + n:3d} = {g / max(1, g + n):.2f}"
        )
    print(f"  popular tier (no viable avenue, not premium): {total[0]} / {total[1]}")


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1])
    path = root / "cut_splits.json"
    if "--from-json" in sys.argv:
        data = json.loads(path.read_text())
    else:
        # misses.py's machine-wide lock: one precon measurement at a time.
        lock = open(pathlib.Path(tempfile.gettempdir()) / "precon-misses.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = dump(root)
        path.write_text(json.dumps(data, indent=0))
    lane_splits(data)
    popular_splits(data)
