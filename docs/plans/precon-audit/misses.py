"""Recall against the upgrade guides: for every card a guide cuts or adds that the
tuner doesn't, the reason it doesn't (docs/plans/precon-audit-2026-10-18.md).

    cd mtg-utils && uv run python ../docs/plans/precon-audit/misses.py ROOT [Name ...]

ROOT holds decks/<Name>/deck.json and articles/<Name>.md. Runs the tune per deck
(--max-swaps 30, the largest guide's swaps, and the precon's own budget from
ROOT/budgets.json — guide_sizes.py — as the rerun recipe does) with the cut ranking and
the candidate searches recorded, then sorts each guide card into one reason.

CUT reasons, first that applies: cut (a hit); protected (a combo piece, an at-floor
closer, a commander multiplier); land / commander; cut pool, not reached (ranked
below the cuts made — the swap budget or the adds ran out); lane doer (the
commander's lane, outside the deep-lane half); carer (cares about a built theme);
fed or filler but no issue drew it; popular (off-lane, ranked inside UPGRADE_RANK);
other.

ADD reasons: added (a hit); out of scope (in the deck, a land, out of identity or
format); no search for it (no candidate page this run held a card of its kind —
its template job, protection, or the main theme); page held it — over budget /
failed the job gate / higher mana-value band / outranked; not on any page (a page
of its kind was searched, but its spec or page depth missed the card).
"""
import collections, fcntl, functools, json, multiprocessing, pathlib, re, sys, tempfile

#: The largest upgrade guide's swaps (guide_sizes.py, 2026-10-19), so the recipe
#: never caps recall below what a guide does; the budget is the precon's own
#: (ROOT/budgets.json), else the largest guide's spend.
MAX_SWAPS, BUDGET = 30, 440


def budget_for(root, name):
    path = root / "budgets.json"
    return json.loads(path.read_text()).get(name, BUDGET) if path.exists() else BUDGET


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


def run_deck(args):
    root, name = args
    from mtg_utils import card_search, combo_search
    from mtg_utils._analysis.roles import protects, role_of
    from mtg_utils._card_ir.trees import trees_for
    from mtg_utils._tuner import swaps as S
    from mtg_utils._tuner.classify import UPGRADE_RANK
    from mtg_utils._tuner.issues import upgrade_job
    from mtg_utils._tuner.tune import TuneParams, tune
    from mtg_utils.bulk_loader import default_bulk_path
    from mtg_utils.card_pool import CardPool
    from mtg_utils.deck_cli import acquire_for_cli
    from mtg_utils.hydrated_deck import HydratedDeck

    d = root / "decks" / name
    md = (root / "articles" / f"{name}.md").read_text()
    g_cuts, g_adds = parse_table(md, "Recommended cuts"), parse_table(md, "Recommended adds")
    pages, cut_rank = [], []
    run_search, cut_candidates = S._run_search, S.cut_candidates

    def rec_search(fn, spec, **kw):
        out = run_search(fn, spec, **kw)
        pages.append(({k: v for k, v in spec.items() if not k.startswith("_")}, [c.get("name") for c in out]))
        return out

    def rec_cuts(*a, **kw):
        out = cut_candidates(*a, **kw)
        cut_rank[:] = [(reason, c.name) for reason, c in out]
        return out

    upgrades, gate_fail = S._upgrades, {}

    def rec_upgrades(candidate, cut, job, *, deck_mana=None, deck=None):
        ok = upgrades(candidate, cut, job, deck_mana=deck_mana, deck=deck)
        if not ok:
            key = norm(candidate.get("name") or "")
            if S.over_band(candidate, cut.record, job):
                why = "costs a higher mana-value band than the cut"
            elif job is not None and upgrade_job(role_of(candidate, deck_mana=deck_mana), candidate) != job:
                why = "does a different job than the cut"
            elif not S._does_the_job(candidate, job, deck or (), cut.record):
                why = "the job read says it doesn't do the job (or the deck can't fuel it)"
            else:
                why = "fewer decks play it than the cut"
            gate_fail.setdefault(key, why)
        return ok

    S._run_search, S.cut_candidates, S._upgrades = rec_search, rec_cuts, rec_upgrades
    pool = CardPool.load(None)
    # A guide may name a card by its back face (Agadeem, the Undercrypt); key it
    # by the card's own name, as the deck and the pages are.
    g_cuts, g_adds = ({norm((pool.by_name.get(g) or {}).get("name") or g): g for g in rows.values()}
                      for rows in (g_cuts, g_adds))
    hd = acquire_for_cli(d / "deck.json", None)
    res = tune(hd, search_fn=functools.partial(card_search.search_cards, default_bulk_path()),
               params=TuneParams(budget=budget_for(root, name), max_swaps=MAX_SWAPS),
               combos_fn=lambda deck: combo_search.combo_search(HydratedDeck.from_parsed(deck, by_name=hd.by_name)))
    sc = res["scorecard"]; f = sc["focus"]
    cut_made = {norm(s["cut"]["name"]) for s in res["swaps"] if s.get("cut")}
    add_made = {norm(s["add"]["name"]) for s in res["swaps"]}
    deck = json.loads((d / "deck.json").read_text())
    in_deck = {norm(c["name"]): c["name"] for c in deck["cards"]}
    commanders = {norm(c["name"]) for c in deck["commanders"]}
    protected = {norm(n) for combo in (sc.get("combos") or {}).get("combos") or [] for n in combo.get("cards") or []}
    if sc["wincons"]["count"] <= sc["wincons"]["target"][0]:
        protected |= {norm(n) for n in sc["wincons"]["cards"] + sc["wincons"].get("voltron_cards", [])}
    protected |= {norm(n) for n in sc.get("commander_multipliers") or {}}
    in_cut_pool = {norm(n) for _r, n in cut_rank}
    lane = {norm(n) for n in f.get("commander_lane_cards") or []}
    carers = {norm(n) for a in f["viable_avenues"] for n in a.get("carer_cards") or []}
    weak = {norm(n) for n in (f.get("filler_cards") or []) + (f.get("low_value_cards") or []) + (f.get("fed_only_cards") or [])}
    out = {"cuts": [], "adds": []}
    for key, gname in g_cuts.items():
        if key not in in_deck:
            continue
        rec = pool.by_name.get(in_deck[key]) or {}
        if key in cut_made: why = "cut"
        elif key in protected: why = "protected (combo / closer / multiplier)"
        elif key in commanders or "Land" in (rec.get("type_line") or "").split("//")[0]: why = "land / commander"
        elif key in in_cut_pool: why = "cut pool, not reached"
        elif key in lane: why = "lane doer (outside the deep-lane half)"
        elif key in carers: why = "carer of a built theme"
        elif key in weak: why = "weak but no issue drew it"
        elif (rec.get("edhrec_rank") or 10**9) <= UPGRADE_RANK: why = "popular (inside UPGRADE_RANK)"
        else: why = "other"
        out["cuts"].append((gname, why))
    ident = set().union(*(set(pool.by_name[c["name"]].get("color_identity") or []) for c in deck["commanders"]))
    page_names = {}
    for spec, names in pages:
        for i, n in enumerate(names):
            page_names.setdefault(norm(n), []).append((json.dumps(spec, sort_keys=True), i, len(names)))
    searched = [json.dumps(s, sort_keys=True) for s, _ in pages]
    for key, gname in g_adds.items():
        rec = pool.by_name.get(gname) or pool.by_name.get(gname.split(" // ")[0])
        if key in add_made: why = "added"
        elif rec is None or key in in_deck or "Land" in (rec.get("type_line") or "").split("//")[0] \
                or not set(rec.get("color_identity") or []) <= ident \
                or (rec.get("legalities") or {}).get("commander") != "legal":
            why = "out of scope"
        elif key in page_names:
            price = float((rec.get("prices") or {}).get("usd") or 0) or None
            if price is not None and price > budget_for(root, name): why = "page held it — costs more than the whole budget"
            elif key in gate_fail: why = f"page held it — gated: {gate_fail[key]}"
            else: why = "page held it — outranked (another card ranked first)"
        else:
            roles = role_of(rec); job = upgrade_job(roles, rec)
            kinds = {"ramp": "ramp", "card_draw": "card-draw", "board_wipe": "board-wipe", "interaction": "removal", "protection": "protects-board"}
            want = kinds.get(job or "")
            asked = want is not None and any(want in s for s in searched)
            why = ("not on any page (a page of its job was searched)" if asked
                   else f"no search for its kind ({job or 'theme card'})")
        out["adds"].append((gname, why))
    return name, out


#: Workers per run. A tune holds about 2 GB at its peak (the pool, its trees and the
#: job's whole match set), so six fit beside a desktop on a 36 GB machine.
WORKERS = 6


def main(root, names):
    names = names or sorted(p.name for p in (root / "decks").iterdir())
    # One run at a time per machine: fifteen runs queued at once, each with its
    # workers, took 69 GB on a 36 GB machine (2026-10-23) and crashed it.
    lock = open(pathlib.Path(tempfile.gettempdir()) / "precon-misses.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("misses.py: another run holds the machine; waiting for it...", file=sys.stderr)
        fcntl.flock(lock, fcntl.LOCK_EX)
    with multiprocessing.Pool(WORKERS) as mp:
        results = dict(mp.map(run_deck, [(root, n) for n in names]))
    json.dump(results, open(root / "misses.json", "w"), indent=1)
    for side in ("cuts", "adds"):
        c = collections.Counter(why for r in results.values() for _n, why in r[side])
        total = sum(c.values())
        print(f"== guide {side}: {total}")
        for why, n in c.most_common():
            ex = [n_ for r in results.values() for n_, w in r[side] if w == why][:6]
            print(f"   {n:4d}  {why:52s} e.g. {', '.join(ex)}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), sys.argv[2:])
