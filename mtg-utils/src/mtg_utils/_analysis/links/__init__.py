"""Links derived from the rules and the parsed cards, one event family at a time.

A link says what a card's own text can make happen; a wait says what a card's
trigger watches for. Each carries facts (the route, the rule, certain or not,
whose object, how it is delivered, whether it repeats) and never a verdict: no
card is ruled in or out here, relevance is left to whatever scores the link.

* :mod:`~mtg_utils._analysis.links.deaths` — "a creature dies" (CR 700.4).
"""

from __future__ import annotations

from mtg_utils._analysis.links.deaths import (
    DeathLink,
    DeathWait,
    card_death_links,
    card_death_waits,
    death_links,
    death_waits,
    feeds,
    unit_death_waits,
)

__all__ = [
    "DeathLink",
    "DeathWait",
    "card_death_links",
    "card_death_waits",
    "death_links",
    "death_waits",
    "feeds",
    "unit_death_waits",
]
