"""Per lane card, features vs the guides' cuts, pooled over the 25 precons — the
measurement behind "inside a lane, the cut read is a feeder nobody plays"
(docs/plans/precon-audit-2026-10-18.md, third pass).

Usage (after the rerun recipe in that doc has filled ROOT/decks/<Name>/{deck.json,
tune.json} and ROOT/articles/<Name>.md is the guide summary — the committed
summaries live beside this script as <Name>.md, so ROOT/articles may be a symlink
to this directory):

    cd mtg-utils && uv run python ../docs/plans/precon-audit/lane_quality.py ROOT

Writes ROOT/lane_features.json, one row per main-lane card: whether a guide cuts
it, carer / doer flags, mana value, EDHREC rank, template roles, one-shot, body,
ident count, the in-deck synergy score. The rule experiments are a few lines of
pandas-free Python over that file (see the audit doc for the ones measured).
"""
import json, re, sys, pathlib
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
        for name in re.split(r"\s*(?:;|/(?!/))\s*", cells[0]):
            name = name.strip()
            if name: rows[norm(name)] = (name, cells[1], len(re.findall(r"\d", cells[2])))
    return rows
from mtg_utils.deck_cli import acquire_for_cli
from mtg_utils._analysis.signals import read_deck_signals, extract_signals
from mtg_utils._analysis.ranking import rank_candidates
from mtg_utils._tuner.classify import classify_deck
from mtg_utils.deck import split_type_line
ROOT = pathlib.Path(sys.argv[1])
rows = []
for tune_path in sorted(ROOT.glob("decks/*/tune.json")):
    slug = tune_path.parent.name
    art = ROOT / "articles" / f"{slug}.md"
    if not art.exists(): continue
    a_cuts = parse_table(art.read_text(), "Recommended cuts")
    t = json.load(open(tune_path)); f = t["scorecard"]["focus"]
    if not f["viable_avenues"]: continue
    main = f["viable_avenues"][0]
    lane = set(main["cards"]) | set(main.get("carer_cards") or []) | set(f.get("commander_lane_cards") or [])
    deck_json = json.load(open(tune_path.parent / "deck.json"))
    cmd_names = {c["name"] for c in deck_json["commanders"]}
    hd = acquire_for_cli(str(tune_path.parent / "deck.json"), None)
    read = read_deck_signals(hd.deck_records(), cmd_names)
    classes = classify_deck(hd, read.ranked, cmd_names, deck_mana=hd.deck_mana)
    by_class = {c.name: c for c in classes}
    focus_sets = {"viable": {a["label"] for a in f["viable_avenues"]}, "emerging": {a["label"] for a in f.get("emerging", [])}, "stranded": set(f.get("stranded_avenues") or [])}
    deck_tribes = frozenset(st.lower() for c in classes if "creature" in (c.record.get("type_line") or "").lower() for st in split_type_line(c.record.get("type_line", ""))[1])
    recs = [c.record for c in classes if c.name in lane and c.bucket not in ("land", "commander")]
    scored = {r["card"]["name"]: r["score"] for r in rank_candidates(recs, active_signals=read.ranked, focus_sets=focus_sets, deck_tribes=deck_tribes, deck_mana=hd.deck_mana)}
    cmd_idents = set(read.commander_idents)
    for rec in recs:
        name = rec["name"]; c = by_class[name]; sc = scored.get(name, {})
        tl = (rec.get("type_line") or "").lower()
        sigs = extract_signals(rec, include_membership=False)
        idents = {f"{s.key}|{s.scope}|{s.subject}" for s in sigs}
        high = {f"{s.key}|{s.scope}|{s.subject}" for s in sigs if s.confidence == "high"}
        def num(v):
            try: return float(v)
            except Exception: return None
        p, tt = num(rec.get("power")), num(rec.get("toughness"))
        rows.append(dict(slug=slug, name=name, cut=norm(name) in a_cuts, lane_label=main["label"],
            carer=name in set(main.get("carer_cards") or []), doer=name in set(f.get("commander_lane_cards") or []),
            cmc=c.cmc, rank=c.edhrec_rank, bucket=c.bucket, roles=list(c.roles), served=list(c.served),
            one_shot=("instant" in tl or "sorcery" in tl), creature="creature" in tl,
            power=p, toughness=tt, keywords=len(rec.get("keywords") or []),
            n_idents=len(idents), synergy=sc.get("synergy_score"), fit=sc.get("fit"), served_rank=list(sc.get("served") or []),
            cmd_supplies=bool(high) and high <= cmd_idents, price=(rec.get("prices") or {}).get("usd")))
    print(slug, len(recs), "lane cards,", sum(r["cut"] for r in rows if r["slug"] == slug), "guide cuts", flush=True)
json.dump(rows, open(ROOT / "lane_features.json", "w"), indent=1)
