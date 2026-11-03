"""One precon's tuner proposal beside its upgrade guide, for a deckbuilder's read.

    uv run python deck_report.py <misses.json> <Name> [...]
"""

import json
import pathlib
import re
import sys

import os
ROOT = pathlib.Path(os.environ.get("DECK_ROOT", str(pathlib.Path.home() / "mtg/tuner-work/precons")))


def section(md: str, header: str) -> str:
    parts = md.split(f"## {header}", 1)
    if len(parts) < 2:
        return ""
    return parts[1].split("\n## ", 1)[0].strip()


def table_names(block: str) -> list[str]:
    out = []
    for line in block.splitlines():
        if line.startswith("|") and "---" not in line and not line.lower().startswith("| card"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2:
                out.append(f"{cells[0]} — {cells[1]}")
    return out


def main(path: str, names: list[str]) -> None:
    data = json.load(open(path))
    for name in names or sorted(data):
        m = data[name]
        md = (ROOT / "articles" / f"{name}.md").read_text()
        print("=" * 100)
        print(name, "| swaps", len(m["swaps"]), "| guide cuts hit",
              sum(1 for _n, w in m["cuts"] if w == "cut"), "/", len(m["cuts"]),
              "| guide adds hit", sum(1 for _n, w in m["adds"] if w == "added"), "/", len(m["adds"]))
        print("PLAN:", re.sub(r"\s+", " ", section(md, "Deck plan (as the articles describe it)"))[:600])
        print("WEAKNESSES:", re.sub(r"\s+", " ", section(md, "Weaknesses the articles name"))[:500])
        print("CONSENSUS:", section(md, "Consensus one-liner")[:300])
        print("-- guide cuts:", "; ".join(table_names(section(md, "Recommended cuts")))[:900])
        print("-- guide adds:", "; ".join(table_names(section(md, "Recommended adds")))[:1200])
        print("-- tuner swaps:")
        for kind, cut, add, why in m["swaps"]:
            print(f"   {cut:32} -> {add:32} | {kind:16} | {why[:70]}")
        missed_adds = [f"{n} ({w})" for n, w in m["adds"] if w != "added"]
        print("-- guide adds not taken:", "; ".join(missed_adds)[:1200])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
