"""Compare two cube JSON snapshots.

Reports added/removed/quantity-changed cards between an old and new cube.
With ``--metrics``, also reports balance aggregate deltas (color counts,
removal density, fixing density) — useful for impact-checking proposed
cuts/adds during the tuning pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path


def _name_qty_map(cube: dict) -> dict[str, int]:
    """Flatten cube.cards (+ commander_pool) into a name → quantity dict."""
    counts: dict[str, int] = {}
    for entry in cube.get("cards", []) or []:
        name = entry["name"]
        qty = int(entry.get("quantity", 1))
        counts[name] = counts.get(name, 0) + qty
    for entry in cube.get("commander_pool", []) or []:
        name = entry["name"]
        qty = int(entry.get("quantity", 1))
        counts[name] = counts.get(name, 0) + qty
    return counts


def cube_diff(
    old: dict,
    new: dict,
    *,
    old_hydrated: list[dict] | None = None,
    new_hydrated: list[dict] | None = None,
    include_metrics: bool = False,
) -> dict:
    """Compare two cubes; optionally include balance-metric deltas."""
    old_counts = _name_qty_map(old)
    new_counts = _name_qty_map(new)

    added = sorted(
        (
            {"name": name, "quantity": new_counts[name]}
            for name in new_counts
            if name not in old_counts
        ),
        key=lambda x: x["name"],
    )
    removed = sorted(
        (
            {"name": name, "quantity": old_counts[name]}
            for name in old_counts
            if name not in new_counts
        ),
        key=lambda x: x["name"],
    )
    changed = sorted(
        (
            {
                "name": name,
                "old_quantity": old_counts[name],
                "new_quantity": new_counts[name],
            }
            for name in old_counts
            if name in new_counts and old_counts[name] != new_counts[name]
        ),
        key=lambda x: x["name"],
    )

    result: dict = {
        "added": added,
        "removed": removed,
        "changed": changed,
        "size_delta": sum(new_counts.values()) - sum(old_counts.values()),
    }

    if include_metrics and old_hydrated is not None and new_hydrated is not None:
        from mtg_utils.cube_balance import cube_balance
        from mtg_utils.cube_stats import cube_stats

        old_stats = cube_stats(old, old_hydrated)
        new_stats = cube_stats(new, new_hydrated)
        old_balance = cube_balance(old, old_hydrated)
        new_balance = cube_balance(new, new_hydrated)

        result["metrics"] = {
            "color_counts_delta": {
                color: new_stats["by_color"].get(color, 0)
                - old_stats["by_color"].get(color, 0)
                for color in set(old_stats["by_color"]) | set(new_stats["by_color"])
            },
            "removal_density_pct": {
                "old": old_balance.get("removal", {}).get("density_pct"),
                "new": new_balance.get("removal", {}).get("density_pct"),
            },
            "fixing_density_pct": {
                "old": old_balance.get("fixing", {}).get("density_pct"),
                "new": new_balance.get("fixing", {}).get("density_pct"),
            },
            "land_count": {
                "old": old_stats.get("land_count"),
                "new": new_stats.get("land_count"),
            },
            "creature_count": {
                "old": old_stats.get("creature_count"),
                "new": new_stats.get("creature_count"),
            },
        }

    return result


def render_text_report(diff: dict) -> str:
    lines: list[str] = []
    added = diff.get("added", [])
    removed = diff.get("removed", [])
    changed = diff.get("changed", [])
    lines.append(
        f"cube-diff: +{len(added)} added, -{len(removed)} removed, "
        f"{len(changed)} quantity changes (size delta {diff.get('size_delta', 0):+d})"
    )

    if added:
        lines.append("")
        lines.append("Added:")
        for e in added[:30]:
            qty = f" x{e['quantity']}" if e["quantity"] > 1 else ""
            lines.append(f"  + {e['name']}{qty}")
        if len(added) > 30:
            lines.append(f"  ... and {len(added) - 30} more")

    if removed:
        lines.append("")
        lines.append("Removed:")
        for e in removed[:30]:
            qty = f" x{e['quantity']}" if e["quantity"] > 1 else ""
            lines.append(f"  - {e['name']}{qty}")
        if len(removed) > 30:
            lines.append(f"  ... and {len(removed) - 30} more")

    if changed:
        lines.append("")
        lines.append("Quantity changes:")
        for e in changed:
            lines.append(f"  ~ {e['name']}: {e['old_quantity']} → {e['new_quantity']}")

    metrics = diff.get("metrics")
    if metrics:
        lines.append("")
        lines.append("Metric deltas:")
        delta = metrics.get("color_counts_delta", {})
        parts = [
            f"{c}:{delta[c]:+d}"
            for c in ("W", "U", "B", "R", "G")
            if c in delta and delta[c] != 0
        ]
        if parts:
            lines.append("  colors: " + ", ".join(parts))
        rd = metrics.get("removal_density_pct", {})
        if rd.get("old") is not None:
            lines.append(
                f"  removal density: {rd['old']}% → {rd['new']}% "
                f"({(rd['new'] or 0) - (rd['old'] or 0):+.1f}pp)"
            )
        fd = metrics.get("fixing_density_pct", {})
        if fd.get("old") is not None:
            lines.append(
                f"  fixing density: {fd['old']}% → {fd['new']}% "
                f"({(fd['new'] or 0) - (fd['old'] or 0):+.1f}pp)"
            )

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("old_path", type=click.Path(exists=True, path_type=Path))
@click.argument("new_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--old-hydrated",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Hydrated card data for the old cube (required for --metrics).",
)
@click.option(
    "--new-hydrated",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Hydrated card data for the new cube (required for --metrics).",
)
@click.option(
    "--metrics",
    is_flag=True,
    default=False,
    help="Include balance metric deltas. Requires --old-hydrated and --new-hydrated.",
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
    old_path: Path,
    new_path: Path,
    old_hydrated: Path | None,
    new_hydrated: Path | None,
    output_path: Path | None,
    *,
    metrics: bool,
    emit_json: bool,
):
    """Compare two cube JSON snapshots."""
    old_content = old_path.read_text(encoding="utf-8")
    new_content = new_path.read_text(encoding="utf-8")
    old_cube = json.loads(old_content)
    new_cube = json.loads(new_content)

    if metrics and (not old_hydrated or not new_hydrated):
        raise click.UsageError(
            "--metrics requires both --old-hydrated and --new-hydrated"
        )

    old_hyd = (
        json.loads(old_hydrated.read_text(encoding="utf-8")) if old_hydrated else None
    )
    new_hyd = (
        json.loads(new_hydrated.read_text(encoding="utf-8")) if new_hydrated else None
    )

    result = cube_diff(
        old_cube,
        new_cube,
        old_hydrated=old_hyd,
        new_hydrated=new_hyd,
        include_metrics=metrics,
    )

    if output_path is None:
        output_path = sha_keyed_path(
            "cube-diff",
            old_content,
            new_content,
            str(metrics),
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
