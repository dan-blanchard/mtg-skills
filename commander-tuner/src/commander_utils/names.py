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
from pathlib import Path


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


def build_name_alias_map(bulk_path: Path) -> dict[str, str]:
    """Build ``normalized_alias -> normalized_canonical`` map from bulk data.

    Some cards are known on Arena by a different name than Scryfall's
    canonical ``name`` field:

    - **``printed_name``** — Through the Omenpaths (OM1) cards have
      Arena-specific names (e.g., "Skittering Kitten") while Scryfall
      uses the paper name ("Masked Meower").
    - **``flavor_name``** — Ikoria Godzilla variants, Crimson Vow
      Dracula variants, Avatar: The Last Airbender, Final Fantasy
      crossovers have IP names that Arena may display.

    Collection exports from Arena / Untapped.gg often use these
    alternate names, causing ``mark_owned`` to miss cards whose
    canonical name differs. This map lets callers fall back to alias
    matching when direct matching fails.

    Only English-language Arena cards are indexed. Non-English
    ``printed_name`` values (e.g., Japanese Mystical Archive) are
    excluded to avoid false matches.
    """
    from commander_utils.bulk_loader import load_bulk_cards

    cards = load_bulk_cards(bulk_path)
    aliases: dict[str, str] = {}
    for card in cards:
        if card.get("lang", "en") != "en":
            continue
        if "arena" not in (card.get("games") or []):
            continue
        name = card.get("name", "")
        if not name:
            continue
        canonical = normalize_card_name(name)

        for field in ("printed_name", "flavor_name"):
            alias_name = card.get(field, "")
            if not alias_name or alias_name == name:
                continue
            alias_key = normalize_card_name(alias_name)
            if alias_key != canonical and alias_key not in aliases:
                aliases[alias_key] = canonical
    return aliases
