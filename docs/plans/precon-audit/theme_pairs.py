"""The guide pairs a theme-card quality read is fitted on (the 2026-10-31 grilling).

A theme page dump (``PRECON_PAGE_DUMP_DIR`` under the reads-first S1 order: need
fit, main lanes served, synergy, play-rate, price) holds every theme page a design
precon's tune ranked. For each guide add on such a page, the pair set holds (guide
add, other) for every ON-PLAN non-guide card the order placed above it, within the
same page and the same card type — the mistakes a quality read must fix. "On plan"
is a card that supplies one of the commander's specific needs or serves one of the
deck's main lanes. A consensus add (several guides) counts once per guide, so the
same (add, other) pair repeats once per guide naming the add.

    uv run python ../docs/plans/precon-audit/theme_pairs.py DUMP_DIR ROOT OUT.json

Writes ``{"creature": [...], "noncreature_permanent": [...], "spell": [...]}``, each
pair ``{"deck", "avenue", "preferred", "other", "pos_preferred", "pos_other",
"features": {name: {...}}}`` with the dump's per-card features (need, lanes,
synergy, rank, cmc, price, type_line). The held-out 20 is never read here.
"""

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from misses import norm  # noqa: E402
from scoreboard import guide_counts  # noqa: E402

TYPES = ("creature", "noncreature_permanent", "spell")


def card_type(type_line: str | None) -> str | None:
    front = (type_line or "").split("//")[0]
    if "Land" in front:
        return None
    if "Creature" in front:
        return "creature"
    if "Instant" in front or "Sorcery" in front:
        return "spell"
    if any(t in front for t in ("Artifact", "Enchantment", "Planeswalker", "Battle")):
        return "noncreature_permanent"
    return None


def guide_adds(root: pathlib.Path, name: str) -> collections.Counter:
    """Guide add name (normalized) -> how many of the precon's guides name it
    (the scoreboard's own ``guide_counts``, off the rows' ``Source #`` cell)."""
    md = (root / "articles" / f"{name}.md").read_text()
    return collections.Counter(guide_counts(md, "Recommended adds"))


def pairs_for(name: str, pages: list[dict], adds: collections.Counter) -> dict[str, list]:
    out = {t: [] for t in TYPES}
    for page in pages:
        cards = page["cards"]
        by_key = {norm(c["name"]): i for i, c in enumerate(cards) if c.get("name")}
        for key, weight in adds.items():
            i = by_key.get(key)
            if i is None:
                continue
            add = cards[i]
            t = card_type(add.get("type_line"))
            if t is None:
                continue
            for j in range(i):
                other = cards[j]
                if norm(other["name"]) in adds:
                    continue  # another guide add above it is no mistake
                if card_type(other.get("type_line")) != t:
                    continue
                if not (other["need"] or other["lanes"]):
                    continue  # off plan: the order's own filters, not quality
                pair = {
                    "deck": name,
                    "avenue": page.get("avenue"),
                    "preferred": add["name"],
                    "other": other["name"],
                    "pos_preferred": i,
                    "pos_other": j,
                    "features": {add["name"]: add, other["name"]: other},
                }
                out[t].extend([pair] * weight)
    return out


def main(dump_dir: pathlib.Path, root: pathlib.Path, out: pathlib.Path) -> None:
    result = {t: [] for t in TYPES}
    for path in sorted(dump_dir.glob("*.jsonl")):
        name = path.stem
        pages = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        adds = guide_adds(root, name)
        for t, pairs in pairs_for(name, pages, adds).items():
            result[t].extend(pairs)
    json.dump(result, open(out, "w"), indent=1)
    for t in TYPES:
        decks = {p["deck"] for p in result[t]}
        preferred = {p["preferred"] for p in result[t]}
        print(f"{t:22s} pairs {len(result[t]):5d} | guide adds {len(preferred):3d} | decks {len(decks)}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))
