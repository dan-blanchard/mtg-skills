"""How many swaps, and how much money, each upgrade guide spends — the basis for
the rerun recipe's --max-swaps and --budget (docs/plans/precon-audit-2026-10-18.md).

    cd mtg-utils && uv run python ../docs/plans/precon-audit/guide_sizes.py ROOT

Per source of each articles/<Name>.md: its cuts and adds (rows whose "Source #"
names it), its stated budget (the Sources line), and the summed current price of
its adds (the cheapest printing the card pool lists). Prints per-guide rows and
the medians.
"""
import pathlib, re, statistics, sys

from mtg_utils.card_pool import CardPool


def rows(md, header):
    sec = md.split(f"## {header}", 1)
    out = []
    if len(sec) < 2:
        return out
    for line in sec[1].split("\n## ", 1)[0].splitlines():
        if not line.startswith("|") or "---" in line or line.lower().startswith("| card"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3:
            names = [n.strip() for n in re.split(r"\s*(?:;|/(?!/))\s*", cells[0]) if n.strip()]
            srcs = {int(x) for x in re.findall(r"\b(\d)\b", cells[2].split("(")[0])}
            out.append((names, srcs))
    return out


def main(root):
    pool = CardPool.load(None)
    table = []
    for art in sorted((root / "articles").glob("*.md")):
        md = art.read_text()
        sources = re.findall(r"^(\d)\. (.*)$", md.split("## Sources", 1)[1].split("\n## ", 1)[0], re.M)
        cuts, adds = rows(md, "Recommended cuts"), rows(md, "Recommended adds")
        for num, line in sources:
            n = int(num)
            c = sum(len(names) for names, s in cuts if n in s)
            a_names = [nm for names, s in adds if n in s for nm in names]
            spend = 0.0
            for nm in a_names:
                rec = pool.by_name.get(nm) or pool.by_name.get(nm.split(" // ")[0])
                usd = (rec or {}).get("prices", {}).get("usd")
                spend += float(usd) if usd else 0.0
            m = re.search(r"\$\s?(\d+)", line)
            table.append((art.stem, n, c, len(a_names), int(m.group(1)) if m else None, round(spend, 2)))
    for r in table:
        print(f"{r[0][:22]:22s} src{r[1]} cuts={r[2]:3d} adds={r[3]:3d} stated={r[4]} add-price=${r[5]}")
    sized = [r for r in table if r[2] or r[3]]
    print(f"\nguides with lists: {len(sized)}")
    print("median cuts", statistics.median(r[2] for r in sized), "| median adds", statistics.median(r[3] for r in sized),
          "| median swaps (max of the two)", statistics.median(max(r[2], r[3]) for r in sized))
    stated = [r[4] for r in sized if r[4] is not None]
    print("stated budgets:", sorted(stated), "median", statistics.median(stated) if stated else None)
    print("median add price", statistics.median(r[5] for r in sized), "| quartiles",
          statistics.quantiles([r[5] for r in sized], n=4))


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
