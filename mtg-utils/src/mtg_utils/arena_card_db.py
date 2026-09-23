"""The local MTG Arena card database: Arena's own record of what a card costs to craft.

Every Arena install ships its card database as a SQLite file,
``MTGA_Data/Downloads/Raw/Raw_CardDatabase_<hash>.mtga``. Each row is one printing, and
``IsPrimaryCard`` marks the printings Arena sells, the ones a wildcard crafts. A card's
wildcard cost is the lowest rarity among its primary printings. MTGJSON cannot say this
exactly: it has no primary flag, lists some printings at a sheet rarity Arena doesn't
charge (Special Guests as mythic), and misses some Arena availability. So when this
database is present it decides the rarity, and ``CardPool.rarity_index`` falls back to
MTGJSON only for cards it doesn't list.

Discovery, first hit wins:

1. ``$MTG_SKILLS_ARENA_CARD_DB``: a database path, or ``none`` to turn discovery off
   (the test suite does this, so an installed Arena never changes a test).
2. The download folder ``Player.log`` records (``[Manifest]Bundle download
   destination: <path>``), which follows the install wherever it lives.
3. The standard install locations.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

from mtg_utils.names import normalize_card_name

__all__ = [
    "ENV_VAR",
    "clear_memo",
    "find_card_db",
    "player_log_path",
    "primary_rarities",
]

ENV_VAR = "MTG_SKILLS_ARENA_CARD_DB"

_DB_GLOB = "Raw_CardDatabase_*.mtga"

# Arena's rarity codes; 1 is the basic-land rarity, 0 tokens and specials.
_RARITIES = {2: "common", 3: "uncommon", 4: "rare", 5: "mythic"}
_RANK = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}

_DESTINATION = re.compile(r"Bundle download destination:\s*(.+?)\s*$", re.MULTILINE)
_MARKUP = re.compile(r"<[^>]+>")


def _install_downloads() -> tuple[Path, ...]:
    """The Downloads folder of each standard Arena install on this platform."""
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library/Application Support/Steam/steamapps/common/MTGA"
            / "MTGA_Data/Downloads",
            Path("/Users/Shared/SteamShared/steamapps/common/MTGA/MTGA_Data/Downloads"),
            Path.home() / "Library/Application Support/com.wizards.mtga/Downloads",
        )
    if sys.platform == "win32":
        return tuple(
            Path(root) / "MTGA_Data" / "Downloads"
            for root in (
                r"C:\Program Files\Wizards of the Coast\MTGA",
                r"C:\Program Files (x86)\Steam\steamapps\common\MTGA",
                r"C:\Program Files\Epic Games\MagicTheGathering",
            )
        )
    return ()


_INSTALL_DOWNLOADS = _install_downloads()


def player_log_path() -> Path | None:
    """Where Arena writes ``Player.log`` on this platform (``None`` off
    Windows/macOS, or when Windows gives no ``%USERPROFILE%``)."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Logs/Wizards Of The Coast/MTGA/Player.log"
    if sys.platform == "win32":
        user_profile = os.environ.get("USERPROFILE")
        if not user_profile:
            return None
        return (
            Path(user_profile)
            / "AppData"
            / "LocalLow"
            / "Wizards Of The Coast"
            / "MTGA"
            / "Player.log"
        )
    return None


def _logged_downloads() -> Path | None:
    """The download folder ``Player.log`` names, read line by line so a long log
    stops at the first mention (it is written at startup)."""
    log = player_log_path()
    if log is None or not log.is_file():
        return None
    try:
        with log.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = _DESTINATION.search(line)
                if match:
                    return Path(match.group(1))
    except OSError:
        return None
    return None


def _newest_db(downloads: Path) -> Path | None:
    candidates = sorted(
        (downloads / "Raw").glob(_DB_GLOB), key=lambda p: p.stat().st_mtime_ns
    )
    return candidates[-1] if candidates else None


def find_card_db() -> Path | None:
    """The Arena card database to read, or ``None`` (see the module docstring for
    the order)."""
    override = os.environ.get(ENV_VAR)
    if override is not None:
        if override.strip().lower() in ("", "none"):
            return None
        path = Path(override)
        return path if path.is_file() else None
    logged = _logged_downloads()
    for downloads in (*([logged] if logged else []), *_INSTALL_DOWNLOADS):
        found = _newest_db(downloads)
        if found is not None:
            return found
    return None


def _title(plain: str | None, formatted: str | None) -> str | None:
    """The card's name: the plain row when Arena has one (the formatted row hides a
    rebalanced card's "A-" behind a sprite tag), else the formatted row with its
    markup stripped and a split card's ``///`` written as ``//``."""
    if plain:
        return plain
    if not formatted:
        return None
    return _MARKUP.sub("", formatted).replace(" /// ", " // ")


_MEMO: dict[tuple[str, int], dict[str, str]] = {}


def primary_rarities(path: Path) -> dict[str, str]:
    """``normalize_card_name(name) -> rarity``: each card's lowest rarity among its
    primary printings. Tokens, rebalanced (Alchemy "A-") printings and rows below
    common (basics, specials) are skipped. Memoized per (path, mtime)."""
    key = (str(path), path.stat().st_mtime_ns)
    cached = _MEMO.get(key)
    if cached is not None:
        return cached
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT c.Rarity,"
            " (SELECT Loc FROM Localizations_enUS WHERE LocId = c.TitleId"
            "   AND Formatted = 0 LIMIT 1),"
            " (SELECT Loc FROM Localizations_enUS WHERE LocId = c.TitleId"
            "   AND Formatted = 1 LIMIT 1)"
            " FROM Cards c"
            " WHERE c.IsPrimaryCard = 1 AND c.IsToken = 0 AND c.IsRebalanced = 0"
        ).fetchall()
    finally:
        con.close()
    rarities: dict[str, str] = {}
    for code, plain, formatted in rows:
        rarity = _RARITIES.get(code)
        name = _title(plain, formatted)
        if rarity is None or name is None:
            continue
        key_name = normalize_card_name(name)
        held = rarities.get(key_name)
        if held is None or _RANK[rarity] < _RANK[held]:
            rarities[key_name] = rarity
    _MEMO.clear()
    _MEMO[key] = rarities
    return rarities


def clear_memo() -> None:
    """Drop the memoized database read (test hygiene)."""
    _MEMO.clear()
