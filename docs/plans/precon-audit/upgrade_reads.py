"""The two measurements behind the upgrade slots (docs/plans/precon-audit-2026-10-18.md,
seventh pass), over the 25 precons and their guide summaries.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/upgrade_reads.py cuts ROOT
    cd mtg-utils && uv run python ../docs/plans/precon-audit/upgrade_reads.py adds ROOT

ROOT holds decks/<Name>/{deck.json,tune.json} (the rerun recipe) and articles/<Name>.md
(may be a symlink to this directory). ``cuts``: every nonland deck card, split by
whether it is on a lane (a commander-lane doer or a carer of a built theme) and
whether it holds a template role, bucketed by EDHREC rank, against the guides' cuts.
``adds``: reruns the tune with the swap engine's candidate pages recorded, then
scores where the guides' adds land on each page under several orderings (synergy
first; a fit floor then play-rate; play-rate alone).
"""
import collections, functools, json, pathlib, re, statistics, sys


def norm(n):
    n = n.split("//")[0].strip().strip("*").strip()
    return re.sub(r"\s+", " ", n).lower()


def parse_table(md, header):
    rows = {}
    sec = md.split(f"## {header}", 1)
    if len(sec) < 2:
        return rows
    body = sec[1].split("\n## ", 1)[0]
    for line in body.splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| card"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        for name in re.split(r"\s*(?:;|/(?!/))\s*", cells[0]):
            if name.strip():
                rows[norm(name.strip())] = name.strip()
    return rows


def cuts(root):
    from mtg_utils._analysis.roles import protects, role_of
    from mtg_utils.card_pool import CardPool

    pool = CardPool.load(None)
    bands = [(0, 1000), (1000, 3000), (3000, 6000), (6000, 10000), (10000, 15000), (15000, 10**7)]
    n, hit = collections.Counter(), collections.Counter()
    for d in sorted((root / "decks").iterdir()):
        guide = parse_table((root / "articles" / f"{d.name}.md").read_text(), "Recommended cuts")
        focus = json.load(open(d / "tune.json"))["scorecard"]["focus"]
        lane = set(focus.get("commander_lane_cards") or ())
        lane |= {c for a in focus["viable_avenues"] for c in a.get("carer_cards") or ()}
        for entry in json.load(open(d / "deck.json"))["cards"]:
            rec = pool.by_name.get(entry["name"])
            if rec is None or "Land" in (rec.get("type_line") or ""):
                continue
            role = bool(role_of(rec)) or protects(rec)
            rank = rec.get("edhrec_rank") or 10**6
            band = next(i for i, (lo, hi) in enumerate(bands) if lo <= rank < hi)
            key = ("role" if role else "no role", "lane" if entry["name"] in lane else "off", band)
            n[key] += 1
            hit[key] += norm(entry["name"]) in guide
    for key in sorted(n):
        lo, hi = bands[key[2]]
        print(f"{key[0]:8s} {key[1]:5s} rank {lo:>6}-{hi:<8} n={n[key]:4d} guide cuts={hit[key]:3d} ({hit[key] / n[key]:.2f})")


def adds(root):
    from mtg_utils import card_search, combo_search
    from mtg_utils._tuner import swaps
    from mtg_utils._tuner.tune import TuneParams, tune
    from mtg_utils.bulk_loader import default_bulk_path
    from mtg_utils.deck_cli import acquire_for_cli
    from mtg_utils.hydrated_deck import HydratedDeck

    pages = []
    rank = swaps.rank_candidates

    def recording(cards, **kw):
        out = rank(cards, **kw)
        pages.append([(r["card"]["name"], r["score"]["synergy_score"], r["card"].get("edhrec_rank")) for r in out])
        return out

    swaps.rank_candidates = recording
    bulk = default_bulk_path()
    orders = {
        "synergy": lambda rows, mx: sorted(rows, key=lambda r: (-r[1], r[2] or 10**6)),
        "fit>=0.2 then play-rate": lambda rows, mx: sorted(rows, key=lambda r: (r[1] < 0.2 * mx, r[2] or 10**6, -r[1])),
        "play-rate": lambda rows, mx: sorted(rows, key=lambda r: r[2] or 10**6),
    }
    agg = {k: {"top3": 0, "top10": 0, "ranks": []} for k in orders}
    for d in sorted((root / "decks").iterdir()):
        pages.clear()
        hd = acquire_for_cli(d / "deck.json", None)
        tune(hd, search_fn=functools.partial(card_search.search_cards, bulk),
             params=TuneParams(budget=100, max_swaps=10),
             combos_fn=lambda deck, hd=hd: combo_search.combo_search(HydratedDeck.from_parsed(deck, by_name=hd.by_name)))
        guide = set(parse_table((root / "articles" / f"{d.name}.md").read_text(), "Recommended adds"))
        for rows in {json.dumps(p): p for p in pages if len(p) > 1}.values():
            mx = max(s for _, s, _ in rows)
            for k, order in orders.items():
                names = [norm(r[0]) for r in order(rows, mx)]
                agg[k]["top3"] += sum(n in guide for n in names[:3])
                agg[k]["top10"] += sum(n in guide for n in names[:10])
                agg[k]["ranks"] += [i for i, n in enumerate(names) if n in guide]
    for k, a in agg.items():
        print(f"{k:24s} guide adds in top 3: {a['top3']:3d}  top 10: {a['top10']:3d}  median rank {statistics.median(a['ranks']) if a['ranks'] else None}")


if __name__ == "__main__":
    {"cuts": cuts, "adds": adds}[sys.argv[1]](pathlib.Path(sys.argv[2]))
