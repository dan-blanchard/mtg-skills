"""Multi-format MTG deck list parser."""

import contextlib
import csv
import io
import json
import re
from pathlib import Path

import click

from mtg_utils.format_config import FORMAT_CONFIGS


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
    commanders: list[dict] = []
    cards: list[dict] = []
    sideboard: list[dict] = []
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
            commanders.append({"name": name, "quantity": quantity})
        elif current_section == "sideboard":
            sideboard.append({"name": name, "quantity": quantity})
        else:
            cards.append({"name": name, "quantity": quantity})

    return {"commanders": commanders, "cards": cards, "sideboard": sideboard}


_ARENA_SECTION_HEADERS = frozenset(
    {
        "commander",
        "companion",
        "deck",
        "sideboard",
    }
)


def _parse_mtgo(content: str) -> dict:
    commanders: list[dict] = []
    cards: list[dict] = []
    sideboard: list[dict] = []
    current_section = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Recognise bare Arena section headers (e.g. "Commander", "Deck")
        if line.lower() in _ARENA_SECTION_HEADERS:
            current_section = line.lower()
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
            if current_section == "commander":
                commanders.append({"name": name, "quantity": quantity})
            elif current_section == "sideboard":
                sideboard.append({"name": name, "quantity": quantity})
            else:
                cards.append({"name": name, "quantity": quantity})

    return {"commanders": commanders, "cards": cards, "sideboard": sideboard}


def parse_csv(content: str) -> dict:
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

    return {"commanders": [], "cards": cards, "sideboard": []}


def _parse_plain(content: str) -> dict:
    commanders: list[dict] = []
    cards: list[dict] = []
    sideboard: list[dict] = []
    current_section = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Recognise bare Arena section headers (e.g. "Commander", "Deck")
        if line.lower() in _ARENA_SECTION_HEADERS:
            current_section = line.lower()
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
        else:
            quantity = 1
            name = line

        if current_section == "commander":
            commanders.append({"name": name, "quantity": quantity})
        elif current_section == "sideboard":
            sideboard.append({"name": name, "quantity": quantity})
        else:
            cards.append({"name": name, "quantity": quantity})

    return {"commanders": commanders, "cards": cards, "sideboard": sideboard}


# Matches Moxfield set code + collector number suffix: " (SET) 123" or " (SET) 123a"
_SET_CODE_PATTERN = re.compile(r"\s+\([A-Z0-9]+\)\s+\S+$")


def _strip_set_code(name: str) -> str:
    """Remove Moxfield-style set code and collector number from a card name."""
    return _SET_CODE_PATTERN.sub("", name)


_PARSERS = {
    "moxfield": _parse_moxfield,
    "mtgo": _parse_mtgo,
    "csv": parse_csv,
    "plain": _parse_plain,
}


def parse_deck(
    path: Path,
    *,
    format: str = "commander",  # noqa: A002
    deck_size: int | None = None,
) -> dict:
    content = path.read_text(encoding="utf-8")
    fmt = _detect_format(content)
    result = _PARSERS[fmt](content)

    config = FORMAT_CONFIGS[format]

    # For commander formats, fold any sideboard entries back into cards so
    # Arena exports that include a "Sideboard" header don't silently lose cards.
    if config.get("has_commander", True):
        result["cards"].extend(result.get("sideboard", []))
        result["sideboard"] = []

    # Strip Moxfield-style set codes from all names and merge duplicates
    # that arise from the same card appearing with different set codes
    # (e.g., "2 Ethereal Armor (DSK) 7" + "2 Ethereal Armor (RTR) 9").
    for section in ("commanders", "cards", "sideboard"):
        entries = result.get(section, [])
        for entry in entries:
            entry["name"] = _strip_set_code(entry["name"])
        merged: dict[str, int] = {}
        for entry in entries:
            name = entry["name"]
            qty = entry.get("quantity", 1)
            merged[name] = merged.get(name, 0) + qty
        result[section] = [
            {"name": name, "quantity": qty} for name, qty in merged.items()
        ]

    result["total_cards"] = sum(
        c.get("quantity", 1) for c in result["commanders"]
    ) + sum(c.get("quantity", 1) for c in result["cards"])

    result["total_sideboard"] = sum(
        c.get("quantity", 1) for c in result.get("sideboard", [])
    )

    result.setdefault("owned_cards", [])
    result.setdefault("sideboard", [])

    result["format"] = format
    result["sideboard_size"] = config.get("sideboard_size", 0)
    if deck_size is not None:
        result["deck_size"] = deck_size
    else:
        result["deck_size"] = config["deck_size"]

    return result


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "deck_format",
    type=click.Choice(sorted(FORMAT_CONFIGS.keys())),
    default="commander",
    show_default=True,
    help="Game format.",
)
@click.option(
    "--deck-size",
    type=int,
    default=None,
    help="Override deck size (default: derived from format).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write JSON to this file instead of stdout.",
)
def main(
    deck_path: Path,
    deck_format: str,
    deck_size: int | None,
    output_path: Path | None,
):
    """Parse a deck list file and output JSON."""
    result = parse_deck(deck_path, format=deck_format, deck_size=deck_size)
    payload = json.dumps(result, indent=2)
    if output_path is not None:
        if output_path.resolve() == deck_path.resolve():
            raise click.UsageError(
                "--output would overwrite the input deck file; pass a different path."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n")
        resolved = output_path.resolve()
        commander_count = len(result["commanders"])
        sideboard_count = result.get("total_sideboard", 0)
        summary = f"parse-deck: {result['total_cards']} cards"
        if commander_count:
            summary += f", {commander_count} commander(s)"
        if sideboard_count:
            summary += f", {sideboard_count} sideboard"
        click.echo(f"{summary} -> {resolved}")
    else:
        click.echo(payload)


def extract_deck_names(payload: list | dict) -> list[str]:
    """Extract card names from a plain name list or a parsed-deck JSON.

    Accepted shapes:

    * ``list[str]`` — returned as-is (non-strings filtered). No dedup;
      callers that accept duplicates (e.g., a paper deck with seven
      copies of Hare Apparent) get the literal list. ``scryfall-lookup``'s
      batch hydration relies on this: duplicates in the input are
      treated as distinct work items, and the hydrated cache dedupes
      downstream.
    * ``list[dict]`` — extracts the ``name`` field from each entry.
      Entries missing ``name`` are skipped, not errored (some Scryfall
      responses lack ``name`` in degenerate cases).
    * ``dict`` — a parsed deck JSON of the shape
      ``{commanders, cards, sideboard}``. Walks all three sections and
      dedups across them (so a legendary creature listed in both
      ``commanders`` and ``cards`` yields one name, not two) — this
      matches ``mark_owned._collect_entries(sum_duplicates=False)``.

    This is the canonical extractor; ``scryfall_lookup`` and
    ``rulings_lookup`` both delegate here rather than maintaining their
    own copies.
    """
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            return [entry["name"] for entry in payload if "name" in entry]
        return [n for n in payload if isinstance(n, str)]
    names: list[str] = []
    seen: set[str] = set()
    for section in ("commanders", "cards", "sideboard"):
        for entry in payload.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if name and name not in seen:
                names.append(name)
                seen.add(name)
    return names
