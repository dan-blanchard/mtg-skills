import json, sys, pathlib
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
d = json.load(open(src))["data"]
lines = ["Commander"] + [f"{c['count']} {c['name']}" for c in d["commander"]] + ["", "Deck"]
lines += [f"{c['count']} {c['name']}" for c in d["mainBoard"]]
out.write_text("\n".join(lines) + "\n")
print(src.stem, d["name"], "|", ", ".join(c["name"] for c in d["commander"]), "|", sum(c["count"] for c in d["mainBoard"]) + sum(c["count"] for c in d["commander"]))
