"""Wire serialization for the deck-forge browser surface — the card-view shapes the
Svelte SPA consumes.

Split out of ``app.py`` (and the deck-analysis ``engine``) so the frontend contract
lives in ONE module the SPA can be diffed against. Every card the UI renders is one of
four named shapes, and all four compose the single atomic projection ``project`` — so a
new display field is one edit here, not five scattered across the route bodies (where
the deck / search / candidate / combo serializers had already drifted).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from mtg_utils._analysis.signal_specs import spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._deck_forge.images import image_urls
from mtg_utils._deck_forge.state import ForgeState
from mtg_utils.card_classify import get_mana_cost, get_oracle_text
from mtg_utils.formats import FORMATS, Format
from mtg_utils.hydrated_deck import ZONES


def printing_view(record: dict) -> dict:
    """One selectable printing for the picker: identity + set/collector + cost + art."""
    return {
        "id": record.get("id"),
        "set": record.get("set"),
        "set_name": record.get("set_name"),
        "collector_number": record.get("collector_number"),
        "released_at": record.get("released_at"),
        "rarity": record.get("rarity", ""),
        "finishes": record.get("finishes", []),
        "prices": record.get("prices", {}),
        "images": image_urls(record),
    }


def project(record: dict, fmt: Format, *, unreleased: bool = False) -> dict:
    """The atomic display projection for one Scryfall record (no name/quantity). ``fmt``
    is the deck's format, so ``can_be_commander`` reflects the right legality mode (a
    card can be a commander in brawl but not commander, and vice versa).

    ``unreleased`` marks a card from a spoiled-but-unreleased set. It is decided by the
    caller against ``ForgeState.unreleased_ids`` (an ORACLE-level set) rather than from
    the record's own ``released_at``, because the search layer dedups to the cheapest
    printing — which for a reprint can itself be a future one. Reading the date off the
    record would badge 15 currently-legal cards (Settle the Wreckage among them) as
    pre-release. Emitted only when True, keeping the wire shape byte-compatible for
    everything already released, exactly as the ownership keys do.
    """
    view = {
        "type_line": record.get("type_line", ""),
        # DFCs (transform/flip, many MDFCs) leave the top-level mana_cost/oracle_text
        # empty (or absent → None) and carry the real values on card_faces; fold them
        # in so the SPA renders a cost and oracle line instead of blanks.
        "mana_cost": get_mana_cost(record),
        "cmc": record.get("cmc", 0.0),
        "color_identity": record.get("color_identity", []),
        "oracle_text": get_oracle_text(record),
        "rarity": record.get("rarity", ""),
        "prices": record.get("prices", {}),
        "images": image_urls(record),
        "game_changer": record.get("game_changer"),
        # A pre-release legend has no legal format yet, so the default gate would
        # report it commander-ineligible and the SPA would render its ★ disabled —
        # searchable but un-buildable. Judge those on type/oracle alone.
        "can_be_commander": fmt.commander_eligibility(record, unreleased=unreleased)[
            "eligible"
        ],
        "layout": record.get("layout", ""),
    }
    if unreleased:
        view["unreleased"] = True
        view["released_at"] = record.get("released_at")
    return view


def result_view(record: dict, fmt: Format, *, unreleased: bool = False) -> dict:
    """A raw search hit: name + projection (no quantity/score)."""
    return {
        "name": record.get("name", ""),
        **project(record, fmt, unreleased=unreleased),
    }


_FINISH_PRICE_KEYS = {"foil": "usd_foil", "etched": "usd_etched"}


def card_view(
    name: str,
    qty: int,
    by_name: Mapping[str, dict],
    fmt: Format,
    owned_qty: int | None = None,
    *,
    printing_id: str | None = None,
    resolve_printing: Callable[[str], dict | None] | None = None,
    finish: str | None = None,
    owned_printing: bool | None = None,
    unreleased_ids: frozenset[str] = frozenset(),
) -> dict:
    """A deck-zone card: name + quantity + an ``unknown`` flag + projection (when the
    name resolves against the bulk index). ``owned_qty`` (when set) marks the card as
    owned in the active Collection slot — DERIVED upstream, never stored (ADR-0018).

    When ``printing_id`` names a chosen printing (and ``resolve_printing`` can find it),
    the card's image / prices / set are overridden to it — the gameplay fields (type,
    oracle, cmc) come from the canonical record, which is printing-invariant.

    ``finish`` ("foil" / "etched") surfaces as-is and swaps the displayed ``prices.usd``
    to the finish price (``usd_foil`` / ``usd_etched``, falling back to ``usd``) —
    additive: every other price key stays, so the shape is unchanged. The tri-state
    ``owned_printing`` (printing-level ownership vs the merely name-level ``owned``)
    is emitted only when non-None — absent means the Collection has no printing detail
    for this name."""
    base: dict = {"name": name, "quantity": qty}
    if owned_qty is not None:
        base["owned"] = True
        base["owned_qty"] = owned_qty
    if owned_printing is not None:
        base["owned_printing"] = owned_printing
    if finish:
        base["finish"] = finish
    record = by_name.get(name)
    if record is None:
        return {**base, "unknown": True}
    view = {
        **base,
        "unknown": False,
        **project(record, fmt, unreleased=record.get("oracle_id") in unreleased_ids),
    }
    chosen = resolve_printing(printing_id) if printing_id and resolve_printing else None
    if chosen is not None:
        view["printing_id"] = printing_id
        view["set"] = chosen.get("set")
        view["set_name"] = chosen.get("set_name")
        view["collector_number"] = chosen.get("collector_number")
        view["prices"] = chosen.get("prices", {})
        imgs = image_urls(chosen)
        if imgs:
            view["images"] = imgs
    price_key = _FINISH_PRICE_KEYS.get(finish or "")
    if price_key:
        prices = view.get("prices") or {}
        view["prices"] = {
            **prices,
            "usd": prices.get(price_key) or prices.get("usd"),
        }
    return view


def candidate_view(
    row: dict, fmt: Format, *, owned_qty: int | None = None, unreleased: bool = False
) -> dict:
    """A ranked candidate — a ``rank_candidates`` row ``{"card", "score"}`` — as
    name + projection + score. ``owned_qty`` (when set) marks it owned in the active
    Collection slot (ADR-0018), mirroring ``card_view``; absent → no ownership keys, so
    the wire shape stays byte-compatible for a no-collection request."""
    card = row["card"]
    view = {
        "name": card.get("name", ""),
        **project(card, fmt, unreleased=unreleased),
        "score": row["score"],
    }
    if owned_qty is not None:
        view["owned"] = True
        view["owned_qty"] = owned_qty
    return view


def combo_card_view(
    name: str, record: dict | None, *, in_deck: bool, fmt: Format
) -> dict:
    """A combo piece: name + an ``in_deck`` flag + projection when the card is known."""
    view = {"name": name, "in_deck": in_deck}
    if record is not None:
        view.update(project(record, fmt))
    return view


def deck_view(
    state: ForgeState,
    owned: dict[str, int] | None = None,
    printing_owned: Callable[[str, str | None], bool | None] | None = None,
) -> dict:
    """The serialized deck: ``{format, commanders[], cards[], sideboard[],
    companion[], pool[]}``, each zone a list of ``card_view`` dicts. ``owned``
    (deck card name → owned count in the active Collection slot) marks owned
    cards; absent → no ownership shown (no collection).
    ``printing_owned`` (name, printing_id → tri-state) resolves whether the card's
    effectively-chosen printing is owned at printing level (``engine.printing_owned``);
    absent → the ``owned_printing`` field never renders."""
    deck = state.session.to_deck_dict()
    by_name = state.by_name
    fmt = FORMATS[deck["format"]]
    owned = owned or {}
    return {
        "format": fmt.name,
        # medium (paper/digital) drives the slot + cost mode; deck_size is the effective
        # size (60/100 for paper Historic Brawl). Both surface so the header can render
        # the medium toggle + the size selector.
        "medium": state.session.medium,
        "deck_size": state.session.deck_size,
        **{
            zone: [
                card_view(
                    e["name"],
                    e["quantity"],
                    by_name,
                    fmt,
                    owned.get(e["name"]),
                    printing_id=e.get("printing_id"),
                    resolve_printing=state.printing_by_id.get,
                    finish=e.get("finish"),
                    unreleased_ids=state.unreleased_ids,
                    owned_printing=(
                        printing_owned(e["name"], e.get("printing_id"))
                        if printing_owned
                        else None
                    ),
                )
                for e in deck[zone]
            ]
            for zone in ZONES
        },
    }


def signal_view(signal: Signal) -> dict:
    """One deck signal on the wire: identity + the served spec's label / avenue."""
    spec = spec_for(signal)
    return {
        "key": signal.key,
        "scope": signal.scope,
        "subject": signal.subject,
        "source": signal.source,
        "confidence": signal.confidence,
        "label": spec.label if spec else signal.key,
        "avenue": spec.avenue if spec else "",
        "actionable": spec is not None,
    }


def commander_view(row: dict, fmt: Format) -> dict:
    """A discovered commander (an ``discovery.discover_commanders`` row: the record plus
    its support scores) as name + projection + scores."""
    view = {"name": row["name"], **project(row["record"], fmt)}
    for key in ("support_depth", "lanes", "supported_lanes", "novelty"):
        if key in row:
            view[key] = row[key]
    return view


def enrich_combos(
    result: dict, by_name: Mapping[str, dict], *, in_deck: set[str], fmt: Format
) -> dict:
    """Attach ``card_views`` (image / type / price + an ``in_deck`` flag) to every
    combo and near-miss in a combo-search result, so the SPA renders them as the same
    CardTiles as search. Mutates and returns *result*."""
    for group in ("combos", "near_misses"):
        for combo in result.get(group) or []:
            combo["card_views"] = [
                combo_card_view(
                    name, by_name.get(name), in_deck=name in in_deck, fmt=fmt
                )
                for name in (combo.get("cards") or [])
            ]
    return result
