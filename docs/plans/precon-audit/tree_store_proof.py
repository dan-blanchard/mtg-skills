"""Proof that a stored (pickled) tree reads exactly as a built one (backlog (l),
``_card_ir/tree_store``): run one sample of cards through every per-card read, with
the trees built, then read from the store, and compare.

    cd mtg-utils
    export MTG_SKILLS_CACHE_DIR=<a private cache dir>   # the store lives beside its card-data
    uv run python ../docs/plans/precon-audit/tree_store_proof.py ROOT build OUT/build.json
    uv run python ../docs/plans/precon-audit/tree_store_proof.py ROOT store OUT/fill.json
    uv run python ../docs/plans/precon-audit/tree_store_proof.py ROOT store OUT/store.json
    uv run python ../docs/plans/precon-audit/tree_store_proof.py compare OUT/build.json OUT/store.json

``build`` turns the store off (every tree built); the first ``store`` run fills the
store (start from a key no run has written: a code edit gives one) and the second
reads it — it builds only the bulk-face reads the store never holds
(``trees.reads_bulk_faces``, about 17). The sample is every card of the precons
under ROOT/decks, 3,000 random cards and every aftermath / two-face split, each
read in both ``trees_for`` orders. A card's fingerprint: its trees, its signals
with and without the membership floor, the concept arms, the role reads, the
per-card reads ``card_reads`` persists, the job scores, the ident attribution
and the object facts, hashed hash-seed independently. 2026-10-25: 4,470 cards,
none differing (build against fill against store).
"""

import dataclasses
import hashlib
import json
import os
import random
import sys
from pathlib import Path


def canon(x):
    """A hash-seed-independent structure: sets sorted, dataclasses by field."""
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return [type(x).__name__] + [
            [f.name, canon(getattr(x, f.name))] for f in dataclasses.fields(x)
        ]
    if isinstance(x, (set, frozenset)):
        return ["set"] + sorted((canon(i) for i in x), key=repr)
    if isinstance(x, dict):
        return ["dict"] + sorted(([canon(k), canon(v)] for k, v in x.items()), key=repr)
    if isinstance(x, (list, tuple)):
        return [type(x).__name__] + [canon(i) for i in x]
    return repr(x)


def h(x) -> str:
    return hashlib.sha256(repr(canon(x)).encode()).hexdigest()[:20]


def compare(a_path: str, b_path: str) -> None:
    a, b = (json.loads(Path(p).read_text()) for p in (a_path, b_path))
    differing = [oid for oid in sorted(a) if a[oid] != b.get(oid)]
    for oid in differing[:15]:
        print(oid, {k: (v, b[oid].get(k)) for k, v in a[oid].items() if v != b[oid].get(k)})
    print("differing cards", len(differing), "of", len(a))


def run(root: Path, mode: str, out: Path) -> None:
    if mode == "build":
        os.environ["MTG_SKILLS_TREE_STORE"] = "none"
    from mtg_utils._analysis import card_reads, ident_provenance, roles
    from mtg_utils._analysis.job_quality import READS, job_score
    from mtg_utils._analysis.lanes import card_advantage
    from mtg_utils._analysis.signals import extract_signals
    from mtg_utils._card_ir import trees
    from mtg_utils.card_pool import CardPool
    from mtg_utils.theme_presets import concept_arms_holding

    builds: list[str] = []
    build_trees = trees.build_trees

    def counting(oid, recs, bulk=None):
        builds.append(oid)
        return build_trees(oid, recs, bulk=bulk)

    trees.build_trees = counting
    pool = CardPool.load(None)
    records: dict[str, dict] = {}
    for deck in sorted((root / "decks").glob("*/deck.json")):
        d = json.loads(deck.read_text())
        for entry in [*(d.get("commanders") or []), *(d.get("cards") or [])]:
            r = pool.by_name.get(entry["name"])
            if r and r.get("oracle_id"):
                records[r["oracle_id"]] = r
    everything = sorted(
        {r["oracle_id"]: r for r in pool.by_name.values() if r.get("oracle_id")}.items()
    )
    for oid, r in random.Random(15).sample(everything, 3000):
        records.setdefault(oid, r)
    for oid, r in everything:
        if len(r.get("card_faces") or ()) == 2 and r.get("layout") in ("aftermath", "split"):
            records.setdefault(oid, r)
    cards = [records[k] for k in sorted(records)]

    def fingerprint(i: int, card: dict) -> dict:
        if i % 2:  # both orders of the bulk-face hazard
            with_faces, plain = trees.trees_for(card, bulk=card), trees.trees_for(card)
        else:
            plain, with_faces = trees.trees_for(card), trees.trees_for(card, bulk=card)
        free = extract_signals(card, include_membership=False)
        return {
            "plain": h(plain),
            "bulk": h(with_faces),
            "signals": h(sorted(map(canon, extract_signals(card)), key=repr)),
            "signals_free": h(sorted(map(canon, free), key=repr)),
            "arms": list(concept_arms_holding(card)),
            "role_of": sorted(roles.role_of(card)),
            "is_ramp": roles.is_ramp(card),
            "reliable_ramp": roles.is_reliable_ramp(card),
            "wipe": roles.is_board_wipe(card),
            "interaction": roles.is_interaction(card),
            "protects": roles.protects(card),
            "mana_effects": h(roles._mana_effects.__wrapped__(card)),
            "mana_gated": roles._conditionally_gated.__wrapped__(card),
            "self_return": h(card_advantage.card_self_return_routes.__wrapped__(card)),
            "has_trees": card_reads.has_trees.__wrapped__(card),
            "jobs": {job: job_score(card, job) for job in sorted(READS)},
            "attribution": h(ident_provenance.unit_idents_for(card)),
            "facts": h(trees.object_facts(card)),
        }

    result = {c["oracle_id"]: fingerprint(i, c) for i, c in enumerate(cards)}
    store = trees._tree_store()
    if store is not None:
        store.flush()
    print(mode, "cards", len(cards), "builds", len(builds), file=sys.stderr)
    out.write_text(json.dumps(result, sort_keys=True, indent=0))


if __name__ == "__main__":
    if sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3])
    else:
        run(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
