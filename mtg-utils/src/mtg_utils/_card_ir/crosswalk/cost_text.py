"""Printed costs: a card's keyword costs as the card prints them.

The display side of the crosswalk's cost reads (``reads.keyword_cost`` unwraps
phase's keyword payloads): mana symbols from phase's ``ManaCostShard`` names, a
cost's non-mana parts in words, and :func:`keyword_alt_costs`, the
:class:`AltCost` rows a printed keyword gives its card (deck-stats' alternative-cost
listing). Imports :mod:`reads` one way; nothing here builds a concept node.
"""

from __future__ import annotations

import re
from typing import Literal, NamedTuple

from mtg_utils._card_ir.crosswalk.reads import (
    amount_factor,
    filter_core_types,
    filter_subtypes,
    has_fixed_count,
    keyword_cost,
    tag_of,
)
from mtg_utils._card_ir.mirror.runtime import MISSING, MirrorVariant, TypedMirrorNode

# ── Mana symbols ──────────────────────────────────────────────────────────────

_SHARD_COLOR_LETTER: dict[str, str] = {
    "White": "W",
    "Blue": "U",
    "Black": "B",
    "Red": "R",
    "Green": "G",
}
_SHARD_SPECIAL: dict[str, str] = {
    "Colorless": "C",
    "Snow": "S",
    "X": "X",
    "TwoOrMoreColorSource": "Z",
}
_COLOR_WORD_RE = re.compile("White|Blue|Black|Red|Green")
_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def shard_symbol(shard: object) -> str:
    """The printed symbol for one of phase's ``ManaCostShard`` names: ``Blue`` →
    ``{U}``, the hybrid ``BlueRed`` → ``{U/R}``, the two-generic hybrid ``TwoRed``
    → ``{2/R}``, the Phyrexian ``PhyrexianBlack`` → ``{B/P}`` (and the hybrid
    Phyrexian ``PhyrexianBlackRed`` → ``{B/R/P}``), the colorless hybrid
    ``ColorlessRed`` → ``{C/R}`` (CR 107.4). An unknown name prints as itself."""
    if not isinstance(shard, str):
        return ""
    if shard in _SHARD_SPECIAL:
        return "{" + _SHARD_SPECIAL[shard] + "}"
    parts: list[str] = []
    rest = shard
    for prefix, sym in (("Phyrexian", None), ("Two", "2"), ("Colorless", "C")):
        if rest.startswith(prefix) and rest != prefix:
            rest = rest[len(prefix) :]
            if sym is not None:
                parts.append(sym)
            break
    colors = _COLOR_WORD_RE.findall(rest)
    if not colors or "".join(colors) != rest:
        return "{" + shard + "}"
    parts.extend(_SHARD_COLOR_LETTER[c] for c in colors)
    if shard.startswith("Phyrexian"):
        parts.append("P")
    return "{" + "/".join(parts) + "}"


def cost_symbols(cost: object) -> str:
    """A phase ``Cost`` node as printed mana symbols: ``{X}`` shards first, then
    the generic amount, then the rest in phase's order (Ancestral Vision's
    suspend cost ``{U}``, Lotus Bloom's ``{0}``). ``""`` for anything else."""
    if tag_of(cost) != "Cost":
        return ""
    generic = getattr(cost, "generic", 0)
    shards = [s for s in (getattr(cost, "shards", None) or []) if isinstance(s, str)]
    xs = [s for s in shards if s == "X"]
    rest = [s for s in shards if s != "X"]
    out = "".join(shard_symbol(s) for s in xs)
    if isinstance(generic, int) and (generic > 0 or not shards):
        out += "{" + str(generic) + "}"
    return out + "".join(shard_symbol(s) for s in rest)


def mana_value_of_cost(mana_cost: str) -> int | None:
    """Mana value (CR 202.3) of a printed mana cost string, or ``None`` for an
    empty string (the caller falls back to the record ``cmc``). A generic symbol
    adds its number; ``X``/``Y``/``Z`` add 0 (CR 107.3c); a hybrid symbol
    (``{2/W}``/``{W/P}``) adds the larger side (1 when neither side is numeric);
    any other symbol (a color, ``{C}``, ``{S}``) adds 1."""
    if not mana_cost:
        return None
    total = 0
    for raw_sym in _MANA_SYMBOL_RE.findall(mana_cost):
        sym = raw_sym.upper()
        if sym.isdigit():
            total += int(sym)
        elif sym in ("X", "Y", "Z"):
            continue
        elif "/" in sym:
            nums = [int(p) for p in sym.split("/") if p.isdigit()]
            total += max(nums) if nums else 1
        else:
            total += 1
    return total


# ── A cost's parts in words ───────────────────────────────────────────────────


_NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten",
)  # fmt: skip


def _plural(n: int, noun: str) -> str:
    """``n`` of ``noun`` the way a card prints a count: "a red card", "an
    artifact", "two cards", "five other cards" (a number word up to ten)."""
    if n == 1:
        article = "an" if noun and noun[0] in "aeiou" else "a"
        return f"{article} {noun}".rstrip()
    number = _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)
    return f"{number} {noun}s"


def _count(node: object, field: str = "count") -> int | None:
    """A cost's count: a bare int (an exile's ``count``) or a ``Fixed`` quantity
    (:func:`~reads.amount_factor`); ``None`` when it has neither."""
    v = getattr(node, field, MISSING)
    if isinstance(v, int):
        return v
    if isinstance(node, TypedMirrorNode) and has_fixed_count(node, field):
        return amount_factor(node, field)
    return None


def _cost_object_words(filt: object, *, default: str) -> str:
    """The object noun a cost filter names, with its colour and "other"
    adjectives: Fury's "red card", Uro's "other card", Constant Mists' "land"."""
    adjectives: list[str] = []
    for prop in getattr(filt, "properties", None) or ():
        if tag_of(prop) == "Another":
            adjectives.append("other")
        elif tag_of(prop) == "HasColor" and isinstance(
            getattr(prop, "color", None), str
        ):
            adjectives.append(prop.color.lower())
    words = [
        w.lower() for w in filter_core_types(filt) if w not in ("Card", "Permanent")
    ] + list(filter_subtypes(filt))  # subtypes print capitalized ("Islands")
    noun = " ".join(words) or default
    return " ".join([*adjectives, noun])


def cost_text(cost: object) -> str:
    """A keyword's cost in printed words: mana symbols (:func:`cost_symbols`), a
    life payment ("Pay 3 life" — Deep Analysis's flashback), an exile from a zone
    ("Exile a red card from your hand" — Fury's evoke; "Exile five other cards
    from your graveyard" — Uro's escape), a discard, a sacrifice; a ``Composite``
    joins its parts the way the card prints them. A part with no renderer reads
    as its tag in words ("Collect evidence 6")."""
    tag = tag_of(cost)
    if tag == "Cost":
        return cost_symbols(cost)
    if tag == "Mana":
        return cost_text(getattr(cost, "cost", MISSING))
    if tag == "Composite":
        parts = [cost_text(c) for c in getattr(cost, "costs", None) or ()]
        return ", ".join(p for p in parts if p)
    if tag == "PayLife":
        n = _count(cost, "amount")
        return f"Pay {n} life" if n else "Pay life"
    if tag == "Exile":
        # A count of 0 is phase's X ("Exile X blue cards" — Flash of Insight).
        n = _count(cost)
        zone = getattr(cost, "zone", None)
        noun = _cost_object_words(getattr(cost, "filter", None), default="card")
        where = f" from your {zone.lower()}" if isinstance(zone, str) else ""
        what = f"X {noun}s" if n == 0 else _plural(n or 1, noun)
        return f"Exile {what}{where}"
    if tag == "Discard":
        n = _count(cost)
        return "Discard X cards" if not n else f"Discard {_plural(n, 'card')}"
    if tag == "Sacrifice":
        n = _count(cost) or 1
        noun = _cost_object_words(getattr(cost, "target", None), default="permanent")
        return f"Sacrifice {_plural(n, noun)}"
    if tag is None:
        return ""
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", tag).capitalize()
    n = _count(cost, "amount")
    if n is None:
        n = _count(cost)
    return f"{words} {n}" if n else words


# ── Alternative costs ─────────────────────────────────────────────────────────


#: What the rules make of an :class:`AltCost` payment (see its docstring).
AltCostKind = Literal[
    "alternative", "additional", "alternative_characteristics", "special_action",
    "ability",
]  # fmt: skip


class AltCost(NamedTuple):
    """One of a card's other ways to pay for or cast it, from a printed keyword.

    ``kind`` is the keyword in lowercase words (``"suspend"``, ``"commander
    ninjutsu"``, ``"morph (face up)"``); ``cost`` its printed cost; ``cost_kind``
    what the rules make of that payment:

    * ``"alternative"`` — paid rather than the mana cost (CR 118.9): evoke,
      flashback, dash, warp, morph's face-down {3} (702.37a) …
    * ``"additional"`` — paid on top of the mana cost (CR 118.8): buyback
      (702.27a), retrace's land discard (702.81a).
    * ``"alternative_characteristics"`` — prototype casts the card with its
      secondary mana cost, power and toughness (702.160a, 718.3b).
    * ``"special_action"`` — suspend and plot exile the card now to cast it free
      later (CR 116.2f, 116.2k); turning a morph or disguise face up (116.2b).
    * ``"ability"`` — ninjutsu's activated ability puts the card onto the
      battlefield without casting it (702.49a; commander ninjutsu 702.49d)."""

    kind: str
    cost: str
    cost_kind: AltCostKind


# The keywords whose cost is paid rather than the mana cost (CR 118.9): evoke
# 702.74a, foretell 702.143a, flashback 702.34a, escape 702.138a, dash 702.109a,
# disturb 702.146a, madness 702.35a, miracle 702.94a, blitz 702.152a, spectacle
# 702.137a, emerge 702.119a, overload 702.96a, bestow 702.103a, mutate 702.140a,
# prowl 702.76a, surge 702.117a, warp 702.185a, impending 702.176a, harmonize
# 702.180a, sneak 702.190a, freerunning 702.173a, mayhem 702.187b, cleave 702.148a.
# Each one's kind is its name in lowercase.
_ALTERNATIVE_KEYWORDS = frozenset(
    {
        "Evoke",
        "Foretell",
        "Flashback",
        "Escape",
        "Dash",
        "Disturb",
        "Madness",
        "Miracle",
        "Blitz",
        "Spectacle",
        "Emerge",
        "Overload",
        "Bestow",
        "Mutate",
        "Prowl",
        "Surge",
        "Warp",
        "Impending",
        "Harmonize",
        "Sneak",
        "Freerunning",
        "Mayhem",
        "Cleave",
    }
)
# Morph-family keywords: cast face down for {3} rather than the mana cost
# (702.37a, megamorph 702.37b, disguise 702.168a), then turned face up for the
# keyword's cost as a special action (116.2b).
FACE_DOWN_KEYWORDS = frozenset({"Morph", "Megamorph", "Disguise"})
# Every other keyword: (kind, cost kind). Retrace prints no cost: it casts the card
# from the graveyard by discarding a land card as an additional cost (702.81a).
_ALT_COST_EXCEPTIONS: dict[str, tuple[str, AltCostKind]] = {
    "WebSlinging": ("web-slinging", "alternative"),  # 702.188a
    "Prototype": ("prototype", "alternative_characteristics"),
    "Buyback": ("buyback", "additional"),
    "Retrace": ("retrace", "additional"),
    "Plot": ("plot", "special_action"),
    "Suspend": ("suspend", "special_action"),
    "Ninjutsu": ("ninjutsu", "ability"),
    "CommanderNinjutsu": ("commander ninjutsu", "ability"),
}
_RETRACE_COST = "Discard a land card"

#: Phase keyword → ``(kind, cost_kind)`` for every keyword that gives an
#: :class:`AltCost` row (a face-down keyword's row is its "{3} (face down)" cast).
ALT_COST_KEYWORDS: dict[str, tuple[str, AltCostKind]] = {
    **{key: (key.lower(), "alternative") for key in _ALTERNATIVE_KEYWORDS},
    **{key: (key.lower(), "alternative") for key in FACE_DOWN_KEYWORDS},
    **_ALT_COST_EXCEPTIONS,
}


def face_down_rows(name: str, face_up_cost: str) -> tuple[AltCost, ...]:
    """A morph-family keyword's two rows: the face-down {3} cast and, when it has
    one, the face-up cost."""
    down = AltCost(name, "{3} (face down)", "alternative")
    if not face_up_cost:
        return (down,)
    return (down, AltCost(f"{name} (face up)", face_up_cost, "special_action"))


def keyword_alt_costs(keyword: object) -> tuple[AltCost, ...]:
    """The :class:`AltCost` rows a printed keyword gives its card, or ``()``.

    Suspend's and impending's costs print with their time counters ("4—{U}"),
    prototype's with its power and toughness ("{1}{B}{B} — 3/3"), emerge's with
    its sacrifice ("{6}{B}, Sacrifice a creature")."""
    if isinstance(keyword, MirrorVariant):
        key = keyword.key
    elif isinstance(keyword, str):
        key = keyword
    else:
        return ()
    if key not in ALT_COST_KEYWORDS:
        return ()
    kind, cost_kind = ALT_COST_KEYWORDS[key]
    if key == "Retrace":
        return (AltCost(kind, _RETRACE_COST, cost_kind),)
    if key in FACE_DOWN_KEYWORDS:
        return face_down_rows(kind, cost_text(keyword_cost(keyword)))
    text = cost_text(keyword_cost(keyword))
    if not text or not isinstance(keyword, MirrorVariant):
        return ()
    inner = keyword.inner
    if key in ("Suspend", "Impending"):
        # "Suspend N—[cost]" (702.62a), "Impending N—[cost]" (702.176a).
        count = getattr(inner, "count" if key == "Suspend" else "counters", None)
        if isinstance(count, int):
            text = f"{count}—{text}"
    elif key == "Emerge":
        # "paying [cost] and sacrificing a creature" (702.119a).
        victim = _cost_object_words(
            getattr(inner, "sacrifice_filter", None), default="creature"
        )
        text = f"{text}, Sacrifice {_plural(1, victim)}"
    elif key == "Prototype":
        power = getattr(inner, "power", None)
        toughness = getattr(inner, "toughness", None)
        if isinstance(power, int) and isinstance(toughness, int):
            text = f"{text} — {power}/{toughness}"
    return (AltCost(kind, text, cost_kind),)
