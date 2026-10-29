"""Compare each precon's tuner read (decks/<s>/tune.json) with the article consensus
(articles/<s>.md). Prints one block per precon plus a summary table."""
import json, re, sys, pathlib, collections
ROOT = pathlib.Path(__file__).parent  # expects decks/<Name>/{tune.json,deck.json} and articles/<Name>.md beside it (or edit)
def norm(n):
    n = n.split("//")[0].strip().strip("*").strip()
    return re.sub(r"\s+", " ", n).lower()
def parse_table(md, header):
    rows = {}
    sec = md.split(f"## {header}", 1)
    if len(sec) < 2: return rows
    body = sec[1].split("\n## ", 1)[0]
    for line in body.splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| card"): continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3: continue
        src = cells[2]
        n_src = len(re.findall(r"\d", src))
        for name in re.split(r"\s*(?:;|(?<!/)/(?!/))\s*", cells[0]):
            name = name.strip()
            if name: rows[norm(name)] = (name, cells[1], n_src)
    return rows
summary = []
TUNE = sys.argv[1] if len(sys.argv) > 1 else "tune.json"
for tune_path in sorted(ROOT.glob(f"decks/*/{TUNE}")):
    slug = tune_path.parent.name
    art = ROOT / "articles" / f"{slug}.md"
    if not art.exists(): continue
    md = art.read_text()
    a_cuts = parse_table(md, "Recommended cuts"); a_adds = parse_table(md, "Recommended adds")
    t = json.load(open(tune_path)); f = t["scorecard"]["focus"]
    t_cuts = [s["cut"]["name"] for s in t["swaps"] if s.get("cut")]
    t_adds = [s["add"]["name"] for s in t["swaps"]]
    t_weak = set(f["filler_cards"]) | set(f["low_value_cards"]) | set(f.get("fed_only_cards") or [])
    deck_names = {norm(c["name"]) for c in json.load(open(tune_path.parent / "deck.json"))["cards"]}
    main = f["viable_avenues"][0] if f["viable_avenues"] else None
    main_carers = set(main.get("carer_cards") or []) if main else set()
    lane = set(f.get("commander_lane_cards") or [])
    cut_hit = [n for n in t_cuts if norm(n) in a_cuts]
    weak_hit = [n for n in t_weak if norm(n) in a_cuts]
    add_hit = [n for n in t_adds if norm(n) in a_adds]
    art_cuts_in_deck = [v[0] for k, v in a_cuts.items() if k in deck_names]
    protected = [v[0] for k, v in a_cuts.items() if k in deck_names and (v[0] in main_carers or v[0] in lane)]
    multi_cuts = [v[0] for k, v in a_cuts.items() if v[2] >= 2 and k in deck_names]
    multi_adds = [v[0] for k, v in a_adds.items() if v[2] >= 2]
    print(f"=== {slug}  verdict={f['verdict']}  main={main['label'] if main else None}")
    print(f"  tuner cuts {len(t_cuts)}: {t_cuts}")
    print(f"    in article cuts: {cut_hit}")
    print(f"  tuner weak-list {len(t_weak)} in article cuts: {weak_hit}")
    print(f"  tuner adds {len(t_adds)}: {t_adds}")
    print(f"    in article adds: {add_hit}")
    print(f"  article consensus cuts (2+ sources, in deck): {multi_cuts}")
    print(f"  article cuts the tuner PROTECTS (main carer / lane): {protected}")
    print(f"  article consensus adds (2+ sources): {multi_adds}")
    summary.append((slug, f["verdict"], len(t_cuts), len(cut_hit), len(weak_hit), len(t_adds), len(add_hit), len(multi_cuts), len(protected)))
print("\n| precon | verdict | tuner cuts | cuts matching articles | weak-list matching | tuner adds | adds matching | article consensus cuts | article cuts tuner protects |")
print("|---|---|---|---|---|---|---|---|---|")
for r in summary: print("| " + " | ".join(str(x) for x in r) + " |")
tot = [sum(r[i] for r in summary) for i in range(2, 9)]
print("| TOTAL | | " + " | ".join(str(x) for x in tot) + " |")
