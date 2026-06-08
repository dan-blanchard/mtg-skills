"""Opt-in: suggest a commander that fits the deck you already built.

Commander discovery (``engine.discover_commanders``) ranks commanders to a *stated
intent*; this ranks them to the *built deck's* viable avenues instead, surfacing each
with its **identity cost** — the in-deck cards that fall out of color identity on the
switch (deck-forge CONTEXT.md, "Commander fit"). The one fix a card swap structurally
can't make.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from mtg_utils._deck_forge.signal_specs import serves, spec_for
from mtg_utils._tuner.classify import CardClass

if TYPE_CHECKING:
    from mtg_utils._deck_forge.signals import Signal


def _identity_cost(candidate_ci: set[str], classes: Sequence[CardClass]) -> list[str]:
    """Names of in-deck cards that fall outside a candidate's color identity."""
    out = []
    for c in classes:
        if c.bucket == "commander":
            continue
        ci = set(c.record.get("color_identity") or [])
        if not ci.issubset(candidate_ci):
            out.append(c.name)
    return out


def suggest_commanders(
    classes: Sequence[CardClass],
    deck_signals: list,
    *,
    viable_labels: Sequence[str],
    identity: str,
    fmt: str,
    paper_only: bool,
    search_fn: Callable[..., list[dict]],
    owned: set[str],
    limit: int = 5,
) -> list[dict]:
    """Rank legal commanders by how many of the deck's viable avenues they serve.

    Owned-first (you can actually switch to them), each annotated with its identity
    cost. Empty when the deck has no viable avenues to fit (nothing to realign to).
    """
    if not viable_labels:
        return []
    pool = search_fn(
        color_identity=identity,
        exact_colors=False,
        oracle=None,
        card_type=None,
        name=None,
        cmc_min=None,
        cmc_max=None,
        price_min=None,
        price_max=None,
        format=fmt,
        paper_only=paper_only,
        preset_names=(),
        is_commander_filter=True,
        sort="cmc-asc",
        limit=300,
    )
    in_deck = {c.name for c in classes}
    wanted = set(viable_labels)
    scored: list[dict] = []
    for cand in pool:
        name = cand.get("name", "")
        if name in in_deck:
            continue
        served = {
            lbl
            for sig in deck_signals
            if serves(cand, sig)
            for lbl in (_label(sig),)
            if lbl
        }
        fit = served & wanted
        if not fit:
            continue
        cost = _identity_cost(set(cand.get("color_identity") or []), classes)
        scored.append(
            {
                "name": name,
                "serves": sorted(fit),
                "serves_count": len(fit),
                "owned": name in owned,
                "identity_cost": cost,
                "identity_cost_count": len(cost),
            }
        )
    scored.sort(
        key=lambda s: (s["owned"], s["serves_count"], -s["identity_cost_count"]),
        reverse=True,
    )
    return scored[:limit]


def _label(sig: Signal) -> str | None:
    spec = spec_for(sig)
    return spec.label if spec else None
