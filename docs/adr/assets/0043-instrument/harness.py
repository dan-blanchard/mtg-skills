"""EDHREC discovery-study harness — durable reconstruction (2026-07-23).

Regenerated from the memory recipe after the /tmp purge; same method as the
2026-07-16 original: fetch average decks + commander pages, derive
signals/focus/tribes via deck_rank's plumbing, rank the whole in-identity
commander-legal nonland pool, measure recall of out-of-deck synergy>=0.10
targets. Run from mtg-utils (uv run python) with this dir on sys.path.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "edhrec"  # durable — survives /tmp purges
POOLS = Path(os.environ.get("MTG_STUDY_POOLS", HERE / "pools"))
CACHE.mkdir(exist_ok=True)
POOLS.mkdir(exist_ok=True, parents=True)

SYNERGY_MIN = 0.10

COMMANDERS = [
    ("Krenko, Mob Boss", "krenko-mob-boss"),
    ("Atraxa, Praetors' Voice", "atraxa-praetors-voice"),
    ("Meren of Clan Nel Toth", "meren-of-clan-nel-toth"),
    ("Talrand, Sky Summoner", "talrand-sky-summoner"),
    ("The Ur-Dragon", "the-ur-dragon"),
    ("Yuriko, the Tiger's Shadow", "yuriko-the-tigers-shadow"),
    ("Muldrotha, the Gravetide", "muldrotha-the-gravetide"),
    ("Lathril, Blade of the Elves", "lathril-blade-of-the-elves"),
    ("Wilhelt, the Rotcleaver", "wilhelt-the-rotcleaver"),
    ("Giada, Font of Hope", "giada-font-of-hope"),
    ("Kaalia of the Vast", "kaalia-of-the-vast"),
    ("Chulane, Teller of Tales", "chulane-teller-of-tales"),
    ("Feather, the Redeemed", "feather-the-redeemed"),
    ("Gishath, Sun's Avatar", "gishath-suns-avatar"),
    ("Sythis, Harvest's Hand", "sythis-harvests-hand"),
    ("Urza, Lord High Artificer", "urza-lord-high-artificer"),
    ("Zaxara, the Exemplary", "zaxara-the-exemplary"),
    ("Isshin, Two Heavens as One", "isshin-two-heavens-as-one"),
    ("Teysa Karlov", "teysa-karlov"),
    ("Niv-Mizzet, Parun", "niv-mizzet-parun"),
]


def _fetch(url: str, cache_key: str) -> dict:
    p = CACHE / f"{cache_key}.json"
    if p.exists():
        return json.loads(p.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": "mtg-skills-study"})
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = json.loads(r.read().decode())
    p.write_text(json.dumps(doc))
    time.sleep(0.5)
    return doc


def _deck_names(slug: str) -> list[str]:
    doc = _fetch(
        f"https://json.edhrec.com/pages/average-decks/{slug}.json", f"deck-{slug}"
    )
    out = []
    for line in doc.get("deck", []):
        # entries carry a "N " count prefix
        name = line.split(" ", 1)[1] if line[:1].isdigit() else line
        out.append(name)
    return out


def _synergy_targets(slug: str) -> set[str]:
    doc = _fetch(
        f"https://json.edhrec.com/pages/commanders/{slug}.json", f"cmd-{slug}"
    )
    targets: set[str] = set()
    container = doc.get("container", {}).get("json_dict", {})
    for cl in container.get("cardlists", []):
        for cv in cl.get("cardviews", []):
            if (cv.get("synergy") or 0) >= SYNERGY_MIN:
                targets.add(cv["name"])
    return targets


def _bulk_by_name() -> dict[str, dict]:
    from mtg_utils.bulk_loader import default_bulk_path, load_bulk_cards

    by_name: dict[str, dict] = {}
    for c in load_bulk_cards(default_bulk_path()):
        # art-series records poison first-wins name indexes (memory trap)
        if c.get("layout") == "art_series":
            continue
        front_type = (c.get("type_line") or "").split(" // ")[0]
        if front_type == "Card":
            continue
        for key in (c.get("name") or "", (c.get("name") or "").split(" // ")[0]):
            if key and key not in by_name:
                by_name[key] = c
    return by_name


def rank_one(args: tuple[str, str]) -> str:
    name, slug = args
    from mtg_utils._deck_forge._ir_lookup import ir_for
    from mtg_utils._deck_forge.pair_reads import build_pair_context
    from mtg_utils._deck_forge.ranking import score_candidate
    from mtg_utils._deck_forge.signals import ranked_signals_and_payoffs
    from mtg_utils.deck_rank import _deck_tribes, _focus_sets
    from mtg_utils.hydrated_deck import HydratedDeck

    out_path = POOLS / f"{slug}.jsonl"
    if out_path.exists():
        return f"{slug}: cached"

    by_name = _bulk_by_name()
    cmd_rec = by_name[name]
    deck_names = _deck_names(slug)
    records, missing = [], []
    for n in deck_names:
        rec = by_name.get(n) or by_name.get(n.split(" // ")[0])
        (records if rec is not None else missing).append(rec if rec else n)
    if name not in {r["name"] for r in records}:
        records.append(cmd_rec)
    deck = {
        "format": "commander",
        "deck_size": 100,
        "commanders": [{"name": name, "count": 1}],
        "cards": [
            {"name": r["name"], "count": 1} for r in records if r["name"] != name
        ],
    }
    hd = HydratedDeck(deck, records)
    commander_names = {name}
    signals, payoff_subjects = ranked_signals_and_payoffs(
        hd.records, commander_names, ir_for=ir_for
    )
    focus = _focus_sets(hd, signals, commander_names, payoff_subjects)
    tribes = _deck_tribes(hd)

    identity = set(cmd_rec.get("color_identity") or [])
    assert identity, f"{name}: empty color identity — bad record pick"
    in_deck = {r["name"] for r in records} | set(deck_names)
    pool, seen = [], set()
    for c in by_name.values():
        n = c.get("name") or ""
        if n in seen or n in in_deck:
            continue
        seen.add(n)
        if (c.get("legalities") or {}).get("commander") != "legal":
            continue
        if not set(c.get("color_identity") or []) <= identity:
            continue
        front_type = (c.get("type_line") or "").split(" // ")[0]
        if "Land" in front_type:
            continue
        pool.append(c)

    pair_ctx = build_pair_context([cmd_rec], records)
    rows = []
    for c in pool:
        sc = score_candidate(
            c,
            active_signals=signals,
            focus_sets=focus,
            deck_tribes=tribes,
            _ir_resolved=(ir_for(c),),
            pair_ctx=pair_ctx,
        )
        rows.append(
            {
                "name": c["name"],
                "score": sc["synergy_score"],
                "pair": sc["pair_score"],
                "pairs": [p["pair"] for p in sc.get("pairs", [])],
                "clusters": sc["clusters"],
                "price": sc["price"],
                "cmc": sc["cmc"],
            }
        )

    meta = {
        "commander": name,
        "slug": slug,
        "focus": {k: sorted(v) for k, v in focus.items()},
        "tribes": sorted(tribes),
        "deck": sorted(in_deck),
        "targets": sorted(_synergy_targets(slug)),
        "missing": missing,
        "pool_size": len(rows),
    }
    (POOLS / f"{slug}.meta.json").write_text(json.dumps(meta, indent=1))
    with out_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return f"{slug}: pool={len(rows)} targets={len(meta['targets'])}"


def rank_all(workers: int = 5) -> None:
    from mtg_utils._deck_forge.production import ensure_card_ir

    ensure_card_ir()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for msg in ex.map(rank_one, list(COMMANDERS)):
            print(msg, flush=True)


def sort_key(row: dict) -> tuple:
    price = row["price"] if row["price"] is not None else float("inf")
    return (-(row["score"] + row.get("pair", 0.0)), price, row["cmc"])


def recall(slug: str, ks=(100, 250)) -> dict:
    meta = json.loads((POOLS / f"{slug}.meta.json").read_text())
    rows = [
        json.loads(x) for x in (POOLS / f"{slug}.jsonl").read_text().splitlines()
    ]
    rows.sort(key=sort_key)
    names = [r["name"] for r in rows]
    targets = {
        t for t in meta["targets"] if t in set(names) and t not in set(meta["deck"])
    }
    out = {"slug": slug, "n_targets": len(targets)}
    for k in ks:
        out[f"recall@{k}"] = (
            len(targets & set(names[:k])) / len(targets) if targets else 0.0
        )
    ranks = sorted(names.index(t) + 1 for t in targets)
    out["median_target_rank"] = ranks[len(ranks) // 2] if ranks else None
    return out


def drift() -> tuple[float, float]:
    accs = {100: [], 250: []}
    for _, slug in COMMANDERS:
        if not (POOLS / f"{slug}.meta.json").exists():
            continue
        r = recall(slug)
        if r["n_targets"]:
            accs[100].append(r["recall@100"])
            accs[250].append(r["recall@250"])
    return (
        sum(accs[100]) / len(accs[100]),
        sum(accs[250]) / len(accs[250]),
    )


if __name__ == "__main__":
    rank_all()
