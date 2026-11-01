"""Guide pairs from a source the tuner's order never picked: each guide's ADDS against
that same guide's CUTS of the same card type (the 2026-10-31 grilling, after the
ADR-0063 reads fitted on order-chosen pairs learned what the order overrates).

For a design precon, every (add, cut) pair of one card type, weighted by the number
of guides naming the add (a consensus add counts once per guide). The cut is a card
the precon shipped and a guide took out; the add is what came in. Design 25 only;
the held-out 20 is never read here. Names are the pool's canonical names.

    uv run python ../docs/plans/precon-audit/theme_pairs_cuts.py ROOT OUT.json

Writes ``{"creature": [...], "noncreature_permanent": [...], "spell": [...]}``, each
pair ``{"deck", "preferred", "other", "weight"}`` — features are the reader's to
compute off the pool's records (``mtg_utils._analysis.card_quality``).
"""

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from scoreboard import guide_counts  # noqa: E402
from theme_pairs import TYPES, card_type  # noqa: E402

from mtg_utils.card_pool import CardPool  # noqa: E402


def main(root: pathlib.Path, out: pathlib.Path) -> None:
    pool = CardPool.load(None)
    by_name = pool.by_name
    result = {t: [] for t in TYPES}
    for md_path in sorted((root / "articles").glob("*.md")):
        name = md_path.stem
        md = md_path.read_text()
        adds = guide_counts(md, "Recommended adds")
        cuts = guide_counts(md, "Recommended cuts")

        def records(counter: collections.Counter | dict) -> list[tuple[dict, int]]:
            rows = []
            for key, weight in counter.items():
                rec = by_name.get(key)
                if rec is None:
                    continue
                rows.append((rec, weight))
            return rows

        add_rows, cut_rows = records(adds), records(cuts)
        for add, weight in add_rows:
            t = card_type(add.get("type_line"))
            if t is None:
                continue
            for cut, _w in cut_rows:
                if card_type(cut.get("type_line")) != t or cut["name"] == add["name"]:
                    continue
                result[t].append(
                    {"deck": name, "preferred": add["name"], "other": cut["name"], "weight": weight}
                )
    json.dump(result, open(out, "w"), indent=1)
    for t in TYPES:
        decks = {p["deck"] for p in result[t]}
        preferred = {p["preferred"] for p in result[t]}
        others = {p["other"] for p in result[t]}
        print(
            f"{t:22s} pairs {len(result[t]):5d} | guide adds {len(preferred):3d} | "
            f"guide cuts {len(others):3d} | decks {len(decks)}"
        )


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
