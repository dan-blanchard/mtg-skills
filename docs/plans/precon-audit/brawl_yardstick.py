"""The Brawl yardstick: do the tuner's adds have better measured results than its cuts?

A yardstick that needs neither the upgrade guides nor a game engine (Dan, 2026-11-28).
Untapped publishes, per Competitive Brawl commander, each card's games and wins with
the card in hand and with it in the deck and never in hand (``_arena_meta.card_stats``).
This tunes real ladder lists and prices each proposed swap by those results.

    cd mtg-utils && uv run python ../docs/plans/precon-audit/brawl_yardstick.py OUT \
        [--meta off] [--commanders 20] [--mine deck.json ...] [--swaps 10]

- The decks: the most-played list of each of the ``--commanders`` most-played
  commanders (Platinum and up, the last three months), and each ``--mine`` deck (a
  parsed deck JSON), reported on its own line.
- The tune: ``deck-tune --max-swaps N`` with a wildcard budget wide enough that cost
  never decides, and ``--meta`` as given. ``off`` is the tuner reading cards alone;
  ``auto`` also lets it read the commander's published lists (ADR-0059).
- A card's worth under its commander: its lift (win rate in hand minus win rate in the
  deck and never in hand) times how often it reaches the hand, in win-rate points. A
  thin card's lift is pulled toward the card's lift under every commander.
- A swap's worth is its add's minus its cut's. A swap is priced only when both cards
  have results under the commander.

The tuner never reads these results; this only scores what it proposes. Needs a fresh
``arena-meta --format competitive_brawl`` cache and its signed-in session. Holds the
precon runs' machine lock (``misses.py``): one heavy run at a time.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mtg_utils._arena_meta import card_stats as cs
from mtg_utils._arena_meta import meta as m
from mtg_utils._arena_meta.untapped import cached_snapshot
from mtg_utils.card_pool import CardPool

EVENT = "Brawl_Ladder"
WILDCARDS = "mythic=20,rare=40,uncommon=60,common=60"
#: A card's games under the commander before its results price a swap.
MIN_DECK_GAMES = 400
WORKERS = 4


def card_worth(mine: dict, overall: dict) -> dict[str, tuple[float, float]]:
    """Card -> (worth, standard error): the card's effect on the deck's win rate
    under this commander. Its lift is shrunk toward its lift under every commander
    (plus this commander's average offset from that): the spread of own-minus-overall
    beyond sampling noise is the prior's width."""
    gaps, noise = [], []
    for name, res in mine.items():
        base = overall.get(name)
        if (
            res.lift is None
            or not res.lift_se
            or base is None
            or base.lift is None
            or res.deck.matches < MIN_DECK_GAMES
        ):
            continue
        gaps.append(res.lift - base.lift)
        noise.append(res.lift_se**2 + (base.lift_se or 0) ** 2)
    if not gaps:
        return {}
    offset = sum(gaps) / len(gaps)
    spread = sum((g - offset) ** 2 for g in gaps) / len(gaps) - sum(noise) / len(noise)
    tau2 = max(1e-5, spread)
    out: dict[str, tuple[float, float]] = {}
    for name, res in mine.items():
        base = overall.get(name)
        if (
            res.lift is None
            or not res.lift_se
            or base is None
            or base.lift is None
            or res.deck.matches < MIN_DECK_GAMES
        ):
            continue
        own, prior = 1 / res.lift_se**2, 1 / tau2
        lift = (res.lift * own + (base.lift + offset) * prior) / (own + prior)
        seen = res.in_hand.matches / res.deck.matches
        out[name] = (lift * seen, seen / math.sqrt(own + prior))
    return out


def as_deck(commanders: tuple[str, ...], main: tuple[tuple[str, int], ...]) -> dict:
    return {
        "format": "competitive_brawl",
        "commanders": [{"name": n, "quantity": 1} for n in commanders],
        "cards": [{"name": n, "quantity": c} for n, c in main],
    }


def tune(deck: Path, out: Path, meta: str, swaps: int) -> dict:
    if not out.exists():
        subprocess.run(
            [
                "uv",
                "run",
                "deck-tune",
                str(deck),
                "--max-swaps",
                str(swaps),
                "--wildcards",
                WILDCARDS,
                "--meta",
                meta,
                "--output",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    return json.loads(out.read_text())


def score(result: dict, worth: dict[str, tuple[float, float]]) -> dict:
    rows = []
    for swap in result.get("swaps") or []:
        cut, add = swap["cut"]["name"], swap["add"]["name"]
        row = {"cut": cut, "add": add, "issue": swap.get("issue")}
        if cut in worth and add in worth:
            row["worth"] = round(100 * (worth[add][0] - worth[cut][0]), 3)
            row["se"] = round(100 * math.hypot(worth[add][1], worth[cut][1]), 3)
        rows.append(row)
    priced = [r for r in rows if "worth" in r]
    return {
        "swaps": len(rows),
        "priced": len(priced),
        "worth": round(sum(r["worth"] for r in priced), 3),
        "se": round(math.sqrt(sum(r["se"] ** 2 for r in priced)), 3),
        "swaps_better": sum(r["worth"] > 0 for r in priced),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--meta", default="off")
    parser.add_argument("--commanders", type=int, default=20)
    parser.add_argument("--swaps", type=int, default=10)
    parser.add_argument("--mine", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    lock = (Path(tempfile.gettempdir()) / "precon-misses.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    (args.out / "decks").mkdir(parents=True, exist_ok=True)
    pool = CardPool.load(None)
    snap = cached_snapshot(EVENT)
    if snap is None:
        sys.exit("no cached meta: run `arena-meta --format competitive_brawl`")
    period = int(snap.period["id"])
    everything = cs.load_card_stats(
        EVENT, [cs.EVERY_COMMANDER], period_id=period, pool=pool
    )[cs.EVERY_COMMANDER]
    overall = cs.card_results(everything)
    games = everything["games_by_partition"]

    def plat(key: str) -> int:
        return sum(games[key].get(r, 0) for r in m.DEFAULT_RANKS)

    lists: dict[int, list[m.MetaDeck]] = {}
    for deck in snap.decks:
        lists.setdefault(deck.archetype, []).append(deck)
    jobs: list[dict] = []
    for key in sorted(
        (k for k in games if k != cs.EVERY_COMMANDER), key=plat, reverse=True
    ):
        arch = int(key)
        if arch not in lists or arch not in snap.archetypes:
            continue
        best = max(
            lists[arch],
            key=lambda d: sum(
                d.stats[r].matches for r in m.DEFAULT_RANKS if r in d.stats
            ),
        )
        path = args.out / "decks" / f"ladder-{len(jobs):02d}.json"
        path.write_text(json.dumps(as_deck(best.commanders, best.main)))
        jobs.append(
            {
                "kind": "ladder",
                "arch": arch,
                "commander": snap.archetypes[arch].name,
                "commander_games": plat(key),
                "deck": path,
            }
        )
        if len(jobs) == args.commanders:
            break
    for path in args.mine:
        deck = json.loads(path.read_text())
        match = m.resolve(snap, deck=deck, archetype=None)
        if match is None:
            print(f"{path}: matches no meta archetype; skipped", file=sys.stderr)
            continue
        key = str(match.archetype.id)
        jobs.append(
            {
                "kind": "mine",
                "arch": match.archetype.id,
                "commander": match.archetype.name,
                "commander_games": plat(key) if key in games else 0,
                "deck": path,
            }
        )
    stats = cs.load_card_stats(
        EVENT, sorted({j["arch"] for j in jobs}), period_id=period, pool=pool
    )

    def run(job: dict) -> dict:
        name = f"{job['kind']}-{Path(job['deck']).stem}"
        result = tune(
            job["deck"],
            args.out / f"tune-{args.meta}-{name}.json",
            args.meta,
            args.swaps,
        )
        worth = card_worth(cs.card_results(stats[job["arch"]]), overall)
        # the level a swap drawn at random would score: a priced card outside the
        # deck for a priced nonland card inside it
        held = {c["name"] for c in json.loads(Path(job["deck"]).read_text())["cards"]}
        inside = [
            w for n, (w, _se) in worth.items() if n in held and n not in snap.lands
        ]
        outside = [
            w for n, (w, _se) in worth.items() if n not in held and n not in snap.lands
        ]
        random_swap = (
            100 * (sum(outside) / len(outside) - sum(inside) / len(inside))
            if inside and outside
            else None
        )
        scored = score(result, worth)
        return {
            **{k: v for k, v in job.items() if k != "deck"},
            "deck": str(job["deck"]),
            **scored,
            "random_swap_worth": None if random_swap is None else round(random_swap, 3),
            "random_level": (
                None
                if random_swap is None
                else round(random_swap * scored["priced"], 3)
            ),
        }

    with ThreadPoolExecutor(WORKERS) as workers:
        rows = list(workers.map(run, jobs))
    summary: dict = {"meta": args.meta, "period": period, "swaps_asked": args.swaps}
    for kind in ("ladder", "mine"):
        mine = [r for r in rows if r["kind"] == kind and r["priced"]]
        if not mine:
            continue
        worths = [r["worth"] for r in mine]
        mean = sum(worths) / len(worths)
        spread = (
            math.sqrt(
                sum((w - mean) ** 2 for w in worths) / (len(worths) - 1) / len(worths)
            )
            if len(worths) > 1
            else 0.0
        )
        summary[kind] = {
            "decks": len(mine),
            "mean_worth_points": round(mean, 2),
            "se_across_decks": round(spread, 2),
            "decks_better": sum(w > 0 for w in worths),
            "swaps": sum(r["swaps"] for r in mine),
            "swaps_priced": sum(r["priced"] for r in mine),
            "swaps_better": sum(r["swaps_better"] for r in mine),
            "mean_random_level_points": round(
                sum(r["random_level"] or 0.0 for r in mine) / len(mine), 2
            ),
        }
    (args.out / f"yardstick-{args.meta}.json").write_text(
        json.dumps({"summary": summary, "decks": rows}, indent=1)
    )
    print(json.dumps(summary, indent=1))
    for r in rows:
        print(
            f"{r['kind']:>6} {r['worth']:+6.2f} ±{r['se']:.2f}  "
            f"{r['priced']}/{r['swaps']} "
            f"priced, {r['swaps_better']} better, random {r['random_level']}  "
            f"{r['commander']}"
        )


if __name__ == "__main__":
    main()
