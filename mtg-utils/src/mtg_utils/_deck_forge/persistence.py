"""Build library: crash-safe autosave + named, resumable builds (D14 / ADR-0011).

Each build is one JSON file under the store root. Writes are atomic (temp + rename)
so a crash mid-save can't corrupt a build. deck-forge deliberately departs from the
repo's no-resume convention because a creative tool spans days.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def _card_count(deck: dict) -> int:
    total = 0
    for zone in ("commanders", "cards", "sideboard"):
        total += sum(int(e.get("quantity", 1)) for e in deck.get(zone) or [])
    return total


class BuildStore:
    """Directory-backed store of saved deck builds."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, build_id: str) -> Path:
        return self.root / f"{build_id}.json"

    def save(self, build_id: str, name: str, deck: dict) -> None:
        record = {
            "id": build_id,
            "name": name,
            "deck": deck,
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        path = self._path(build_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic on POSIX

    def load(self, build_id: str) -> dict | None:
        path = self._path(build_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, build_id: str) -> bool:
        path = self._path(build_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list(self) -> list[dict]:
        """Summaries of every build, newest first."""
        out: list[dict] = []
        for path in self.root.glob("*.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            deck = rec.get("deck") or {}
            out.append(
                {
                    "id": rec.get("id", path.stem),
                    "name": rec.get("name", "Untitled"),
                    "format": deck.get("format", "commander"),
                    "card_count": _card_count(deck),
                    "updated_at": rec.get("updated_at", ""),
                }
            )
        out.sort(key=lambda r: r["updated_at"], reverse=True)
        return out
