"""Corpus file names: ``session_YYYY-MM-DD_HHMM[_suffix].log.gz``.

The time is the session's start in local time, as the corpus names its own
(its ``harvest-log`` command uses the client's process start): the log's
``Startup Timestamp:`` line, else the archive file's timestamp (the archived
``Player-prev.log``'s last write, so the session's end). The suffix is the Arena
events the session's matches were played in, read off each match room's
``reservedPlayers[].eventId`` (``Ladder``, ``CubeDraft_Powered_20261020`` →
``ladder``, ``cubedraft-powered``): what the log itself says, never a guess at a
deck or format. A session with no match has no suffix. Nothing else goes in a
name — never the account folder, a handle, or the archive's own file hash.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from datetime import datetime

__all__ = [
    "CORPUS_NAME",
    "base_name",
    "match_events",
    "session_start",
    "suffix_of",
    "unique_name",
]

#: The corpus's naming rule (its ``check-log-sanitization`` workflow).
CORPUS_NAME = re.compile(
    r"^session_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}(_[a-zA-Z0-9_-]+)?\.log\.gz$"
)
#: The archive's file names: ``<YYYYMMDDTHHMMSS>-<hash>.log.gz``.
ARCHIVE_NAME = re.compile(r"^(?P<ts>\d{8}T\d{6})-[0-9a-f]+\.log(?:\.gz)?$")

_STARTUP = re.compile(
    r"^Startup Timestamp: (\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} [AP]M)",
    re.MULTILINE,
)
_EVENT_ID = re.compile(r"[A-Za-z0-9_]+")
_DATED = re.compile(r"_\d{8}$")
#: At most this many events in a suffix; more are marked ``_more``.
MAX_EVENTS = 3


def session_start(text: str, archive_name: str) -> datetime:
    """When the session started (local time): its ``Startup Timestamp:`` line,
    else the archive file name's timestamp."""
    m = _STARTUP.search(text)
    if m:
        try:
            return datetime.strptime(m[1], "%m/%d/%Y %I:%M:%S %p")  # noqa: DTZ007
        except ValueError:
            pass
    a = ARCHIVE_NAME.match(archive_name)
    if a is None:
        raise ValueError(f"no session time: no Startup Timestamp, {archive_name!r}")
    return datetime.strptime(a["ts"], "%Y%m%dT%H%M%S")  # noqa: DTZ007


def match_events(text: str) -> list[str]:
    """The Arena event ids of the session's matches, first seen first."""
    events: dict[str, None] = {}
    for line in text.splitlines():
        if "matchGameRoomStateChangedEvent" not in line or "{" not in line:
            continue
        try:
            msg = json.loads(line[line.find("{") :])
        except ValueError:
            continue
        room = (msg.get("matchGameRoomStateChangedEvent") or {}).get("gameRoomInfo")
        config = (room or {}).get("gameRoomConfig") or {}
        for player in config.get("reservedPlayers") or ():
            event = player.get("eventId")
            if isinstance(event, str) and _EVENT_ID.fullmatch(event):
                events[event] = None
    return list(events)


def suffix_of(events: list[str]) -> str:
    """``_ladder_picktwodraft-fra`` for those events; ``""`` for none."""
    parts = list(
        dict.fromkeys(_DATED.sub("", e).lower().replace("_", "-") for e in events)
    )
    if not parts:
        return ""
    shown = parts[:MAX_EVENTS] + (["more"] if len(parts) > MAX_EVENTS else [])
    return "_" + "_".join(shown)


def base_name(start: datetime, suffix: str) -> str:
    return f"session_{start:%Y-%m-%d_%H%M}{suffix}"


def unique_name(base: str, taken: Collection[str]) -> str:
    """``base.log.gz``, or with ``_2``, ``_3``, … when that name is taken."""
    name, n = f"{base}.log.gz", 1
    while name in taken:
        n += 1
        name = f"{base}_{n}.log.gz"
    return name
