"""Slot budgets vs a family's (soft) deckbuilding template.

Role targets are *nudges* (D8): the hard land/curve gate lives in ``mana_audit``. Each
row reports min/max band, current, remaining (to the floor), and deviation (distance
outside the band) so the build loop can size a "choose up to N" batch and the Tune
surface can rank template gaps.

A :class:`Template` is **bands** (not single points) per format family, stated at the
family's base deck size and scaled to the deck's: the Command Zone template (Ep. 658,
verified multi-source) for the Commander family; a deliberately minimal constructed
template — interaction (sweepers fold in), card draw, and an advisory creature count,
since ramp and wipes are archetype choices in 60-card; and a limited template of
creatures, interaction and curve buckets. A row counts by template ROLE
(``roles.role_of`` — a view over the signal path, ADR-0051) or by a plain record
predicate (a type-line or mana-value count, labelled as such: a "threat" is not a
role). ``slot_budgets`` takes an optional ``shape``: ``None`` (the always-on Budgets
panel) uses flat bands; a Shape (the Tune surface, near-complete deck) scales them.
Counterspells fold into a single ``interaction`` role; win-cons and protection are NOT
counted roles here — they are Tier-2 advisory flags (ADR-0024).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from mtg_utils._analysis.roles import role_of
from mtg_utils.card_classify import is_creature, is_land
from mtg_utils.formats import Family


@dataclass(frozen=True)
class BudgetRow:
    """One template row: what it counts and the band it wants, at the template's base
    size. A row counts a card when any of its ``roles`` is among the card's template
    roles, or — for a plain-fact row — when ``fills`` holds; the two never mix.
    ``advisory`` marks a row shown but never sourced by the tuner and never a cut
    pool (a creature count is a fact about the deck, not a slot to fill)."""

    key: str
    label: str
    band: tuple[int, int]
    roles: tuple[str, ...] = ()
    fills: Callable[[dict], bool] | None = None
    shape_bands: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    advisory: bool = False

    def counts(self, record: dict, roles: frozenset[str] | set[str]) -> bool:
        """Whether ``record`` (with its template ``roles``) fills this row."""
        if self.fills is not None:
            return self.fills(record)
        return bool(roles & set(self.roles))


@dataclass(frozen=True)
class Template:
    """A family's role-count template: ordered rows at ``base_size``. The ``lands``
    row's band always comes from the mana audit's land band (ADR-0041), never from
    here."""

    family: Family
    base_size: int
    rows: tuple[BudgetRow, ...]

    def row(self, key: str) -> BudgetRow | None:
        for r in self.rows:
            if r.key == key:
                return r
        return None

    def fills(
        self, key: str, record: dict, roles: frozenset[str] | set[str] | None = None
    ) -> bool:
        """The ONE membership read: whether ``record`` counts toward row ``key`` —
        what ``slot_budgets`` counts by and what a template cut pool trims by."""
        r = self.row(key)
        if r is None:
            return False
        return r.counts(record, roles if roles is not None else role_of(record))

    def bands_for(self, shape: str | None) -> dict[str, tuple[int, int]]:
        """The row→(min,max) bands for a Shape (or the flat bands when None)."""
        return {
            r.key: (r.shape_bands.get(shape, r.band) if shape else r.band)
            for r in self.rows
        }


def _nonland_at_cmc(lo: float, hi: float | None) -> Callable[[dict], bool]:
    def pred(record: dict) -> bool:
        if is_land(record):
            return False
        cmc = float(record.get("cmc", 0.0) or 0.0)
        return cmc >= lo and (hi is None or cmc <= hi)

    return pred


# Command Zone template bands, per 100 cards (min, max). Scaled by deck size for
# Brawl. Shape-scaled overrides (ADR-0024 — the literature scales by archetype, not by
# power bracket) ride on each row; the rest keep the flat band.
COMMANDER_TEMPLATE = Template(
    family="commander",
    base_size=100,
    rows=(
        BudgetRow("lands", "Lands", (36, 38), roles=("lands",)),
        BudgetRow(
            "ramp",
            "Ramp",
            (10, 12),
            roles=("ramp",),
            shape_bands={"aggro": (8, 10)},
        ),
        BudgetRow(
            "card_draw",
            "Card draw",
            (10, 12),
            roles=("card_draw",),
            shape_bands={"control": (10, 14)},
        ),
        BudgetRow(
            "interaction",
            "Interaction",
            (10, 12),
            roles=("interaction",),
            shape_bands={"control": (12, 15), "aggro": (8, 10), "combo": (8, 12)},
        ),
        BudgetRow(
            "board_wipe",
            "Board wipes",
            (3, 4),
            roles=("board_wipe",),
            shape_bands={"control": (5, 7), "aggro": (1, 2), "combo": (2, 3)},
        ),
    ),
)

# 60-card constructed, per 60 cards. Deliberately minimal and honest: interaction
# (sweepers fold in — a control deck's Wraths are its interaction, and there is no
# separate wipe row because wipe density is an archetype choice), card draw, and an
# ADVISORY creature count by type line. No ramp row: a Burn deck at zero ramp is
# on-template; ramp is a Shape read the tuner's efficiency panel reports.
CONSTRUCTED_TEMPLATE = Template(
    family="constructed",
    base_size=60,
    rows=(
        BudgetRow("lands", "Lands", (20, 27), roles=("lands",)),
        BudgetRow(
            "interaction",
            "Interaction (incl. sweepers)",
            (4, 12),
            roles=("interaction", "board_wipe"),
            shape_bands={
                "aggro": (2, 6),
                "midrange": (6, 10),
                "control": (10, 16),
                "combo": (4, 8),
            },
        ),
        BudgetRow(
            "card_draw",
            "Card draw",
            (4, 8),
            roles=("card_draw",),
            shape_bands={"aggro": (0, 6), "control": (6, 12)},
        ),
        BudgetRow(
            "creatures",
            "Creatures (type line)",
            (12, 28),
            fills=is_creature,
            shape_bands={
                "aggro": (20, 28),
                "midrange": (14, 22),
                "control": (4, 10),
                "combo": (6, 16),
            },
            advisory=True,
        ),
    ),
)

# Limited (sealed / draft), per 40 cards: the norms every limited primer agrees on —
# a creature-dense deck, a few answers, a real two- and three-drop count, and a
# capped top end. Ceilings on the drop rows are generous by design; the floor is the
# norm. No Shape bands: a limited deck is midrange by construction.
LIMITED_TEMPLATE = Template(
    family="limited",
    base_size=40,
    rows=(
        BudgetRow("lands", "Lands", (16, 18), roles=("lands",)),
        BudgetRow("creatures", "Creatures (type line)", (14, 17), fills=is_creature),
        BudgetRow(
            "interaction",
            "Interaction (removal, tricks)",
            (3, 8),
            roles=("interaction", "board_wipe"),
        ),
        BudgetRow("two_drops", "Two-drops", (4, 10), fills=_nonland_at_cmc(2, 2)),
        BudgetRow("three_drops", "Three-drops", (3, 8), fills=_nonland_at_cmc(3, 3)),
        BudgetRow("six_plus", "Six-plus drops", (0, 2), fills=_nonland_at_cmc(6, None)),
    ),
)

TEMPLATES: dict[str, Template] = {
    t.family: t for t in (COMMANDER_TEMPLATE, CONSTRUCTED_TEMPLATE, LIMITED_TEMPLATE)
}


def template_for(family: Family) -> Template:
    """The template for a format family (``Format.family``)."""
    try:
        return TEMPLATES[family]
    except KeyError:
        msg = f"no template for family {family!r}; expected one of {sorted(TEMPLATES)}"
        raise ValueError(msg) from None


def banded_slot_budgets(
    records: Sequence[dict | None],
    land_band: dict,
    *,
    deck_size: int,
    shape: str | None = None,
    template: Template | None = None,
) -> dict[str, dict]:
    """:func:`slot_budgets` over *records* (a deck's ``expanded()`` cards) with the
    lands row set to *land_band*, the mana audit's own ``{floor, top, …}`` readout
    (ADR-0041) — passed in so a caller that already audited never audits twice, and
    no caller re-derives the band."""
    return slot_budgets(
        records,
        deck_size=deck_size,
        shape=shape,
        land_band=(land_band["floor"], land_band["top"]),
        template=template,
    )


def slot_budgets(
    records: Sequence[dict | None],
    *,
    deck_size: int = 100,
    shape: str | None = None,
    land_band: tuple[int, int],
    template: Template | None = None,
) -> dict[str, dict]:
    """Return ``{row: {min, max, target, current, remaining, deviation, label,
    advisory}}`` vs the band, in template order.

    ``deviation`` is 0 inside the band, negative when short of the floor, positive when
    over the ceiling. ``remaining`` is the gap up to the floor (0 once in band).
    ``target`` is the band ceiling, kept for the existing Budgets-panel bar.

    ``land_band`` (floor, top) is the deck-specific "lands" row: ``mana_audit``'s
    ``land_band`` (ADR-0041), which every deck carries. It is REQUIRED, so this call
    and the mana verdict provably read the same band — a re-derivation here from this
    call's own ramp tally (scoped to *records*, which callers pass as the main deck
    with commanders excluded) is exactly the second band ADR-0041 exists to
    eliminate, and no longer exists.

    ``template`` is the family's (``template_for(fmt.family)``); ``None`` is the
    Commander template.
    """
    tmpl = template or COMMANDER_TEMPLATE
    scale = deck_size / tmpl.base_size
    bands = tmpl.bands_for(shape)
    current: dict[str, int] = dict.fromkeys(bands, 0)
    for record in records:
        if not record:
            continue
        roles = role_of(record)
        for row in tmpl.rows:
            if row.counts(record, roles):
                current[row.key] += 1
    out: dict[str, dict] = {}
    for row in tmpl.rows:
        lo, hi = bands[row.key]
        if row.key == "lands":
            rmin, rmax = land_band  # already scaled to deck_size
        else:
            rmin = round(lo * scale)
            rmax = round(hi * scale)
        have = current[row.key]
        if have < rmin:
            deviation = have - rmin
        elif have > rmax:
            deviation = have - rmax
        else:
            deviation = 0
        out[row.key] = {
            "min": rmin,
            "max": rmax,
            "target": rmax,
            "current": have,
            "remaining": max(0, rmin - have),
            "deviation": deviation,
            "label": row.label,
            "advisory": row.advisory,
        }
    return out
