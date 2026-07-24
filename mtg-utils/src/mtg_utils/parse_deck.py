"""Multi-format MTG deck list parser.

Auto-detects Moxfield / MTGO / Arena / CSV / plain text and emits one JSON shape:
``{commanders, cards, sideboard, companion, ...}`` where every entry is
``{"name": str, "quantity": int}`` plus three OPTIONAL printing keys captured
when the source carried them (and omitted otherwise):

* ``"set"`` — lowercased set code (from a ``(C21) 263`` line suffix or a CSV
  Edition/Set column).
* ``"collector_number"`` — collector number as a string, exactly as written
  (may be non-numeric: ``"263a"``, ``"CMR-99"``, ``"263★"``).
* ``"finish"`` — ``"foil"`` or ``"etched"`` (from a trailing ``*F*`` / ``*E*``
  marker or a CSV Foil column).

The top-level ``"companion"`` list (always present, default ``[]``) holds
entries from a "Companion" section header in Arena/MTGO/plain exports. A
companion is revealed from outside the game and is not part of the deck or
sideboard (CR 702.139a-b), so its entries are kept out of ``cards`` and out of
``total_cards``.
"""

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
    companion: list[dict] = []
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
        elif current_section == "companion":
            companion.append({"name": name, "quantity": quantity})
        else:
            cards.append({"name": name, "quantity": quantity})

    return {
        "commanders": commanders,
        "cards": cards,
        "sideboard": sideboard,
        "companion": companion,
    }


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
    companion: list[dict] = []
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
            elif current_section == "companion":
                # A companion lives outside the deck and sideboard
                # (CR 702.139a-b) — never file it into ``cards``.
                companion.append({"name": name, "quantity": quantity})
            else:
                cards.append({"name": name, "quantity": quantity})

    return {
        "commanders": commanders,
        "cards": cards,
        "sideboard": sideboard,
        "companion": companion,
    }


def _csv_field(row: dict, aliases: tuple[str, ...]) -> str | None:
    """Return the stripped value of the first matching column, or None.

    Missing column and present-but-empty cell both return None, so callers can
    key optional output fields on truthiness.
    """
    for key, value in row.items():
        if key is not None and key.strip().lower() in aliases:
            if value is not None and value.strip():
                return value.strip()
            return None
    return None


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

        entry: dict = {"name": name, "quantity": quantity}

        # Optional printing columns (Moxfield CSV exports carry Edition /
        # Collector Number / Foil; other exporters use Set / Finish).
        set_code = _csv_field(row, ("edition", "set", "set code", "edition code"))
        if set_code:
            entry["set"] = set_code.lower()
        collector = _csv_field(
            row, ("collector number", "collector_number", "card number")
        )
        if collector:
            entry["collector_number"] = collector
        finish = _csv_field(row, ("foil", "finish"))
        if finish and finish.lower() in ("foil", "etched"):
            entry["finish"] = finish.lower()

        cards.append(entry)

    return {"commanders": [], "cards": cards, "sideboard": [], "companion": []}


def _parse_plain(content: str) -> dict:
    commanders: list[dict] = []
    cards: list[dict] = []
    sideboard: list[dict] = []
    companion: list[dict] = []
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
        elif current_section == "companion":
            # A companion lives outside the deck and sideboard
            # (CR 702.139a-b) — never file it into ``cards``.
            companion.append({"name": name, "quantity": quantity})
        else:
            cards.append({"name": name, "quantity": quantity})

    return {
        "commanders": commanders,
        "cards": cards,
        "sideboard": sideboard,
        "companion": companion,
    }


# Matches Moxfield/Archidekt/Arena set code + collector number suffix: " (SET) 123"
# or " (SET) 123a", plus any trailing foil/etched markers ("*F*", "*E*") those
# exporters append after the collector number, e.g. "Sol Ring (C21) 263 *F*".
# Groups: 1 = set code, 2 = collector number (kept as a string — may be
# non-numeric like "263a", "CMR-99", or "263★"), 3 = the marker tail.
_SET_CODE_PATTERN = re.compile(r"\s+\(([A-Z0-9]+)\)\s+(\S+?)((?:\s+\*\w+\*)*)$")

_FINISH_MARKERS = {"f": "foil", "e": "etched"}


def _extract_printing(name: str) -> tuple[str, dict]:
    """Split a Moxfield/Arena-style printing suffix off a card name.

    Returns ``(clean_name, extras)`` where ``extras`` carries the optional
    output keys — ``"set"`` (lowercased), ``"collector_number"`` (string, as
    written), and ``"finish"`` (``"foil"``/``"etched"`` from a ``*F*``/``*E*``
    marker) — each present only when found on the line.
    """
    match = _SET_CODE_PATTERN.search(name)
    if not match:
        return name, {}
    extras = {
        "set": match.group(1).lower(),
        "collector_number": match.group(2),
    }
    for marker in re.findall(r"\*(\w+)\*", match.group(3)):
        finish = _FINISH_MARKERS.get(marker.lower())
        if finish:
            extras["finish"] = finish
            break
    return name[: match.start()], extras


def _strip_set_code(name: str) -> str:
    """Remove Moxfield-style set code and collector number from a card name."""
    return _extract_printing(name)[0]


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
    return parse_deck_text(
        path.read_text(encoding="utf-8"), format=format, deck_size=deck_size
    )


def parse_deck_text(
    content: str,
    *,
    format: str = "commander",  # noqa: A002
    deck_size: int | None = None,
) -> dict:
    """Parse raw deck-list text (auto-detecting Moxfield / MTGO / Arena / CSV / plain).

    The body of ``parse_deck`` minus the file read, so in-process callers (deck-forge's
    import endpoint, ADR-0017) can parse a pasted/uploaded list without writing a temp
    file just to hand it a ``Path``.

    Entries carry the optional ``set`` / ``collector_number`` / ``finish`` keys
    when the source line or CSV columns supplied them (see the module
    docstring). The output always includes a top-level ``"companion"`` list
    (``[]`` when the export has no Companion section); companion entries are
    excluded from ``cards`` and ``total_cards`` because a companion is revealed
    from outside the game and is not part of the deck (CR 702.139a-b).
    """
    fmt = _detect_format(content)
    result = _PARSERS[fmt](content)
    result.setdefault("companion", [])

    config = FORMAT_CONFIGS[format]

    # For commander formats, fold any sideboard entries back into cards so
    # Arena exports that include a "Sideboard" header don't silently lose cards.
    # The companion zone is never folded in: it sits outside the deck.
    if config.get("has_commander", True):
        result["cards"].extend(result.get("sideboard", []))
        result["sideboard"] = []

    # Strip Moxfield-style set codes from all names — retaining them as the
    # optional set/collector_number/finish keys — and merge duplicates that
    # arise from the same card appearing with different set codes
    # (e.g., "2 Ethereal Armor (DSK) 7" + "2 Ethereal Armor (RTR) 9").
    # When merged duplicates disagree on a printing key, the key is dropped
    # rather than guessing which printing wins.
    for section in ("commanders", "cards", "sideboard", "companion"):
        entries = result.get(section, [])
        for entry in entries:
            entry["name"], extras = _extract_printing(entry["name"])
            for key, value in extras.items():
                entry.setdefault(key, value)
        merged: dict[str, dict] = {}
        for entry in entries:
            name = entry["name"]
            qty = entry.get("quantity", 1)
            existing = merged.get(name)
            if existing is None:
                merged[name] = {
                    "name": name,
                    "quantity": qty,
                    **{
                        key: entry[key]
                        for key in ("set", "collector_number", "finish")
                        if key in entry
                    },
                }
            else:
                existing["quantity"] += qty
                for key in ("set", "collector_number", "finish"):
                    if existing.get(key) != entry.get(key):
                        existing.pop(key, None)
        result[section] = list(merged.values())

    # A card promoted to the command zone shouldn't also count in the 99: some
    # exporters list the commander in both the "// Commander" header and the deck
    # body. The command zone wins (singleton), so drop any maindeck/sideboard copy.
    commander_names = {e["name"] for e in result.get("commanders", [])}
    if commander_names:
        for section in ("cards", "sideboard"):
            result[section] = [
                e for e in result.get(section, []) if e["name"] not in commander_names
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
) -> None:
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
        companion_count = len(result.get("companion", []))
        summary = f"parse-deck: {result['total_cards']} cards"
        if commander_count:
            summary += f", {commander_count} commander(s)"
        if sideboard_count:
            summary += f", {sideboard_count} sideboard"
        if companion_count:
            summary += f", {companion_count} companion"
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
