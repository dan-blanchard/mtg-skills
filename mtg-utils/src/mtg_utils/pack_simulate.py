"""Seeded pack generation for a cube.

Generates draft packs using configurable slot templates (per cube or the
``cube_config.PACK_TEMPLATES`` defaults of sizes 9/11/15, ported from
cube-utils). Commander cubes get a dedicated commander pack from the
``commander_pool``.

``--simulate-drafts N`` runs N random opening packs and reports aggregate
category distribution so the designer can sanity-check that packs feel
balanced. There is no pick AI — the simulation doesn't model drafting
choices, only pack composition.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import build_card_lookup, classify_cube_category
from mtg_utils.cube_config import get_pack_templates

MONO_COLORS = ("W", "U", "B", "R", "G")


def _classify_cube(cube: dict, hydrated: list[dict]) -> dict[str, list[dict]]:
    """Partition cube.cards into draft-category buckets.

    Cards are emitted as ``{name, scryfall_id?}`` entries, repeated by
    quantity so random picks scale with duplicated slots (which is rare
    in cubes but handled for completeness).
    """
    lookup = build_card_lookup(hydrated)
    buckets: dict[str, list[dict]] = {
        "W": [],
        "U": [],
        "B": [],
        "R": [],
        "G": [],
        "M": [],
        "L": [],
        "F": [],
        "C": [],
    }
    for entry in cube.get("cards", []):
        card = lookup.get(entry["name"])
        if card is None:
            continue
        category = classify_cube_category(card)
        for _ in range(int(entry.get("quantity", 1))):
            buckets[category].append({"name": entry["name"], "category": category})
    return buckets


def _pick_without_replacement(
    rng: random.Random, bucket: list[dict], n: int
) -> list[dict]:
    """Pick n unique cards from bucket, or fewer if the bucket runs out."""
    if n <= 0 or not bucket:
        return []
    return rng.sample(bucket, min(n, len(bucket)))


def generate_pack(
    buckets: dict[str, list[dict]], template: dict[str, int], rng: random.Random
) -> list[dict]:
    """Build a single pack according to a slot template.

    Ensures no card appears twice in the same pack even when the fixed
    mono-color slots and the extra_mono slot draw from the same color pool.
    Cards already picked for a fixed slot are excluded from the extra_mono
    pool.
    """
    pack: list[dict] = []
    picked_names: set[str] = set()

    def _pick_filtered(pool: list[dict], n: int) -> list[dict]:
        remaining = [c for c in pool if c["name"] not in picked_names]
        chosen = _pick_without_replacement(rng, remaining, n)
        picked_names.update(c["name"] for c in chosen)
        return chosen

    # Fill fixed-category slots first (mono colors, M, L, F, C).
    for slot, count in template.items():
        if slot == "extra_mono":
            continue
        pack.extend(_pick_filtered(buckets.get(slot, []), count))

    # Extra mono slots: randomly distribute across the five mono colors,
    # excluding cards already picked for fixed slots.
    extra = int(template.get("extra_mono", 0))
    if extra > 0:
        mono_pool = [c for color in MONO_COLORS for c in buckets.get(color, [])]
        pack.extend(_pick_filtered(mono_pool, extra))

    return pack


def generate_commander_pack(
    cube: dict, hydrated: list[dict], count: int, rng: random.Random
) -> list[dict]:
    """Pick `count` commanders from the commander pool."""
    lookup = build_card_lookup(hydrated)
    pool = []
    for entry in cube.get("commander_pool", []) or []:
        card = lookup.get(entry["name"])
        for _ in range(int(entry.get("quantity", 1))):
            pool.append(
                {
                    "name": entry["name"],
                    "color_identity": (card or {}).get("color_identity", []) or [],
                }
            )
    return _pick_without_replacement(rng, pool, count)


def simulate_drafts(
    buckets: dict[str, list[dict]],
    template: dict[str, int],
    n: int,
    base_seed: int,
) -> dict:
    """Generate ``n`` packs with sequential seeds and summarize distribution."""
    category_totals: dict[str, int] = {}
    unique_cards: set[str] = set()
    pack_sizes: list[int] = []
    for i in range(n):
        rng = random.Random(base_seed + i)
        pack = generate_pack(buckets, template, rng)
        pack_sizes.append(len(pack))
        for card in pack:
            category_totals[card["category"]] = (
                category_totals.get(card["category"], 0) + 1
            )
            unique_cards.add(card["name"])

    mean_per_pack = {cat: round(total / n, 2) for cat, total in category_totals.items()}
    return {
        "packs_generated": n,
        "avg_pack_size": round(sum(pack_sizes) / n, 2) if pack_sizes else 0,
        "avg_category_counts": mean_per_pack,
        "unique_cards_seen": len(unique_cards),
    }


def pack_simulate(
    cube: dict,
    hydrated: list[dict],
    *,
    pack_size: int = 15,
    seed: int = 0,
    drafts: int = 0,
    commander_pack_size: int = 4,
) -> dict:
    """Generate a single pack (and optionally simulated-draft aggregates)."""
    templates = get_pack_templates(cube)
    if pack_size not in templates:
        msg = (
            f"No template for pack size {pack_size}. Available sizes: "
            f"{sorted(templates.keys())}"
        )
        raise click.UsageError(msg)
    template = templates[pack_size]

    buckets = _classify_cube(cube, hydrated)
    rng = random.Random(seed)
    pack = generate_pack(buckets, template, rng)

    result: dict = {
        "pack_size": pack_size,
        "seed": seed,
        "template": template,
        "pack": [{"name": c["name"], "category": c["category"]} for c in pack],
        "bucket_sizes": {cat: len(lst) for cat, lst in buckets.items()},
    }

    if cube.get("commander_pool"):
        cmd_rng = random.Random(seed + 1_000_000)
        cmd_pack = generate_commander_pack(cube, hydrated, commander_pack_size, cmd_rng)
        result["commander_pack"] = [
            {"name": c["name"], "color_identity": c["color_identity"]} for c in cmd_pack
        ]

    if drafts > 0:
        result["simulation"] = simulate_drafts(buckets, template, drafts, seed)

    return result


def render_text_report(sim: dict) -> str:
    lines: list[str] = []
    pack = sim.get("pack", [])
    lines.append(
        f"pack-simulate: {len(pack)}-card pack (template size "
        f"{sim.get('pack_size')}, seed {sim.get('seed')})"
    )
    lines.append("")
    by_cat: dict[str, list[str]] = {}
    for card in pack:
        by_cat.setdefault(card["category"], []).append(card["name"])
    order = ["W", "U", "B", "R", "G", "M", "L", "F", "C"]
    for cat in order:
        if cat not in by_cat:
            continue
        lines.append(f"  [{cat}] {', '.join(by_cat[cat])}")

    cmd_pack = sim.get("commander_pack")
    if cmd_pack:
        lines.append("")
        lines.append(f"Commander pack ({len(cmd_pack)}):")
        for c in cmd_pack:
            ci = "".join(sorted(c.get("color_identity") or [])) or "C"
            lines.append(f"  {c['name']} ({ci})")

    simulation = sim.get("simulation")
    if simulation:
        lines.append("")
        lines.append(
            f"Simulation ({simulation['packs_generated']} packs): "
            f"avg size {simulation['avg_pack_size']}, "
            f"{simulation['unique_cards_seen']} unique cards seen"
        )
        avg_cats = simulation.get("avg_category_counts", {})
        parts = [f"{cat}:{avg_cats[cat]}" for cat in order if cat in avg_cats]
        if parts:
            lines.append("  avg per pack: " + ", ".join(parts))

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option("--seed", type=int, default=0, show_default=True)
@click.option(
    "--pack-size",
    type=click.Choice(["9", "11", "15"]),
    default="15",
    show_default=True,
)
@click.option(
    "--simulate-drafts",
    "draft_count",
    type=int,
    default=0,
    help="Number of packs to simulate for aggregate stats.",
)
@click.option(
    "--commander-pack-size",
    type=int,
    default=4,
    show_default=True,
    help="Number of commanders in the dedicated commander pack (if any).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
)
def main(
    cube_path: Path,
    hydrated_path: Path,
    seed: int,
    pack_size: str,
    draft_count: int,
    commander_pack_size: int,
    output_path: Path | None,
    *,
    emit_json: bool,
):
    """Generate seeded packs from a cube."""
    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)

    result = pack_simulate(
        cube,
        hydrated,
        pack_size=int(pack_size),
        seed=seed,
        drafts=draft_count,
        commander_pack_size=commander_pack_size,
    )

    if output_path is None:
        output_path = sha_keyed_path(
            "pack-simulate",
            cube_content,
            hydrated_content,
            seed,
            pack_size,
            draft_count,
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    if emit_json:
        click.echo(json.dumps(result, indent=2))
        click.echo(f"Full JSON: {output_path}")
    else:
        click.echo(render_text_report(result), nl=False)
        click.echo(f"\nFull JSON: {output_path}")
