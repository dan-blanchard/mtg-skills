"""Import an MTG Arena collection + wildcard counts from Player.log.

MTG Arena writes a ``<== StartHook`` log entry at login that embeds
``PlayerCards`` (an Arena-id → count map) and ``InventoryInfo`` (gold,
gems, wildcards, vault progress). This script extracts exactly those
two fields, resolves the Arena ids against Scryfall bulk data, and
writes:

- ``collection.json`` in the same parsed-deck shape as ``parse-deck``
  output, ready to feed straight into ``mark-owned`` or ``find-commanders``.
- ``wildcards.json`` with the four wildcard counts plus metadata the
  tuner reads during Step 3 intake.

The scanner is intentionally narrow — it does not parse the dozens of
other log entries that tracking apps like 17Lands and MTGAHelper care
about, and it does not watch the log for updates. It is a one-shot
snapshot tool.

Arena-id resolution notes:

- Scryfall's bulk data has ``arena_id`` on every Arena printing, but a
  single id can reference multiple Scryfall entries when an Alchemy
  rebalance shares its id with the non-rebalanced paper card
  (``A-Teferi, Time Raveler`` and ``Teferi, Time Raveler``). In Historic
  Brawl, players can legitimately use either form, so this importer
  emits a collection entry for **every** name that shares the id.
  ``legality-audit`` downstream will flag any that are banned in the
  user's format.
- Arena grants unlimited copies of the six "free" basic land types
  (``Island``, ``Mountain``, ``Plains``, ``Forest``, ``Swamp``, ``Wastes``),
  so the importer unconditionally injects them at quantity 99 regardless
  of what ``PlayerCards`` said. Snow-covered basics are collected
  normally and are not injected — if the user owns them, they come
  through via arena-id resolution.

Manasight-parser attribution:

The ``<== StartHook`` anchor and the ``PlayerCards`` / ``InventoryInfo``
field paths are the public log format documented by the manasight-parser
Rust library (https://github.com/manasight/manasight-parser). This
importer reimplements the two relevant extractors in Python to avoid
pulling a Rust toolchain into a uv-managed project — the parser itself
is library-only with no CLI, so there is nothing to shell out to.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import click

from commander_utils._sidecar import atomic_write_json
from commander_utils.bulk_loader import load_bulk_cards

# The exact anchor string that marks a login-time API response in the
# Arena log. Verified against manasight-parser's
# src/parsers/collection.rs (constant ``START_HOOK_METHOD``).
_START_HOOK_ANCHOR = "<== StartHook"

# Matches the UnityCrossThreadLogger timestamp prefix that precedes a
# ``<== StartHook`` block. MTGA writes local time with a 12-hour clock.
_UNITY_LOG_PREFIX = re.compile(
    r"\[UnityCrossThreadLogger\]\s*(\d+/\d+/\d+\s+\d+:\d+:\d+\s+[AP]M)",
)

# The six basic land types that Arena grants in unlimited quantities.
# Snow basics are NOT in this list — they are collected normally on
# Arena and only appear in the output when the log reports them.
_FREE_BASICS = ("Island", "Mountain", "Plains", "Forest", "Swamp", "Wastes")

# The in-game deck size for each supported format. Used to stamp a
# cosmetic ``format`` / ``deck_size`` field on the collection output so
# it structurally matches what ``parse-deck`` produces — no downstream
# script reads these fields from the collection side.
_FORMAT_DECK_SIZES = {
    "commander": 100,
    "brawl": 60,
    "historic_brawl": 100,
}

# Freshness thresholds. These are nudges, not gates — the importer
# still emits its output when a warning fires. The 48h mtime window is
# intentionally laxer than ``download-bulk``'s 24h because that
# controls re-downloading while we only decide whether to nag.
_BULK_STALE_HOURS = 48
_UNRESOLVED_PCT_THRESHOLD = 0.02
_UNRESOLVED_MIN_THRESHOLD = 10


def _default_log_path() -> Path:
    """Return the expected ``Player.log`` path for the current platform.

    Raises ``click.UsageError`` on Linux and other unsupported
    platforms — MTGA is Windows/macOS only, and the handful of Linux
    players who run it under Wine/Proton need to supply ``--log-path``
    explicitly since we can't know where their Wine prefix lives.
    """
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Logs"
            / "Wizards Of The Coast"
            / "MTGA"
            / "Player.log"
        )
    if sys.platform == "win32":
        user_profile = os.environ.get("USERPROFILE")
        if not user_profile:
            msg = "Could not determine %USERPROFILE% — pass --log-path explicitly."
            raise click.UsageError(msg)
        return (
            Path(user_profile)
            / "AppData"
            / "LocalLow"
            / "Wizards Of The Coast"
            / "MTGA"
            / "Player.log"
        )
    msg = (
        f"Auto-detecting Player.log is not supported on {sys.platform!r} "
        f"(MTG Arena is Windows/macOS only). If you run MTGA under "
        f"Wine/Proton, pass --log-path <absolute-path>."
    )
    raise click.UsageError(msg)


def _read_log_text(log_path: Path) -> str:
    """Read the full contents of ``log_path`` as UTF-8 text.

    Opens in place first; on ``PermissionError`` (which older Windows
    MTGA clients can raise while Arena is running and holding an
    exclusive lock) copies the file to a temp path and reads the copy.
    This mirrors what 17Lands' log client does for the same reason.
    ``errors="replace"`` is tolerant of the occasional malformed byte
    Arena writes during a crash.
    """
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        # Fall back to copy-then-read.
        with tempfile.NamedTemporaryFile(
            prefix="mtga-import-player-",
            suffix=".log",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copy2(log_path, tmp_path)
            return tmp_path.read_text(encoding="utf-8", errors="replace")
        finally:
            with contextlib.suppress(OSError):
                tmp_path.unlink()


def _extract_json_blob(
    lines: list[str],
    start_line_idx: int,
) -> tuple[dict, int] | None:
    """Extract a JSON object starting at-or-after ``lines[start_line_idx]``.

    Brace-counts from the first ``{`` encountered on that line (or on
    any subsequent line) until depth returns to zero, concatenating
    lines as needed. Returns ``(parsed, end_line_idx)`` on success, or
    ``None`` if no parseable object is found before the file ends.

    This handles both the compact single-line form
    ``[UnityCrossThreadLogger]<== StartHook(uuid) {...}`` and the
    multi-line form where the opening brace is on a following line.
    Naive brace counting is fine because the log entries are
    well-formed JSON — strings containing literal ``{``/``}`` characters
    are escaped during serialization by Unity's logger, so a bare brace
    in the middle of the buffer always indicates structural depth.
    """
    buffer_parts: list[str] = []
    depth = 0
    started = False
    i = start_line_idx
    while i < len(lines):
        line = lines[i]
        # On the first pass, skip everything up to and including the
        # first ``{`` on the anchor line so we don't try to parse the
        # anchor prefix as JSON.
        if not started:
            first_brace = line.find("{")
            if first_brace == -1:
                i += 1
                continue
            line = line[first_brace:]
            started = True
        buffer_parts.append(line)
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    # Found the end of the outermost object.
                    buffer = "".join(buffer_parts)
                    # Trim to the matched region — the final "}" may be
                    # in the middle of a line, but json.loads handles a
                    # trailing newline fine. We track the close index
                    # to be safe.
                    close_pos = buffer.rfind("}")
                    try:
                        parsed = json.loads(buffer[: close_pos + 1])
                    except json.JSONDecodeError:
                        return None
                    if isinstance(parsed, dict):
                        return parsed, i
                    return None
        i += 1
    return None


def _parse_timestamp_prefix(line: str) -> datetime | None:
    """Extract and parse the ``[UnityCrossThreadLogger]`` timestamp prefix.

    Returns a naive ``datetime`` (local time — MTGA writes client-local
    timestamps with no timezone indicator, so we cannot convert to UTC
    without guessing, and guessing an offset is worse than keeping the
    value naive and explicitly labeled "local" in the output).
    Returns ``None`` when the line doesn't match or the parse fails.
    """
    match = _UNITY_LOG_PREFIX.search(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1).strip(), "%m/%d/%Y %I:%M:%S %p")  # noqa: DTZ007
    except ValueError:
        return None


def _scan_log(
    text: str,
) -> tuple[dict[str, int] | None, dict | None, datetime | None]:
    """Scan a log buffer for the most recent PlayerCards/InventoryInfo.

    Returns ``(player_cards, inventory_info, snapshot_time)`` — any
    element may be ``None`` when the log did not contain that field.
    Latest-wins for both fields independently (they can come from the
    same StartHook block or from two different login sessions in the
    same log file). ``snapshot_time`` is the prefix timestamp of the
    StartHook block that supplied the ``PlayerCards`` — the collection
    snapshot is what callers typically care about dating.
    """
    lines = text.splitlines()
    latest_player_cards: dict[str, int] | None = None
    latest_inventory: dict | None = None
    latest_timestamp: datetime | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if _START_HOOK_ANCHOR not in line:
            i += 1
            continue
        # Timestamp prefix may be on this line or the preceding line.
        ts = _parse_timestamp_prefix(line)
        if ts is None and i > 0:
            ts = _parse_timestamp_prefix(lines[i - 1])
        extracted = _extract_json_blob(lines, i)
        if extracted is None:
            # Move past this anchor and keep scanning.
            i += 1
            continue
        parsed, end_idx = extracted
        player_cards = parsed.get("PlayerCards")
        if isinstance(player_cards, dict) and player_cards:
            # Only accept dicts with plausible ``"arena_id": count`` shape.
            latest_player_cards = {
                str(k): int(v) for k, v in player_cards.items() if _is_int_like(v)
            }
            latest_timestamp = ts
        inventory = parsed.get("InventoryInfo")
        if isinstance(inventory, dict):
            latest_inventory = inventory
        i = end_idx + 1

    return latest_player_cards, latest_inventory, latest_timestamp


def _is_int_like(value: object) -> bool:
    """Return True for values that can losslessly become an int.

    PlayerCards values should always be integer counts, but we stay
    defensive about boolean-typed values (``bool`` is a subclass of
    ``int`` in Python so naive ``isinstance(v, int)`` would accept
    them) and numeric strings.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        try:
            int(value)
        except ValueError:
            return False
        return True
    return False


def _build_arena_id_index(bulk_path: Path) -> dict[int, list[str]]:
    """Return ``{arena_id: [card_name, ...]}`` from Scryfall bulk data.

    An Arena id can map to multiple card names when an Alchemy rebalance
    shares its id with the paper version (``A-Teferi, Time Raveler`` /
    ``Teferi, Time Raveler``). We preserve the full list so the
    importer can emit all variants — in Historic Brawl, both forms are
    legal unless explicitly banned, and the user can choose either.

    Names are deduplicated (two Scryfall printings of the same card
    share an id) while preserving first-seen order.
    """
    cards = load_bulk_cards(bulk_path)
    index: dict[int, list[str]] = {}
    for card in cards:
        arena_id = card.get("arena_id")
        if not isinstance(arena_id, int):
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name:
            continue
        bucket = index.setdefault(arena_id, [])
        if name not in bucket:
            bucket.append(name)
    return index


def _resolve_collection(
    player_cards: dict[str, int],
    arena_index: dict[int, list[str]],
) -> tuple[list[dict], list[int]]:
    """Resolve Arena-id counts into parsed-deck-shaped card entries.

    Returns ``(cards, unresolved_ids)``. ``cards`` is a list of
    ``{"name": str, "quantity": int}`` dicts, sorted by lowercased name
    for deterministic output. When an Arena id maps to multiple names
    (Alchemy collision), every name gets its own entry at the same
    quantity — see the module docstring.
    """
    totals: dict[str, int] = {}
    unresolved: list[int] = []
    for arena_id_str, count in player_cards.items():
        try:
            arena_id = int(arena_id_str)
        except (TypeError, ValueError):
            continue
        names = arena_index.get(arena_id)
        if not names:
            unresolved.append(arena_id)
            continue
        for name in names:
            # max() defends against a card name legitimately appearing
            # under two different arena_ids (rare but possible for
            # reprints) — take the highest count rather than summing,
            # because the counts represent the same physical copies in
            # the player's inventory.
            prior = totals.get(name, 0)
            totals[name] = max(prior, count)
    cards = [
        {"name": name, "quantity": qty}
        for name, qty in sorted(totals.items(), key=lambda kv: kv[0].lower())
    ]
    return cards, unresolved


def _inject_free_basics(cards: list[dict]) -> list[dict]:
    """Ensure every free basic land appears with quantity ≥ 99.

    Arena grants unlimited basics, so the user effectively owns them
    regardless of what ``PlayerCards`` reports (sometimes the field
    omits basics entirely). Injecting quantity 99 lets ``price-check``'s
    Arena 4-cap substitution treat basics as infinite supply. Snow
    basics are NOT injected — the user has to actually own those.
    """
    by_name = {entry["name"]: entry for entry in cards}
    for basic in _FREE_BASICS:
        existing = by_name.get(basic)
        if existing is None:
            by_name[basic] = {"name": basic, "quantity": 99}
        else:
            existing["quantity"] = max(int(existing["quantity"]), 99)
    return sorted(by_name.values(), key=lambda entry: entry["name"].lower())


def _extract_wildcards(inventory: dict) -> dict[str, int]:
    """Return ``{mythic, rare, uncommon, common}`` from an InventoryInfo blob.

    Keys map to ``wcMythic/wcRare/wcUncommon/wcCommon`` per
    manasight-parser/src/parsers/inventory.rs. Missing values default
    to 0 — a brand-new account may not have all four counters written.
    """
    return {
        "mythic": int(inventory.get("wcMythic", 0) or 0),
        "rare": int(inventory.get("wcRare", 0) or 0),
        "uncommon": int(inventory.get("wcUncommon", 0) or 0),
        "common": int(inventory.get("wcCommon", 0) or 0),
    }


def _check_bulk_freshness(bulk_path: Path) -> str | None:
    """Return a WARN message if bulk data is older than ``_BULK_STALE_HOURS``.

    Returns ``None`` when the bulk data is fresh enough. Missing/unreadable
    files are handled by the caller — ``load_bulk_cards`` will raise its
    own clear error in that case.
    """
    try:
        mtime = bulk_path.stat().st_mtime
    except OSError:
        return None
    age_hours = (datetime.now(tz=UTC).timestamp() - mtime) / 3600
    if age_hours < _BULK_STALE_HOURS:
        return None
    days = age_hours / 24
    return (
        f"WARN: bulk data is {days:.1f} days old — consider running "
        f"'download-bulk' to refresh (missing cards from recent Arena "
        f"releases will show up as unresolved arena_ids)."
    )


def _check_unresolved_threshold(
    unresolved_count: int,
    total_count: int,
) -> str | None:
    """Return a WARN if unresolved ids exceed ``max(10, 2%)`` of the total."""
    threshold = max(
        _UNRESOLVED_MIN_THRESHOLD,
        int(total_count * _UNRESOLVED_PCT_THRESHOLD),
    )
    if unresolved_count <= threshold:
        return None
    return (
        f"WARN: {unresolved_count} arena_ids unresolved (>{threshold} "
        f"threshold) — your Scryfall bulk data may not include recent "
        f"Arena releases; run 'download-bulk' to refresh."
    )


def _build_collection_json(
    cards: list[dict],
    *,
    format: str,  # noqa: A002 — parameter name intentionally matches script flag
) -> dict:
    """Shape the resolved cards into parse-deck-compatible JSON."""
    total_cards = sum(int(entry["quantity"]) for entry in cards)
    return {
        "format": format,
        "deck_size": _FORMAT_DECK_SIZES.get(format, 100),
        "commanders": [],
        "cards": cards,
        "total_cards": total_cards,
        "owned_cards": [],
    }


def _build_wildcards_json(
    wildcards: dict[str, int],
    *,
    log_path: Path,
    snapshot_time: datetime | None,
) -> dict:
    """Shape the wildcard counts and metadata into the wildcards.json blob."""
    return {
        **wildcards,
        "source": "mtga-log",
        "log_path": str(log_path.resolve()),
        "snapshot_captured_local": (
            snapshot_time.isoformat() if snapshot_time is not None else None
        ),
        "extracted_at": datetime.now(tz=UTC).isoformat(),
    }


def _default_output_dir() -> Path:
    """Return the default --output-dir under $TMPDIR/mtga-import."""
    tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    return Path(tmpdir) / "mtga-import"


@click.command()
@click.option(
    "--bulk-data",
    "bulk_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Scryfall default-cards.json (required — used to "
    "resolve Arena card IDs to card names).",
)
@click.option(
    "--log-path",
    "log_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to Player.log. Defaults to the OS-appropriate MTGA "
    "location (macOS/Windows).",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory to write collection.json + wildcards.json. "
    "Defaults to $TMPDIR/mtga-import.",
)
@click.option(
    "--format",
    "format_",
    type=click.Choice(sorted(_FORMAT_DECK_SIZES), case_sensitive=False),
    default="historic_brawl",
    help="Cosmetic format stamp for the collection JSON. Downstream "
    "scripts read their own --format flag; this field is purely "
    "descriptive.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print the list of unresolved Arena ids after the summary.",
)
def main(  # noqa: PLR0915 — CLI orchestration is naturally statement-heavy
    bulk_path: Path,
    log_path: Path | None,
    output_dir: Path | None,
    format_: str,
    verbose: bool,  # noqa: FBT001 — click injects as a keyword arg at runtime
) -> None:
    """Import an MTGA Arena collection and wildcard counts from Player.log.

    Reads the most recent ``<== StartHook`` snapshot from the log,
    resolves Arena card ids against Scryfall bulk data, and writes a
    parse-deck-compatible ``collection.json`` plus a ``wildcards.json``
    into ``--output-dir``. Auto-falls-back to ``Player-prev.log`` in the
    same directory when the current log has no snapshot.
    """
    # Resolve paths.
    if log_path is None:
        log_path = _default_log_path()
    log_path = log_path.resolve()
    if not log_path.exists():
        msg = (
            f"Could not find Player.log at {log_path}. "
            f"If MTG Arena is installed elsewhere, pass --log-path."
        )
        raise click.UsageError(msg)
    if output_dir is None:
        output_dir = _default_output_dir()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Freshness check on bulk data — non-fatal.
    mtime_warn = _check_bulk_freshness(bulk_path)
    if mtime_warn:
        click.echo(mtime_warn, err=True)

    # Primary scan.
    try:
        log_text = _read_log_text(log_path)
    except FileNotFoundError as exc:
        msg = f"Could not read Player.log at {log_path}: {exc}"
        raise click.UsageError(msg) from exc
    except PermissionError as exc:
        msg = (
            f"Could not read Player.log at {log_path}: {exc}. "
            f"If MTG Arena is running on an older Windows client, "
            f"quit Arena and re-run."
        )
        raise click.UsageError(msg) from exc

    player_cards, inventory, snapshot_time = _scan_log(log_text)
    collection_source = log_path
    inventory_source = log_path

    # Player-prev.log fallback — only scan if we're missing something.
    if player_cards is None or inventory is None:
        prev_path = log_path.with_name("Player-prev.log")
        if prev_path.exists():
            try:
                prev_text = _read_log_text(prev_path)
            except (PermissionError, FileNotFoundError):
                prev_text = None
            if prev_text is not None:
                prev_player, prev_inventory, prev_time = _scan_log(prev_text)
                if player_cards is None and prev_player is not None:
                    player_cards = prev_player
                    snapshot_time = prev_time
                    collection_source = prev_path
                if inventory is None and prev_inventory is not None:
                    inventory = prev_inventory
                    inventory_source = prev_path

    if player_cards is None and inventory is None:
        prev_suffix = (
            " or Player-prev.log"
            if log_path.with_name("Player-prev.log").exists()
            else ""
        )
        msg = (
            f"No <== StartHook blocks with PlayerCards/InventoryInfo "
            f"found in {log_path.name}{prev_suffix}. "
            f"Has the user logged into Arena recently?"
        )
        raise click.UsageError(msg)

    # Resolve Arena ids → card names.
    arena_index = _build_arena_id_index(bulk_path)
    if player_cards is not None:
        resolved_cards, unresolved_ids = _resolve_collection(player_cards, arena_index)
        unresolved_warn = _check_unresolved_threshold(
            len(unresolved_ids),
            len(player_cards),
        )
        if unresolved_warn:
            click.echo(unresolved_warn, err=True)
    else:
        resolved_cards = []
        unresolved_ids = []

    # Inject free basics.
    cards_with_basics = _inject_free_basics(resolved_cards)
    collection_json = _build_collection_json(cards_with_basics, format=format_)

    # Wildcards output (only when InventoryInfo was found).
    wildcards_path = output_dir / "wildcards.json"
    collection_path = output_dir / "collection.json"
    if inventory is not None:
        wildcards = _extract_wildcards(inventory)
        wildcards_json = _build_wildcards_json(
            wildcards,
            log_path=inventory_source,
            snapshot_time=snapshot_time,
        )
        atomic_write_json(wildcards_path, wildcards_json)
    else:
        wildcards = None

    atomic_write_json(collection_path, collection_json)

    # Stdout summary.
    unique_count = len(collection_json["cards"])
    total_count = collection_json["total_cards"]
    click.echo(
        f"mtga-import: {unique_count} unique cards, {total_count} total "
        f"from {collection_source.name}",
    )
    if collection_source != inventory_source and inventory is not None:
        click.echo(f"  Inventory from: {inventory_source.name}")
    if snapshot_time is not None:
        click.echo(
            f"  Snapshot captured: {snapshot_time.strftime('%Y-%m-%d %H:%M')} (local)",
        )
    if wildcards is not None:
        click.echo(
            f"  Wildcards: {wildcards['mythic']}M / {wildcards['rare']}R / "
            f"{wildcards['uncommon']}U / {wildcards['common']}C",
        )
    if unresolved_ids:
        click.echo(
            f"  Unresolved arena_ids: {len(unresolved_ids)}"
            + ("" if verbose else " (use --verbose to list)"),
        )
        if verbose:
            for arena_id in sorted(unresolved_ids):
                click.echo(f"    {arena_id}")
    click.echo(f"Collection: {collection_path}")
    if wildcards is not None:
        click.echo(f"Wildcards:  {wildcards_path}")


if __name__ == "__main__":
    main()
