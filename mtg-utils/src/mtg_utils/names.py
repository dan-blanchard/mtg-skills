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

This module is the single home for name -> key transforms. They look
similar but serve different purposes and are NOT interchangeable:

- ``normalize_card_name`` — cross-source identity fold (does name A from
  source A refer to the same card as name B from source B?). NFKD +
  ASCII-fold + lowercase; keeps punctuation.
  ``"Lim-Dûl's Vault"`` -> ``"lim-dul's vault"``
- ``slug`` — filesystem / art-catalog key (one name -> one
  safe-to-write-to-disk token). Lowercases, strips apostrophes, collapses
  everything else to hyphens. ``"Urza's Saga"`` -> ``"urzas-saga"``
- ``slugify`` — URL slug for an EDHREC commander page (one or more names ->
  one hyphenated path segment). Unlike ``slug``, hyphens already in the name
  become word separators (not dropped) and diacritics are folded via
  ``normalize_card_name`` rather than just lowercased; a DFC/meld name keeps
  only its front face and an Arena "A-" rebalance prefix is stripped — both
  because EDHREC pages the *original* card, not the alternate name/face.
  ``"Korvold, Fae-Cursed King"`` -> ``"korvold-fae-cursed-king"``
"""

from __future__ import annotations

import re
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


def slug(name: str) -> str:
    """Normalize a name to a filename-safe slug.

    Examples
    --------
    >>> slug("Eldrazi Spawn")
    'eldrazi-spawn'
    >>> slug("Urza's")
    'urzas'
    """
    s = name.lower()
    s = s.replace("'", "").replace("’", "")  # noqa: RUF001 (curly apostrophe is intentional)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def slugify(*names: str) -> str:
    """Build an EDHREC commander-page URL slug from one or more card names.

    Lifted out of ``edhrec_lookup`` (which keeps a re-export) so the module
    doc above can list it alongside the other name -> key transforms.

    Examples
    --------
    >>> slugify("Korvold, Fae-Cursed King")
    'korvold-fae-cursed-king'
    >>> slugify("Thrasios, Triton Hero", "Tymna the Weaver")
    'thrasios-triton-hero-tymna-the-weaver'
    """
    parts: list[str] = []
    for name in names:
        # EDHREC pages a DFC/meld card under its FRONT face only, and an Arena-
        # rebalanced "A-" card under the original (non-rebalanced) name. Slugging the
        # whole "Front // Back" string or keeping the "A-" prefix 403s/404s.
        base = name.split("//")[0].strip().removeprefix("A-")
        # Hyphens in card names (e.g., "Fae-Cursed") must become word separators
        # in the slug, so convert to spaces before stripping non-alphanumeric chars.
        hyphen_to_space = base.replace("-", " ")
        # ASCII-fold accented letters to their base (Márton -> marton, Nazgûl ->
        # nazgul), matching EDHREC's slugs. Deleting them outright (the old
        # re.sub([^a-zA-Z0-9 ])) gave "mrton-stromgald" and a 403. normalize_card_name
        # NFKD-decomposes, drops combining marks, and lowercases.
        folded = normalize_card_name(hyphen_to_space)
        cleaned = re.sub(r"[^a-z0-9 ]", "", folded)
        piece = re.sub(r"\s+", "-", cleaned.strip())
        parts.append(piece)
    return "-".join(parts)


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
    from mtg_utils.bulk_loader import load_bulk_cards

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
