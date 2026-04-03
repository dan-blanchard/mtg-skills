"""Multi-format MTG deck list parser."""

import contextlib
import csv
import io
import json
import re
from pathlib import Path

import click


def _detect_format(content: str) -> str:
    lines = content.strip().splitlines()
    if not lines:
        return "plain"

    first_line = lines[0].strip()
    if "," in first_line and any(
        kw in first_line.lower() for kw in ("quantity", "name", "count")
    ):
        return "csv"

    if any(line.strip().startswith("//") for line in lines):
        return "moxfield"

    non_empty = [line for line in lines if line.strip()]
    if non_empty and all(re.match(r"^\d+\s+", line) for line in non_empty):
        return "mtgo"

    return "plain"


def _parse_moxfield(content: str) -> dict:
    commanders: list[str] = []
    cards: list[dict] = []
    current_section = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("//"):
            current_section = line.lstrip("/").strip().lower()
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
        else:
            quantity = 1
            name = line

        if current_section == "commander":
            commanders.append(name)
        else:
            cards.append({"name": name, "quantity": quantity})

    return {"commanders": commanders, "cards": cards}


def _parse_mtgo(content: str) -> dict:
    cards: list[dict] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
            cards.append({"name": name, "quantity": quantity})

    return {"commanders": [], "cards": cards}


def _parse_csv(content: str) -> dict:
    cards: list[dict] = []
    reader = csv.DictReader(io.StringIO(content))

    for row in reader:
        name = None
        for key in row:
            if key is not None and key.strip().lower() in (
                "name",
                "card name",
                "card_name",
            ):
                name = row[key].strip()
                # Reconstruct name if it contained commas (overflow into row[None])
                overflow = row.get(None)
                if overflow:
                    name = name + ", " + ", ".join(part.strip() for part in overflow)
                break

        if not name:
            continue

        quantity = 1
        for key in row:
            if key is not None and key.strip().lower() in ("quantity", "count", "qty"):
                with contextlib.suppress(ValueError, TypeError):
                    quantity = int(row[key].strip())
                break

        cards.append({"name": name, "quantity": quantity})

    return {"commanders": [], "cards": cards}


def _parse_plain(content: str) -> dict:
    cards: list[dict] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
        else:
            quantity = 1
            name = line

        cards.append({"name": name, "quantity": quantity})

    return {"commanders": [], "cards": cards}


# Matches Moxfield set code + collector number suffix: " (SET) 123" or " (SET) 123a"
_SET_CODE_PATTERN = re.compile(r"\s+\([A-Z0-9]+\)\s+\S+$")


def _strip_set_code(name: str) -> str:
    """Remove Moxfield-style set code and collector number from a card name."""
    return _SET_CODE_PATTERN.sub("", name)


_PARSERS = {
    "moxfield": _parse_moxfield,
    "mtgo": _parse_mtgo,
    "csv": _parse_csv,
    "plain": _parse_plain,
}


def parse_deck(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    fmt = _detect_format(content)
    result = _PARSERS[fmt](content)

    # Strip Moxfield-style set codes from all names
    result["commanders"] = [_strip_set_code(c) for c in result["commanders"]]
    for card in result["cards"]:
        card["name"] = _strip_set_code(card["name"])

    return result


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
def main(deck_path: Path):
    """Parse a deck list file and output JSON."""
    result = parse_deck(deck_path)
    click.echo(json.dumps(result, indent=2))
