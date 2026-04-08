"""Canonical card-name normalization for cross-source lookup.

A single implementation shared by every tuner script that needs to ask
"does this name from source A refer to the same card as this name from
source B?" Having one function rather than per-script copies matters
because the comparison is load-bearing for correctness: if two callers
drift on Unicode folding rules, a card can be "owned" by one script
and "unknown" to another, and the resulting bug is silent.

Callers today:

- ``find_commanders`` indexes a bulk-data card pool and looks up
  collection entries against it.
- ``mark_owned`` intersects a parsed deck against a parsed collection
  to populate ``owned_cards``.

Both need ``"Lim-Dul's Vault"`` (ASCII-only collection export) to match
``"Lim-Dûl's Vault"`` (bulk-data canonical) and neither cares about
case. If a future script needs a different normalization (e.g., split
cards), add a new function here rather than diverging in place.
"""

from __future__ import annotations

import unicodedata


def normalize_card_name(name: str) -> str:
    """Return a lowercased, ASCII-folded form of *name*.

    NFKD-decomposes accented characters, drops the combining marks,
    then lowercases. This lets an ASCII-only source (Moxfield CSV,
    typed-in card name) match the bulk-data canonical spelling which
    typically preserves diacritics.
    """
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower()
