"""Import an MTG Arena collection + wildcard counts from Player.log.

MTG Arena writes a ``<== StartHook`` log entry at login that embeds
``InventoryInfo`` (gold, gems, wildcards, vault progress) and ``Decks``
(every saved deck with its card lists). This script pulls the wildcard
counts from ``InventoryInfo`` and assembles an owned-cards list from
one of two sources, then writes:

- ``collection.json`` in the same parsed-deck shape as ``parse-deck``
  output, ready to feed straight into ``mark-owned`` or ``find-commanders``.
- ``wildcards.json`` with the four wildcard counts plus metadata the
  tuner reads during Step 3 intake.

Collection paths
----------------

Two ``--collection-source`` values are supported, each trading
completeness for setup friction:

**``decks`` (default): lower-bound reconstruction from the log.**
There used to be a ``PlayerCards`` field on ``<== StartHook`` that was
a direct arena-id → count map of the player's collection. **WotC
removed that structured API in 2021** (confirmed against
``manasight-parser/src/parsers/collection.rs``; its own docstring
admits the field no longer fires). On a real 2026-era Player.log
there is no arena-id → count map anywhere — the login response has
``InventoryInfo``, ``Decks``, ``DeckSummariesV2``, and a dozen other
top-level keys, but nothing resembling a full collection dump. The
only log-derivable source of owned cards is the ``Decks`` dict, whose
entries each have ``MainDeck``, ``Sideboard``, ``CommandZone``, and
``Companions`` lists of ``{cardId, quantity}``. Summing per-printing
quantities across every zone of every saved deck (capped at Arena's
4-copy playset limit) gives a **subset** of the user's real
collection — cards they own but have never put into a deck are
missed. Usually fine for deckbuilding workflows since binder-only
cards are noise for ``find-commanders``-style queries.

**``untapped-csv``: full snapshot from an Untapped.gg CSV export.**
Reads the CSV produced by the "Export Collection" button on
untapped.gg. Covers every printing Arena knows about, including the
newest Alchemy / Universes Beyond sets where Scryfall's ``arena_id``
field is still null. Requires ``--untapped-csv <path>``. No Arena
process, no sudo, no Rust toolchain.

A previous revision of this module also shelled out to a forked
``mtga-reader`` npm package to read the live collection directly
from the Arena process memory. That path was removed — the
signature-based heap scan proved brittle across Arena updates and
the Untapped CSV source provides a cleaner, permission-free full
snapshot with authoritative arena_id → name mappings. Notes from
the investigation (including how Untapped's own in-memory approach
works and what it would take to replicate) live at
``~/repos/mtga-reader/NOTES.md`` alongside the fork itself.

Arena-id resolution notes:

- Scryfall's bulk data has ``arena_id`` on every Arena printing, but a
  single id can reference multiple Scryfall entries when an Alchemy
  rebalance shares its id with the non-rebalanced paper card
  (``A-Teferi, Time Raveler`` and ``Teferi, Time Raveler``). In Historic
  Brawl, players can legitimately use either form, so this importer
  emits a collection entry for **every** name that shares the id.
  ``legality-audit`` downstream will flag any that are banned in the
  user's format.
- ``--untapped-csv`` can be supplied alongside any collection source
  (not just ``untapped-csv``) to act as a supplementary arena_id →
  name resolver: Scryfall's bulk data still takes precedence, but
  ids Scryfall can't map fall back to Untapped's names. This is the
  cleanest way to handle the newest Alchemy / Universes Beyond sets
  where Scryfall's ``arena_id`` field is still null because the
  upstream ingestion hasn't caught up yet.
- Arena grants unlimited copies of the six "free" basic land types
  (``Island``, ``Mountain``, ``Plains``, ``Forest``, ``Swamp``, ``Wastes``),
  so the importer unconditionally injects them at quantity 99 regardless
  of what the collection source reported. Snow-covered basics are
  collected normally and are not injected — if the user owns them, they
  come through via arena-id resolution.
"""

from __future__ import annotations

import contextlib
import csv
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
# Arena log. The StartHook response carries ``InventoryInfo`` (wildcards
# + currency) and ``Decks`` (every saved deck's card list) — the only
# two fields this importer relies on.
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

# Arena's deckbuilding cap on per-card copies. Any card can be placed
# in a deck at most 4 times (except for basic lands and the
# "any number allowed" cards like Hare Apparent, Persistent Petitioners,
# Shadowborn Apostle, Relentless Rats, Rat Colony, Seven Dwarves).
# Arena's internal ownership model also caps at 4 per oracle card —
# once you own 4 physical copies from any combination of printings,
# additional acquisitions don't give you more usable copies. Used by
# ``_resolve_collection`` when aggregating per-printing counts up to
# per-oracle-name totals.
_ARENA_PLAYSET_CAP = 4

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

# Minimum column set every Untapped.gg "Export Collection" CSV has.
# ``_load_untapped_csv`` checks for these up-front so a user pointing
# at the wrong file (deck export, Moxfield CSV, etc.) gets a targeted
# error instead of silently producing an empty collection.
_UNTAPPED_REQUIRED_COLUMNS = frozenset({"Id", "Name", "Count"})


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
) -> tuple[dict | None, dict | None, datetime | None]:
    """Scan a log buffer for the most recent Decks + InventoryInfo blobs.

    Returns ``(decks, inventory_info, snapshot_time)`` — any element
    may be ``None`` when the log did not contain that field. Latest-wins
    for both fields independently (they can come from the same StartHook
    block or from two different login sessions in the same log file).
    ``snapshot_time`` is the prefix timestamp of the StartHook block
    that supplied the ``Decks`` dict — the collection snapshot is what
    callers typically care about dating.

    ``decks`` is the raw ``{deckUuid: {MainDeck, Sideboard, ...}}`` dict
    straight from the log; call ``_collection_from_decks`` to reduce it
    to a ``{cardId: max_quantity}`` map ready for ``_resolve_collection``.
    Returning the raw dict here keeps the scanner agnostic about how
    the collection is derived — useful for future alternative strategies.
    """
    lines = text.splitlines()
    latest_decks: dict | None = None
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
        decks = parsed.get("Decks")
        if isinstance(decks, dict) and decks:
            latest_decks = decks
            latest_timestamp = ts
        inventory = parsed.get("InventoryInfo")
        if isinstance(inventory, dict):
            latest_inventory = inventory
        i = end_idx + 1

    return latest_decks, latest_inventory, latest_timestamp


def _is_int_like(value: object) -> bool:
    """Return True for values that can losslessly become an int.

    Used to guard against malformed deck entries where ``quantity``
    could be a bool (``bool`` is a subclass of ``int`` in Python so
    naive ``isinstance(v, int)`` would accept them), a float, or a
    numeric string. Normal MTGA deck entries are well-formed ints, but
    the helper is cheap and keeps the reconstruction defensive against
    future log format drift.
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


# The four zones in an MTGA Deck payload that can carry owned cards.
# ``CardSkins`` is the fifth zone but it holds cosmetic overrides, not
# card counts, so it's excluded. ``Companions`` is kept because a
# companion is still a card the user owns even when the slot is usually
# empty in non-companion decks.
_DECK_ZONES_WITH_CARDS = ("MainDeck", "Sideboard", "CommandZone", "Companions")


def _collection_from_decks(decks: dict | None) -> dict[str, int]:
    """Reconstruct an arena-id → count map from a StartHook ``Decks`` dict.

    Takes the raw ``Decks`` value from a ``<== StartHook`` blob — a
    dict of ``{deck_uuid: {MainDeck, Sideboard, CommandZone, Companions,
    CardSkins}}`` where each zone list contains ``{cardId, quantity}``
    dicts — and returns ``{str(cardId): max_quantity_seen}`` across
    every zone of every deck.

    **This is unreliable**, not a true collection. It has false positives
    (Arena allows building decks with unowned cards, so cards in
    speculative decks appear as "owned") and false negatives (owned
    cards never put in any deck are invisible). See the module
    docstring for why the log has no better source.

    The ``max`` reduction (rather than sum) is intentional: the user's
    inventory has one copy count per ``cardId``, and the same card
    appearing in two different decks at quantity 4 and 2 means they
    own ≥4 copies, not 6. Taking the max is the correct per-card estimate.

    Returns an empty dict when ``decks`` is ``None``, non-dict, or has
    no valid entries — callers should treat an empty result as "no
    collection data found" and fall through to whatever error handling
    covers a missing snapshot.
    """
    if not isinstance(decks, dict):
        return {}
    totals: dict[int, int] = {}
    for deck in decks.values():
        if not isinstance(deck, dict):
            continue
        for zone_name in _DECK_ZONES_WITH_CARDS:
            entries = deck.get(zone_name)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                card_id = entry.get("cardId")
                quantity = entry.get("quantity")
                if not isinstance(card_id, int) or not _is_int_like(quantity):
                    continue
                qty_int = int(quantity)  # type: ignore[arg-type]
                if qty_int <= 0:
                    continue
                prior = totals.get(card_id, 0)
                if qty_int > prior:
                    totals[card_id] = qty_int
    return {str(cid): qty for cid, qty in totals.items()}


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


def _load_untapped_csv(
    csv_path: Path,
) -> tuple[dict[str, int], dict[int, list[str]]]:
    """Parse an Untapped.gg collection CSV into a player-cards dict
    and an arena-id → name index.

    Returns ``(player_cards, arena_index)``:

    - ``player_cards`` is ``{arena_id_str: quantity}`` for rows
      with ``Count > 0`` — the user's owned cards in the same shape
      the ``decks`` collection source returns. Keys are strings to
      match ``_resolve_collection``'s expected ``player_cards``
      parameter.

    - ``arena_index`` is ``{arena_id: [name]}`` for EVERY row
      (owned or not), so it can be merged into the Scryfall-derived
      arena_index as a fallback name resolver for ids Scryfall
      doesn't yet know about. Untapped gets their
      ``arena_id → name`` mapping directly from Arena's own
      internal card database, so it's authoritative for every
      printing Arena ships — including the newest Alchemy /
      Universes Beyond sets where Scryfall's ``arena_id`` field
      is still null because Scryfall's upstream data hasn't
      caught up yet.

    Untapped's CSV columns are
    ``Id,Name,Set,Color,Rarity,Count,PrintCount``, one row per
    printing. The ``Id`` column is Arena's internal grp_id,
    equivalent to Scryfall's ``arena_id`` field. Silently skips
    malformed rows (non-integer ``Id``, empty ``Name``, etc.) —
    the CSV format has been stable for years but shouldn't crash
    the whole import on one bad row.

    Raises ``click.UsageError`` if the header row is missing the
    required ``Id``, ``Name``, and ``Count`` columns — that almost
    always means the user pointed at the wrong file (a deck export,
    a Moxfield CSV, etc.) and we'd otherwise silently degrade to an
    empty collection.
    """
    player_cards: dict[str, int] = {}
    arena_index: dict[int, list[str]] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = set(reader.fieldnames or ())
        missing = _UNTAPPED_REQUIRED_COLUMNS - header
        if missing:
            msg = (
                f"{csv_path} does not look like an Untapped.gg collection "
                f"export: missing required columns {sorted(missing)!r}. "
                f"Expected a header row with at least 'Id', 'Name', and "
                f"'Count'. Use 'Export Collection' on untapped.gg to "
                f"generate the right file."
            )
            raise click.UsageError(msg)
        for row in reader:
            try:
                arena_id = int((row.get("Id") or "").strip())
            except (TypeError, ValueError):
                continue
            if arena_id <= 0:
                continue
            name = (row.get("Name") or "").strip()
            if not name:
                continue
            try:
                count = int((row.get("Count") or "0").strip())
            except (TypeError, ValueError):
                count = 0
            # Build the name index for EVERY row (not just owned)
            # so it can serve as a fallback resolver even for cards
            # the user doesn't own.
            bucket = arena_index.setdefault(arena_id, [])
            if name not in bucket:
                bucket.append(name)
            # Only owned rows contribute to player_cards.
            if count > 0:
                player_cards[str(arena_id)] = count
    return player_cards, arena_index


def _resolve_collection(
    player_cards: dict[str, int],
    arena_index: dict[int, list[str]],
) -> tuple[list[dict], list[int]]:
    """Resolve Arena-id counts into parsed-deck-shaped card entries.

    Returns ``(cards, unresolved_ids)``. ``cards`` is a list of
    ``{"name": str, "quantity": int}`` dicts, sorted by lowercased name
    for deterministic output. When an Arena id maps to multiple names
    (Alchemy collision), every name gets its own entry with a
    properly aggregated quantity.

    **Per-printing aggregation:** Arena stores physical card ownership
    **per printing**, not per oracle name. A card like *Lightning
    Strike* that has been reprinted in multiple sets (XLN, M19, JMP,
    DMU, DFT, TLA...) has a distinct arena_id for each printing, and
    each printing has its own acquired-copy count. The user's true
    ownership of the oracle card "Lightning Strike" is the SUM of
    copies owned across all printings, capped at 4 (Arena's
    deckbuilding limit — once you own 4 physical copies from any
    combination of printings you can deck a full playset). So we:

    1. Sum quantities across every arena_id that resolves to the
       same oracle name.
    2. Cap the total at ``_ARENA_PLAYSET_CAP`` (4). Acquiring
       beyond 4 total is possible in Arena (pack rewards can push
       you past the cap) but not useful for deckbuilding.

    The previous implementation used ``max(prior, count)`` on the
    theory that multiple arena_ids for the same name represented
    "the same physical copies" — that's wrong. Each printing is
    independent physical storage, and max() systematically
    underreports users' true usable ownership.
    """
    # Both callers (``_collection_from_decks``, ``_load_untapped_csv``)
    # emit real ``int`` values for quantity and decimal-digit strings
    # for arena_id, so we trust the contract here rather than catching
    # conversion errors. A violation is a caller bug, not a data-quality
    # issue to paper over.
    totals: dict[str, int] = {}
    unresolved: list[int] = []
    for arena_id_str, count in player_cards.items():
        arena_id = int(arena_id_str)
        names = arena_index.get(arena_id)
        if not names:
            unresolved.append(arena_id)
            continue
        for name in names:
            prior = totals.get(name, 0)
            totals[name] = min(prior + count, _ARENA_PLAYSET_CAP)
    cards = [
        {"name": name, "quantity": qty}
        for name, qty in sorted(totals.items(), key=lambda kv: kv[0].lower())
    ]
    return cards, unresolved


def _inject_free_basics(cards: list[dict]) -> list[dict]:
    """Ensure every free basic land appears with quantity ≥ 99.

    Arena grants unlimited basics, so the user effectively owns them
    regardless of what the collection source reported (the Decks
    reconstruction omits basics the user has never put in a deck,
    and the Untapped CSV reports true owned quantities rather than
    Arena's unlimited grant). Injecting quantity 99 lets
    ``price-check``'s Arena 4-cap substitution treat basics as
    infinite supply. Snow basics are NOT injected — the user has
    to actually own those.
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

    Keys map to ``WildCardMythics/WildCardRares/WildCardUnCommons/
    WildCardCommons`` — the actual field names in a 2026-era MTGA
    ``<== StartHook`` ``InventoryInfo`` blob. (Note the trailing ``s``
    on each name and the camel-case ``Un`` in ``WildCardUnCommons``.)
    Missing values default to 0; in particular, a user with zero of a
    given rarity often has the corresponding field omitted entirely
    from the payload, so we can't rely on every field being present.
    The ``wc`` prefix that older tracker documentation references
    (``wcMythic`` etc.) is only ever used for the unrelated
    ``wcTrackPosition`` mastery-track counter — relying on it
    silently zeros every wildcard reading.
    """
    return {
        "mythic": int(inventory.get("WildCardMythics", 0) or 0),
        "rare": int(inventory.get("WildCardRares", 0) or 0),
        "uncommon": int(inventory.get("WildCardUnCommons", 0) or 0),
        "common": int(inventory.get("WildCardCommons", 0) or 0),
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
    """Return a WARN if unresolved ids exceed ``max(10, 2%)`` of the total.

    The usual cause of an unresolved id under any collection source
    is stale Scryfall bulk data — a new set shipped on Arena but the
    local bulk hasn't been refreshed. ``download-bulk`` fixes it.
    Under the ``untapped-csv`` source the Untapped export also feeds
    its own arena_id → name mapping into the resolver, so unresolved
    counts there tend to be small and mostly indicate Alchemy
    printings whose mappings haven't yet reached Scryfall.
    """
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


def _chown_outputs_to_sudo_user(*paths: Path) -> None:
    """Chown each path to the real (non-root) invoking user if we're
    running under sudo.

    None of the currently-supported collection sources require sudo,
    but this helper stays wired in defensively: if a user happens to
    run the importer under ``sudo`` for any reason (e.g., writing
    into a restricted ``--output-dir``), we still want the resulting
    files to be owned by the invoking user rather than root, so that
    subsequent non-sudo runs can read and overwrite them. ``sudo``
    exports ``SUDO_UID`` / ``SUDO_GID`` env vars with the real
    user's ids, so we can reach down and fix ownership after writing.

    Silently no-ops when not running under sudo, or when the paths
    don't exist, or when the chown itself fails (e.g., on a
    platform without the env vars). Failure to chown is never a
    reason to fail the overall import.
    """
    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if not sudo_uid or not sudo_gid:
        return
    try:
        uid = int(sudo_uid)
        gid = int(sudo_gid)
    except ValueError:
        return
    for path in paths:
        if path is None:
            continue
        with contextlib.suppress(OSError):
            if path.exists():
                os.chown(path, uid, gid)


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
    "--collection-source",
    "collection_source",
    type=click.Choice(
        ["decks", "untapped-csv"],
        case_sensitive=False,
    ),
    default="decks",
    help="Where to get the owned-cards data. 'decks' (default) "
    "reconstructs a LOWER-BOUND collection from the StartHook Decks "
    "dict in Player.log — captures every card used in any saved deck "
    "but misses binder-only cards. 'untapped-csv' reads from a CSV "
    "file exported from Untapped.gg ('Export Collection' button on "
    "untapped.gg) — covers every printing Arena knows about "
    "(including the newest Alchemy / Universes Beyond sets where "
    "Scryfall's arena_id field is still null). Requires "
    "--untapped-csv <path>.",
)
@click.option(
    "--untapped-csv",
    "untapped_csv",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a CSV exported from Untapped.gg via 'Export "
    "Collection'. Required when --collection-source=untapped-csv. "
    "Also acts as a supplementary arena_id → name resolver for "
    "other collection sources when provided: Scryfall's bulk data "
    "still takes precedence, but ids Scryfall can't map fall back "
    "to the Untapped CSV's names (useful for new Alchemy / UB sets).",
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
    collection_source: str,
    untapped_csv: Path | None,
    verbose: bool,  # noqa: FBT001 — click injects as a keyword arg at runtime
) -> None:
    """Import an MTGA Arena collection and wildcard counts from Player.log.

    Reads the most recent ``<== StartHook`` snapshot from the log,
    resolves Arena card ids against Scryfall bulk data, and writes a
    parse-deck-compatible ``collection.json`` plus a ``wildcards.json``
    into ``--output-dir``. Auto-falls-back to ``Player-prev.log`` in the
    same directory when the current log has no snapshot.

    Two collection sources are supported:

    - ``decks`` (default) — LOWER BOUND reconstructed from the
      ``Decks`` dict in the StartHook blob. Captures cards used in
      any saved deck; misses binder-only cards.
    - ``untapped-csv`` — reads from an Untapped.gg CSV export.
      Requires ``--untapped-csv <path>``. Covers every printing
      Arena knows about, including newer Alchemy / Universes Beyond
      sets where Scryfall's ``arena_id`` field is still ``None``.

    ``--untapped-csv`` can also be passed with a different
    ``--collection-source`` to use as a supplementary name resolver:
    Scryfall's bulk data still takes precedence, but ids Scryfall
    can't map fall back to Untapped's names.

    Wildcard data still comes from Player.log's StartHook
    ``InventoryInfo`` block regardless of collection source — the
    Untapped CSV doesn't include wildcard counts. When using
    ``untapped-csv`` without a readable Player.log, wildcards will
    be zero in the output.
    """
    # Validate the untapped-csv source's required arg before touching
    # anything else.
    if collection_source == "untapped-csv" and untapped_csv is None:
        msg = (
            "--collection-source untapped-csv requires --untapped-csv "
            "<path>. Export from Untapped.gg via 'Export Collection' "
            "and pass the downloaded CSV path."
        )
        raise click.UsageError(msg)

    # Resolve paths. Player.log is soft-required: for the 'decks'
    # source it's mandatory (there's nothing else to read); for
    # 'untapped-csv' it's only needed for wildcards, so we fall
    # through if missing.
    log_required = collection_source == "decks"
    if log_path is None:
        try:
            log_path = _default_log_path()
        except click.UsageError:
            if log_required:
                raise
            log_path = None
    if log_path is not None:
        log_path = log_path.resolve()
        if not log_path.exists():
            if log_required:
                msg = (
                    f"Could not find Player.log at {log_path}. "
                    f"If MTG Arena is installed elsewhere, pass --log-path."
                )
                raise click.UsageError(msg)
            log_path = None
    if output_dir is None:
        output_dir = _default_output_dir()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Freshness check on bulk data — non-fatal.
    mtime_warn = _check_bulk_freshness(bulk_path)
    if mtime_warn:
        click.echo(mtime_warn, err=True)

    # Log scan — optional when log_path is None (we only hit this
    # path for non-decks sources without an accessible log file).
    decks: dict | None = None
    inventory: dict | None = None
    snapshot_time: datetime | None = None
    collection_log_source = log_path
    inventory_source = log_path

    if log_path is not None:
        try:
            log_text = _read_log_text(log_path)
        except FileNotFoundError as exc:
            if log_required:
                msg = f"Could not read Player.log at {log_path}: {exc}"
                raise click.UsageError(msg) from exc
            log_text = None
        except PermissionError as exc:
            if log_required:
                msg = (
                    f"Could not read Player.log at {log_path}: {exc}. "
                    f"If MTG Arena is running on an older Windows client, "
                    f"quit Arena and re-run."
                )
                raise click.UsageError(msg) from exc
            log_text = None

        if log_text is not None:
            decks, inventory, snapshot_time = _scan_log(log_text)

        # Player-prev.log fallback — only scan if we're missing something.
        if log_path is not None and (decks is None or inventory is None):
            prev_path = log_path.with_name("Player-prev.log")
            if prev_path.exists():
                try:
                    prev_text = _read_log_text(prev_path)
                except (PermissionError, FileNotFoundError):
                    prev_text = None
                if prev_text is not None:
                    prev_decks, prev_inventory, prev_time = _scan_log(prev_text)
                    if decks is None and prev_decks is not None:
                        decks = prev_decks
                        snapshot_time = prev_time
                        collection_log_source = prev_path
                    if inventory is None and prev_inventory is not None:
                        inventory = prev_inventory
                        inventory_source = prev_path

    if log_required and decks is None and inventory is None:
        prev_suffix = (
            " or Player-prev.log"
            if log_path is not None and log_path.with_name("Player-prev.log").exists()
            else ""
        )
        log_name = log_path.name if log_path is not None else "Player.log"
        msg = (
            f"No <== StartHook blocks with Decks/InventoryInfo "
            f"found in {log_name}{prev_suffix}. "
            f"Has the user logged into Arena recently?"
        )
        raise click.UsageError(msg)

    # Load Untapped CSV if provided. Used as a primary source for
    # ``--collection-source untapped-csv`` and as a supplementary
    # name resolver merged into arena_index for any source.
    untapped_player_cards: dict[str, int] | None = None
    untapped_arena_index: dict[int, list[str]] | None = None
    if untapped_csv is not None:
        untapped_player_cards, untapped_arena_index = _load_untapped_csv(
            untapped_csv,
        )

    # Reduce the raw Decks dict to a cardId → count map according to
    # the selected collection source. The ``untapped_player_cards is
    # not None`` guard is load-bearing belt-and-suspenders: the
    # UsageError at the top of main() for ``collection_source ==
    # "untapped-csv" and untapped_csv is None`` already prevents
    # reaching here with an unloaded CSV, but a plain runtime check
    # is more robust than ``assert`` (which strips under ``python -O``).
    if collection_source == "untapped-csv":
        if untapped_player_cards is None:  # pragma: no cover — defensive
            msg = (
                "--collection-source untapped-csv reached dispatch without a loaded CSV"
            )
            raise RuntimeError(msg)
        player_cards = untapped_player_cards
    else:
        player_cards = _collection_from_decks(decks)

    # Resolve Arena ids → card names. Scryfall's bulk data is the
    # authoritative source for canonical names (including DFC full
    # names), but Untapped's index fills the gap for arena_ids
    # Scryfall hasn't yet populated.
    arena_index = _build_arena_id_index(bulk_path)
    if untapped_arena_index is not None:
        for aid, names in untapped_arena_index.items():
            if aid in arena_index:
                continue
            arena_index[aid] = list(names)
    if player_cards:
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
        # inventory is only populated inside the ``if log_path is not
        # None`` block above, and every code path that sets inventory
        # also sets inventory_source (either to log_path or prev_path,
        # both non-None). Pin the invariant so _build_wildcards_json's
        # non-Optional log_path parameter is honored.
        assert inventory_source is not None
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

    # Always write a debug sidecar listing every raw arena_id the
    # collection source produced, with a (resolved|unresolved) tag
    # and the resolved name if we have one. Makes it trivial to
    # cross-reference against external ground-truth sources like
    # Untapped's CSV exports when investigating "why does this
    # card not show up" questions. Cheap to emit (few hundred KB
    # at most) and avoids a separate --debug-dump flag.
    raw_ids_path = output_dir / "raw-arena-ids.json"
    raw_id_entries: list[dict] = []
    for arena_id_str, qty in sorted(
        player_cards.items(),
        key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0,
    ):
        try:
            aid = int(arena_id_str)
        except ValueError:
            continue
        names = arena_index.get(aid) or []
        raw_id_entries.append(
            {
                "arena_id": aid,
                "quantity": int(qty),
                "resolved": bool(names),
                "names": list(names),
            },
        )
    atomic_write_json(
        raw_ids_path,
        {
            "source": collection_source,
            "count": len(raw_id_entries),
            "resolved_count": sum(1 for e in raw_id_entries if e["resolved"]),
            "unresolved_count": sum(1 for e in raw_id_entries if not e["resolved"]),
            "entries": raw_id_entries,
        },
    )

    # If we're running under sudo, restore output-file ownership to
    # the invoking user so subsequent non-sudo runs can read and
    # overwrite the files without fighting root permissions.
    _chown_outputs_to_sudo_user(
        collection_path,
        raw_ids_path,
        wildcards_path if inventory is not None else None,
        output_dir,
    )

    # Stdout summary.
    unique_count = len(collection_json["cards"])
    total_count = collection_json["total_cards"]
    source_label: str
    if collection_source == "untapped-csv":
        source_label = untapped_csv.name if untapped_csv is not None else "(CSV)"
    elif collection_log_source is not None:
        source_label = collection_log_source.name
    else:
        source_label = "(no log)"
    click.echo(
        f"mtga-import: {unique_count} unique cards, {total_count} total "
        f"from {source_label}",
    )
    if collection_source == "untapped-csv":
        click.echo(
            "  Collection: parsed from Untapped.gg CSV export "
            "(authoritative arena_id → name mapping)",
        )
    elif decks is not None:
        deck_count = len(decks)
        click.echo(
            f"  Collection: reconstructed from {deck_count} saved "
            f"deck{'s' if deck_count != 1 else ''} (UNRELIABLE — "
            f"may include cards from speculative decks you don't own, "
            f"and misses owned cards never put in a deck. "
            f"Use an Untapped.gg or Moxfield CSV for authoritative ownership)",
        )
    if untapped_csv is not None and collection_source != "untapped-csv":
        click.echo(
            f"  Name fallback: {untapped_csv.name} "
            "(used for arena_ids Scryfall bulk can't resolve)",
        )
    if (
        collection_log_source is not None
        and inventory_source is not None
        and collection_log_source != inventory_source
        and inventory is not None
    ):
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
        # Always print a compact range histogram so we can see
        # whether the unresolved ids cluster in specific grp_id
        # ranges (pointing at missing sets) or are spread across
        # every range (pointing at a bulk-file coverage gap — e.g.,
        # `default_cards` vs `all_cards`). 10k-id buckets roughly
        # correspond to Arena release eras. Each bucket line also
        # includes 5 example ids so the user can look them up via
        # Scryfall's web API to identify the coverage pattern.
        buckets: dict[int, list[int]] = {}
        for aid in sorted(unresolved_ids):
            bucket_key = (aid // 10_000) * 10_000
            buckets.setdefault(bucket_key, []).append(aid)
        for bucket_start in sorted(buckets):
            ids_in_bucket = buckets[bucket_start]
            sample = ids_in_bucket[:5]
            sample_str = ", ".join(str(i) for i in sample)
            click.echo(
                f"    [{bucket_start:>6}-{bucket_start + 9999:<6}] "
                f"{len(ids_in_bucket):>5} unresolved (e.g., {sample_str})",
            )
        if verbose:
            for arena_id in sorted(unresolved_ids):
                click.echo(f"    {arena_id}")
    click.echo(f"Collection: {collection_path}")
    if wildcards is not None:
        click.echo(f"Wildcards:  {wildcards_path}")


if __name__ == "__main__":
    main()
