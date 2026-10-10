"""The arena-meta report: the four reads over a snapshot, as ``arena-meta`` prints
them and deck-forge's Meta panel serves them (ADR-0059). Ownership is the one rule
(``Format.coverage`` via ``price_check.arena_wildcard_cost``) over the lowest Arena
rarities (``CardPool.rarity_index(arena_only=True)``)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from mtg_utils._arena_meta import meta as m

if TYPE_CHECKING:
    from mtg_utils._name_index import NameIndex
    from mtg_utils.card_pool import CardPool

#: Rows per ranked list.
TOP = 25


def collection_owned(
    snap: m.Snapshot, collection: Mapping, pool: CardPool
) -> dict[str, int]:
    """``normalize_card_name(card) -> copies owned`` for every card the snapshot
    names, from a parsed collection — one ``mark_owned`` pass, Arena aliases
    included."""
    from mtg_utils.mark_owned import mark_owned
    from mtg_utils.price_check import owned_quantities

    most: dict[str, int] = {}
    for deck in snap.decks:
        for name, qty in _entries(deck, sideboard=True):
            most[name] = max(most.get(name, 0), qty)
    marked = mark_owned(
        {"cards": [{"name": n, "quantity": q} for n, q in most.items()]},
        dict(collection),
        name_aliases=pool.name_aliases,
    )
    return owned_quantities(marked["owned_cards"])


def wildcard_cost_fn(
    owned: Mapping[str, int],
    rarity: NameIndex,
    *,
    sideboard: bool = False,
) -> Callable[[m.MetaDeck], dict[str, int]]:
    """rarity -> wildcards still needed for a published list, given ``owned``
    (``normalize_card_name`` keys) and the format's Arena rarity index."""
    from mtg_utils.price_check import arena_wildcard_cost

    def cost(deck: m.MetaDeck) -> dict[str, int]:
        entries = _entries(deck, sideboard=sideboard)
        return arena_wildcard_cost(entries, dict(owned), rarity)["wildcard_cost"]

    return cost


def _entries(deck: m.MetaDeck, *, sideboard: bool) -> list[tuple[str, int]]:
    """A list's ``(name, copies)`` with each card once — its main and sideboard
    copies summed, so ownership covers them together."""
    copies: dict[str, int] = {}
    zones: list[Iterable[tuple[str, int]]] = [
        [(c, 1) for c in deck.commanders],
        deck.main,
    ]
    if sideboard:
        zones.append(deck.sideboard)
    for zone in zones:
        for name, qty in zone:
            copies[name] = copies.get(name, 0) + qty
    return list(copies.items())


def _deck_json(deck: m.MetaDeck) -> dict:
    return {
        "commanders": list(deck.commanders),
        "main": [{"name": n, "quantity": q} for n, q in deck.main],
        "sideboard": [{"name": n, "quantity": q} for n, q in deck.sideboard],
    }


def build_report(
    snap: m.Snapshot,
    *,
    ranks: Sequence[str] = m.DEFAULT_RANKS,
    min_matches: int = m.MIN_MATCHES,
    core_share: float = m.CORE_SHARE,
    field_share: float = m.FIELD_SHARE,
    match: m.Match | None = None,
    held: Iterable[str] = (),
    cost: Callable[[m.MetaDeck], Mapping[str, int]] | None = None,
    wildcards: Mapping[str, int] | None = None,
    top: int = TOP,
) -> dict:
    """The report envelope: ``ranking``, ``field``, the deck's (or the named)
    meta archetype ``match`` and its ``core``, and ``buildable`` (when ``cost`` is
    given: that archetype's lists, or every list with no match). Each core card
    says whether ``held`` (the deck's cards) runs it."""
    target = match.archetype.id if match else None
    out: dict = {
        "event": snap.event,
        "period": dict(snap.period),
        "fetched_at": snap.fetched_at,
        "ranked": snap.ranked,
        "ranks": list(ranks) if snap.ranked else [m.UNRANKED],
        "thresholds": {
            "min_matches": min_matches,
            "mythic_min_matches": m.MYTHIC_MIN_MATCHES,
            "core_share": core_share,
            "field_share": field_share,
        },
        "ranking": m.ranking(snap, ranks, min_matches=min_matches)[:top],
        "field": m.field_shares(snap, ranks, min_share=field_share),
        "match": match.to_json() if match else None,
        "core": (
            {
                "archetype": match.archetype.name,
                # The sample in the asked ranks, and whether the tuner reads it —
                # :func:`meta.tunable`'s answer, never judged again here.
                **m.list_sample(snap, match.archetype.id, ranks)._asdict(),
                "tuned": m.tunable(snap, match.archetype.id),
                "cards": m.mark_held(
                    m.core(snap, match.archetype.id, ranks, min_share=core_share),
                    held,
                ),
            }
            if match
            else None
        ),
        "buildable": None,
    }
    if cost is not None:
        rows = m.buildable(snap, cost, ranks, wildcards=wildcards, archetype=target)
        out["buildable"] = [
            {
                **{k: v for k, v in r.items() if k != "deck"},
                "list": _deck_json(r["deck"]),
            }
            for r in rows[:top]
        ]
    return out


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def render_text(report: Mapping) -> str:
    """The report as plain-text tables."""
    period = report.get("period") or {}
    lines = [
        (
            f"{report['event']} — period {period.get('id')} "
            f"({period.get('description') or ''}, {period.get('start')} → "
            f"{period.get('end') or 'now'}), ranks {', '.join(report['ranks'])}, "
            f"fetched {report.get('fetched_at')}"
        ),
        "",
        (
            f"## Ranking (≥ {report['thresholds']['min_matches']} matches, "
            "by Wilson lower bound)"
        ),
    ]
    for i, r in enumerate(report["ranking"], 1):
        mythic = r.get("mythic")
        tail = (
            f"  mythic {_pct(mythic['winrate'])} ({mythic['matches']}"
            f"{', thin' if mythic['matches'] < m.MYTHIC_MIN_MATCHES else ''})"
            if mythic and mythic["matches"]
            else ""
        )
        lines.append(
            f"{i:>3}. {r['name']}: {_pct(r['winrate'])} over {r['matches']} "
            f"(lower {_pct(r['wilson_lower'])}, share {_pct(r['share'])}){tail}"
        )
    lines += ["", f"## Field (≥ {_pct(report['thresholds']['field_share'])} share)"]
    lines += [
        f"  {_pct(r['share']):>6}  {r['name']} ({_pct(r['winrate'])})"
        for r in report["field"]
    ]
    mt = report.get("match")
    if mt and mt["by"] != "named":
        how = f"{_pct(mt['overlap'])} overlap" if mt["by"] == "overlap" else mt["by"]
        lines += ["", f"Deck matches {mt['archetype']} ({how})."]
    if report.get("core"):
        c = report["core"]
        thin = "" if c["tuned"] else " — too thin: deck-tune skips it"
        lines += [
            "",
            (
                f"## Core of {c['archetype']} ({c['lists']} lists, "
                f"{c['matches']} matches{thin})"
            ),
        ]
        lines += [
            f"  {_pct(c['share']):>6}  {c['avg_copies']:.1f}x  {c['name']}"
            for c in report["core"]["cards"]
        ]
    if report.get("buildable") is not None:
        lines += ["", "## Buildable lists (fits your wildcards first, then cheapest)"]
        for r in report["buildable"]:
            need = ", ".join(f"{n} {k}" for k, n in r["wildcards_needed"].items())
            mark = "✓" if r["fits"] else " "
            lines.append(
                f"  {mark} {r['archetype']}: {_pct(r['winrate'])} over "
                f"{r['matches']} — needs {need or 'nothing'}"
            )
    return "\n".join(lines) + "\n"
