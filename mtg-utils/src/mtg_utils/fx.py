"""Currency conversion — USD → AUD.

Scryfall (the repo's price source) publishes ``usd`` but no AUD, so any AUD
figure is a conversion of the USD price. To keep the "safe / offline" posture
(no new network egress, no PII), the rate is read from configuration, not a
live FX API:

- ``MTG_SKILLS_AUD_PER_USD`` environment variable, if set and parseable; else
- :data:`DEFAULT_AUD_PER_USD` below (update it when you care about accuracy).

AUD prices are therefore a *reference conversion*, not a live quote. When the
future Australian-LGS search lands (see ``docs/FUTURE-LGS-SEARCH.md``), the
store's own scraped AUD price is the source of truth and this conversion is the
sanity-check comparison.

A ``--live-fx`` toggle that fetches the daily rate from an FX endpoint could be
added later, but it adds an outbound host and should be opt-in and documented as
a network-surface change before it is enabled.
"""

from __future__ import annotations

import os

__all__ = ["DEFAULT_AUD_PER_USD", "aud_per_usd", "usd_to_aud"]

# Approximate AUD per 1 USD. Update as you like; override at runtime with
# MTG_SKILLS_AUD_PER_USD. This is a static default on purpose — no network call.
DEFAULT_AUD_PER_USD = 1.52

_ENV_VAR = "MTG_SKILLS_AUD_PER_USD"


def aud_per_usd() -> float:
    """The active USD→AUD rate: env override if valid and positive, else default."""
    raw = os.environ.get(_ENV_VAR)
    if raw:
        try:
            rate = float(raw)
        except ValueError:
            return DEFAULT_AUD_PER_USD
        if rate > 0:
            return rate
    return DEFAULT_AUD_PER_USD


def usd_to_aud(usd: float | None, *, rate: float | None = None) -> float | None:
    """Convert a USD amount to AUD; ``None`` in → ``None`` out.

    ``rate`` lets a caller pass a rate it already resolved (e.g. once per report)
    instead of re-reading the environment for every card.
    """
    if usd is None:
        return None
    r = rate if rate is not None else aud_per_usd()
    return round(usd * r, 2)
