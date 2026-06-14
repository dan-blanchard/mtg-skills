"""Curated Commander staples — the cards that are broadly good in *most* commander
decks, offered as an always-present avenue filtered by color identity and format
legality.

This is a HARD-CODED, hand-curated list. That is deliberate and consistent with the
load-bearing contract (ADR-0009): the deterministic core names real cards; the session
agent never names a card from memory. It is NOT an EDHREC-popularity scrape — the
project ranks by synergy / curve / price and never by popularity (see the EDHREC
caveat memory). Inclusion here is by FUNCTION: every card fills a generically useful
role (ramp, fixing, card advantage, removal, interaction, protection, utility land)
and is useful regardless of archetype, so a random commander gets a sane "good stuff"
shortlist rather than archetype-specific payoffs (those come from the signal avenues).

Color identity is NOT duplicated here — it is a fact about the card read from the bulk
record at filter time. A staple is offered to a deck iff its color identity is a subset
of the deck's (the CR 903.4 rule the rest of the engine already enforces) AND it is
legal in the deck's format. The legality gate is load-bearing: Sol Ring is the #1
commander staple but is BANNED in Brawl / Historic Brawl, and most paper staples have
no Arena printing — so the brawl formats see a much shorter list.

Every name below was verified to resolve against the real Scryfall bulk with the
expected color identity and per-format legality during authoring.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

# Ordered so a grouped render reads ramp → fixing → advantage → removal → interaction →
# protection → lands. Used both to validate categories and to order the offered pool.
CATEGORY_ORDER: tuple[str, ...] = (
    "Ramp",
    "Fixing",
    "Card advantage",
    "Removal",
    "Interaction",
    "Protection",
    "Utility land",
)

# name -> category. Grouped by color in source order for readability only.
STAPLES: dict[str, str] = {
    # ── Colorless: fit ANY deck ───────────────────────────────────────────────
    "Sol Ring": "Ramp",
    "Arcane Signet": "Ramp",
    "Mind Stone": "Ramp",
    "Fellwar Stone": "Ramp",
    "Wayfarer's Bauble": "Ramp",
    "Thought Vessel": "Ramp",
    "Commander's Sphere": "Ramp",
    "Hedron Archive": "Ramp",
    "Worn Powerstone": "Ramp",
    "Thran Dynamo": "Ramp",
    "Solemn Simulacrum": "Ramp",
    "Burnished Hart": "Ramp",
    "Skullclamp": "Card advantage",
    "War Room": "Card advantage",
    "Bonders' Enclave": "Card advantage",
    "Swiftfoot Boots": "Protection",
    "Lightning Greaves": "Protection",
    "Command Tower": "Fixing",
    "Path of Ancestry": "Fixing",
    "Exotic Orchard": "Fixing",
    "Myriad Landscape": "Fixing",
    "Evolving Wilds": "Fixing",
    "Terramorphic Expanse": "Fixing",
    "Ash Barrens": "Fixing",
    "Bojuka Bog": "Utility land",
    "Reliquary Tower": "Utility land",
    "Rogue's Passage": "Utility land",
    # ── White ─────────────────────────────────────────────────────────────────
    "Swords to Plowshares": "Removal",
    "Path to Exile": "Removal",
    "Generous Gift": "Removal",
    "Despark": "Removal",
    "Wrath of God": "Removal",
    "Day of Judgment": "Removal",
    "Smothering Tithe": "Card advantage",
    "Esper Sentinel": "Card advantage",
    "Teferi's Protection": "Protection",
    "Flawless Maneuver": "Protection",
    # ── Blue ──────────────────────────────────────────────────────────────────
    "Counterspell": "Interaction",
    "Swan Song": "Interaction",
    "Negate": "Interaction",
    "Cyclonic Rift": "Removal",
    "Pongify": "Removal",
    "Rapid Hybridization": "Removal",
    "Rhystic Study": "Card advantage",
    "Mystic Remora": "Card advantage",
    "Fact or Fiction": "Card advantage",
    "Brainstorm": "Card advantage",
    "Ponder": "Card advantage",
    "Preordain": "Card advantage",
    # ── Black ─────────────────────────────────────────────────────────────────
    "Go for the Throat": "Removal",
    "Deadly Rollick": "Removal",
    "Feed the Swarm": "Removal",
    "Damnation": "Removal",
    "Toxic Deluge": "Removal",
    "Night's Whisper": "Card advantage",
    "Sign in Blood": "Card advantage",
    "Read the Bones": "Card advantage",
    "Village Rites": "Card advantage",
    # ── Red ───────────────────────────────────────────────────────────────────
    "Chaos Warp": "Removal",
    "Blasphemous Act": "Removal",
    "Vandalblast": "Removal",
    "Wheel of Fortune": "Card advantage",
    # ── Green ─────────────────────────────────────────────────────────────────
    "Cultivate": "Ramp",
    "Kodama's Reach": "Ramp",
    "Rampant Growth": "Ramp",
    "Farseek": "Ramp",
    "Nature's Lore": "Ramp",
    "Three Visits": "Ramp",
    "Sakura-Tribe Elder": "Ramp",
    "Wood Elves": "Ramp",
    "Birds of Paradise": "Ramp",
    "Llanowar Elves": "Ramp",
    "Nature's Claim": "Removal",
    "Beast Within": "Removal",
    "Krosan Grip": "Removal",
    "Heroic Intervention": "Protection",
    "Return of the Wildspeaker": "Card advantage",
}

_LEGAL = ("legal", "restricted")

# Colorless on the card, but only useful in a MULTICOLOR deck: any-color FIXING lands
# tap for "a color in your identity", so in a mono-color deck they're a strictly-worse
# (often tapped) basic — never surface them there (matches the no-Command-Tower-in-mono
# rule). Mana ROCKS (Arcane Signet, Fellwar, Commander's Sphere) still ramp in mono and
# stay universal; this set is only the fixing lands.
_MULTICOLOR_ONLY: frozenset[str] = frozenset(
    {"Command Tower", "Path of Ancestry", "Exotic Orchard"}
)


# Color-specific format staples, generated (data/format-staples.txt): cards played in
# >=20% of the commander decks whose color identity can include them (color-NORMALIZED
# broad play, not a flat popularity count), with basics and the curated function staples
# above removed. This is a deliberately popularity-INFORMED tier — distinct from the
# hand-curated function list above — so each color's genuinely-played best cards (Toxic
# Deluge, Mana Drain, Beast Within, …) are surfaced and counted as covered, not just the
# colorless good-stuff. Color-filtered + multicolor-gated at offer time like the rest.
# staples.py lives in mtg_utils/_deck_forge/, so the data dir is one level up.
_FORMAT_STAPLES_FILE = Path(__file__).parent.parent / "data" / "format-staples.txt"


def _load_format_staples() -> frozenset[str]:
    try:
        text = _FORMAT_STAPLES_FILE.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(ln.strip() for ln in text.splitlines() if ln.strip())


_FORMAT_STAPLES: frozenset[str] = _load_format_staples()


def staple_names() -> frozenset[str]:
    """The full staple name set: hand-curated function staples + the color-normalized
    format-staples tier (color-/format-agnostic; callers filter by identity)."""
    return frozenset(STAPLES) | _FORMAT_STAPLES


def staples_for(
    color_identity: str, by_name: Mapping[str, dict], *, legality_key: str = "commander"
) -> list[dict]:
    """Resolve the curated staples to the bulk records offered to a deck whose color
    identity is ``color_identity`` and whose format uses ``legality_key``.

    A staple is offered iff (1) it resolves in ``by_name``, (2) its color identity is a
    subset of the deck's (colorless fits any deck), and (3) it is legal/restricted in
    the format. Names absent from ``by_name`` (no bulk, or not in this bulk) are
    silently skipped. Sorted by category order then name for a stable, grouped render.
    """
    deck_ci = set(color_identity)
    multicolor = len(deck_ci) >= 2
    out: list[dict] = []
    # Curated function staples first, then the color-normalized format-staples tier.
    for name in (*STAPLES, *sorted(_FORMAT_STAPLES)):
        rec = by_name.get(name)
        if rec is None:
            continue
        if name in _MULTICOLOR_ONLY and not multicolor:
            continue  # any-color fixing land is dead in a mono-color deck
        if not set(rec.get("color_identity") or []) <= deck_ci:
            continue
        if (rec.get("legalities") or {}).get(legality_key) not in _LEGAL:
            continue
        out.append(rec)
    order = {cat: i for i, cat in enumerate((*CATEGORY_ORDER, "Format staple"))}
    out.sort(key=lambda r: (order.get(_category_of(r["name"]), 99), r["name"]))
    return out


def _category_of(name: str) -> str:
    """The curated category, or the generic 'Format staple' tier for derived staples."""
    return STAPLES.get(name, "Format staple")
