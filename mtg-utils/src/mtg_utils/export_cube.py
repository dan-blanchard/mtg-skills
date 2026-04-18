"""Export a canonical cube JSON to CubeCobra CSV or plain text.

The CSV output is designed to round-trip through CubeCobra's
"replace with CSV import" feature. Per-card overrides (``cube_color``,
``cube_cmc``, ``tags``) are preserved in the ``Color Category``, ``CMC``,
and ``Tags`` columns so the cube identity isn't lost on re-import.

Plain text emits ``N CardName`` lines, optionally with a ``//Commander``
section header for cubes with a dedicated commander pool.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import click

CUBECOBRA_COLUMNS = [
    "name",
    "CMC",
    "Type",
    "Color",
    "Set",
    "Collector Number",
    "Rarity",
    "Color Category",
    "Status",
    "Finish",
    "Maybeboard",
    "Image URL",
    "Image Back URL",
    "Tags",
    "Notes",
    "MTGO ID",
]


def _card_to_csv_row(entry: dict) -> dict:
    """Map a canonical cube card entry onto CubeCobra CSV columns."""
    tags = entry.get("tags") or []
    return {
        "name": entry["name"],
        "CMC": entry.get("cube_cmc", "") or "",
        "Type": "",
        "Color": entry.get("cube_color", "") or "",
        "Set": "",
        "Collector Number": "",
        "Rarity": "",
        "Color Category": entry.get("cube_color", "") or "",
        "Status": "Owned",
        "Finish": "Non-foil",
        "Maybeboard": "false",
        "Image URL": "",
        "Image Back URL": "",
        "Tags": ", ".join(tags) if tags else "",
        "Notes": "",
        "MTGO ID": "",
    }


def export_csv(cube: dict) -> str:
    """Emit a CubeCobra-compatible CSV for the cube's mainboard."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CUBECOBRA_COLUMNS)
    writer.writeheader()
    for entry in cube.get("cards", []) or []:
        qty = int(entry.get("quantity", 1))
        row = _card_to_csv_row(entry)
        for _ in range(qty):
            writer.writerow(row)
    return buf.getvalue()


def export_text(cube: dict) -> str:
    """Emit a plain ``N CardName`` list, with optional commander section."""
    lines: list[str] = []
    commander_pool = cube.get("commander_pool") or []
    if commander_pool:
        lines.append("//Commander")
        for entry in commander_pool:
            qty = int(entry.get("quantity", 1))
            lines.append(f"{qty} {entry['name']}")
        lines.append("")
        lines.append("//Mainboard")
    for entry in cube.get("cards", []) or []:
        qty = int(entry.get("quantity", 1))
        lines.append(f"{qty} {entry['name']}")
    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["csv", "text"]),
    default="csv",
    show_default=True,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout.",
)
def main(cube_path: Path, output_format: str, output_path: Path | None):
    """Export a canonical cube JSON to CubeCobra CSV or plain text."""
    cube = json.loads(cube_path.read_text(encoding="utf-8"))

    commander_pool = cube.get("commander_pool") or []
    if output_format == "csv" and commander_pool:
        click.echo(
            f"export-cube: WARNING: CSV export drops the commander pool "
            f"({len(commander_pool)} cards). CubeCobra's CSV import doesn't "
            "have a commander-pool column — use --format text (which writes "
            "a //Commander section) if you need to preserve the pool on re-import.",
            err=True,
        )

    content = export_csv(cube) if output_format == "csv" else export_text(cube)

    if output_path is not None:
        if output_path.resolve() == cube_path.resolve():
            raise click.UsageError(
                "--output would overwrite the input cube file; pass a different path."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        total = sum(int(e.get("quantity", 1)) for e in cube.get("cards", []) or [])
        cmd_total = sum(
            int(e.get("quantity", 1)) for e in cube.get("commander_pool", []) or []
        )
        summary = f"export-cube: {total} cards"
        if cmd_total:
            summary += f", {cmd_total} commanders"
        summary += f" → {output_path.resolve()} ({output_format})"
        click.echo(summary)
        click.echo(f"Full JSON: {cube_path.resolve()}")
    else:
        click.echo(content, nl=False)
