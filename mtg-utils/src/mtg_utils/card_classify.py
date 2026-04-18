"""Shared card classification helpers for hydrated card dicts."""

from __future__ import annotations

import re

SKIP_LAYOUTS = frozenset(("token", "double_faced_token", "art_series"))

# Singleton-rule exemption patterns.
#
# Standard MTG deck-building rules cap non-basic cards at 4 copies (or 1 in
# singleton formats like Commander/Brawl). Some cards opt out via oracle
# text: "A deck can have any number of cards named X" (Relentless Rats,
# Persistent Petitioners, Hare Apparent, Shadowborn Apostle, Rat Colony,
# Dragon's Approach) or "A deck can have up to N cards named X" (Seven
# Dwarves, Nazgul). These cards break two assumptions:
#
#   1. Singleton legality (handled by legality_audit).
#   2. The Arena 4-cap rule: Arena normally treats ownership of 4 copies
#      of a card as "infinite" for deck-building purposes (you can never
#      need a 5th in a legal deck), but this substitution does NOT apply
#      to cards with an oracle exemption — you can legitimately want 17
#      Hare Apparent and Arena will charge wildcards for the 13 you don't
#      own. price_check uses ``has_copy_limit_exemption`` to gate the
#      4-cap substitution.
_ANY_NUMBER_PATTERN = "A deck can have any number of cards named"
_UP_TO_N_PATTERN = re.compile(
    r"A deck can have up to (\w+) cards named",
    re.IGNORECASE,
)
_WORD_TO_INT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def get_oracle_text(card: dict) -> str:
    """Get oracle text, falling back to joined card_faces for MDFCs/split cards."""
    oracle = card.get("oracle_text") or ""
    if not oracle:
        faces = card.get("card_faces", [])
        oracle = "\n// \n".join(
            f.get("oracle_text", "") for f in faces if f.get("oracle_text")
        )
    return oracle


def extract_price(card: dict | None) -> float | None:
    """Extract USD price from a card dict, preferring usd over usd_foil."""
    if card is None:
        return None
    prices = card.get("prices") or {}
    usd = prices.get("usd")
    if usd is not None:
        return float(usd)
    usd_foil = prices.get("usd_foil")
    if usd_foil is not None:
        return float(usd_foil)
    return None


def build_card_lookup(hydrated: list[dict | None]) -> dict[str, dict]:
    """Build name -> card dict lookup from a hydrated card list.

    Indexes by canonical name, DFC/MDFC front-face name, printed_name,
    and flavor_name so downstream tools (deck_stats, mana_audit, etc.)
    find cards regardless of which spelling the deck author used.
    Canonical names take priority — alias keys never overwrite them.

    DFC aliasing mirrors ``mark_owned._build_alias_lookup``: Moxfield,
    Arena, and plain-text deck exports commonly list a card by front
    face only (``"Hengegate Pathway"``) while Scryfall's bulk data uses
    the canonical combined form (``"Hengegate Pathway // Mistgate
    Pathway"``). Without this alias, ``card_lookup.get`` misses the
    entry and the card silently drops out of every downstream count
    (land_count, creature_count, CMC, color sources, legality checks).
    """
    lookup: dict[str, dict] = {}
    # Pass 1: canonical names
    for card in hydrated:
        if card is not None:
            lookup[card["name"]] = card
    # Pass 2: DFC / MDFC / split / adventure front-face aliases.
    # Standalone-wins: skip if a canonical card already owns this key.
    for card in hydrated:
        if card is None:
            continue
        name = card["name"]
        if " // " not in name:
            continue
        front_face = name.split(" // ", 1)[0]
        if front_face and front_face not in lookup:
            lookup[front_face] = card
    # Pass 3: Arena alternate names (printed_name / flavor_name)
    for card in hydrated:
        if card is None:
            continue
        for field in ("printed_name", "flavor_name"):
            alias = card.get(field)
            if alias and alias != card["name"] and alias not in lookup:
                lookup[alias] = card
    return lookup


def color_identity_subset(card_identity: list[str], allowed: set[str]) -> bool:
    """Check whether a card's color identity is a subset of the allowed colors."""
    return set(card_identity).issubset(allowed)


def is_land(card: dict) -> bool:
    """Check if type_line contains 'Land'."""
    type_line = card.get("type_line", "")
    return "Land" in type_line


def is_creature(card: dict) -> bool:
    """Check if type_line contains 'Creature'."""
    type_line = card.get("type_line", "")
    return "Creature" in type_line


def is_ramp(card: dict) -> bool:
    """Check if a non-land card produces mana or fetches lands."""
    if is_land(card):
        return False

    oracle = get_oracle_text(card)
    oracle_lower = oracle.lower()

    # Non-land cards that add mana in any form:
    #   "Add {C}{C}" / "Add {G}" — mana symbols
    #   "Add one mana of any color" — flexible mana (e.g. Birds of Paradise)
    #   "add mana of that color" — conditional mana (e.g. Bloom Tender)
    #   "Add X mana" — scaled mana (e.g. Nykthos)
    if re.search(r"add\s+(?:\{|one mana|mana of|an amount of mana)", oracle_lower):
        return True

    # Cards that search library for lands
    return "search your library for" in oracle_lower and "land" in oracle_lower


# Pattern to find explicit mana symbols in "Add {X}" patterns
_ADD_MANA_PATTERN = re.compile(r"[Aa]dd\s+(\{[^}]+\}(?:\s*(?:or\s+)?\{[^}]+\})*)")
_MANA_SYMBOL_PATTERN = re.compile(r"\{([WUBRGC])\}")

_FETCH_ANY_BASIC_PATTERN = re.compile(r"[Ss]earch your library for a basic land card")
_FETCH_BASIC_LAND_PATTERN = re.compile(
    r"[Ss]earch your library for (?:a |an )?(?:basic )?"
    r"((?:Plains|Island|Swamp|Mountain|Forest)"
    r"(?:(?:,|,? or) (?:Plains|Island|Swamp|Mountain|Forest))*)"
    r"(?: card| land)"
)

_BASIC_LAND_TYPES: dict[str, str] = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


def color_sources(card: dict) -> set[str]:
    """Parse which colors of mana a card can produce."""
    oracle = get_oracle_text(card)
    type_line = card.get("type_line", "") or ""
    colors: set[str] = set()

    # Check for "any color" first
    if re.search(r"[Aa]dd.*\bany color\b", oracle):
        return {"any"}

    # Check for "basic land card" fetch (any color)
    if _FETCH_ANY_BASIC_PATTERN.search(oracle):
        return {"any"}

    # Check for specific land type fetches
    for match in _FETCH_BASIC_LAND_PATTERN.finditer(oracle):
        types_text = match.group(1)
        for land_type, color in _BASIC_LAND_TYPES.items():
            if land_type in types_text:
                colors.add(color)

    # Check explicit Add {X} patterns
    for match in _ADD_MANA_PATTERN.finditer(oracle):
        symbols_text = match.group(1)
        for sym_match in _MANA_SYMBOL_PATTERN.finditer(symbols_text):
            colors.add(sym_match.group(1))

    # Check basic land types in type_line
    for land_type, color in _BASIC_LAND_TYPES.items():
        if land_type in type_line:
            colors.add(color)

    if not colors:
        return set()

    # If only colorless symbols found, return {C}
    if colors == {"C"}:
        return {"C"}

    # Remove C if we also found real colors
    colors.discard("C")
    return colors


def is_commander(card: dict, format: str = "commander") -> dict:  # noqa: A002
    """Check if a card is eligible to be a commander in the given format.

    Returns {"eligible": bool, "requires_partner": bool}.
    """
    type_line = card.get("type_line", "")
    oracle = get_oracle_text(card).lower()

    if "Legendary" not in type_line:
        return {"eligible": False, "requires_partner": False}

    # Legendary Creature — always eligible
    # Check "choose a background" before returning, since those creatures
    # support (but don't require) a Background partner.
    if "Creature" in type_line:
        requires_partner = "choose a background" in oracle
        return {"eligible": True, "requires_partner": requires_partner}

    # Legendary Vehicle — always eligible
    if "Vehicle" in type_line:
        return {"eligible": True, "requires_partner": False}

    # Legendary Spacecraft with P/T — always eligible
    if "Spacecraft" in type_line and card.get("power") and card.get("toughness"):
        return {"eligible": True, "requires_partner": False}

    # Brawl formats: Legendary Planeswalker — eligible
    if format in ("brawl", "historic_brawl") and "Planeswalker" in type_line:
        return {"eligible": True, "requires_partner": False}

    # "can be your commander" oracle text — eligible
    if "can be your commander" in oracle:
        return {"eligible": True, "requires_partner": False}

    # "Choose a Background" — eligible but needs Background partner
    if "choose a background" in oracle:
        return {"eligible": True, "requires_partner": True}

    # Legendary Background enchantment — eligible only as partner
    if "Background" in type_line and "Enchantment" in type_line:
        return {"eligible": True, "requires_partner": True}

    return {"eligible": False, "requires_partner": False}


def has_any_number_exemption(card: dict) -> bool:
    """True if oracle text reads "A deck can have any number of cards named X".

    Narrower than ``has_copy_limit_exemption``: returns False for the
    "up to N" variant, which still has a numeric cap. Used by
    ``legality_audit.check_singletons`` to short-circuit the cap check
    for unlimited cards.
    """
    return _ANY_NUMBER_PATTERN in get_oracle_text(card)


def named_card_cap(card: dict) -> int | None:
    """Return the integer cap from "A deck can have up to N cards named X".

    Returns None if the card has no such clause. Used by the singleton
    legality audit to permit up-to-N duplicates (e.g. 7 Seven Dwarves).
    """
    oracle = get_oracle_text(card)
    match = _UP_TO_N_PATTERN.search(oracle)
    if match is None:
        return None
    return _WORD_TO_INT.get(match.group(1).lower())


def has_copy_limit_exemption(card: dict) -> bool:
    """True if the card's oracle text lets a deck run more than 4 copies.

    Returns True for cards with either:
      - "A deck can have any number of cards named X" (unlimited)
      - "A deck can have up to N cards named X" (capped at N, but
        still exempts the card from the standard 4-copy limit)

    Used by ``price_check`` to suppress the Arena 4-cap substitution
    rule. Arena normally treats ownership of 4 copies of a playset-
    capped card as "infinite" because no legal deck can need a 5th —
    but for exempt cards, a deck can legitimately want 17 copies, so
    owning 4 does not grant the remaining 13.
    """
    oracle = get_oracle_text(card)
    if _ANY_NUMBER_PATTERN in oracle:
        return True
    return _UP_TO_N_PATTERN.search(oracle) is not None


_LAND_PRODUCES_MANA = re.compile(
    r"[Aa]dd\s+(?:\{[WUBRGC]|one mana|an? amount|X\s+mana|that much|mana of)",
    re.IGNORECASE,
)


def is_fixing_land(card: dict) -> bool:
    """True if a land counts toward the "fixing density" metric.

    This is the BROAD Lucky Paper definition used in ``cube-balance``'s
    fixing density check — it counts any land that helps a drafter cast
    multi-color spells:

    * Multi-color mana producers: duals (Overgrown Tomb), triomes, Command
      Tower, Exotic Orchard.
    * Any-color producers: City of Brass, Mana Confluence.
    * Land-fetchers that don't tap for mana: Evolving Wilds, Fabled Passage,
      fetchlands (Polluted Delta, Flooded Strand, etc.).

    Mono-color basic-producing lands and mono-color taplands are NOT fixing.

    Distinct from ``classify_cube_category`` which uses cube-utils' pack-
    template semantics (multi-color duals fill the L slot; only mana rocks
    and non-mana lands fill the F slot). Lucky Paper's published fixing
    numbers (17-28% at 360) measure the broader definition here.
    """
    if not is_land(card):
        return False
    sources = color_sources(card)
    if "any" in sources or len(sources) >= 2:
        return True
    # Lands that fetch lands without tapping for mana themselves
    # (Evolving Wilds, fetchlands). ``is_ramp`` early-returns for lands,
    # so we detect this by checking the oracle text directly.
    oracle = get_oracle_text(card).lower()
    return (
        "search your library for" in oracle
        and "land" in oracle
        and not _LAND_PRODUCES_MANA.search(get_oracle_text(card))
    )


def _land_produces_mana_directly(card: dict) -> bool:
    """True if a land has an explicit ``Add <mana>`` oracle clause.

    Distinguishes mana-producing lands (duals, Command Tower, Underground
    Sea, Karakas) from lands that only fetch other lands without tapping
    for mana (Evolving Wilds, Fabled Passage, Prismatic Vista, all fetch
    lands). A basic land's oracle text is empty — but basic lands produce
    mana by virtue of their type line, so callers short-circuit the basic
    case themselves.
    """
    oracle = get_oracle_text(card)
    if _LAND_PRODUCES_MANA.search(oracle):
        return True
    # Basic lands have empty oracle text; their type_line carries the mana
    # ability implicitly.
    type_line = card.get("type_line", "") or ""
    return any(t in type_line for t in _BASIC_LAND_TYPES)


def classify_cube_category(card: dict) -> str:
    """Classify a hydrated card into one of nine cube draft categories.

    Returns one of:
      "W" / "U" / "B" / "R" / "G" — mono-color non-land. Includes mana
            dorks and land-fetchers that have a color in their identity
            (Llanowar Elves, Birds of Paradise, Cultivate, Sakura-Tribe
            Elder). These slot into their mono-color pack position so
            every pack offers a color-specific card for each color.
      "M" — multicolor non-land (includes multicolor ramp like Golos).
      "L" — land that taps for mana directly (duals, Command Tower,
            basic-typed lands, utility lands with mana abilities).
      "F" — *colorless* fixing: cards with no color identity that
            produce mana of any kind (Sol Ring, Arcane Signet, Chromatic
            Lantern, Chromatic Sphere) or fetch lands (Wayfarer's Bauble,
            Expedition Map), *plus* lands that only sacrifice to fetch a
            land without tapping for mana themselves (Evolving Wilds,
            Fabled Passage, all fetch lands). Packs reserve one F slot
            so every pack offers a drafter a colorless fixing option.
      "C" — colorless non-land non-fixing (token generators, utility
            artifacts like Sensei's Divining Top, colorless threats).

    The key distinction from simpler "produces mana = fixing" rules:
    cube-utils pack templates put one-of-each-color in every pack, so a
    mana dork with color identity G belongs in the G slot (where it
    helps drafters building green) rather than the colorless F slot.
    Only cards with NO color identity compete for the F slot.

    Basic lands are unlimited outside the cube and not part of the draft
    pool, so ``F`` isn't about mana availability — it's about the
    colorless slot reserved for generically-useful fixing tools.

    Priority:
      land → (L vs F based on direct mana production)
      colorless non-land mana rock / land-fetcher → F
      multicolor → M
      mono-color (including colored mana dorks / colored ramp) → W/U/B/R/G
      colorless non-fixing → C
    """
    identity = card.get("color_identity", []) or []

    if is_land(card):
        if _land_produces_mana_directly(card):
            return "L"
        return "F"

    # Non-land F is restricted to COLORLESS fixing. Colored mana sources
    # (Llanowar Elves, Birds of Paradise, Cultivate) slot into their
    # mono-color position so each pack offers drafters color-specific
    # fixing help.
    if not identity and is_ramp(card):
        return "F"

    if len(identity) >= 2:
        return "M"

    if len(identity) == 1:
        return identity[0]

    return "C"
