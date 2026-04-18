"""Parse an MTG cube list into canonical cube JSON."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
from pathlib import Path

import click

from mtg_utils.cube_config import (
    CUBE_FORMAT_CONFIGS,
    drafters_for_size,
    get_cube_config,
)

_CUBECOBRA_CSV_MARKERS = frozenset({"color category", "maybeboard"})
_DECK_JSON_KEYS = frozenset({"commanders", "cards", "format"})

# Arena-style section headers a plain text file might contain. Cubes don't
# have sideboards, but CubeCobra plaintext exports sometimes include a
# "Maybeboard" divider.
_SECTION_HEADERS = frozenset({"mainboard", "maybeboard", "commander", "commanders"})


def _detect_format(path: Path, content: str) -> str:
    """Detect the input format from path suffix + content sniffing."""
    suffix = path.suffix.lower()

    if suffix == ".json":
        with contextlib.suppress(json.JSONDecodeError):
            data = json.loads(content)
            if isinstance(data, dict):
                # Canonical cube JSON (ours) — has cube_format or a plain
                # top-level cards list (list of {name, quantity} entries).
                if "cube_format" in data:
                    return "cube_json"
                # CubeCobra v2 shape: cards is a dict with mainboard/maybeboard.
                if isinstance(data.get("cards"), dict) and "mainboard" in data["cards"]:
                    return "cubecobra_json"
                # CubeCobra v1 shape: top-level mainboard field.
                if "mainboard" in data:
                    return "cubecobra_json"
                # Any short/long CubeCobra ID field indicates a CubeCobra export.
                if any(
                    k in data for k in ("shortID", "shortId", "short_id", "cardCount")
                ):
                    return "cubecobra_json"
                if _DECK_JSON_KEYS.issubset(data.keys()):
                    return "deck_json"
                # Fall through: canonical cube JSON with top-level cards list.
                if isinstance(data.get("cards"), list):
                    return "cube_json"
        return "cube_json"

    if suffix == ".csv":
        head = content.splitlines()[0].lower() if content.strip() else ""
        if any(marker in head for marker in _CUBECOBRA_CSV_MARKERS):
            return "cubecobra_csv"
        return "generic_csv"

    return "plain"


def _card_entry(
    name: str,
    quantity: int = 1,
    *,
    scryfall_id: str | None = None,
    cube_color: str | None = None,
    cube_cmc: float | None = None,
    tags: list[str] | None = None,
) -> dict:
    entry: dict = {"name": name, "quantity": quantity}
    if scryfall_id:
        entry["scryfall_id"] = scryfall_id
    if cube_color:
        entry["cube_color"] = cube_color
    if cube_cmc is not None:
        entry["cube_cmc"] = cube_cmc
    if tags:
        entry["tags"] = tags
    return entry


def _parse_cubecobra_json(content: str) -> dict:
    """Parse a CubeCobra cubeJSON export.

    Supports both top-level ``mainboard`` (older shape / our own fixtures)
    and the current CubeCobra v2 shape where cards live under
    ``cards.mainboard`` / ``cards.maybeboard``. Extracts per-card overrides
    (color category, CMC override, tags, Scryfall IDs).

    Maybeboard entries are dropped — they're candidates the designer is
    considering but not actively including.
    """
    data = json.loads(content)

    # CubeCobra v2 nests mainboard under "cards"; older shape has it top-level.
    cards_block = data.get("cards") if isinstance(data.get("cards"), dict) else None
    mainboard_raw = (
        cards_block.get("mainboard", []) if cards_block else data.get("mainboard", [])
    )
    maybeboard_raw = (
        cards_block.get("maybeboard", []) if cards_block else data.get("maybeboard", [])
    )
    _ = maybeboard_raw  # dropped

    cards: list[dict] = []
    commander_pool: list[dict] = []

    _type = data.get("type") or ""
    _prefixes = data.get("category_prefixes") or []
    if isinstance(_prefixes, str):
        _prefixes = [_prefixes]
    _markers = {str(_type).lower(), *(str(p).lower() for p in _prefixes)}
    is_commander_cube = bool(_markers & {"commander", "pdh"})

    for raw in mainboard_raw:
        entry = _cubecobra_card_to_entry(raw)
        if entry is None:
            continue
        type_line = (
            (raw.get("details") or {}).get("type_line")
            or raw.get("type_line")
            or raw.get("typeLine")
            or ""
        )
        if is_commander_cube and "Legendary" in type_line and "Creature" in type_line:
            commander_pool.append(entry)
        else:
            cards.append(entry)

    # Some CubeCobra exports explicitly include a commander_pool field.
    for raw in data.get("commander_pool", []) or []:
        entry = _cubecobra_card_to_entry(raw)
        if entry is not None:
            commander_pool.append(entry)

    name = data.get("name") or data.get("title") or ""
    description = data.get("description") or ""
    tags = data.get("tags") or []
    short_id = data.get("shortID") or data.get("short_id") or data.get("shortId")

    result: dict = {"cards": cards}
    if commander_pool:
        result["commander_pool"] = commander_pool
    if name:
        result["name"] = name
    if description or tags:
        result["designer_intent"] = {
            "description": description,
            "tags": list(tags),
            "stated_archetypes": [],
        }
    if short_id:
        result["source"] = f"cubecobra:{short_id}"
    return result


def _cubecobra_card_to_entry(raw: dict) -> dict | None:
    details = raw.get("details") or {}
    name = raw.get("name") or details.get("name")
    if not name:
        return None

    # CubeCobra exposes both per-card color overrides (``colorCategory`` — a
    # string like "White" or "Multicolored") and the default Scryfall colors
    # (a list). The cube-wizard schema stores a short-code override when
    # present; we only capture the user's explicit colorCategory override.
    color_override = raw.get("colorCategory") or raw.get("color_category")
    if isinstance(color_override, list):
        color_override = None
    if color_override is not None and not isinstance(color_override, str):
        color_override = None

    return _card_entry(
        name,
        quantity=int(raw.get("quantity", 1) or 1),
        scryfall_id=raw.get("cardID") or details.get("scryfall_id"),
        cube_color=color_override,
        cube_cmc=_coerce_float(raw.get("cmc")),
        tags=list(raw.get("tags") or []),
    )


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    with contextlib.suppress(ValueError, TypeError):
        return float(value)
    return None


def _parse_cubecobra_csv(content: str) -> dict:
    """Parse CubeCobra's CSV export format.

    Columns (order may vary): name, CMC, Type, Color, Set, Collector Number,
    Rarity, Color Category, Status, Finish, Maybeboard, Image URL,
    Image Back URL, Tags, Notes, MTGO ID.
    """
    reader = csv.DictReader(io.StringIO(content))
    cards: list[dict] = []

    for row in reader:
        normalized = {
            (k or "").strip().lower(): (v or "").strip() for k, v in row.items()
        }
        name = normalized.get("name") or normalized.get("card name")
        if not name:
            continue

        maybeboard = normalized.get("maybeboard", "").lower() in {"true", "1", "yes"}
        if maybeboard:
            continue

        raw_tags = normalized.get("tags") or ""
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []

        cards.append(
            _card_entry(
                name,
                quantity=1,
                cube_color=normalized.get("color category") or None,
                cube_cmc=_coerce_float(normalized.get("cmc")),
                tags=tags,
            )
        )

    return {"cards": cards}


def _parse_generic_csv(content: str) -> dict:
    """Fall-back CSV parser that only reads name / quantity columns."""
    reader = csv.DictReader(io.StringIO(content))
    cards: list[dict] = []
    for row in reader:
        normalized = {
            (k or "").strip().lower(): (v or "").strip() for k, v in row.items()
        }
        name = normalized.get("name") or normalized.get("card name")
        if not name:
            continue
        qty_raw = (
            normalized.get("quantity")
            or normalized.get("count")
            or normalized.get("qty")
            or "1"
        )
        try:
            quantity = int(qty_raw)
        except ValueError:
            quantity = 1
        cards.append(_card_entry(name, quantity=quantity))
    return {"cards": cards}


def _parse_plain(content: str) -> dict:
    cards: list[dict] = []
    current_section = "mainboard"

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() in _SECTION_HEADERS:
            current_section = line.lower()
            continue
        if current_section == "maybeboard":
            continue
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
        else:
            quantity = 1
            name = line
        cards.append(_card_entry(name, quantity=quantity))
    return {"cards": cards}


def _parse_deck_json(content: str) -> dict:
    """Reshape a parsed deck JSON into cube JSON by dropping deck-only fields."""
    deck = json.loads(content)
    cards: list[dict] = []
    for entry in deck.get("commanders", []) or []:
        cards.append(_card_entry(entry["name"], quantity=int(entry.get("quantity", 1))))
    for entry in deck.get("cards", []) or []:
        cards.append(_card_entry(entry["name"], quantity=int(entry.get("quantity", 1))))
    return {"cards": cards}


def _parse_cube_json(content: str) -> dict:
    """Load an already-canonical cube JSON (pass-through)."""
    return json.loads(content)


_PARSERS = {
    "cubecobra_json": _parse_cubecobra_json,
    "cubecobra_csv": _parse_cubecobra_csv,
    "generic_csv": _parse_generic_csv,
    "deck_json": _parse_deck_json,
    "cube_json": _parse_cube_json,
    "plain": _parse_plain,
}


def _detect_set_cube(cards: list[dict]) -> bool:
    """Auto-detect set cubes: every card tagged with the same set code.

    Requires ``set`` column data to populate a tag; falls back to False when
    we don't have set info in the parsed cards. Called only when the caller
    doesn't explicitly specify a cube_format.
    """
    sets = {
        tag
        for card in cards
        for tag in (card.get("tags") or [])
        if isinstance(tag, str) and len(tag) <= 5 and tag.isupper()
    }
    return len(sets) == 1


def parse_cube(
    path: Path,
    *,
    cube_format: str | None = None,
    target_size: int | None = None,
    name: str | None = None,
) -> dict:
    """Parse a cube list file into canonical cube JSON."""
    content = path.read_text(encoding="utf-8")
    fmt = _detect_format(path, content)
    parsed = _PARSERS[fmt](content)

    cards = parsed.get("cards", [])
    commander_pool = parsed.get("commander_pool") or []

    # Auto-detect set cubes when the user didn't specify a format.
    effective_format = cube_format
    if effective_format is None:
        effective_format = "set" if _detect_set_cube(cards) else "vintage"

    cfg = get_cube_config({"cube_format": effective_format})

    inferred_size = sum(c.get("quantity", 1) for c in cards) + sum(
        c.get("quantity", 1) for c in commander_pool
    )

    resolved_target = target_size or cfg["default_size"]

    result = {
        "cube_format": effective_format,
        "target_size": resolved_target,
        "name": name or parsed.get("name") or path.stem,
        "drafters": drafters_for_size(resolved_target),
        "pack_size": 15,
        "packs_per_drafter": 3,
        "cards": cards,
        "total_cards": inferred_size,
    }

    if commander_pool or cfg.get("has_commander_pool"):
        result["commander_pool"] = commander_pool

    for key in ("source", "designer_intent"):
        if key in parsed:
            result[key] = parsed[key]

    return result


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cube-format",
    type=click.Choice(sorted(CUBE_FORMAT_CONFIGS.keys())),
    default=None,
    help="Cube format (auto-detects 'set' from single-set cubes, else 'vintage').",
)
@click.option(
    "--target-size",
    type=int,
    default=None,
    help="Override target cube size (default: format default).",
)
@click.option(
    "--name",
    "cube_name",
    type=str,
    default=None,
    help="Override cube name (default: from source or filename).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write JSON to this file instead of stdout.",
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
    help="Emit JSON envelope to stdout instead of a text summary.",
)
def main(
    cube_path: Path,
    cube_format: str | None,
    target_size: int | None,
    cube_name: str | None,
    output_path: Path | None,
    *,
    emit_json: bool,
):
    """Parse a cube list file into canonical cube JSON."""
    result = parse_cube(
        cube_path,
        cube_format=cube_format,
        target_size=target_size,
        name=cube_name,
    )

    payload = json.dumps(result, indent=2)

    if output_path is not None:
        if output_path.resolve() == cube_path.resolve():
            raise click.UsageError(
                "--output would overwrite the input cube file; pass a different path."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n")
        resolved = output_path.resolve()
        commander_count = len(result.get("commander_pool", []))
        summary = (
            f"parse-cube: {result['total_cards']} cards "
            f"(target {result['target_size']}, format {result['cube_format']})"
        )
        if commander_count:
            summary += f", {commander_count} commanders"
        click.echo(summary)
        click.echo(f"Full JSON: {resolved}")
    elif emit_json:
        click.echo(payload)
    else:
        commander_count = len(result.get("commander_pool", []))
        click.echo(
            f"parse-cube: {result['total_cards']} cards "
            f"(target {result['target_size']}, format {result['cube_format']})"
        )
        if commander_count:
            click.echo(f"  commander pool: {commander_count}")
        click.echo(payload)
