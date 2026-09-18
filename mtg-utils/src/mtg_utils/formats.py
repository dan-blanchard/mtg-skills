"""Formats — the one module that answers every deck-format question (ADR-0045).

A ``Format`` is a frozen value that owns the *behaviour* of a format, not just its
flags: whether a record is legal here (with the Competitive Brawl override and the
Arena-pool gate folded in), whether a record can be a commander here, which media the
format is played in and which one is the default, what size a deck must be and which
sizes a medium may choose from, the CR citation for that size, and the cost mode a
medium implies. Callers resolve a name once (``FORMATS[name]`` / ``get_format`` /
``Format.for_deck``) and never re-derive a rule from the table again — the six
legality predicates, four medium rules and three SPA hand-lists this module replaced
were each a re-derivation that drifted (a card ``brawl`` bans but Competitive Brawl
legalizes was hidden from ``card-search`` while ``legality-audit`` accepted it).

Record contract (the MTGJSON adapter emits both; see ``_mtgjson.adapter``):
  - ``legalities[legality_key]`` — the oracle-level status, aggregated across printings.
  - ``arena_available`` — oracle-level: True when ANY printing exists on Arena. A record
    that lacks the key carries no availability evidence and is not gated (hand-built
    fixtures, Scryfall-API fallback records).

Legality statuses are Scryfall's four plus ``unreleased``: a card whose blanket
``not_legal`` is a release-date artifact (see ``card_search.unreleased_oracle_ids``).
The module cannot tell that from one record — the oracle-level set is an input — so
``unreleased`` is reported only when the caller passes the set; without it the status
is ``not_legal``, which is the default gate everywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from mtg_utils.card_classify import is_commander
from mtg_utils.names import normalize_card_name

Legality = Literal["legal", "restricted", "banned", "not_legal", "unreleased"]
Medium = Literal["paper", "digital"]
CostMode = Literal["usd", "wildcards"]
#: The format families. A family is what a deck's SHAPE rules follow — a command zone
#: and exact size (commander), a copy limit + sideboard over a minimum size
#: (constructed), or a build bounded by an opened pool over a minimum size, with no
#: copy limit and no sideboard cap (limited: sealed / draft, CR 100.2b). A caller
#: that needs the family reads ``Format.family``, one that needs a single family
#: fact reads it (``has_commander``, ``pool_bounded``, ``size_is_minimum``, …); no
#: caller compares format names.
Family = Literal["commander", "constructed", "limited"]

#: The statuses under which a card may be played (Vintage's restricted list is a copy
#: limit, not a ban).
LEGAL_STATUSES: frozenset[str] = frozenset({"legal", "restricted"})

#: How the browser names each medium.
MEDIUM_LABELS: dict[str, str] = {"digital": "Arena", "paper": "Paper"}


def medium_is_digital(medium: str) -> bool:
    """The one place "is this an Arena game?" is decided from a medium string."""
    return medium == "digital"


@dataclass(frozen=True, slots=True)
class Game:
    """The game a deck built for one medium is played in — what the tuner's closer
    read and bracket gate are relative to. Built by ``Format.game``, never ad hoc."""

    medium: Medium
    #: Starting life (CR 103.4: 20; 103.4c Commander 40; 103.4d Brawl 25 two-player /
    #: 30 multiplayer).
    life: int
    #: A multiplayer table (a Commander pod, a multiplayer Brawl game) vs one opponent.
    multiplayer: bool
    #: Whether 21 combat damage from one commander wins (CR 903.10a; Commander only).
    commander_damage: bool


# Arena's Competitive Brawl (June 2026) bans ten cards outright — as commander AND in
# the 99 — and legalizes everything else on Arena, including the ~28 cards the ordinary
# Brawl queue bans. MTGJSON/Scryfall publish no legality key for it, so legality runs
# off the ``brawl`` key plus two overrides: ``banned`` under that key is legal here,
# ``not_legal`` still is not (it means the card isn't in the Arena pool at all).
# Canonical Scryfall names (``A-`` is the Alchemy-rebalanced printing).
#
# Source: https://mtg.wiki/page/Competitive_Brawl (banned list as of 2026-08).
# Re-verify after each B&R announcement; this list is a point-in-time snapshot.
COMPETITIVE_BRAWL_BANNED: frozenset[str] = frozenset(
    {
        "Ajani, Nacatl Pariah",
        "A-Nadu, Winged Wisdom",
        "Lutri, the Spellchaser",
        "Oko, Thief of Crowns",
        "Old Stickfingers",
        "Ragavan, Nimble Pilferer",
        "Rusko, Clockmaker",
        "Tamiyo, Inquisitive Student",
        "Wrenn and Six",
        "Tajic, Legion's Valor",
    }
)


@dataclass(frozen=True, slots=True)
class Format:
    """One deck format's rules. Build from ``FORMATS`` / ``get_format`` /
    ``Format.for_deck``; never construct ad hoc."""

    name: str
    label: str
    deck_size: int
    #: The sideboard cap; ``None`` where a format has no cap (limited: the sideboard
    #: is the unused pool, CR 100.4b).
    sideboard_size: int | None
    life_total: int
    has_commander: bool
    #: The copy limit; ``None`` where a format has none (limited: as many duplicates
    #: as the product included, CR 100.2b).
    max_copies: int | None
    #: Whether the format has Commander's extra loss rule — 21 combat damage from one
    #: commander (CR 903.10a). Commander only: Brawl games do not use it (CR 903.12h)
    #: and no other format has it.
    commander_damage: bool
    #: The MTGJSON legality key, or ``None`` for a pool-bounded format: a limited
    #: deck's legality is pool membership, not a set's status, so every record is
    #: ``legal`` here and ``legality_audit`` checks containment instead.
    legality_key: str | None
    planeswalker_commander_requires_text: bool
    free_mulligan: bool
    colorless_any_basic: bool
    #: Played on MTG Arena (possibly also in paper).
    is_arena: bool
    #: Multiplayer starting life (CR 103.4d: a multiplayer Brawl game starts at 30);
    #: None for formats with no multiplayer variant.
    multiplayer_life_total: int | None = None
    #: No paper counterpart at all: the medium is always digital, never a choice.
    is_arena_only: bool = False
    #: For a format played in BOTH media, the one a new build defaults to. ``None``
    #: keeps digital first (the Brawl queues live on Arena); ``"paper"`` puts paper
    #: first for a paper-defined format Arena also hosts (Standard, Pioneer).
    primary_medium: Medium | None = None
    #: The format's card pool IS Arena's (MTGJSON's brawl / historic / alchemy /
    #: timeless / standardbrawl keys): a card with no Arena printing is not legal, even
    #: when MTGJSON marks it so (Lord of Atlantis, pw24). Medium-independent — the paper
    #: Brawl queues use Arena's pool too. Standard / Pioneer are Arena formats whose
    #: pool is defined in paper, so they are NOT gated.
    arena_pool: bool = False
    #: Treat ``banned`` under ``legality_key`` as legal (Competitive Brawl shares
    #: ``brawl`` but not its ban list) and enforce ``banned_cards`` by name instead.
    ignores_legality_key_bans: bool = False
    #: Canonical names banned by this format's own list (empty for most formats).
    banned_cards: frozenset[str] = frozenset()
    #: ``banned_cards`` folded through ``names.normalize_card_name`` — the keys the
    #: legality read matches a record's name against (derived, never set by hand).
    banned_keys: frozenset[str] = field(
        init=False, repr=False, compare=False, default=frozenset()
    )
    #: CR citation for the exact deck size (Commander family only): the over-size
    #: message cites it. None where the CR sets only a minimum (CR 100.2a).
    size_rule: str | None = None
    #: Per-medium size choices where a medium may pick (paper Historic Brawl, a.k.a.
    #: paper "Brawl", is 60 OR 100). Absent medium → the fixed ``deck_size``.
    size_choices_by_medium: Mapping[str, tuple[int, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "banned_keys",
            frozenset(normalize_card_name(n) for n in self.banned_cards),
        )
        # The medium flags must agree: Arena-only is a kind of Arena, and a primary
        # medium names one the format is actually played in.
        if self.is_arena_only and not self.is_arena:
            msg = f"{self.name}: is_arena_only requires is_arena"
            raise ValueError(msg)
        if self.primary_medium is not None and self.primary_medium not in self.media:
            msg = f"{self.name}: primary_medium {self.primary_medium!r} not in media"
            raise ValueError(msg)

    # --- family -------------------------------------------------------------------

    @property
    def is_singleton(self) -> bool:
        return self.max_copies == 1

    @property
    def is_constructed(self) -> bool:
        """60-card constructed (no command zone)."""
        return not self.has_commander

    @property
    def pool_bounded(self) -> bool:
        """A limited format: the deck is built from an opened pool (CR 100.2b), so
        legality is pool membership and the sideboard is the unused pool."""
        return self.legality_key is None

    @property
    def family(self) -> Family:
        """Which family's shape rules this format follows (see ``Family``)."""
        if self.has_commander:
            return "commander"
        if self.pool_bounded:
            return "limited"
        return "constructed"

    @property
    def size_is_minimum(self) -> bool:
        """Whether ``deck_size`` is a floor the deck may exceed (CR 100.2a sets only a
        minimum for constructed) rather than the exact size the Commander family's
        ``size_rule`` cites (CR 903.5a / 903.12d)."""
        return not self.has_commander

    @property
    def min_deck_size(self) -> int:
        """The smallest legal deck. For an exact-size family it is ``deck_size``; for a
        size-minimum family it is the TABLE's size (the CR floor) even when this
        value carries a build's own larger ``deck_size`` (an 80-card Yorion deck is
        still a 60-minimum Standard deck — ``for_deck`` / ``resolve_deck_size`` set
        the target, never the floor)."""
        if self.size_is_minimum:
            return FORMATS[self.name].deck_size
        return self.deck_size

    @property
    def size_cap(self) -> int | None:
        """The largest legal deck, or ``None`` where the family sets only a minimum."""
        return None if self.size_is_minimum else self.deck_size

    # --- medium -------------------------------------------------------------------

    @property
    def media(self) -> tuple[Medium, ...]:
        """The media this format is played in, default first."""
        if self.is_arena_only:
            return ("digital",)
        if self.is_arena:
            if self.primary_medium == "paper":
                return ("paper", "digital")
            return ("digital", "paper")
        return ("paper",)

    @property
    def default_medium(self) -> Medium:
        return self.media[0]

    def resolve_medium(self, override: str | None) -> Medium:
        """The effective medium: ``override`` when this format allows it, else the
        default. An override the format cannot honour (paper on an Arena-only format,
        digital on Commander) is ignored rather than raised, so a preference set under
        one format survives toggling to another (deck-forge keeps the raw override)."""
        if override in self.media:
            return override  # type: ignore[return-value]
        return self.default_medium

    def is_multiplayer(self, medium: str) -> bool:
        """Whether a game in ``medium`` is multiplayer: Arena is one-on-one for every
        format; in paper, a format is multiplayer iff it has a multiplayer variant
        (Commander's pod, paper Brawl's 30-life table — CR 103.4d)."""
        return not medium_is_digital(medium) and self.multiplayer_life_total is not None

    def starting_life(self, medium: str) -> int:
        """The starting life a deck built for ``medium`` plays against — the
        multiplayer total at a paper table, else the one-on-one total."""
        if self.is_multiplayer(medium):
            assert self.multiplayer_life_total is not None  # is_multiplayer's rule
            return self.multiplayer_life_total
        return self.life_total

    def game(self, medium: str | None = None) -> Game:
        """The ``Game`` a build in ``medium`` plays (an override the format cannot
        honour resolves as in ``resolve_medium``): starting life and table size follow
        the medium; commander damage is the format's own rule (CR 903.10a)."""
        resolved = self.resolve_medium(medium)
        return Game(
            medium=resolved,
            life=self.starting_life(resolved),
            multiplayer=self.is_multiplayer(resolved),
            commander_damage=self.commander_damage,
        )

    def paper_only(self, medium: str | None = None) -> bool:
        """Whether a card search for a build in ``medium`` is restricted to paper
        printings. It follows the MEDIUM, not ``is_arena``: a paper Historic Brawl
        table buys paper printings in USD, while the same format built for Arena
        searches Arena's printings (whose rarity is the wildcard cost). The
        Arena-pool gate is separate and medium-independent — ``legality`` applies it
        either way."""
        return not medium_is_digital(self.resolve_medium(medium))

    @staticmethod
    def cost_mode(medium: str) -> CostMode:
        """What a card costs to acquire in ``medium``: Arena wildcards or paper USD."""
        return "wildcards" if medium_is_digital(medium) else "usd"

    # --- size ---------------------------------------------------------------------

    def size_choices(self, medium: str) -> tuple[int, ...]:
        """The deck sizes ``medium`` may choose from (usually just ``deck_size``)."""
        return self.size_choices_by_medium.get(medium, (self.deck_size,))

    @property
    def all_size_choices(self) -> tuple[int, ...]:
        """Every size some medium of this format may choose, ascending."""
        return tuple(sorted({s for m in self.media for s in self.size_choices(m)}))

    def is_valid_deck_size(self, size: int) -> bool:
        """Commander family: one of the size choices across every medium (exact-size
        formats, CR 903.5a / 903.12d). Constructed and limited: any positive size —
        CR 100.2a / 100.2b set only a minimum (an 80-card Yorion deck is legal; a
        build's size is its target, ``min_deck_size`` its floor)."""
        if self.has_commander:
            return any(size in self.size_choices(m) for m in self.media)
        return size > 0

    def resolve_deck_size(self, override: int | None, medium: str) -> int:
        """The effective size under ``medium``: ``override`` when it is one of that
        medium's choices, else the fixed size (the override lies dormant). A
        constructed format honours any valid size (an 80-card Yorion deck), since its
        size is a minimum, not a choice list."""
        if override is None:
            return self.deck_size
        if self.has_commander:
            if override in self.size_choices(medium):
                return override
            return self.deck_size
        return override if self.is_valid_deck_size(override) else self.deck_size

    # --- legality -----------------------------------------------------------------

    def legality(
        self, record: dict, *, unreleased: frozenset[str] | bool = False
    ) -> Legality:
        """This format's status for a card record (see the module docstring for the
        record contract). ``unreleased`` is the oracle-level pre-release set, or
        ``True`` when the caller has already established this record is pre-release
        (the hub's views carry that as a flag per card)."""
        if self.banned_keys and normalize_card_name(record.get("name", "")) in (
            self.banned_keys
        ):
            return "banned"
        if self.legality_key is None:
            return "legal"  # pool-bounded: membership is the audit's question
        status = (record.get("legalities") or {}).get(self.legality_key, "not_legal")
        if status == "banned" and self.ignores_legality_key_bans:
            status = "legal"
        if status in LEGAL_STATUSES:
            if self.arena_pool and record.get("arena_available") is False:
                return "not_legal"
            return status  # type: ignore[return-value]
        if status == "banned":
            return "banned"
        if unreleased is True or (unreleased and record.get("oracle_id") in unreleased):
            return "unreleased"
        return "not_legal"

    def is_legal(
        self, record: dict, *, unreleased: frozenset[str] | bool = False
    ) -> bool:
        """Playable here: ``legal`` or ``restricted``. Never true for ``unreleased``;
        callers that widen for pre-release cards test the status themselves."""
        return self.legality(record, unreleased=unreleased) in LEGAL_STATUSES

    def commander_eligibility(
        self, record: dict, *, unreleased: frozenset[str] | bool = False
    ) -> dict:
        """``{"eligible", "requires_partner"}`` for this format: legality (a pre-release
        legend counts, so brewing around a spoiled commander works) composed with the
        type-line / oracle-text rules in ``card_classify.is_commander``, under this
        format's planeswalker rule (the Brawl family admits any legendary planeswalker;
        Commander needs "can be your commander"). A format with no command zone has
        no commanders: nothing is eligible, however legendary."""
        if not self.has_commander:
            return {"eligible": False, "requires_partner": False}
        status = self.legality(record, unreleased=unreleased)
        if status not in LEGAL_STATUSES and status != "unreleased":
            return {"eligible": False, "requires_partner": False}
        return is_commander(
            record,
            planeswalker_commander_requires_text=self.planeswalker_commander_requires_text,
        )

    # --- deck ---------------------------------------------------------------------

    @classmethod
    def for_deck(cls, deck: Mapping) -> Format:
        """The format of a parsed-deck dict, with the deck's own ``deck_size`` applied.
        The one home of the ``"commander"`` default. An explicit size a Commander-family
        format cannot be (a 73-card Commander deck) raises ``ValueError`` rather than
        silently driving the land math off a nonsense size; constructed formats accept
        any size (limited decks, Yorion)."""
        fmt = get_format(deck.get("format") or "commander")
        raw = deck.get("deck_size")
        if raw is None:
            return fmt
        size = int(raw)
        if not fmt.is_valid_deck_size(size):
            choices = list(fmt.all_size_choices)
            msg = f"deck_size {size} is not legal for {fmt.name}: expected {choices}"
            raise ValueError(msg)
        return replace(fmt, deck_size=size) if size != fmt.deck_size else fmt

    # --- SPA ----------------------------------------------------------------------

    def spa_entry(self) -> dict:
        """The one row the browser SPA reads for this format (labels, media, sizes) —
        replaces the hand-lists that mirrored the backend by comment."""
        return {
            "id": self.name,
            "label": self.label,
            "family": self.family,
            "has_commander": self.has_commander,
            "pool_bounded": self.pool_bounded,
            "max_copies": self.max_copies,
            "sideboard_size": self.sideboard_size,
            "size_is_minimum": self.size_is_minimum,
            "media": list(self.media),
            "medium_labels": {m: MEDIUM_LABELS[m] for m in self.media},
            "default_medium": self.default_medium,
            "deck_size": self.deck_size,
            "size_choices": {m: list(self.size_choices(m)) for m in self.media},
        }


def _commander_variant(name: str, label: str, **kw: object) -> Format:
    base: dict = {
        "sideboard_size": 0,
        "has_commander": True,
        "max_copies": 1,
        "planeswalker_commander_requires_text": False,
        "colorless_any_basic": True,
        "commander_damage": False,
        # CR 103.5c: the first mulligan in any Brawl game is free.
        "free_mulligan": True,
    }
    base.update(kw)
    return Format(name=name, label=label, **base)  # type: ignore[arg-type]


def _constructed(
    name: str,
    label: str,
    *,
    legality_key: str,
    arena: bool,
    arena_pool: bool = False,
    arena_only: bool = False,
    primary_medium: Medium | None = None,
) -> Format:
    return Format(
        name=name,
        label=label,
        deck_size=60,
        sideboard_size=15,
        life_total=20,
        has_commander=False,
        max_copies=4,
        commander_damage=False,
        legality_key=legality_key,
        planeswalker_commander_requires_text=False,
        free_mulligan=False,
        colorless_any_basic=False,
        is_arena=arena,
        arena_pool=arena_pool,
        is_arena_only=arena_only,
        primary_medium=primary_medium,
    )


def _limited(name: str, label: str) -> Format:
    """A pool-bounded format (CR 100.2b): 40-card minimum, as many duplicates as the
    product included, the unused pool as the sideboard; played on Arena and on
    paper, Arena first."""
    return Format(
        name=name,
        label=label,
        deck_size=40,
        sideboard_size=None,
        life_total=20,
        has_commander=False,
        max_copies=None,
        commander_damage=False,
        legality_key=None,
        planeswalker_commander_requires_text=False,
        free_mulligan=False,
        colorless_any_basic=False,
        is_arena=True,
    )


_ALL: tuple[Format, ...] = (
    # ── Commander / Brawl variants (singleton, has commander) ──
    _commander_variant(
        "commander",
        "Commander",
        deck_size=100,
        life_total=40,
        multiplayer_life_total=40,
        commander_damage=True,
        legality_key="commander",
        planeswalker_commander_requires_text=True,
        free_mulligan=False,
        colorless_any_basic=False,
        is_arena=False,
        size_rule="CR 903.5a",
    ),
    _commander_variant(
        "brawl",
        "Brawl",
        deck_size=60,
        # CR 103.4d: 25 in a two-player Brawl game, 30 in a multiplayer one.
        life_total=25,
        multiplayer_life_total=30,
        legality_key="standardbrawl",
        is_arena=True,
        arena_pool=True,
        size_rule="CR 903.12d",
    ),
    _commander_variant(
        "historic_brawl",
        "Historic Brawl",
        deck_size=100,
        life_total=25,
        multiplayer_life_total=30,
        legality_key="brawl",
        is_arena=True,
        arena_pool=True,
        size_rule="CR 903.5a",
        # Paper "Brawl" may be 60 OR 100 cards; Arena fixes it at 100.
        size_choices_by_medium={"paper": (60, 100)},
    ),
    _commander_variant(
        "competitive_brawl",
        "Competitive Brawl",
        deck_size=100,
        life_total=25,
        # Arena is 1v1 only; there is no multiplayer Competitive Brawl.
        multiplayer_life_total=None,
        legality_key="brawl",
        # Unlike ordinary Brawl, Competitive Brawl has no free mulligan.
        free_mulligan=False,
        is_arena=True,
        # No paper counterpart at all: the medium is always digital.
        is_arena_only=True,
        arena_pool=True,
        ignores_legality_key_bans=True,
        banned_cards=COMPETITIVE_BRAWL_BANNED,
        size_rule="CR 903.5a",
    ),
    # ── Constructed formats (60-card, 4-of, sideboard) ──
    # Standard and Pioneer are paper-defined formats Arena also hosts: a new build
    # defaults to paper. Alchemy / Historic / Timeless exist only on Arena.
    _constructed(
        "standard",
        "Standard",
        legality_key="standard",
        arena=True,
        primary_medium="paper",
    ),
    _constructed(
        "alchemy",
        "Alchemy",
        legality_key="alchemy",
        arena=True,
        arena_pool=True,
        arena_only=True,
    ),
    _constructed(
        "historic",
        "Historic",
        legality_key="historic",
        arena=True,
        arena_pool=True,
        arena_only=True,
    ),
    _constructed(
        "timeless",
        "Timeless",
        legality_key="timeless",
        arena=True,
        arena_pool=True,
        arena_only=True,
    ),
    _constructed(
        "pioneer",
        "Pioneer",
        legality_key="pioneer",
        arena=True,
        primary_medium="paper",
    ),
    _constructed("modern", "Modern", legality_key="modern", arena=False),
    _constructed("premodern", "Premodern", legality_key="premodern", arena=False),
    _constructed("legacy", "Legacy", legality_key="legacy", arena=False),
    _constructed("vintage", "Vintage", legality_key="vintage", arena=False),
    # ── Limited (40-card minimum, pool-bounded: sealed / draft) ──
    _limited("sealed", "Sealed"),
    _limited("draft", "Draft"),
)
#: Every supported format, by name, in the order the table declares.
FORMATS: dict[str, Format] = {f.name: f for f in _ALL}

#: The Commander family — every format with a command zone — derived from the table so
#: a new commander variant is wired everywhere by adding ONE entry.
COMMANDER_FORMATS: tuple[str, ...] = tuple(f.name for f in _ALL if f.has_commander)


def family_size_choices(family: Family) -> tuple[int, ...]:
    """Every size some format of ``family`` may choose in some medium, ascending —
    what a build may set as its size before the (format, medium) that honours it is
    active (the override lies dormant until then; ``Format.resolve_deck_size``)."""
    return tuple(
        sorted(
            {
                s
                for f in FORMATS.values()
                if f.family == family
                for s in f.all_size_choices
            }
        )
    )


def get_format(name: str) -> Format:
    """``FORMATS[name]`` with the fail-loud unknown-format error every CLI wants."""
    fmt = FORMATS.get(name)
    if fmt is None:
        valid = ", ".join(sorted(FORMATS))
        msg = f"Unknown format: {name!r}. Valid formats: {valid}"
        raise ValueError(msg)
    return fmt


def format_options(names: tuple[str, ...] | None = None) -> list[dict]:
    """The format table the browser SPA reads (``Format.spa_entry`` per format) —
    every format in table order unless ``names`` narrows it."""
    if names is None:
        names = tuple(FORMATS)
    return [FORMATS[n].spa_entry() for n in names]
