"""Untapped.gg deckstrings: the ``ds`` field of every deck its meta API serves.

A V4 deckstring is URL-safe base64 (padding stripped) over LEB128 varints, read
from Untapped's own encoder (``nb`` / ``n_`` in its app bundle, 2026-10-05):

- a ``0`` byte, then the version (``4``);
- the command zone: a count, then per card the titleId as a delta from the
  previous one and its mechanic (``1`` commander, ``2`` companion);
- sections until a ``0``: a section id (``1`` main deck, ``2`` sideboard, ``3``
  wishboard), then five quantity groups — cards run 1, 2, 3 and 4 times, then a
  group whose rows carry their own quantity first. Each group is a count, then
  titleId deltas restarting from 0.

Cards are Arena **titleIds** (a card name across printings), never grpids.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

_COMMANDER, _COMPANION = 1, 2
_MAIN, _SIDEBOARD = 1, 2
_FIXED_GROUPS = (1, 2, 3, 4)


class DeckstringError(ValueError):
    """Not a deckstring this decoder reads."""


@dataclass(frozen=True, slots=True)
class DecodedDeck:
    """A deckstring's cards as ``(titleId, quantity)`` pairs, per zone."""

    commanders: tuple[int, ...]
    companions: tuple[int, ...]
    main: tuple[tuple[int, int], ...]
    sideboard: tuple[tuple[int, int], ...]


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.at = 0

    def varint(self) -> int:
        value = shift = 0
        while True:
            if self.at >= len(self.data):
                raise DeckstringError("truncated deckstring")
            byte = self.data[self.at]
            self.at += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value

    def done(self) -> bool:
        return self.at >= len(self.data)


def _section(reader: _Reader) -> list[tuple[int, int]]:
    cards: list[tuple[int, int]] = []
    for fixed in (*_FIXED_GROUPS, None):
        title = 0
        for _ in range(reader.varint()):
            quantity = fixed if fixed is not None else reader.varint()
            title += reader.varint()
            cards.append((title, quantity))
    return cards


def decode(deckstring: str) -> DecodedDeck:
    """The cards a V4 deckstring holds. Raises :class:`DeckstringError`."""
    try:
        data = base64.urlsafe_b64decode(deckstring + "=" * (-len(deckstring) % 4))
    except (ValueError, TypeError) as exc:
        raise DeckstringError("not base64") from exc
    reader = _Reader(data)
    if reader.done() or reader.varint() != 0:
        raise DeckstringError("missing the leading 0 byte")
    version = reader.varint()
    if version != 4:
        raise DeckstringError(f"unsupported deckstring version {version}")
    zone: dict[int, list[int]] = {_COMMANDER: [], _COMPANION: []}
    title = 0
    for _ in range(reader.varint()):
        title += reader.varint()
        zone.setdefault(reader.varint(), []).append(title)
    sections: dict[int, list[tuple[int, int]]] = {}
    while not reader.done():
        section = reader.varint()
        if section == 0:
            break
        sections[section] = _section(reader)
    return DecodedDeck(
        commanders=tuple(zone[_COMMANDER]),
        companions=tuple(zone[_COMPANION]),
        main=tuple(sections.get(_MAIN, ())),
        sideboard=tuple(sections.get(_SIDEBOARD, ())),
    )
