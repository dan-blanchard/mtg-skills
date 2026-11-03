"""The swap budget: the paper USD ledger, the Arena wildcard ledger, and the
bracket's game-changer room (split out of ``swaps``)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from mtg_utils._tuner.classify import CardClass
from mtg_utils.card_classify import (
    extract_price,
)

_WC_TIERS: tuple[str, ...] = ("mythic", "rare", "uncommon", "common")


class _Purse(Protocol):  # noqa: PYI046 — the type swaps annotates its ledger with
    """An acquisition budget, probed read-only then charged on commit. It prices only
    copies the collection does NOT cover — the caller decides coverage once, by
    ``Format.copies_short`` — and each purse reads what it needs from the record."""

    def acquire_cost(self, record: dict) -> float | None:
        """The cost of one uncovered copy, or None when unaffordable."""

    def charge(self, record: dict, cost: float) -> None: ...

    def refund(self, record: dict, cost: float) -> None: ...

    def share(self, adds: int) -> float:
        """An even share of what is left over ``adds`` more adds: an add priced
        within it leaves every later add the same, so the budget binds only
        past it (``find_add``'s near tie)."""

    @property
    def usd_spent(self) -> float: ...

    @property
    def wildcards_spent(self) -> dict[str, int] | None: ...


class _UsdLedger:
    """Paper acquisition budget: a single USD pool. A no-listing card is never free
    (treated as scarce); ``budget is None`` is the owned-only pass."""

    def __init__(self, budget: float | None) -> None:
        self.budget = budget
        self.spent = 0.0

    def acquire_cost(self, record: dict) -> float | None:
        price = extract_price(record)
        if price is None:  # no-listing: never $0
            return None
        if self.budget is None:  # owned-only pass
            return None
        return price if self.spent + price <= self.budget else None

    def charge(self, record: dict, cost: float) -> None:
        self.spent += cost

    def refund(self, record: dict, cost: float) -> None:
        self.spent -= cost

    def share(self, adds: int) -> float:
        if self.budget is None:  # owned-only: every add it can make is free
            return math.inf
        return (self.budget - self.spent) / max(1, adds)

    @property
    def usd_spent(self) -> float:
        return round(self.spent, 2)

    @property
    def wildcards_spent(self) -> dict[str, int] | None:
        return None


class _WildcardLedger:
    """Digital (Arena) acquisition budget: four per-rarity wildcard pools. An uncovered
    copy costs ONE wildcard of its rarity. Wildcards are NOT interchangeable, so each
    tier is gated independently — an all-zero budget is the owned-only pass. The
    swap's USD ``cost`` is 0.0 (the UI costs by rarity); ``total`` is the per-tier
    wildcards spent."""

    def __init__(self, budget: Mapping[str, int]) -> None:
        self.remaining = {t: int(budget.get(t, 0)) for t in _WC_TIERS}
        self.spent = dict.fromkeys(_WC_TIERS, 0)

    def acquire_cost(self, record: dict) -> float | None:
        rarity = record.get("rarity")
        if rarity not in self.remaining or self.remaining[rarity] <= 0:
            return None
        return 0.0

    def charge(self, record: dict, cost: float) -> None:
        rarity = record.get("rarity")
        if rarity in self.remaining:
            self.remaining[rarity] -= 1
            self.spent[rarity] += 1

    def refund(self, record: dict, cost: float) -> None:
        rarity = record.get("rarity")
        if rarity in self.remaining:
            self.remaining[rarity] += 1
            self.spent[rarity] -= 1

    def share(self, adds: int) -> float:
        return math.inf  # one wildcard of its rarity, whatever the card

    @property
    def usd_spent(self) -> float:
        return 0.0  # Arena spends wildcards, not dollars — see wildcards_spent.

    @property
    def wildcards_spent(self) -> dict[str, int]:
        return dict(self.spent)


class _GameChangerRoom:
    """How many more Game Changers the target bracket allows (ADR-0030: the proposer
    never adds one past the ceiling). ``room=None`` is no ceiling — no target bracket,
    a one-on-one game, brackets 4-5; a NEGATIVE room is a deck already over, which
    must cut its way back under before any Game Changer add. The third ledger beside
    the two purses: probed read-only, charged on commit."""

    def __init__(self, room: int | None) -> None:
        self.room = room

    def allows(self, record: dict) -> bool:
        return self.room is None or self.room > 0 or not record.get("game_changer")

    def charge(self, add: dict, cut: CardClass | None) -> None:
        """A Game Changer added spends a slot; one cut frees a slot."""
        if self.room is None:
            return
        self.room -= bool(add.get("game_changer"))
        self.room += bool(cut is not None and cut.record.get("game_changer"))
