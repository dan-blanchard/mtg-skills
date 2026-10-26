"""A type line's words: its card types and supertypes, and its subtypes.

Its own module, below ``deck`` (which re-exports both): the corrected trees read it
for a face phase has no record for (``_card_ir.trees``), and the trees store keys
by that module's import closure (``_card_ir.tree_store``), which ``deck``'s imports
would widen to the whole signal path.
"""

from __future__ import annotations

import re

#: The card types of a playable card's type line; its other words before the
#: dash are supertypes.
CARD_TYPE_WORDS: frozenset[str] = frozenset(
    {
        "creature",
        "artifact",
        "enchantment",
        "land",
        "sorcery",
        "instant",
        "planeswalker",
        "battle",
    }
)


def split_type_line(type_line: str) -> tuple[list[str], list[str]]:
    """Return ``(card_types, subtypes)`` split on em-dash.

    >>> split_type_line("Legendary Creature — Vampire Knight")
    (['legendary', 'creature'], ['vampire', 'knight'])
    >>> split_type_line("Sorcery")
    (['sorcery'], [])
    """
    if not type_line:
        return [], []
    parts = re.split(r"\s+[—\-]\s+", type_line, maxsplit=1)
    types_part = parts[0].strip()
    subs_part = parts[1].strip() if len(parts) > 1 else ""
    types = [w.lower() for w in types_part.split() if w]
    subs = [w.lower() for w in subs_part.split() if w]
    return types, subs
