"""Deterministic validators for the ten Ikoria companion deckbuilding conditions.

A companion is a card revealed from outside the game whose "Companion — [Condition]"
must be fulfilled by your STARTING deck (CR 702.139a, verified via rules-lookup).
Per CR 702.139b (verified): "If a companion ability refers to your starting deck, it
refers to your deck after you've set aside any sideboard cards. In a Commander game,
this is also before you've set aside your commander." — so callers must pass the
full starting deck INCLUDING commanders and EXCLUDING the sideboard and the
companion itself. A player may reveal at most one companion (CR 103.2b, verified).

Mana value grounding (all verified via rules-lookup):
- CR 202.3: mana value = total amount of mana in the mana cost, regardless of color.
- CR 202.3a: an object with no mana cost (e.g. a land) has mana value 0.
- CR 202.3b: a nonmodal double-faced card's mana value comes from its front face.
- CR 202.3e: {X} is treated as 0 while the object is not on the stack (so a card's
  library mana value already treats X as 0 — Scryfall's top-level ``cmc`` matches).
Therefore this module always reads the record's top-level ``cmc`` (0 when absent)
and never recomputes it from the mana-cost string. 0 is even, so lands are
Gyruda-legal by arithmetic alone.

Characteristics in the library (all verified via rules-lookup):
- CR 712.8a: while a double-faced card is outside the battlefield/stack, it has
  only the characteristics of its FRONT face.
- CR 715.4: in every zone except the stack, an adventurer card has only its normal
  characteristics (the creature half — Scryfall face 0).
- CR 709.4: in every zone except the stack, a split card's characteristics are its
  two halves COMBINED (but each half keeps its own mana cost — see Jegantha notes
  on ``_mana_costs``).

Card types / permanent types (verified via rules-lookup):
- CR 300.1: the card types are artifact, battle, conspiracy, creature, dungeon,
  enchantment, instant, kindred, land, phenomenon, plane, planeswalker, scheme,
  sorcery, and vanguard. ("Tribal" is the pre-2023 printed name for kindred and is
  normalized here.)
- CR 110.4: the six permanent types are artifact, battle, creature, enchantment,
  land, and planeswalker; instant and sorcery cards can't be permanents.

Every violation dict cites CR 702.139b because that is the rule that makes the
starting deck the object being validated.

This module is pure: no I/O, no network. Cards are hydrated Scryfall-shaped
records (``name``, ``cmc``, ``type_line``, ``oracle_text``, ``mana_cost``,
``keywords``, ``card_faces``, optional ``quantity``).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable

RULE = "702.139b"

COMPANION_NAMES: frozenset[str] = frozenset(
    {
        "Gyruda, Doom of Depths",
        "Jegantha, the Wellspring",
        "Kaheera, the Orphanguard",
        "Keruga, the Macrosage",
        "Lurrus of the Dream-Den",
        "Lutri, the Spellchaser",
        "Obosh, the Preypiercer",
        "Umori, the Collector",
        "Yorion, Sky Nomad",
        "Zirda, the Dawnwaker",
    }
)

# CR 300.1 (verified): the full card-type list.
CARD_TYPES: frozenset[str] = frozenset(
    {
        "artifact",
        "battle",
        "conspiracy",
        "creature",
        "dungeon",
        "enchantment",
        "instant",
        "kindred",
        "land",
        "phenomenon",
        "plane",
        "planeswalker",
        "scheme",
        "sorcery",
        "vanguard",
    }
)

# CR 110.4 (verified): the six permanent types.
PERMANENT_TYPES: frozenset[str] = frozenset(
    {"artifact", "battle", "creature", "enchantment", "land", "planeswalker"}
)

# Keyword abilities the CR defines as activated abilities, for Zirda's condition.
# Each entry was verified via rules-lookup on the cited rule:
#   Equip 702.6a, Cycling 702.29a (also Typecycling variants, same rule family),
#   Ninjutsu 702.49a, Transmute 702.53a, Forecast 702.57a, Aura Swap 702.65a,
#   Fortify 702.67a, Transfigure 702.71a, Reinforce 702.77a, Unearth 702.84a,
#   Level Up 702.87a, Scavenge 702.97a, Outlast 702.107a, Crew 702.122a,
#   Embalm 702.128a, Eternalize 702.129a, Reconfigure 702.151a, Craft 702.167a.
# (Boast, CR 702.142a, "adds additional rules to the activated ability that
# follows it" — the following ability is written with a colon in oracle text, so
# the colon heuristic already catches Boast cards.)
ACTIVATED_KEYWORDS: frozenset[str] = frozenset(
    {
        "equip",
        "cycling",
        "ninjutsu",
        "transmute",
        "forecast",
        "aura swap",
        "fortify",
        "transfigure",
        "reinforce",
        "unearth",
        "level up",
        "scavenge",
        "outlast",
        "crew",
        "embalm",
        "eternalize",
        "reconfigure",
        "craft",
    }
)

# CR 305.6 (verified): a land with a basic land type has the intrinsic activated
# ability "{T}: Add [mana symbol]" even with an empty text box. (Also confirmed by
# an official Zirda ruling, 2020-04-17: "Land cards with basic land types have
# intrinsic activated mana abilities associated with those types.")
_BASIC_LAND_TYPES: frozenset[str] = frozenset(
    {"plains", "island", "swamp", "mountain", "forest"}
)

# Kaheera's verified oracle condition names exactly these creature subtypes.
_KAHEERA_TYPES: frozenset[str] = frozenset(
    {"cat", "elemental", "nightmare", "dinosaur", "beast"}
)

# Layouts where CR 712.8a applies: only the front face's characteristics exist
# in the library.
_FRONT_FACE_ONLY_LAYOUTS = frozenset(
    {"transform", "modal_dfc", "meld", "reversible_card", "flip"}
)

_MANA_SYMBOL_RE = re.compile(r"\{([^{}]+)\}")
_REMINDER_TEXT_RE = re.compile(r"\([^()]*\)")


# ---------------------------------------------------------------------------
# Record-shape helpers
# ---------------------------------------------------------------------------


def _front_name(record: dict) -> str:
    """A record's front-face name (handles the Scryfall DFC "A // B" shape)."""
    name = record.get("name") or ""
    faces = record.get("card_faces") or []
    if faces and faces[0].get("name"):
        return faces[0]["name"]
    return name.split(" // ")[0].strip() if " // " in name else name


def _quantity(entry: dict) -> int:
    try:
        return max(1, int(entry.get("quantity", 1)))
    except (TypeError, ValueError):
        return 1


def _characteristic_faces(record: dict) -> list[dict]:
    """The face dicts whose characteristics exist while the card is in the library.

    - DFC layouts: front face only (CR 712.8a, verified).
    - Adventure: the normal (creature) half only, Scryfall face 0 (CR 715.4).
    - Split: both halves combined (CR 709.4).
    - No faces: the record itself.
    """
    faces = record.get("card_faces") or []
    if not faces:
        return [record]
    layout = (record.get("layout") or "").lower()
    if layout == "split":
        return list(faces)
    # transform / modal_dfc / adventure / unknown-with-faces: front face rules the
    # library (CR 712.8a; CR 715.4 for adventure). Defaulting unknown layouts to
    # the front face matches how the rest of mtg_utils reads DFC records.
    return [faces[0]]


def _type_words(record: dict) -> set[str]:
    """Lowercased words of the record's library type line(s), tribal→kindred."""
    words: set[str] = set()
    for face in _characteristic_faces(record):
        type_line = face.get("type_line") or ""
        # A faceless record may still carry a joined "A // B" type line; the front
        # segment is the library-relevant one (CR 712.8a) unless it's a split card,
        # which _characteristic_faces already expanded when faces are present.
        if " // " in type_line and not record.get("card_faces"):
            type_line = type_line.split(" // ")[0]
        for word in re.split(r"[\s—-]+", type_line):
            if word:
                words.add(word.lower())
    if "tribal" in words:  # pre-2023 name for kindred (CR 300.1)
        words.discard("tribal")
        words.add("kindred")
    return words


def _card_types(record: dict) -> set[str]:
    return _type_words(record) & CARD_TYPES


def _subtype_words(record: dict) -> set[str]:
    """Lowercased words appearing after the em dash on any library type line."""
    subtypes: set[str] = set()
    for face in _characteristic_faces(record):
        type_line = face.get("type_line") or ""
        for sep in ("—", " - "):
            if sep in type_line:
                _, _, tail = type_line.partition(sep)
                subtypes.update(w.lower() for w in tail.split() if w)
                break
    return subtypes


def _mana_value(record: dict) -> float:
    """Library mana value: the record's top-level cmc (CR 202.3 / 202.3a / 202.3b /
    202.3e — X counts as 0 in the library, no-cost cards are 0)."""
    try:
        return float(record.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def _mana_costs(record: dict) -> list[str]:
    """Each separately-checked mana cost of the record, for Jegantha.

    A card qualifies for Jegantha unless "any one card has the same symbol twice"
    in a mana cost (official Jegantha ruling, 2020-04-17, verified via
    rulings-lookup: {X}{X}{R} and {R/G}{R/G} both fail). Faces/halves keep their
    own mana costs, and only library-relevant faces are considered: front face
    for DFCs (CR 712.8a), the normal half for adventures (CR 715.4), both halves
    for split cards (CR 709.4) — each half's cost checked independently, matching
    tournament practice (e.g. Bonecrusher Giant {2}{R} // Stomp {1}{R} was
    Jegantha-legal in Standard).
    """
    faces = _characteristic_faces(record)
    costs: list[str] = []
    for face in faces:
        cost = face.get("mana_cost") or ""
        costs.extend(seg.strip() for seg in cost.split("//"))
    if not any(costs) and not record.get("card_faces"):
        cost = record.get("mana_cost") or ""
        costs = [seg.strip() for seg in cost.split("//")]
    return [c for c in costs if c]


def _oracle_texts(record: dict) -> list[str]:
    texts: list[str] = []
    for face in _characteristic_faces(record):
        text = face.get("oracle_text")
        if text:
            texts.append(text)
    if not texts and record.get("oracle_text"):
        texts.append(record["oracle_text"])
    return texts


def _keywords(record: dict) -> set[str]:
    kws = {str(k).lower() for k in record.get("keywords") or []}
    for face in record.get("card_faces") or []:
        kws.update(str(k).lower() for k in face.get("keywords") or [])
    return kws


def _strip_reminder_text(text: str) -> str:
    """Remove parenthesized reminder text (activated-keyword reminder text carries
    colons — e.g. cycling's "[Cost], Discard this card: Draw a card." — which must
    not satisfy Zirda's colon heuristic; see the official Zirda ruling that keyword
    activated abilities 'will have colons in their reminder text')."""
    return _REMINDER_TEXT_RE.sub("", text)


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def is_companion(record: dict) -> bool:
    """True when the record has the companion keyword ability (CR 702.139a).

    Prefers the Scryfall ``keywords`` list; falls back to an oracle-text
    "Companion —" line prefix on any face.
    """
    if "companion" in _keywords(record):
        return True
    texts = [record.get("oracle_text") or ""]
    texts += [f.get("oracle_text") or "" for f in record.get("card_faces") or []]
    for text in texts:
        for line in text.splitlines():
            if line.startswith(("Companion —", "Companion -")):
                return True
    return False


def _has_activated_ability(record: dict) -> bool:
    """Heuristic for Zirda: does this card's library face carry an activated ability?

    An activated ability is written "[Cost]: [Effect]" (CR 113.3b / 602.1,
    verified). Detection, in order:
    1. A basic land type grants the intrinsic "{T}: Add [mana]" ability even with
       an empty text box (CR 305.6, verified).
    2. A colon anywhere in the oracle text after stripping parenthesized reminder
       text (reminder colons, e.g. cycling's, must not count on their own).
    3. A keyword the CR defines as an activated ability (ACTIVATED_KEYWORDS,
       every entry rule-verified) — via the ``keywords`` list, or a line-leading
       keyword word in oracle text when the list is absent.

    Known misses of this text heuristic (documented, not silent): a card whose
    only activated ability lives in non-parenthesized text with unusual
    punctuation; abilities granted by other cards (irrelevant — Zirda checks the
    printed card); keyword activated abilities newer than the verified list whose
    records lack both a colon and a ``keywords`` entry.
    """
    if _subtype_words(record) & _BASIC_LAND_TYPES and "land" in _type_words(record):
        return True
    for text in _oracle_texts(record):
        if ":" in _strip_reminder_text(text):
            return True
    if _keywords(record) & ACTIVATED_KEYWORDS:
        return True
    for text in _oracle_texts(record):
        for line in _strip_reminder_text(text).splitlines():
            lowered = line.strip().lower()
            if any(lowered.startswith(kw) for kw in ACTIVATED_KEYWORDS):
                return True
    return False


# ---------------------------------------------------------------------------
# Per-companion condition checks
# ---------------------------------------------------------------------------
# Each validator receives the starting deck (per CR 702.139b: including
# commanders, excluding sideboard and the companion itself) and returns
# violation dicts. Oracle condition text in each docstring was verified
# against the local card data via scryfall-lookup.


def _violation(card: str | None, reason: str) -> dict:
    return {"card": card, "reason": reason, "rule": RULE}


def _check_gyruda(deck: list[dict]) -> list[dict]:
    """Gyruda, Doom of Depths — verified oracle condition: "Your starting deck
    contains only cards with even mana values."

    Lands and other no-cost cards are mana value 0 (CR 202.3a) and 0 is even, so
    they qualify. {X} counts as 0 in the library (CR 202.3e), so e.g. an {X}{X}
    cost is mana value 0 (even) while {X}{U} is 1 (odd).
    """
    out = []
    for card in deck:
        mv = _mana_value(card)
        if int(mv) % 2 != 0 or mv != int(mv):
            out.append(
                _violation(
                    _front_name(card),
                    f"Gyruda, Doom of Depths requires every card in the starting "
                    f"deck to have an even mana value; this card's mana value is "
                    f"{mv:g}.",
                )
            )
    return out


def _check_jegantha(deck: list[dict]) -> list[dict]:
    """Jegantha, the Wellspring — verified oracle condition: "No card in your
    starting deck has more than one of the same mana symbol in its mana cost."

    Exact-symbol comparison per the official 2020-04-17 ruling: {X}{X}{R} and
    {(r/g)}{(r/g)} both fail. Each face/half's cost is checked independently
    (see _mana_costs).
    """
    out = []
    for card in deck:
        for cost in _mana_costs(card):
            counts = Counter(_MANA_SYMBOL_RE.findall(cost))
            dupes = sorted(sym for sym, n in counts.items() if n > 1)
            if dupes:
                pretty = ", ".join("{" + s + "}" for s in dupes)
                out.append(
                    _violation(
                        _front_name(card),
                        f"Jegantha, the Wellspring requires that no card's mana "
                        f"cost contain more than one of the same mana symbol; "
                        f"{cost} repeats {pretty}.",
                    )
                )
                break
    return out


def _check_kaheera(deck: list[dict]) -> list[dict]:
    """Kaheera, the Orphanguard — verified oracle condition: "Each creature card
    in your starting deck is a Cat, Elemental, Nightmare, Dinosaur, or Beast card."

    Noncreature cards are unconstrained. A changeling card is every creature type
    everywhere, even outside the game (CR 702.73a, verified), so it qualifies.
    """
    out = []
    for card in deck:
        if "creature" not in _type_words(card):
            continue
        if "changeling" in _keywords(card):
            continue
        if any("changeling" in t.lower() for t in _oracle_texts(card)):
            continue
        if not (_subtype_words(card) & _KAHEERA_TYPES):
            out.append(
                _violation(
                    _front_name(card),
                    "Kaheera, the Orphanguard requires every creature card to be "
                    "a Cat, Elemental, Nightmare, Dinosaur, or Beast card; this "
                    "creature is none of those types.",
                )
            )
    return out


def _check_keruga(deck: list[dict]) -> list[dict]:
    """Keruga, the Macrosage — verified oracle condition: "Your starting deck
    contains only cards with mana value 3 or greater and land cards."

    Land cards are exempt by the explicit "and land cards" clause.
    """
    out = []
    for card in deck:
        if "land" in _type_words(card):
            continue
        mv = _mana_value(card)
        if mv < 3:
            out.append(
                _violation(
                    _front_name(card),
                    f"Keruga, the Macrosage requires every nonland card to have "
                    f"mana value 3 or greater; this card's mana value is {mv:g}.",
                )
            )
    return out


def _check_lurrus(deck: list[dict]) -> list[dict]:
    """Lurrus of the Dream-Den — verified oracle condition: "Each permanent card
    in your starting deck has mana value 2 or less."

    Permanent cards are those with a permanent type — artifact, battle, creature,
    enchantment, land, planeswalker (CR 110.4, verified). Instants and sorceries
    are unconstrained.
    """
    out = []
    for card in deck:
        if not (_type_words(card) & PERMANENT_TYPES):
            continue
        mv = _mana_value(card)
        if mv > 2:
            out.append(
                _violation(
                    _front_name(card),
                    f"Lurrus of the Dream-Den requires every permanent card to "
                    f"have mana value 2 or less; this card's mana value is "
                    f"{mv:g}.",
                )
            )
    return out


def _check_lutri(deck: list[dict]) -> list[dict]:
    """Lutri, the Spellchaser — verified oracle condition: "Each nonland card in
    your starting deck has a different name."

    Quantities count: a nonland entry with quantity 2 is two same-named cards.
    """
    totals: Counter[str] = Counter()
    display: dict[str, str] = {}
    for card in deck:
        if "land" in _type_words(card):
            continue
        name = _front_name(card)
        key = name.lower()
        display.setdefault(key, name)
        totals[key] += _quantity(card)
    out = []
    for key, count in sorted(totals.items()):
        if count > 1:
            out.append(
                _violation(
                    display[key],
                    f"Lutri, the Spellchaser requires every nonland card to have "
                    f"a different name; {count} copies of this card are in the "
                    f"starting deck.",
                )
            )
    return out


def _check_obosh(deck: list[dict]) -> list[dict]:
    """Obosh, the Preypiercer — verified oracle condition: "Your starting deck
    contains only cards with odd mana values and land cards."

    Land cards are exempt by the explicit "and land cards" clause (so a mana
    value 0 land is legal even though 0 is even).
    """
    out = []
    for card in deck:
        if "land" in _type_words(card):
            continue
        mv = _mana_value(card)
        if int(mv) % 2 != 1 or mv != int(mv):
            out.append(
                _violation(
                    _front_name(card),
                    f"Obosh, the Preypiercer requires every nonland card to have "
                    f"an odd mana value; this card's mana value is {mv:g}.",
                )
            )
    return out


def _check_umori(deck: list[dict]) -> list[dict]:
    """Umori, the Collector — verified oracle condition: "Each nonland card in
    your starting deck shares a card type."

    Card types, never subtypes (CR 300.1; official 2020-04-17 ruling: supertypes
    and subtypes don't count). Per the same ruling there must be ONE card type
    that every nonland card has — an artifact creature can bridge with both
    creatures and artifacts, but {artifact creature, artifact, creature} fails
    because no single type spans all three. Deck-level: returns one summary
    violation when the intersection is empty.
    """
    shared: set[str] | None = None
    considered = 0
    for card in deck:
        types = _card_types(card)
        if "land" in types:
            continue
        considered += 1
        shared = types if shared is None else shared & types
        if not shared:
            break
    if considered >= 2 and not shared:
        return [
            _violation(
                None,
                "Umori, the Collector requires all nonland cards in the starting "
                "deck to share a card type; no single card type is common to "
                "every nonland card.",
            )
        ]
    return []


def _check_yorion(deck: list[dict], deck_minimum: int | None) -> list[dict]:
    """Yorion, Sky Nomad — verified oracle condition: "Your starting deck contains
    at least twenty cards more than the minimum deck size."

    The minimum deck size comes from the format, so the caller supplies
    ``deck_minimum`` (e.g. 60 for 60-card constructed). When ``deck_minimum`` is
    None the deck's own size is treated as both minimum and maximum — the
    exact-size-format reading (e.g. Commander, where CR 903.5a, verified, sets
    minimum = maximum = 100) — which makes "minimum + 20" unsatisfiable, and one
    summary violation is reported saying so.
    """
    size = sum(_quantity(card) for card in deck)
    if deck_minimum is None:
        return [
            _violation(
                None,
                f"Yorion, Sky Nomad requires the starting deck to contain at "
                f"least 20 cards more than the minimum deck size; no format "
                f"minimum was supplied, so the deck's own size ({size}) is "
                f"treated as an exact size (minimum = maximum, as in Commander, "
                f"CR 903.5a), which makes the condition unsatisfiable.",
            )
        ]
    required = deck_minimum + 20
    if size < required:
        return [
            _violation(
                None,
                f"Yorion, Sky Nomad requires the starting deck to contain at "
                f"least 20 cards more than the minimum deck size ({deck_minimum} "
                f"+ 20 = {required}); the deck has {size}.",
            )
        ]
    return []


def _check_zirda(deck: list[dict]) -> list[dict]:
    """Zirda, the Dawnwaker — verified oracle condition: "Each permanent card in
    your starting deck has an activated ability."

    Nonpermanent cards (instants/sorceries, CR 110.4) are unconstrained. See
    _has_activated_ability for the detection heuristic and its documented misses.
    """
    out = []
    for card in deck:
        if not (_type_words(card) & PERMANENT_TYPES):
            continue
        if not _has_activated_ability(card):
            out.append(
                _violation(
                    _front_name(card),
                    "Zirda, the Dawnwaker requires every permanent card to have "
                    "an activated ability; none was detected on this card.",
                )
            )
    return out


_CHECKS: dict[str, Callable[[list[dict]], list[dict]]] = {
    "Gyruda, Doom of Depths": _check_gyruda,
    "Jegantha, the Wellspring": _check_jegantha,
    "Kaheera, the Orphanguard": _check_kaheera,
    "Keruga, the Macrosage": _check_keruga,
    "Lurrus of the Dream-Den": _check_lurrus,
    "Lutri, the Spellchaser": _check_lutri,
    "Obosh, the Preypiercer": _check_obosh,
    "Umori, the Collector": _check_umori,
    "Zirda, the Dawnwaker": _check_zirda,
}


def companion_violations(
    companion: dict,
    starting_deck: Iterable[dict],
    *,
    deck_minimum: int | None = None,
) -> list[dict]:
    """Validate ``starting_deck`` against ``companion``'s deckbuilding condition.

    ``starting_deck`` must be the full starting deck INCLUDING commanders (CR
    702.139b, verified) and EXCLUDING the companion itself and any sideboard.
    Entries may carry a ``quantity`` (default 1).

    ``deck_minimum`` is only consulted for Yorion, Sky Nomad — the format's
    minimum deck size (e.g. 60). Leave it None for exact-size formats such as
    Commander (CR 903.5a: minimum = maximum = 100), where Yorion's "+20"
    condition is unsatisfiable and reported as such.

    Returns [] when the condition is satisfied, else one violation dict per
    offending card — or one summary violation for the deck-level conditions
    (Umori, Yorion) — shaped::

        {"card": <name or None>, "reason": <str>, "rule": "702.139b"}

    Raises ValueError if ``companion`` is not one of the ten Ikoria companions.
    """
    name = _front_name(companion)
    deck = list(starting_deck)
    if name == "Yorion, Sky Nomad":
        return _check_yorion(deck, deck_minimum)
    check = _CHECKS.get(name)
    if check is None:
        raise ValueError(f"not a known companion: {name!r}")
    return check(deck)
