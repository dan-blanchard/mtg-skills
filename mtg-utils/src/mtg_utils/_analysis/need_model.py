"""The commander-need model (ADR-0061): the ``Need`` a commander's text asks
the deck for, the one ``satisfies`` test, and the share and breadth reads
over the pool (split out of ``commander_need``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtg_utils._analysis.signal_base import ident_key
from mtg_utils.type_line import split_type_line

if TYPE_CHECKING:
    pass


#: The card types a type-count condition or a two-type graveyard need counts
#: (CR 205.2a; the ones that appear on Commander-legal cards).
CARD_TYPES: tuple[str, ...] = (
    "artifact",
    "battle",
    "creature",
    "enchantment",
    "instant",
    "kindred",
    "land",
    "planeswalker",
    "sorcery",
)


@dataclass(frozen=True)
class Need:
    """One thing the commander asks the deck for.

    ``kind`` is ``"event"`` / ``"condition"`` / ``"resource"`` / ``"redundancy"``
    / ``"payoff"``;
    ``source`` the commander ability (its description) the need was read from.
    A card satisfies the need when any arm holds: it emits one of ``idents``
    (exact ``key|scope|subject``), one of ``keys`` (any scope / subject), its
    type line holds every word of one of ``types`` (each a frozenset of words:
    ``{"aura"}``, ``{"artifact", "creature"}``), or ``predicate`` holds on its
    record."""

    kind: str
    label: str
    source: str
    idents: frozenset[str] = frozenset()
    keys: frozenset[str] = frozenset()
    types: frozenset[frozenset[str]] = frozenset()
    predicate: Callable[[dict], bool] | None = field(default=None, compare=False)
    #: The mana value the need's spells start at, when it asks for big ones
    #: (Zhulodok's colorless spells at 7+, Bello's artifacts at 4+): a plan
    #: whose top end is the point, which the tuner reads before trimming ramp.
    mana_floor: int | None = None
    #: Whether the need may lead a theme page's order and gate an upgrade
    #: (``swaps.propose_swaps``' ``built_needs``). A need that is a property of
    #: the card, not a role in the plan — "cheap spells", "instants and
    #: sorceries" — is counted on the scoreboard but leads no page: under Ms.
    #: Bumbleflower it put Forget and Martyr's Cry over the group-hug payoffs
    #: (2026-11-01).
    leads: bool = True

    @property
    def empty(self) -> bool:
        return not (self.idents or self.keys or self.types or self.predicate)


def _card_idents(card: Mapping, *, membership: bool = True) -> frozenset[str]:
    from mtg_utils.theme_presets import _signal_idents_for

    record = card if isinstance(card, dict) else dict(card)
    return _signal_idents_for(record, include_membership=membership)


def _type_words(card: Mapping) -> frozenset[str]:
    """Every type-line word across the card's faces, lower-cased."""
    faces = card.get("card_faces") or [card]
    words: set[str] = set()
    for face in faces:
        types, subs = split_type_line(face.get("type_line") or "")
        words.update(types)
        words.update(subs)
    return frozenset(words)


def card_type_count(card: Mapping) -> int:
    """How many card types (CR 205.2a) the card holds across its faces — what
    it adds to a "card types among cards in your graveyard" count. A battle's
    back face is a creature, an artifact creature two types; a modal
    double-faced card's land face counts (both faces are the card)."""
    return len(_type_words(card) & set(CARD_TYPES))


def satisfies(card: Mapping, need: Need) -> bool:
    """Whether ``card`` supplies ``need``."""
    if need.predicate is not None and need.predicate(dict(card)):
        return True
    if need.types:
        words = _type_words(card)
        if any(t <= words for t in need.types):
            return True
    if need.idents or need.keys:
        idents = _card_idents(card)
        if need.idents & idents:
            return True
        if need.keys and any(ident_key(i) in need.keys for i in idents):
            return True
    return False


def need_predicate(needs: Sequence[Need]) -> Callable[[dict], bool]:
    """The "supplies any of the commander's needs" test."""

    def holds(card: dict) -> bool:
        return any(satisfies(card, n) for n in needs)

    return holds


#: A need more than this share of the pool supplies is BROAD ("instants and
#: sorceries" under a spellslinger, "enchantments" under an enchantress: every
#: fourth or eighth card); the plan-consistency line counts
#: the specific needs and reports the broad ones beside them.
BROAD_SHARE = 0.10


#: The toughness a body needs to supply a toughness-reading commander: four,
#: where the walls Felothar's guides add sit (Wall of Souls, Giant Ox, Flumph
#: 0/4; Shield Sphere 0/6) and every Dinosaur Pantlaza's guides add clears.
#: This read's own line, no rule's.
HIGH_TOUGHNESS = 4


_SHARE_MEMO: dict[tuple, float] = {}


def need_pool_share(need: Need, pool: Sequence[Mapping]) -> float:
    """The share of ``pool`` that supplies ``need`` (memoized per need shape
    and pool size; a predicate need keys on its label)."""
    key = (need.kind, need.label, need.idents, need.keys, need.types, len(pool))
    hit = _SHARE_MEMO.get(key)
    if hit is None:
        hit = sum(1 for c in pool if satisfies(c, need)) / max(1, len(pool))
        _SHARE_MEMO[key] = hit
    return hit


def is_broad(need: Need, share: float, *, floor: float = BROAD_SHARE) -> bool:
    """Whether a need ``share`` of the pool supplies is broad (over ``floor``).
    A need with a mana-value floor never is: it is read off the commander's own
    filter — the types it names at the mana value it names — so its page is the
    plan's top end, however many such cards the pool holds (Bello's artifacts
    and enchantments at 4+ mana are 10.5% of a Gruul pool, and over the line
    his page never led, gated or trimmed by his need; Animated Army,
    2026-11-01). The line is for the umbrella needs: every enchantment under
    an enchantress, every instant under a spellslinger."""
    return need.mana_floor is None and share > floor


def specific_needs(
    needs: Sequence[Need], pool: Sequence[Mapping], *, floor: float = BROAD_SHARE
) -> tuple[Need, ...]:
    """The needs that are not :func:`is_broad` over ``pool``."""
    return tuple(
        n for n in needs if not is_broad(n, need_pool_share(n, pool), floor=floor)
    )


def needs_met(card: Mapping, needs: Sequence[Need]) -> tuple[Need, ...]:
    """The needs ``card`` supplies, in ``needs`` order."""
    return tuple(n for n in needs if satisfies(card, n))
