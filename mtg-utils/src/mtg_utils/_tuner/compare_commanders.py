"""Which of a deck's own legends leads it best: the tune run under each.

A precon ships with a face commander and two or three other legendary
creatures a guide sometimes builds around instead (Temur Roar's Ureni of the
Unwritten, World Shaper's Szarel, Genesis Shepherd; nine of the 55 audited
precons' guides switch). This read puts the question to the tuner itself: for
every candidate command zone the deck can field — each single the format's
``commander_eligibility`` accepts, and every legal partner pair among them
(``card_classify.can_partner``, CR 702.124f) — move it to the command zone, run
the same tune, and rank the results. Advisory only: it proposes nothing and
changes nothing; the user (or deck-wizard) decides whether to switch.

The scorecard has no single total, so the rank is defined here (Dan,
2026-11-01): first by the post-tune **commander fit** (``metrics.commander_fit``
— the share of the deck's viable avenues the commander itself serves: what
"this deck is built for that commander" means), then by the post-tune **issue
load** (the sum of the scorecard's top-issue severities: what is left wrong
once the tune has had its swaps), lowest first. Both numbers are reported so a
reader can rank by either.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from itertools import combinations
from typing import TYPE_CHECKING

from mtg_utils.card_classify import can_partner, partner_abilities
from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.set_commander import set_commander

if TYPE_CHECKING:
    from mtg_utils._tuner.tune import TuneParams

#: How many of a candidate's proposed swaps the table shows.
TOP_SWAPS = 3


def candidate_command_zones(hd: HydratedDeck) -> list[tuple[str, ...]]:
    """Every command zone the deck can field, the current one first: each card
    of the deck (commanders and the 99) the format accepts as a commander on
    its own, and every pair among them that can partner (one ability of each
    matching the other's, CR 702.124f; ``can_partner`` holds the rule). Sorted
    by name after the current zone, so the table reads the same every run."""
    fmt = hd.format
    current = tuple(c["name"] for c in hd.commanders)
    seen: dict[str, dict] = {}
    for entry in [*hd.commanders, *hd.cards]:
        name = entry.get("name", "")
        rec = hd.by_name.get(name)  # the zones hold entries; the record is the join's
        if name in seen or rec is None:
            continue
        verdict = fmt.commander_eligibility(rec)
        if verdict.get("eligible") and not verdict.get("requires_partner"):
            seen[name] = rec
    singles = sorted(seen)
    zones: list[tuple[str, ...]] = [(n,) for n in singles]
    for a, b in combinations(singles, 2):
        ab = partner_abilities(seen[a])
        ba = partner_abilities(seen[b])
        if ab and ba and can_partner(ab, seen[b]) and can_partner(ba, seen[a]):
            zones.append((a, b))
    zones = [z for z in zones if z != current]
    return [current, *zones] if current else zones


def _with_command_zone(hd: HydratedDeck, names: Sequence[str]) -> HydratedDeck:
    """``hd`` led by ``names``: the current commanders go back to the 99 and the
    named cards move up (``set_commander``), over the same hydrated records."""
    deck = dict(hd.deck)
    cards = [*deck.get("cards", []), *deck.get("commanders", [])]
    deck = set_commander({**deck, "commanders": [], "cards": cards}, list(names))
    return HydratedDeck(deck, hd.records)


def issue_load(scorecard: Mapping) -> int:
    """The sum of the scorecard's top-issue severities (an issue with none
    counts one): what the tune left wrong."""
    return sum(int(i.get("severity") or 1) for i in scorecard.get("top_issues", ()))


def compare_commanders(
    hd: HydratedDeck,
    *,
    tune_fn: Callable[..., dict],
    search_fn: Callable[..., list[dict]],
    params: TuneParams,
    owned: Mapping[str, int] | None = None,
    combos_fn: Callable[[dict], dict] | None = None,
    pool: Mapping[str, int] | None = None,
) -> list[dict]:
    """The tune under every candidate command zone (:func:`candidate_command_zones`),
    ranked best first: commander fit (desc), then issue load (asc). Each row:
    ``commanders`` (names), ``current`` (the deck's zone today), ``fit`` and
    ``issues`` before (the scorecard as tuned) and ``fit_after`` / ``issues_after``
    (after the proposed swaps are read as applied — the tune's own post-swap
    scorecard when it reports one, else the same numbers), ``swaps`` (the first
    :data:`TOP_SWAPS` proposed, cut → add), ``rank`` (1 = best). ``tune_fn`` is
    ``_tuner.tune.tune`` (passed in: this module must not import the tuner it
    is called from)."""
    rows: list[dict] = []
    for zone in candidate_command_zones(hd):
        led = (
            hd
            if tuple(c["name"] for c in hd.commanders) == zone
            else _with_command_zone(hd, zone)
        )
        result = tune_fn(
            led,
            search_fn=search_fn,
            params=params,
            owned=owned,
            combos_fn=combos_fn,
            pool=pool,
        )
        sc = result.get("scorecard") or {}
        cfit = sc.get("commander_fit") or {}
        rows.append(
            {
                "commanders": list(zone),
                "current": tuple(c["name"] for c in hd.commanders) == zone,
                "fit": float(cfit.get("fit", 0.0) or 0.0),
                "issues": issue_load(sc),
                "focus": [
                    a.get("label")
                    for a in (sc.get("focus") or {}).get("viable_avenues", [])
                ][:3],
                "swaps": [
                    {
                        "cut": s.get("cut", {}).get("name"),
                        "add": s.get("add", {}).get("name"),
                    }
                    for s in (result.get("swaps") or [])[:TOP_SWAPS]
                ],
            }
        )
    rows.sort(key=lambda r: (-r["fit"], r["issues"], r["commanders"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
