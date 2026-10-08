"""Shared card classification helpers for hydrated card dicts."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple

from mtg_utils._card_ir.crosswalk import (
    BASIC_LAND_TYPE_COLORS,
    land_searches,
    mana_colors,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils._name_index import NameIndex, build_name_index

SKIP_LAYOUTS = frozenset(
    # token / art_series / reversible_card are non-gameplay or cosmetic-reprint
    # printings. "reversible_card" is the Secret Lair novelty layout (e.g. Krark,
    # the Thumbless // Krark, the Thumbless): legally single-faced, with a null
    # top-level cmc/type_line, and always backed by a canonical printing — so it
    # would otherwise show up as a duplicate, mis-parsed search entry.
    ("token", "double_faced_token", "art_series", "reversible_card")
)


def _terminate_face(text: str) -> str:
    """Ensure a DFC face's oracle ends with sentence punctuation. A single-face effect
    must not be 'completed' by text on the OTHER side of the card, but the folded text
    joins faces, so a sentence-scoped regex (``[^.]*`` and friends) could otherwise
    bridge the ``// `` boundary — e.g. 'flying' on one face + 'create a token' on the
    other reading as 'creates flying tokens'. A trailing period is the hard stop
    ``[^.]*`` respects. Most faces already end in one; keyword-only faces ('Flying',
    'Daybound') don't, so add it."""
    stripped = text.rstrip()
    if stripped and not stripped.endswith((".", "!", '"', ")", "”")):
        return stripped + "."
    return text


def get_oracle_text(card: dict) -> str:
    """Get oracle text, falling back to joined card_faces for DFCs/split cards. Each
    face is sentence-terminated first (see ``_terminate_face``) so a ``[^.]*`` regex
    can't bridge two faces of the joined text."""
    oracle = card.get("oracle_text") or ""
    if not oracle:
        # `or []`, not a .get default: the MTGJSON adapter emits `card_faces: null`
        # on single-faced records, and a vanilla creature has no oracle_text either.
        faces = card.get("card_faces") or []
        oracle = "\n// \n".join(
            _terminate_face(f.get("oracle_text", ""))
            for f in faces
            if f.get("oracle_text")
        )
    return oracle


def get_colors(card: dict) -> set[str]:
    """The card's CASTABLE colors (its ``colors`` — the mana cost's, plus a color
    indicator), folding ``card_faces`` when the top level carries none: a transform
    / flip card is cast as its FRONT face (the back never enters from hand, the same
    rule ``classifying_type_line`` applies to its type), an MDFC as either face.
    Distinct from ``color_identity``, which also counts activation and rules-text
    symbols and is the Commander family's axis; a 60-card deck's colors are the
    colors it casts."""
    colors = card.get("colors")
    if colors:
        return set(colors)
    faces = card.get("card_faces") or []
    if card.get("layout") in ("transform", "flip"):
        faces = faces[:1]
    out: set[str] = set()
    for face in faces:
        out.update(face.get("colors") or [])
    return out


def get_mana_cost(card: dict) -> str:
    """Get the displayable mana cost, falling back to ``card_faces`` for DFCs.

    Transform / flip cards (and many MDFCs) carry an empty — or absent, hence
    ``None`` — top-level ``mana_cost``; the real cost lives on the front face,
    while the back of a transform card has none. Return the first face with a
    non-empty cost so a transform Saga shows its front cost and a land-front MDFC
    still finds the spell side. Single cost only (no " // " join) so the existing
    symbol renderer needs no separator handling."""
    cost = card.get("mana_cost") or ""
    if cost:
        return cost
    for face in card.get("card_faces") or []:
        face_cost = face.get("mana_cost") or ""
        if face_cost:
            return face_cost
    return ""


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


#: The price key for a finish (foil / etched); the nonfoil price is ``usd``.
FINISH_PRICE_KEYS: dict[str, str] = {"foil": "usd_foil", "etched": "usd_etched"}


def finish_price(card: Mapping | None, finish: str | None) -> float | None:
    """*card*'s USD price in *finish* — ``usd_foil`` / ``usd_etched`` for a foil or
    etched finish, ``usd`` otherwise — or None when that price isn't listed."""
    if card is None:
        return None
    value = (card.get("prices") or {}).get(FINISH_PRICE_KEYS.get(finish or "", "usd"))
    return float(value) if value is not None else None


def build_card_lookup(hydrated: Sequence[dict | None]) -> NameIndex:
    """Build a folding name -> card index from a hydrated (resolved-records) list.

    The keying — NFKD folding, every-face DFC aliases, Arena printed_name / flavor_name
    — is the shared ``_name_index`` core, so a deck author's spelling resolves to the
    canonical record regardless of case, diacritics ("Lim-Dul's Vault"), or which face
    they typed ("Hengegate Pathway"). Hydration already picked one record per name, so
    there's nothing to dedup (first-seen) and no prefilter. The returned ``NameIndex``
    folds the query on ``.get`` / ``in`` the same way the keys were folded — without
    that, a miss silently drops the card from every downstream count (lands, CMC,
    colors, legality).
    """
    return build_name_index(hydrated)


def color_identity_subset(card_identity: list[str], allowed: set[str]) -> bool:
    """Check whether a card's color identity is a subset of the allowed colors."""
    return set(card_identity).issubset(allowed)


def classifying_type_line(card: dict) -> str:
    """The type line to classify a card by. A transform/flip card enters as its FRONT
    face, so use that face's type — the back (e.g. a Saga that transforms into a Land or
    Creature) only appears conditionally and must not count for deckbuilding. Modal DFCs
    (either face is playable) and single-faced cards use the full type line.

    Use this anywhere a card's type is matched by substring (``card_type`` filters,
    serve/score classification) so a transform DFC's back-face type can't leak in —
    e.g. a Saga-front // Land-back card must not read as 'Land' for a manland search."""
    if card.get("layout") in ("transform", "flip"):
        faces = card.get("card_faces")
        if faces:
            return faces[0].get("type_line", "") or card.get("type_line", "")
    return card.get("type_line", "")


def _type_token_re(token: str) -> re.Pattern[str]:
    pat = _TYPE_TOKEN_CACHE.get(token)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(token)}\b")
        _TYPE_TOKEN_CACHE[token] = pat
    return pat


_TYPE_TOKEN_CACHE: dict[str, re.Pattern[str]] = {}


def type_line_has(type_line_lower: str, token_lower: str) -> bool:
    """Word-boundary type-line membership (both args pre-lowercased).

    A type filter must match whole type-line TOKENS, never substrings of
    another type: 'rat' is not a Pirate ("pi[rat]e"), 'orc' is not a Sorcery,
    'mount' is not a Mountain, 'bat' is not a Battle (CR 205.3 — each subtype
    is its own word). Multi-word filters ("basic land") match as a bounded
    phrase."""
    return _type_token_re(token_lower).search(type_line_lower) is not None


def is_land(card: dict) -> bool:
    """Check if the card's (front-face) type line contains 'Land'."""
    return "Land" in classifying_type_line(card)


def is_creature(card: dict) -> bool:
    """Check if the card's (front-face) type line contains 'Creature'."""
    return "Creature" in classifying_type_line(card)


#: The basic land names: the five basic land types (CR 305.6) plus Wastes; a
#: Snow-Covered basic shares the name with its prefix stripped.
BASIC_LAND_NAMES: frozenset[str] = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
)


def is_basic_land_name(name: str) -> bool:
    """Whether a card NAME is a basic land's (for a names-only read with no record —
    ``is_basic_land`` is the record read)."""
    return name.removeprefix("Snow-Covered ") in BASIC_LAND_NAMES


def is_basic_land(card: dict) -> bool:
    """A basic land, including Snow basics: a land whose type line says 'Basic'.

    The ``is_land`` guard keeps a non-land card that merely mentions "basic" in
    its text from matching. Centralizes the basic-land test that had drifted into
    three incompatible private helpers (legality_audit, tuner swaps, deck-forge).
    """
    return is_land(card) and "basic" in (card.get("type_line") or "").lower()


#: The evasion keyword abilities a limited scan counts (a body that gets past
#: blockers) — read off the record's ``keywords``.
EVASION_KEYWORDS: frozenset[str] = frozenset(
    {
        "Flying",
        "Menace",
        "Trample",
        "Shadow",
        "Fear",
        "Intimidate",
        "Skulk",
        "Horsemanship",
    }
)


def has_evasion(card: dict) -> bool:
    """Whether a card carries one of ``EVASION_KEYWORDS``."""
    return any(k in EVASION_KEYWORDS for k in card.get("keywords") or [])


def card_pt_int(card: dict, field: str = "power") -> int:
    """A creature's printed power/toughness as an int, defaulting non-numeric
    values (``*``, ``X``, missing) to 0. Centralizes the parse that had been
    reimplemented in the gauntlet builder, tuner metrics, and signal specs."""
    try:
        return int(str(card.get(field) or 0))
    except (TypeError, ValueError):
        return 0


_COLOR_PIP_RE = re.compile(r"\{([WUBRG])\}")


def count_color_pips(mana_cost: str) -> dict[str, int]:
    """Count colored mana pips (W/U/B/R/G) in a mana-cost string.

    The shared primitive behind every pip tally (mana_audit pip demand, the
    goldfish color model, the custom-format classifier), which had reimplemented
    the same ``{([WUBRG])}`` scan. Callers that need a card's faces (modal DFCs)
    pick the cost string first, then pass it here.
    """
    out: dict[str, int] = {}
    for m in _COLOR_PIP_RE.finditer(mana_cost or ""):
        out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


# The regexes from here to ``ramp_by_text`` are ITS no-coverage text degrade (ADR-0051)
# and stay; every other card read in this module goes through phase's trees.
# ``_REMINDER_RE`` is also ``twohg_scan``'s oracle-text fallback.
#
# Reminder text (always parenthetical) describes a TOKEN's ability, not the card's own
# — so a counterspell that hands an opponent Treasures carries "(… Add one mana …)" even
# though it produces no mana for you.
_REMINDER_RE = re.compile(r"\([^)]*\)")
_ADD_MANA_RE = re.compile(
    r"add\s+(?:\{|(?:one|two|three|four|five|six|seven|eight|nine|ten|x) mana\b"
    r"|mana of|an amount of (?:mana|\{))"
)
# Mana AMPLIFIERS: "add(s) an additional {X}/mana" when you tap a land (Nirkana
# Revenant, Crypt Ghast, Caged Sun, Gauntlet of Power, High Tide, Bubbling Muck). The
# mana symbol isn't adjacent to "add", so _ADD_MANA_RE misses it — but they ramp you
# (extra mana per land); symmetric ones (Mana Flare) still ramp the controller.
_AMPLIFY_MANA_RE = re.compile(
    r"adds? an additional (?:\{|mana|one mana)", re.IGNORECASE
)
# Land-acceleration ramp that adds no mana directly: extra land drops (Azusa,
# Exploration, Dryad of the Ilysian Grove) and putting a land from hand into play
# (Arboreal Grazer, Burgeoning) — both accelerate your mana via lands.
_EXTRA_LAND_RE = re.compile(r"play [^.]{0,18}additional lands?", re.IGNORECASE)
_LAND_FROM_HAND_RE = re.compile(
    r"put a land card from your hand onto the battlefield", re.IGNORECASE
)
# A land search naming basic land types ("a Forest card", "a Plains or Island card").
_FETCH_BASIC_LAND_PATTERN = re.compile(
    r"[Ss]earch your library for (?:a |an )?(?:basic )?"
    r"((?:Plains|Island|Swamp|Mountain|Forest)"
    r"(?:(?:,|,? or) (?:Plains|Island|Swamp|Mountain|Forest))*)"
    r"(?: card| land)"
)
# Phrases that hand a created token to someone other than you (An Offer You Can't
# Refuse: "Its controller creates two Treasure tokens").
_OPPONENT_DIRECTED = (
    "its controller",
    "target opponent",
    "each opponent",
    "target player",
)


def ramp_by_text(card: dict) -> bool:
    """Oracle-text read of "is this nonland card ramp" — the NO-COVERAGE DEGRADE only.

    ``_analysis.roles.is_ramp`` owns the ramp answer (the ``ramp`` preset, a view
    over the signal path — ADR-0051) and falls back here ONLY for a card the signal
    path cannot see: a synthetic record with no ``oracle_id``, or a run with no
    phase card-data. Do not call this to classify a real card — ask ``roles.is_ramp``.

    Note: mana-token makers (Treasure/Gold/Powerstone) are detected only via the
    token's "Add … mana" reminder text (the second ``_ADD_MANA_RE`` branch below).
    A printing that omits that reminder text is not counted as ramp here — counting
    raw "create a Treasure" would also sweep in one-shot value tokens, so widening
    it is a deliberate policy choice, not made here.
    """
    if is_land(card):
        return False

    oracle = get_oracle_text(card)
    oracle_lower = oracle.lower()

    # Non-land cards that add mana in any form:
    #   "Add {C}{C}" / "Add {G}" — mana symbols
    #   "Add one mana of any color" — flexible mana (e.g. Birds of Paradise)
    #   "add mana of that color" — conditional mana (e.g. Bloom Tender)
    #   "Add X mana" — scaled mana (e.g. Nykthos)
    # The card ITSELF adds mana when the match survives stripping reminder text.
    if _ADD_MANA_RE.search(_REMINDER_RE.sub("", oracle_lower)):
        return True
    # Otherwise the only "add mana" is a token's reminder (Treasure/Gold/…). That's ramp
    # when YOU keep the token (Dockside, Smothering Tithe), NOT when it's handed to an
    # opponent (An Offer You Can't Refuse counters a spell, Treasuring its controller).
    if _ADD_MANA_RE.search(oracle_lower):
        return not any(p in oracle_lower for p in _OPPONENT_DIRECTED)

    # Mana amplifiers ("add an additional {X}" per land tapped) ramp you too.
    if _AMPLIFY_MANA_RE.search(oracle_lower):
        return True
    # Cards that search the library for a LAND and put it onto the battlefield are ramp.
    # Require the battlefield destination — a land TUTOR to hand (Moonsilver Key, Sylvan
    # Scrying) adds no mana and drops no land, so it is not acceleration — and match the
    # land by basic-land subtype name / "land card" / "basic land", not a raw "land"
    # substring (which missed "Forest card" yet let "Island" slip through).
    if (
        "search your library for" in oracle_lower
        and "onto the battlefield" in oracle_lower
        and (
            _FETCH_BASIC_LAND_PATTERN.search(oracle)
            or "land card" in oracle_lower
            or "basic land" in oracle_lower
        )
    ):
        return True
    # Land-acceleration that adds no mana: extra land drops (Azusa) and put-a-land-from-
    # hand (Arboreal Grazer, Burgeoning) — both ramp your lands ahead of the curve.
    return bool(
        _EXTRA_LAND_RE.search(oracle_lower) or _LAND_FROM_HAND_RE.search(oracle_lower)
    )


def _face_basic_land_colors(card: dict) -> set[str]:
    """The colours of the basic land types on the card's own type line: a land
    with a basic land type taps for that type's colour by its intrinsic ability
    (CR 305.6), even with no text box. Per " // " face, so a non-land face's
    subtypes never count. A type-line read: it holds for a card phase has no
    trees for (a new-set dual)."""
    out: set[str] = set()
    for face in (card.get("type_line") or "").split(" // "):
        if "Land" not in face:
            continue
        low = face.lower()
        out.update(
            color
            for land_type, color in BASIC_LAND_TYPE_COLORS.items()
            if type_line_has(low, land_type.lower())
        )
    return out


def _taps_for_mana(card: dict) -> bool:
    """Whether the card itself adds mana: a ``Mana`` effect in its trees, or a basic
    land type on a land's type line (CR 305.6)."""
    return bool(_face_basic_land_colors(card)) or any(
        mana_colors(tree) for tree in trees_for(card)
    )


def color_sources(card: dict) -> set[str]:
    """Which colours of mana a card can produce: ``{"any"}``, a set of colour letters,
    ``{"C"}`` for colorless only, or empty.

    Read off phase's trees: the card's own ``Mana`` effects
    (``crosswalk.mana_colors`` — Arcane Sanctum's {W}, {U}, or {B} is all three;
    a filter land's combinations, Cascade Bluffs U/R; a deck-dependent kind such as
    Command Tower reads ``"any"``), plus a land search of YOURS that puts the land
    onto the battlefield (``crosswalk.land_searches`` — a fetch land's types; a basic
    land of any type reads ``"any"``), plus the basic land types on a land's type line
    (CR 305.6). A Treasure maker is not a colour source — this module's own
    decision: the Treasure is a one-shot sacrifice, so ramp counts it and colour
    balance doesn't — and a landcycling card's search puts the land into hand (CR
    702.29e), so it adds no colour. A card phase has no trees for reads its type
    line only."""
    colors = _face_basic_land_colors(card)
    for tree in trees_for(card):
        produced = mana_colors(tree)
        if produced == "any":
            return {"any"}
        colors |= produced
        for search in land_searches(tree):
            if not search.to_battlefield:
                continue
            if not isinstance(search.colors, frozenset):  # any / any_basic
                return {"any"}
            colors |= search.colors
    if colors == {"C"}:
        return {"C"}
    colors.discard("C")
    return colors


class LandFetch(NamedTuple):
    """What a "search your library for a land" effect actually delivers.

    ``color_sources`` answers the coarse question (which colors could this make,
    with a generic basic search collapsing to ``{"any"}``). Simulators need three
    more facts before they can credit mana for the effect, so they live here rather
    than being re-derived per consumer:

    * ``colors`` — resolved against the deck's own basics, because a generic
      "basic land" search can only find what the deck actually runs.
    * ``to_battlefield`` — a search that puts the land in *hand* produces no mana
      now; only "onto the battlefield" does.
    * ``enters_tapped`` — delays the land by a turn.
    * ``on_etb`` — True for the card's own enters trigger (Wood Elves; Primeval
      Herald's "enters or attacks", whose enters event is an ETB per CR 603.6a).
      False means the fetch sits behind
      an activation cost the caller must price itself. Note CR 302.6 scopes summoning
      sickness to *creatures*, so an artifact fetcher may legally tap the turn it
      enters; the unmodeled cost, not sickness, is why callers generally skip these.
    * ``count`` — lands it puts where it puts them. Explosive Vegetation and Krosan
      Verge fetch two.
    """

    colors: frozenset[str]
    to_battlefield: bool
    enters_tapped: bool
    on_etb: bool
    count: int


def land_fetch_profile(
    card: dict, *, deck_basic_colors: frozenset[str] = frozenset()
) -> LandFetch | None:
    """Resolve the card's land search, or ``None`` when it has none of YOUR library.

    Scryfall leaves ``produced_mana`` empty for every land whose only mana ability
    is sacrificing itself to fetch a basic (Evolving Wilds, Hobbit Hole), so a
    model keyed solely off ``produced_mana`` scores them as colorless while still
    counting them toward available mana — reporting *more* color screw the more
    fixing a deck runs. See tests/mtg-utils/test_playtest_goldfish.py.

    Read off phase's trees (``crosswalk.land_searches``): an opponent's compensation
    search (Path to Exile, Ghost Quarter) is not the card's, and a landcycling
    search is left out — it functions only while the card is in your hand (CR
    702.29a). The search that reaches the battlefield is the profile's; a basic land
    of any type, or any land card, resolves to ``deck_basic_colors`` — what the
    deck's own basics can make.

    ``None`` means "no land-search effect here". A returned profile with an EMPTY
    ``colors`` means "there is one, but it can't be resolved" — a generic basic
    search in a deck running no basics. Keeping those distinct lets a caller label
    the card a fetch (deck-stats) or warn about it, instead of silently treating an
    unresolvable fetch as if the card had no such ability at all. A card phase has
    no trees for has no profile.
    """
    searches = [
        s for tree in trees_for(card) for s in land_searches(tree) if not s.cycling
    ]
    if not searches:
        return None
    landing = [s for s in searches if s.to_battlefield] or searches
    primary = landing[0]
    colors: set[str] = set()
    for search in landing:
        if isinstance(search.colors, frozenset):
            colors |= search.colors
        else:  # any_basic / any: what the deck's own basics can make
            colors |= deck_basic_colors
    return LandFetch(
        colors=frozenset(colors),
        to_battlefield=primary.to_battlefield,
        enters_tapped=primary.enters_tapped,
        on_etb=primary.on_self_etb,
        count=primary.count,
    )


def is_commander(
    card: dict,
    *,
    planeswalker_commander_requires_text: bool = True,
) -> dict:
    """Commander eligibility from the card's TYPE LINE and phase's trees alone.

    Returns {"eligible": bool, "requires_partner": bool}.

    Knows nothing about formats: legality is ``formats.Format.legality``, and
    ``Format.commander_eligibility`` composes the two. The one format-dependent rule
    — whether a legendary planeswalker needs "can be your commander" (Commander) or
    is eligible outright (the Brawl family, CR 903.12c) — arrives as the flag.

    A legendary creature, Vehicle or Spacecraft with power/toughness is eligible by
    type (CR 903.3); "can be your commander" is phase's ``root.is_commander``
    (``ConceptTree.can_be_commander`` — Grist, the Hunger Tide's ruling: it "can be
    your commander as its first ability works before the game begins during deck
    construction"); choose a Background is phase's ``Partner`` keyword. A legendary
    Background enchantment is eligible only beside a choose-a-Background commander
    (CR 702.124k). A card phase has no trees for is judged on its type line alone.
    """
    type_line = card.get("type_line", "")
    if "Legendary" not in type_line:
        return {"eligible": False, "requires_partner": False}

    trees = trees_for(card)
    chooses_background = any(
        variant == "ChooseABackground"
        for tree in trees
        for variant, _data in tree.card_partner_kinds
    )

    # Legendary Creature — always eligible; a choose-a-Background creature pairs
    # with a Background.
    if "Creature" in type_line:
        return {"eligible": True, "requires_partner": chooses_background}

    # Legendary Vehicle — always eligible
    if "Vehicle" in type_line:
        return {"eligible": True, "requires_partner": False}

    # Legendary Spacecraft with P/T — always eligible
    if "Spacecraft" in type_line and card.get("power") and card.get("toughness"):
        return {"eligible": True, "requires_partner": False}

    # Brawl family: any Legendary Planeswalker is eligible; Commander keeps requiring
    # "can be your commander". The format's flag decides, never a name tuple.
    if "Planeswalker" in type_line and not planeswalker_commander_requires_text:
        return {"eligible": True, "requires_partner": False}

    # Legendary Background enchantment — eligible only as partner (CR 702.124k).
    if "Background" in type_line and "Enchantment" in type_line:
        return {"eligible": True, "requires_partner": True}

    # "Choose a Background" — eligible but needs a Background partner.
    if chooses_background:
        return {"eligible": True, "requires_partner": True}

    # "can be your commander" — phase's own verdict.
    if any(tree.can_be_commander for tree in trees):
        return {"eligible": True, "requires_partner": False}

    return {"eligible": False, "requires_partner": False}


class PartnerAbility(NamedTuple):
    """One partner ability (CR 702.124a): ``kind`` is ``plain`` (partner,
    702.124h), ``group`` (partner—[text], 702.124i; ``value`` the text),
    ``with`` (partner with [name], 702.124j; ``value`` the name),
    ``choose_background`` / ``background`` (702.124k), or
    ``doctors_companion`` / ``doctor`` (702.124m)."""

    kind: str
    value: str = ""


#: Phase's ``Partner`` keyword variant → ``(kind, value)``; a None value passes the
#: keyword's own data through (the named partner, the corrected partner—[text]
#: group — ``crosswalk.PARTNER_GROUPS_PHASE_COLLAPSES``). CR 702.124a's abilities:
#: partner (702.124h), partner—[text] (702.124i), partner with [name] (702.124j),
#: choose a Background (702.124k), Doctor's companion (702.124m).
_PARTNER_KIND_OF_VARIANT: dict[str, tuple[str, str | None]] = {
    "Generic": ("plain", ""),
    "Group": ("group", None),
    "FriendsForever": ("group", "Friends forever"),
    "CharacterSelect": ("group", "Character select"),
    "With": ("with", None),
    "ChooseABackground": ("choose_background", ""),
    "DoctorsCompanion": ("doctors_companion", ""),
}


def partner_abilities(card: dict) -> frozenset[PartnerAbility]:
    """Every partner ability the card has (CR 702.124a) — a SET, since a card can
    print two (Amy Pond: Doctor's companion and partner with Rory Williams; CR
    702.124g lets you use either, never both).

    Read off the trees' ``Partner`` keywords (``ConceptTree.card_partner_kinds``);
    a Background and a Time Lord Doctor are type-line reads (they have no keyword
    of their own). A card phase has no trees for keeps only those type-line kinds.

    CR 702.124a: a partner ability lets you designate two LEGENDARY cards as your
    commander, so a nonlegendary card has none to use — checked first, off the
    front face's type line, before any tree is built (a partner search walks the
    whole pool)."""
    types, _, subtypes = (
        classifying_type_line(card).split(" // ")[0].partition("\u2014")
    )
    if "Legendary" not in types:
        return frozenset()
    out: set[PartnerAbility] = set()
    for tree in trees_for(card):
        for variant, data in tree.card_partner_kinds:
            mapped = _PARTNER_KIND_OF_VARIANT.get(variant)
            if mapped is not None:
                kind, value = mapped
                out.add(PartnerAbility(kind, data if value is None else value))
    # A Background enchantment (CR 702.124k); a Time Lord Doctor creature with no
    # other creature types (CR 702.124m).
    if "Enchantment" in types and type_line_has(subtypes.lower(), "background"):
        out.add(PartnerAbility("background"))
    if "Creature" in types and subtypes.strip() == "Time Lord Doctor":
        out.add(PartnerAbility("doctor"))
    return frozenset(out)


#: The kind each one-sided ability pairs with (CR 702.124k, 702.124m).
_PARTNER_COMPLEMENT = {
    "choose_background": "background",
    "background": "choose_background",
    "doctors_companion": "doctor",
    "doctor": "doctors_companion",
}


def can_partner(abilities: Iterable[Sequence[str]], candidate: dict) -> bool:
    """Whether ``candidate`` can be the second commander of a card with
    ``abilities`` (``(kind, value)`` pairs — :class:`PartnerAbility` or their JSON
    form). One ability of each card must match, the SAME ability on both for
    partner and partner—[text] (CR 702.124f, 702.124h, 702.124i), the named card
    for partner with [name] (702.124j), the other half for choose a Background
    (702.124k) and Doctor's companion (702.124m)."""
    theirs = partner_abilities(candidate)
    name = candidate.get("name") or ""
    for kind, value in abilities:
        if kind == "with":
            if value and (name == value or name.split(" // ")[0] == value):
                return True
        elif kind in _PARTNER_COMPLEMENT:
            if PartnerAbility(_PARTNER_COMPLEMENT[kind]) in theirs:
                return True
        elif PartnerAbility(kind, value) in theirs:
            return True
    return False


def valid_partner_search(card: dict) -> dict | None:
    """``card_search`` filter that finds the cards legally eligible to be ``card``'s
    paired second commander (CR 702.124), or ``None`` if it has no partner ability.

    ``partner_of`` carries the card's partner abilities (JSON-shaped
    ``[kind, value]`` pairs); ``card_search`` keeps a candidate when
    :func:`can_partner` says it pairs. Color-agnostic on purpose: partner legality
    has no color-identity restriction — the pair's identity is the union of the two
    (CR 702.124c) — so we pass ``color_identity`` "WUBRG" (every identity is a
    subset) to disable the color filter rather than wrongly hide an off-color legal
    partner (e.g. a "partner with [name]" target in a new color).
    """
    abilities = partner_abilities(card)
    if not abilities:
        return None
    return {
        "color_identity": "WUBRG",
        "partner_of": [[a.kind, a.value] for a in sorted(abilities)],
    }


def has_any_number_exemption(card: dict) -> bool:
    """Whether a deck can have any number of cards with this name ("A deck can have
    any number of cards named X" — Relentless Rats, Hare Apparent), read off phase's
    ``deck_copy_limit: Unlimited``. Its rulings: the ability "lets you ignore the
    'four-of' rule" (CR 100.2a) — it doesn't let you ignore format legality.

    False for the "up to N" variant, which still has a numeric cap
    (``named_card_cap``), and for a card phase has no trees for."""
    return any(t.many_copies and t.deck_copy_cap is None for t in trees_for(card))


def named_card_cap(card: dict) -> int | None:
    """The cap from "A deck can have up to N cards named X" (Seven Dwarves 7,
    Nazgûl 9), read off phase's ``deck_copy_limit: UpTo``; None if the card has no
    such clause (or phase has no trees for it)."""
    return next(
        (t.deck_copy_cap for t in trees_for(card) if t.deck_copy_cap is not None),
        None,
    )


def land_search_fixes(card: dict) -> bool:
    """Whether the card searches YOUR library for a land that finds you a colour,
    wherever the land goes: any land card (Sylvan Scrying), a basic land of any
    type (Evolving Wilds, Ash Barrens' basic landcycling — CR 702.29e: into your
    hand, still a colour of your choice), or 2+ basic land types (Farseek). A
    single basic type ("a Forest card") is mono-colour ramp, not fixing. The one
    fixing rule for a land search: ``is_fixing_land`` and the tuner's
    ``swaps._is_fixing`` both read it."""
    return any(
        not isinstance(search.colors, frozenset) or len(search.colors) >= 2
        for tree in trees_for(card)
        for search in land_searches(tree)
    )


def is_fixing_land(card: dict) -> bool:
    """True if a land counts toward the "fixing density" metric.

    This is the BROAD Lucky Paper definition used in ``cube-balance``'s
    fixing density check — it counts any land that helps a drafter cast
    multi-color spells:

    * Multi-color mana producers: duals (Overgrown Tomb), triomes, Command
      Tower, Exotic Orchard.
    * Any-color producers: City of Brass, Mana Confluence, Lotus Field.
    * Land-fetchers that don't tap for mana: Evolving Wilds, Fabled Passage,
      fetchlands (Polluted Delta, Flooded Strand, etc.).
    * A land whose search finds a colour (:func:`land_search_fixes` — Ash Barrens'
      basic landcycling).

    Mono-color basic-producing lands and mono-color taplands are NOT fixing.

    Distinct from ``classify_cube_category`` which uses cube-utils' pack-
    template semantics (multi-color duals fill the L slot; only mana rocks
    and non-mana lands fill the F slot). Lucky Paper's published fixing
    numbers (17-28% at 360) measure the broader definition here.
    """
    if not is_land(card):
        return False
    sources = color_sources(card)
    if "any" in sources or len(sources) >= 2 or land_search_fixes(card):
        return True
    # A land that fetches a land onto the battlefield without tapping for mana itself.
    fetch = land_fetch_profile(card)
    return fetch is not None and fetch.to_battlefield and not _taps_for_mana(card)


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
        return "L" if _taps_for_mana(card) else "F"

    # Non-land F is restricted to COLORLESS fixing. Colored mana sources
    # (Llanowar Elves, Birds of Paradise, Cultivate) slot into their
    # mono-color position so each pack offers drafters color-specific
    # fixing help.
    if not identity:
        # Lazy: ``_analysis.roles`` sits above this module (it reads the presets,
        # which read this module's text helpers).
        from mtg_utils._analysis.roles import is_ramp

        if is_ramp(card):
            return "F"

    if len(identity) >= 2:
        return "M"

    if len(identity) == 1:
        return identity[0]

    return "C"
