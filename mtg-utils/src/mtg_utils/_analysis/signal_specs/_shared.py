"""Signal specs — shared building blocks.

Serve/SubAvenue/SignalSpec dataclasses plus every builder-helper constant and
function the SPECS dict literal (split across ``data_1.py``..``data_4.py``)
consumes. Extracted from the original flat ``signal_specs.py`` (task: split
into a package) with zero logic changes. This module has no dependency on
the rest of the ``signal_specs`` package — only on ``signal_keys``,
``_sweep_detectors``, ``card_classify``, and stdlib.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from mtg_utils._analysis._sweep_detectors import (
    SWEEP_DETECTORS,
    SWEEP_LABELS,
)
from mtg_utils._analysis.lanes.card_advantage import (
    FODDER_SELF_RETURNS,
    comes_back_from_graveyard,
)
from mtg_utils.card_classify import (
    card_pt_int,
    type_line_has,
)
from mtg_utils.theme_presets import CardView, _signal_idents_for

_IC = re.IGNORECASE

# Evergreen keyword abilities (CR 702) that a keyword-soup commander (Odric, Akroma)
# shares across the team — counted from the authoritative Scryfall keywords[] field, so
# a "serve N+ keywords" dimension credits the multi-keyword bodies those decks want.
_EVERGREEN_KW = frozenset(
    {
        "flying",
        "first strike",
        "double strike",
        "deathtouch",
        "haste",
        "hexproof",
        "indestructible",
        "lifelink",
        "menace",
        "reach",
        "trample",
        "vigilance",
        "ward",
        "defender",
        "flash",
        "protection",
    }
)


@functools.cache
def _wildcard_scopes(idents: frozenset[str]) -> frozenset[str]:
    """The ``key|scope`` of every ``"key|scope|*"`` wildcard in a serve's idents
    (one set per serve, cached: a serve is checked against every card a theme
    page scans)."""
    return frozenset(w[:-2] for w in idents if w.endswith("|*"))


@dataclass(frozen=True)
class Serve:
    """The precise classifier deciding whether a candidate card FEEDS a signal.

    Oracle-regex is the wrong surface for many characteristics — a "cantrip" is an
    Instant or Sorcery that draws (CR 601.2: what you cast is fixed by the card's
    type), prowess is a `keywords[]` entry (CR 702.108a), devotion/voltron live in
    structured fields. So a Serve ORs three precise dimensions over the full card:

      - ``oracle``: a regex on oracle text (the only signal for effects that truly
        live in prose — e.g. magecraft, an ability word with no rules meaning, CR
        207.2c),
      - ``types``: type-line words (lowercased whole-token match, mirroring
        ``card_search``'s ``card_type`` — never a substring: 'rat' is not a
        Pirate) — ``{"instant", "sorcery"}`` is the gate the bare ``draw a
        card`` regex was missing,
      - ``keywords``: authoritative Scryfall ``keywords`` (prowess, flying, …) —
        exact, never regex-guessed out of prose.

    A card serves iff ANY positive dimension matches (the canonical Spellslinger case
    is an OR): ``oracle``, ``types``, ``keywords``, ``cmc_min`` (big bombs), or
    ``min_devotion`` (a nonland permanent with ≥N single-color mana pips — the
    structured devotion enabler, CR 700.5). ``not_oracle`` VETOes all of them (a
    control Aura must not serve voltron even though its type is Aura). ``search(text)``
    is a back-compat shim so the oracle regex is still directly testable."""

    oracle: re.Pattern[str] | None = None
    types: frozenset[str] = frozenset()
    # The ``types`` arm's exclusions: a card matching ``types`` serves through it
    # only if its type line carries none of these ("noncreature artifact":
    # ``types={"artifact"}, not_types={"creature"}`` — the animation lane's
    # feeders). The other arms are unaffected.
    not_types: frozenset[str] = frozenset()
    # The ``types`` arm's mana-value floor, narrowing it the way ``not_types``
    # does: a card matching ``types`` serves through it only at mana value >= this
    # (Bello animates noncreature artifacts and enchantments of mana value 4 or
    # greater). Unlike ``cmc_min`` — an OR dimension of its own — it never serves
    # a card by itself.
    types_cmc_min: float | None = None
    # The ``types`` arm's colour gate: with it set, a card matching ``types``
    # serves through it only if it is colourless (Reality Smasher, Eldrazi
    # Displacer's devoid — CR 702.114a; not Nest Invader, a green Eldrazi). Like
    # ``types_cmc_min``, never an arm alone.
    types_colorless: bool = False
    # Not a match dimension: the LANDS this serve matches are the avenue's feeders
    # and count toward its depth (the land-type lane's Deserts). Every other
    # avenue's land members are mana base, never theme support (``_tuner.metrics
    # .focus``).
    lands_feed: bool = False
    keywords: frozenset[str] = frozenset()
    cmc_min: float | None = None
    cmc_max: float | None = None  # serve a CHEAP card (mv <= this); inverse of cmc_min
    min_devotion: int | None = None
    produces_mana: bool = False  # serve if the card has a non-empty produced_mana
    power_min: int | None = None  # serve a creature whose power >= this (big-creature)
    toughness_min: int | None = None  # serve a creature whose toughness >= this (Doran)
    toughness_over_power: bool = False  # serve a "butt": toughness > power (>=3 floor)
    keyword_count_min: int | None = None  # serve a creature with >=N EVERGREEN keywords
    vanilla: bool = False  # serve a creature with NO rules text (Muraganda / Ruxa)
    # serve a creature that comes back from its graveyard by one of these routes
    # (``lanes.card_advantage.comes_back_from_graveyard``)
    self_recur: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()  # serve if the card NAME is in this set
    mana_cost: re.Pattern[str] | None = None  # regex on printed mana_cost (X-spells)
    # Structural arm (task #96): serve if the card's own emitted signal idents
    # ("key|scope|subject" — the task-#90 vocabulary, memoized per oracle_id)
    # intersect this set. The theme_presets ``signal_keys`` precedent, with
    # scope/subject discrimination — a Sliver-tribal serve lists
    # ``type_changers|you|Sliver`` and never matches a Goblin changer. Empty
    # idents (synthetic no-oracle_id fixtures) simply never match this arm.
    signal_idents: frozenset[str] = frozenset()
    not_oracle: re.Pattern[str] | None = None
    # AND-composition: when non-empty, the card serves iff EVERY sub-serve matches
    # (each sub-serve is its own OR-of-dimensions). Lets a serve require a conjunction
    # the flat OR can't express — e.g. "self-dies VALUE trigger AND mana value >= 5" (a
    # high-value clone target like Kokusho, excluding a cmc-1 undying body).
    # ``not_oracle`` still vetoes at the top. When set, the OR dimensions on THIS serve
    # are not consulted — put every condition into the sub-serves.
    all_of: tuple[Serve, ...] = ()

    def search(self, text: str) -> re.Match[str] | None:
        """Back-compat: raw oracle-regex search over a string (legacy call sites)."""
        return self.oracle.search(text) if self.oracle is not None else None

    def matches(self, card: dict, view: CardView | None = None) -> bool:
        """True if the card feeds this signal on ANY structured/oracle dimension (or,
        when ``all_of`` is set, EVERY sub-serve) and isn't vetoed by ``not_oracle``.
        ``view`` is the card's :class:`CardView`, when the caller holds it."""
        if view is None:
            view = CardView(card)
        oracle_text = view.oracle
        if self.not_oracle is not None and self.not_oracle.search(oracle_text):
            return False
        if self.all_of:
            return all(sub.matches(card, view) for sub in self.all_of)
        if self.names and (card.get("name") or "").lower() in self.names:
            return True
        if self.oracle is not None and self.oracle.search(oracle_text):
            return True
        # Transform-aware: classify by the FRONT face (what you play), so a transform
        # DFC's back-face type can't satisfy a ``types`` (card_type) serve — the same
        # leak that surfaced a Saga-front // Land-back card as a creature-land.
        # Word-boundary tokens, never substrings: a 'rat' tribal serve must not
        # match every Pirate ("pi[rat]e"), nor 'orc' every Sorcery.
        type_line = view.type_line
        if (
            self.types
            and any(type_line_has(type_line, t) for t in self.types)
            and not any(type_line_has(type_line, t) for t in self.not_types)
            and (
                self.types_cmc_min is None
                or (card.get("cmc") or 0) >= self.types_cmc_min
            )
            and (not self.types_colorless or _is_colorless(card))
        ):
            return True
        if self.keywords and not view.keywords.isdisjoint(self.keywords):
            return True
        if self.mana_cost is not None and self.mana_cost.search(_printed_costs(card)):
            return True
        if self.cmc_min is not None and (card.get("cmc") or 0) >= self.cmc_min:
            return True
        if self.cmc_max is not None and (card.get("cmc") or 0) <= self.cmc_max:
            return True
        if self.produces_mana and card.get("produced_mana"):
            return True
        if (
            self.power_min is not None
            and "creature" in type_line
            and _power(card) >= self.power_min
        ):
            return True
        if (
            self.toughness_min is not None
            and "creature" in type_line
            and _toughness(card) >= self.toughness_min
        ):
            return True
        if (
            self.toughness_over_power
            and "creature" in type_line
            and _toughness(card) >= 3
            and _toughness(card) > _power(card)
        ):
            return True
        if (
            self.keyword_count_min is not None
            and "creature" in type_line
            and len(_EVERGREEN_KW & view.keywords) >= self.keyword_count_min
        ):
            return True
        if (
            self.vanilla
            and "creature" in type_line
            and not re.sub(r"\([^)]*\)", "", oracle_text).strip()
        ):
            return True
        if self.self_recur and comes_back_from_graveyard(card, self.self_recur):
            return True
        if (
            self.min_devotion is not None
            and "instant" not in type_line
            and "sorcery" not in type_line
            and _max_color_pips(card.get("mana_cost") or "") >= self.min_devotion
        ):
            return True
        # Costliest arm (a live crosswalk pass on a cold memo) — checked last,
        # only after every record-shape dimension has missed.
        if not self.signal_idents:
            return False
        card_idents = view.idents
        if not self.signal_idents.isdisjoint(card_idents):
            return True
        return bool(_wildcard_scopes(self.signal_idents)) and any(
            self._serves_ident(i) for i in card_idents
        )

    def _serves_ident(self, ident: str) -> bool:
        """Whether one of the card's idents is one this serve names, exactly or
        through a ``"key|scope|*"`` wildcard (every subject of that key and
        scope — a token doubler serves ANY ``token_maker``, whatever the
        token's subtype; the serve-ident pass, 2026-10-18)."""
        return ident in self.signal_idents or ident.rpartition("|")[
            0
        ] in _wildcard_scopes(self.signal_idents)

    def counts_ident(self, ident: str) -> bool:
        """Whether this serve counts a card emitting ``ident`` toward its theme
        (:meth:`_serves_ident`, on this serve or any ``all_of`` sub-serve)."""
        return self._serves_ident(ident) or any(
            sub.counts_ident(ident) for sub in self.all_of
        )

    def reads_key(self, key: str) -> bool:
        """Whether this serve names any ident of ``key`` (any scope, any
        subject, on this serve or an ``all_of`` sub-serve): its idents are then
        the authority on which of the key's subjects the theme counts."""
        return any(i.partition("|")[0] == key for i in self.signal_idents) or any(
            sub.reads_key(key) for sub in self.all_of
        )

    def matched_idents(self, card: dict) -> frozenset[str]:
        """The card's own idents this serve's ``signal_idents`` match (with
        every ``all_of`` sub-serve's, :meth:`_serves_ident`): what ties a
        served card to the abilities that serve (``ident_provenance``)."""
        own = (
            {i for i in _signal_idents_for(card) if self._serves_ident(i)}
            if self.signal_idents
            else set()
        )
        for sub in self.all_of:
            own |= sub.matched_idents(card)
        return frozenset(own)

    def as_dict(self) -> dict:
        """Serialize for an avenue dict (JSON-safe), so ranking can re-apply the
        SAME precise predicate to candidates it surfaced."""
        out: dict = {}
        if self.oracle is not None:
            out["oracle"] = self.oracle.pattern
        if self.types:
            out["types"] = sorted(self.types)
        if self.not_types:
            out["not_types"] = sorted(self.not_types)
        if self.types_cmc_min is not None:
            out["types_cmc_min"] = self.types_cmc_min
        if self.types_colorless:
            out["types_colorless"] = True
        if self.lands_feed:
            out["lands_feed"] = True
        if self.keywords:
            out["keywords"] = sorted(self.keywords)
        if self.cmc_min is not None:
            out["cmc_min"] = self.cmc_min
        if self.cmc_max is not None:
            out["cmc_max"] = self.cmc_max
        if self.min_devotion is not None:
            out["min_devotion"] = self.min_devotion
        if self.produces_mana:
            out["produces_mana"] = True
        if self.power_min is not None:
            out["power_min"] = self.power_min
        if self.toughness_min is not None:
            out["toughness_min"] = self.toughness_min
        if self.toughness_over_power:
            out["toughness_over_power"] = True
        if self.keyword_count_min is not None:
            out["keyword_count_min"] = self.keyword_count_min
        if self.vanilla:
            out["vanilla"] = True
        if self.self_recur:
            out["self_recur"] = sorted(self.self_recur)
        if self.names:
            out["names"] = sorted(self.names)
        if self.mana_cost is not None:
            out["mana_cost"] = self.mana_cost.pattern
        if self.signal_idents:
            out["signal_idents"] = sorted(self.signal_idents)
        if self.not_oracle is not None:
            out["not_oracle"] = self.not_oracle.pattern
        if self.all_of:
            out["all_of"] = [sub.as_dict() for sub in self.all_of]
        return out

    def admits_nothing(self) -> bool:
        """True for a serve with no dimension set (``Serve()``): no card feeds
        it, so no page filters by it."""
        return self == Serve()

    def is_structured(self) -> bool:
        """True if it carries a dimension the bare ``search`` fragment can't express,
        so the engine should thread it into avenues for precise classification."""
        return bool(
            self.types
            or self.keywords
            or self.cmc_min is not None
            or self.cmc_max is not None
            or self.min_devotion is not None
            or self.produces_mana
            or self.mana_cost is not None
            or self.power_min is not None
            or self.toughness_min is not None
            or self.toughness_over_power
            or self.keyword_count_min is not None
            or self.vanilla
            or self.self_recur
            or self.names
            or self.signal_idents
            or self.not_oracle is not None
            or bool(self.all_of)
        )


def _printed_costs(card: dict) -> str:
    """Every printed mana cost on *card*: the top-level cost plus each face's, since a
    multi-face card (Agadeem's Awakening, a prepare card) carries its cost on the
    faces and leaves the top-level ``mana_cost`` empty."""
    faces = card.get("card_faces") or ()
    return " ".join(
        [card.get("mana_cost") or "", *(f.get("mana_cost") or "" for f in faces)]
    )


def _max_color_pips(mana_cost: str) -> int:
    """Max count of any single color's mana symbols in a mana cost ({3}{B}{B} → 2).
    Hybrid/Phyrexian symbols are ignored (they don't pin a single color's devotion)."""
    from collections import Counter

    syms = re.findall(r"\{([WUBRG])\}", mana_cost or "")
    return max(Counter(syms).values()) if syms else 0


def _power(card: dict) -> int:
    # */X or non-numeric power doesn't count toward a power threshold.
    return card_pt_int(card, "power")


def _toughness(card: dict) -> int:
    # */X or non-numeric toughness doesn't count toward a threshold.
    return card_pt_int(card, "toughness")


def _compile(pat: str | None) -> re.Pattern[str] | None:
    try:
        return re.compile(pat, _IC) if pat else None
    except re.error:
        return None


def _is_colorless(card: dict) -> bool:
    """Whether the card has no colour (CR 105.2c), read off its front face for a
    double-faced card whose record carries the colours per face."""
    colors = card.get("colors")
    if colors is None:
        faces = card.get("card_faces") or ()
        colors = faces[0].get("colors") if faces else None
    return colors is not None and not colors


def serve_from_dict(data: dict) -> Serve:
    """Rebuild a Serve from an avenue dict's stored ``serve`` (or a bare ``search``
    fragment: ``oracle`` + ``card_type``). Used by ranking to classify candidates with
    the same predicate the spec serves on."""
    types = data.get("types")
    if types is None and data.get("card_type"):
        types = [data["card_type"]]
    return Serve(
        oracle=_compile(data.get("oracle")),
        types=frozenset(t.lower() for t in (types or ())),
        not_types=frozenset(t.lower() for t in (data.get("not_types") or ())),
        types_cmc_min=data.get("types_cmc_min"),
        types_colorless=bool(data.get("types_colorless")),
        lands_feed=bool(data.get("lands_feed")),
        keywords=frozenset(k.lower() for k in (data.get("keywords") or ())),
        cmc_min=data.get("cmc_min"),
        cmc_max=data.get("cmc_max"),
        min_devotion=data.get("min_devotion"),
        produces_mana=bool(data.get("produces_mana")),
        power_min=data.get("power_min"),
        toughness_min=data.get("toughness_min"),
        toughness_over_power=bool(data.get("toughness_over_power")),
        keyword_count_min=data.get("keyword_count_min"),
        vanilla=bool(data.get("vanilla")),
        self_recur=frozenset(data.get("self_recur") or ()),
        names=frozenset(n.lower() for n in (data.get("names") or ())),
        mana_cost=_compile(data.get("mana_cost")),
        signal_idents=frozenset(data.get("signal_idents") or ()),
        not_oracle=_compile(data.get("not_oracle")),
        all_of=tuple(serve_from_dict(d) for d in (data.get("all_of") or ())),
    )


@dataclass(frozen=True)
class SubAvenue:
    """An additional, separately-searchable angle on the same signal. A theme like
    land-creatures has genuinely distinct buckets — be the land-creatures (manlands),
    reward them (payoffs), turn lands into creatures (animators) — each needing its
    own precise classifier, so one signal fans out into several explorable avenues.

    ``serve`` is the sub-avenue's precise classifier, and its candidate page
    (``signal_specs.theme_page``); ``search`` is the page's override, as on
    :class:`SignalSpec`."""

    label: str
    avenue: str
    serve: Serve
    search: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SignalSpec:
    """A theme: its label, its avenue blurb, the ``serve`` that says which cards
    feed it (CR-grounded: type / keyword / stat / the lanes' idents / oracle),
    and its sub-avenues.

    The theme's candidate page derives from its serve
    (``signal_specs.theme_page``): the cards the serve admits. ``search`` is the
    page's override, a ``card_search`` kwargs fragment — a tribe's or a source
    type's ``card_type``, a preset, a name — that pages by its own fetch (the
    tribe's members, not the generic tribal support its serve also admits); a
    mana-value band beside nothing else narrows the serve's page. Empty for
    most themes, and never an oracle pattern."""

    label: str
    avenue: str
    serve: Serve
    extras: tuple[SubAvenue, ...] = ()
    search: dict = field(default_factory=dict)


def _spec(
    label: str,
    avenue: str,
    serve: str | None,
    extras: tuple[SubAvenue, ...] = (),
    *,
    search: dict | None = None,
    serve_types: tuple[str, ...] = (),
    serve_keywords: tuple[str, ...] = (),
    serve_cmc_min: float | None = None,
    serve_cmc_max: float | None = None,
    serve_min_devotion: int | None = None,
    serve_produces_mana: bool = False,
    serve_power_min: int | None = None,
    serve_toughness_min: int | None = None,
    serve_toughness_over_power: bool = False,
    serve_keyword_count_min: int | None = None,
    serve_vanilla: bool = False,
    serve_self_recur: frozenset[str] = frozenset(),
    serve_mana_cost: str | None = None,
    serve_idents: frozenset[str] = frozenset(),
    serve_not: str | None = None,
    serve_lands_feed: bool = False,
    serve_types_colorless: bool = False,
) -> SignalSpec:
    return SignalSpec(
        label=label,
        avenue=avenue,
        search=search or {},
        serve=Serve(
            oracle=re.compile(serve, _IC) if serve else None,
            types=frozenset(t.lower() for t in serve_types),
            keywords=frozenset(k.lower() for k in serve_keywords),
            cmc_min=serve_cmc_min,
            cmc_max=serve_cmc_max,
            min_devotion=serve_min_devotion,
            produces_mana=serve_produces_mana,
            power_min=serve_power_min,
            toughness_min=serve_toughness_min,
            toughness_over_power=serve_toughness_over_power,
            keyword_count_min=serve_keyword_count_min,
            vanilla=serve_vanilla,
            self_recur=serve_self_recur,
            mana_cost=re.compile(serve_mana_cost, _IC) if serve_mana_cost else None,
            signal_idents=serve_idents,
            not_oracle=re.compile(serve_not, _IC) if serve_not else None,
            lands_feed=serve_lands_feed,
            types_colorless=serve_types_colorless,
        ),
        extras=tuple(extras),
    )


_SLINGER_TYPES = ("instant", "sorcery")
_SLINGER_KEYWORDS = ("prowess",)
# Spellslinger and magecraft are ONE archetype (CR 207.2c: magecraft = "whenever you
# cast or copy an instant or sorcery spell" — the same cast trigger as prowess/spell-
# cast). Defined once and bound to BOTH the spellcast_matters and magecraft_matters
# keys, so a commander that fires both detectors renders a single "Spellslinger" avenue
# (the render layer dedupes by label) instead of two near-identical lanes (Phase C).
# Pillowfort: make attacking YOU costly/limited (Ghostly Prison, Propaganda, Sphere of
# Safety, Crawlspace). Attached ONLY to the archetypes whose pillowfort SYNERGY (top-20
# pooled, as % of archetype) clears the ~4% background floor (Dan: gate on synergy, not
# raw inclusion): Monarch (86%), Goad/politics (44%), Superfriends (24%), Damage-
# prevention/fog (23%). Dropped after the synergy check: card-advantage / activated /
# voltron / spellslinger (all ~2-6%, at the floor — their big raw counts were SIZE),
# Initiative (0% — it's an aggressive race-the-dungeon mechanic), and counterspell-
# control (0% on both synergy and inclusion). Tallying high-pillowfort activated/combat
# commanders found NO coherent sub-archetype to rescue them (they mostly co-open
# goad/fog), so no combination predicate is needed here. Search and serve both ride
# the ``pillowfort`` key (the ``pillowfort`` preset), the same fact the top-level
# ("pillowfort", "you") spec and ``roles.protects`` read. One ident, shared with
# that spec (data_4), so the two serves can't drift.
_PILLOWFORT_IDENTS = frozenset({"pillowfort|you|"})
_PILLOWFORT_EXTRA = SubAvenue(
    "Pillowfort",
    "taxes and limits that make attacking you costly (Ghostly Prison, Propaganda, "
    "Sphere of Safety, Crawlspace)",
    serve=Serve(signal_idents=_PILLOWFORT_IDENTS),
    search={"preset_names": ("pillowfort",)},
)
# ADR-0036/0037 Stage 5 #62: a GENERIC (any-permanent) counter doubler ALSO doubles
# LOYALTY counters — a real hook, CR 306.6 (loyalty counters are counters, CR 122.1)
# — but it is a DECK-level archetype ADJACENCY, not a card-literal planeswalker fact
# (a +1/+1-counter deck runs Doubling Season too), so it rides the SERVE layer as a
# SubAvenue, never the ``superfriends_matters`` lane's strict membership (ADR-0034:
# membership is what a card LITERALLY does). The counter_doubling LANE already
# credits ``superfriends_matters`` membership when a doubler explicitly NAMES
# "planeswalker" (Lae'zel, Vlaakith's Champion — the existing ``_superfriends_typed_
# ref`` typed-filter arm) — that boundary is precise and stays untouched.
#
# The lane's ``loyalty`` subject: a doubler of every counter kind over permanents
# a planeswalker is among (Doubling Season, Vorinclex, Gilder Bairn, Aetheric
# Amplifier, Lae'zel, Innkeeper's Talent's Level 3). One limited to a kind (Winding
# Constrictor's +1/+1) or to creatures stays out.
_LOYALTY_DOUBLER_EXTRA = SubAvenue(
    "Loyalty doubling",
    "generic (any-permanent) counter doublers, which also double loyalty counters",
    serve=Serve(signal_idents=frozenset({"counter_doubling|you|loyalty"})),
)
# Damage-soak payoffs for a damage-PREVENTION commander (Oriss "{T}: prevent all damage
# to target creature"): a wall that blocks any number of attackers (block the whole
# team, then prevent its damage — extra_blockers' ``any`` subject) or a
# redirect-to-one-body soak (Palisade Giant / Pariah, then prevent that body's damage —
# the damage_redirect lane, CR 614.9) converts prevention into a hard lock. A redirect
# of an opponent's creature's damage onto its controller (Treacherous Link) shields
# nothing of yours.
_DAMAGE_SOAK_EXTRA = SubAvenue(
    "Soak blockers",
    "creatures that block any number of attackers or soak all damage onto one body",
    serve=Serve(
        signal_idents=frozenset({"damage_redirect|you|", "extra_blockers|you|any"})
    ),
)
# Cheap unblockable creatures (Vnwxt speed deck): CHEAP "can't be blocked" bodies
# connect early and reliably, so an opponent loses life every turn (advancing speed)
# — evasion_self's ``unblockable`` subject, ANDed with cmc_max so it's the cheap
# evasion package. Landwalk, protection, "except by" and "as long as" evasion is
# conditional: it doesn't connect every turn.
_CHEAP_EVASION_EXTRA = SubAvenue(
    "Cheap unblockable",
    "cheap unblockable creatures that connect every turn to advance speed",
    serve=Serve(
        all_of=(
            Serve(signal_idents=frozenset({"evasion_self|you|unblockable"})),
            Serve(cmc_max=2),
        ),
    ),
    search={"cmc_max": 2},
)
# Force-the-attack: effects that make ALL / your opponents' creatures attack each combat
# (Goblin Diplomats, War's Toll, Warmonger Hellkite, Disrupt Decorum) — they feed a
# "rewards being attacked / any-player attack" payoff (Kazuul): goad, and
# forced_attack's ``others`` subject. The self forced-attack drawback ("this creature
# attacks each combat if able" — Juggernaut) and a push on only your own creatures
# (Goblin Rabblemaster) are none.
_FORCE_ATTACK_EXTRA = SubAvenue(
    "Force the attack",
    "effects that make all (or your opponents') creatures attack, feeding goad / "
    "rewards-for-being-attacked payoffs (Goblin Diplomats, War's Toll, goad)",
    serve=Serve(
        signal_idents=frozenset({"goad_makers|opponents|", "forced_attack|any|others"})
    ),
)
_SPELLSLINGER_SPEC = _spec(
    "Spellslinger",
    "cheap instants/sorceries plus magecraft/prowess payoffs to chain casts",
    None,
    # Serve rides the lanes: spell-cast triggers (instant/sorcery, noncreature,
    # second spell), magecraft, and the spell-type cost reducers. Remainder: "first
    # spell during each opponent's turn" flash adjacency, first-spell-each-turn,
    # Prismari's granted storm, and Ral's emblem (a phase gap).
    serve_idents=frozenset(
        {
            "spellcast_matters|you|instant_sorcery",
            "spellcast_matters|you|noncreature",
            "spellcast_matters|you|second_spell",
            "magecraft_matters|you|",
            "cost_reduction|you|instant_sorcery",
            "cost_reduction|you|noncreature",
        }
    ),
    serve_types=_SLINGER_TYPES,
    serve_keywords=_SLINGER_KEYWORDS,
    extras=(
        SubAvenue(
            "Cheap instants (fuel)",
            "cheap instants to chain casts and trigger your payoffs",
            serve=Serve(types=frozenset({"instant"})),
            search={"card_type": "Instant", "cmc_max": 3},
        ),
        SubAvenue(
            "Cheap sorceries (fuel)",
            "cheap sorceries to chain casts and trigger your payoffs",
            serve=Serve(types=frozenset({"sorcery"})),
            search={"card_type": "Sorcery", "cmc_max": 3},
        ),
    ),
)


# ── EDHREC-audit sub-avenues shared by the flood/token specs ──────────────────
# Creature/permanent-ETB PAYOFFS (CR 603.6a: enters triggers): a flood or aristocrats
# commander runs Impact Tremors / Purphoros / Corpse Knight — a trigger on a creature of
# yours entering that burns or drains — which the token-MAKER serves never surface: an
# enters payoff (creature_etb, typed_enters_punish — your artifacts or a tribe entering
# burns the table — tribal_etb_multi) on a card that deals damage or drains. A value
# enters payoff (Soul Warden's life) and an opponent's creature entering (Blood Seeker)
# are none. The burn or drain must ride the enters trigger itself (creature_etb's
# ``punish`` subject; typed_enters_punish for your artifacts or a tribe entering), not
# sit elsewhere on the card.
_ETB_PAYOFF_EXTRA = SubAvenue(
    "Creature-ETB payoffs",
    "permanents that punish each creature entering — damage, drain, or power-based "
    "(Impact Tremors / Purphoros)",
    serve=Serve(
        signal_idents=frozenset({"creature_etb|you|punish", "typed_enters_punish|you|"})
    ),
)


def _sub_avenue_spec(sub: SubAvenue) -> SignalSpec:
    """A page-only key's spec: the sub-avenue it serves."""
    return SignalSpec(label=sub.label, avenue=sub.avenue, serve=sub.serve)


# The crippled big bodies an ability strip (Abigale) or an enlist creature (Aradesh)
# makes use of: self_drawback's subjects — a combat restriction, a self-shrink,
# cumulative upkeep, an enters cost, or a harm to their controller — ANDed with a power
# floor so it serves BIG bodies, not small drawback ones.
_CRIPPLED_IDENTS: frozenset[str] = frozenset(
    {"self_drawback|you|restriction", "self_drawback|you|harm"}
)
_CRIPPLED_BIG_BODIES = Serve(
    all_of=(
        Serve(signal_idents=_CRIPPLED_IDENTS),
        Serve(power_min=5),
    )
)
# Enlist fodder (Aradesh): a big creature that stays back (a crippling drawback keeps it
# from attacking) is ideal to TAP for enlist — its full power is added with no downside.
_ENLIST_FODDER_EXTRA = SubAvenue(
    "Enlist fodder",
    "big stay-back creatures to tap for their power (their drawback stops them "
    "attacking anyway)",
    serve=_CRIPPLED_BIG_BODIES,
)
# Token DOUBLERS (CR 614.1a: a replacement effect): a token-flood commander doubles
# output with Doubling Season / Parallel Lives / Mondrak — the lane's increase
# replacements over your token creation, one an effect sets up for a turn included
# (Kaya, Geist Hunter's -2).
_TOKEN_DOUBLER_EXTRA = SubAvenue(
    "Token doublers",
    "replacement effects that double your token output (Doubling Season / Parallel "
    "Lives / Mondrak)",
    serve=Serve(signal_idents=frozenset({"token_doubling|you|"})),
)
# Go-wide anthems: "creatures you control get +1/+1" (Glorious Anthem), "creature
# tokens you control get …" (Intangible Virtue) and the one-shot team pump ("Creatures
# you control get +1/+0 until end of turn" — Banners Raised, team_buff's ``pump``) —
# anthem_static over the whole team and every team_buff. A single-target pump needn't
# hit your team, and a tribe's lord (Goblin King) pumps one tribe. A token / go-wide
# deck's tokens ARE creatures, so creature anthems pump them.
_GOWIDE_ANTHEM_EXTRA = SubAvenue(
    "Go-wide anthems",
    "team anthems that pump every creature/token you control (Glorious Anthem, Dictate "
    "of Heliod, Intangible Virtue)",
    serve=Serve(signal_idents=frozenset({"anthem_static|you|", "team_buff|you|*"})),
)
# Token-aristocrats drain: payoffs that fire on TOKEN creation / a token leaving and
# bleed the table (Mirkwood Bats, Nadier's Nightblade, Sanguine Brushstroke's Blood
# tokens) — tokens_matter's ``drain`` subject. A token-flood commander triggers these
# just by making tokens, so it wants them even without a sac outlet. Token-SPECIFIC
# trigger (not the generic "whenever a creature dies" Blood Artist, which needs deaths
# and is already served by the death/aristocrats lanes), and never a made token's own
# leaves trigger (Kaito, Dancing Shadow's Drone).
_TOKEN_ARISTOCRAT_EXTRA = SubAvenue(
    "Token-aristocrats drain",
    "payoffs that bleed the table whenever you make or lose a token (Mirkwood Bats, "
    "Nadier's Nightblade)",
    serve=Serve(signal_idents=frozenset({"tokens_matter|you|drain"})),
)
# MASS token makers — "create TWO/X creature tokens at once" (Battle Screech, Grand
# Crescendo, Secure the Wastes, Champions from Beyond): the mass_token_makers lane, one
# token effect making two or more creature tokens of yours, or a number the board or a
# choice decides. The go-wide BUILD-AROUND subset, distinct from the generic
# single-token makers the tokens_matter serve deliberately excludes: a single-maker is
# generically good (every deck runs a few), but "create X tokens in one card" is
# archetype-unique to go-wide.
_GOWIDE_MAKER_EXTRA = SubAvenue(
    "Mass token makers",
    "cards that create two or more creature tokens at once to flood the board "
    "(Battle Screech, Secure the Wastes, Grand Crescendo)",
    serve=Serve(signal_idents=frozenset({"mass_token_makers|you|"})),
)
# Protect the wide board: team-wide indestructible / hexproof / protection / shroud
# (Heroic Intervention, Rootborn Defenses, Boros Charm, Flawless Maneuver): a go-wide
# deck's answer to a board wipe — the board_protection lane's per-keyword team
# subjects. Distinct from the voltron SINGLE-threat protect ("target creature gains
# hexproof").
_TEAM_PROTECT_EXTRA = SubAvenue(
    "Protect the wide board",
    "team-wide indestructible / protection to survive a wrath (Heroic Intervention, "
    "Rootborn Defenses, Flawless Maneuver)",
    serve=Serve(
        signal_idents=frozenset(
            f"board_protection|you|{kw}"
            for kw in ("indestructible", "hexproof", "protection", "shroud")
        )
    ),
)
# The creature-token makers as the lanes read them: every token_maker subject
# (token_maker reads amass's Army, endure's Spirit and populate's copy through
# ``crosswalk.keyword_token_creations``) plus amass_makers, whose keyword fallback
# keeps the amass clauses phase drops (Commence the Endgame, Fall of Cair Andros).
_TOKEN_MAKER_IDENTS: frozenset[str] = frozenset(
    {"token_maker|you|*", "amass_makers|you|"}
)
# Raw creature-token MAKERS — fuel for a token-COPY commander (Esix turns each token
# she'd create into a copy of a chosen creature, so the more tokens she'd have made,
# the more copies): the lanes' creature-token makers (Hornet Queen / Avenger of
# Zendikar / Deep Forest Hermit). A gift token an opponent creates is theirs.
_TOKEN_MAKER_EXTRA = SubAvenue(
    "Token makers",
    "creature-token makers whose tokens become copies (Hornet Queen / Avenger of "
    "Zendikar / Deep Forest Hermit)",
    serve=Serve(signal_idents=_TOKEN_MAKER_IDENTS),
)
# Flicker enablers (CR 603.6a) for a repeated-ETB commander — re-use your own ETBs:
# the blink lane's exile-and-return of a permanent you control.
_FLICKER_EXTRA = SubAvenue(
    "Blink / flicker",
    "exile-and-return your own ETB creatures to re-use their enter triggers "
    "(Ephemerate / Cloudshift / Conjurer's Closet)",
    serve=Serve(signal_idents=frozenset({"blink_flicker|you|enabler"})),
    search={"preset_names": ("blink",)},
)
# Dies-recursion is a DISTINCT mechanic from flicker (CR: blink exiles to the exile
# zone, 400.1; dies puts to the graveyard, 700.4 — different zones, 603.6c). Both
# re-fire an ETB by making the creature leave and return, so an ETB-reuse / LTB
# commander wants BOTH — but as SEPARATE avenues, never lumped into the flicker serve.
# The dies_recursion lane: dies-return grants, undying / persist, earthbend's return.
_DIES_RECURSION_EXTRA = SubAvenue(
    "Dies-recursion",
    "creatures that come back when they die — re-fire enter triggers via death "
    "(Feign Death / Supernatural Stamina / undying / persist)",
    serve=Serve(signal_idents=frozenset({"dies_recursion|you|"})),
)
# Sacrifice OUTLETS (Viscera Seer / Ashnod's Altar / Carrion Feeder), to kill a
# self-death-payoff commander on demand: the lane's you-sacrifice outlets.
_SAC_OUTLET_EXTRA = SubAvenue(
    "Sacrifice outlets",
    "free/cheap activated sac outlets to kill your commander on demand and re-fire "
    "its death trigger (Viscera Seer / Ashnod's Altar / Carrion Feeder)",
    serve=Serve(signal_idents=frozenset({"sacrifice_outlets|you|"})),
)
#: A permanent you control returned to your hand to recast: permanent_recast's
#: ``replay`` subject (both self-bounce sub-avenues serve it).
_REPLAY_IDENTS: frozenset[str] = frozenset({"permanent_recast|you|replay"})
# Self-bounce recast engines (Whitemane Lion / Kor Skyfisher / Stonecloaker, Mistbreath
# Elder's upkeep return): a permanent you control returned to your hand to recast,
# re-firing both the creature-cast trigger and the enter trigger.
_SELF_BOUNCE_EXTRA = SubAvenue(
    "Self-bounce recast engines",
    "creatures that return your own permanent on enter — recast to re-fire enter and "
    "cast triggers (Whitemane Lion / Kor Skyfisher / Stonecloaker)",
    serve=Serve(signal_idents=_REPLAY_IDENTS),
)
# Self-SACRIFICING creatures (Spore Frog / Caustic Caterpillar / Selfless Spirit): the
# sac is the activation cost, so one use both yields a repeatable effect AND drops the
# creature into the graveyard — ideal fuel for a creature-recursion engine (loop: recur
# it, recast, sac again; no separate sac outlet). The lane's ``self`` subject: a
# creature whose own ability, or one a grant it falls under gives it (Basal Sliver),
# sacrifices itself.
_SELF_SAC_CREATURE_EXTRA = SubAvenue(
    "Self-sacrificing creatures",
    "creatures that sacrifice themselves for value — recur and re-sac them every turn "
    "(Spore Frog / Caustic Caterpillar / Sakura-Tribe Elder)",
    serve=Serve(signal_idents=frozenset({"sacrifice_outlets|you|self"})),
)
# Blink wants more than flicker effects: the ETB-VALUE creatures it re-flickers (CR
# 603.6a: enters triggers) and the ETB-trigger DOUBLERS that multiply every enter
# (Panharmonicon / Yarok). The self_etb_payload lane: a card's own enters trigger with
# a value payload (an edict, exploit and squad included; one a grant it falls under
# gives it — Harmonic Sliver). Another permanent entering is a payoff, not this; a
# bounce land's return and an opponent's gift are drawbacks.
_ETB_VALUE_EXTRA = SubAvenue(
    "ETB-value creatures",
    "creatures with strong enter triggers worth flickering "
    "(Mulldrifter / Eternal Witness / Reflector Mage)",
    serve=Serve(signal_idents=frozenset({"self_etb_payload|you|"})),
)
# The trigger doublers whose cause is an object entering (Panharmonicon, Yarok):
# trigger_doubling's ``enters`` subject. A death or attack doubler (Teysa Karlov,
# Isshin) doubles no enter trigger.
_ETB_DOUBLER_EXTRA = SubAvenue(
    "ETB-trigger doublers",
    "permanents that double every enter trigger (Panharmonicon / Yarok)",
    serve=Serve(signal_idents=frozenset({"trigger_doubling|you|enters"})),
)
# Trigger COPIERS (Strionic Resonator / Lithoform Engine): copy a triggered ability
# (CR 707.10) — a payoff for any trigger-heavy deck, ETB triggers included:
# ability_copy's ``triggered`` subject. Distinct from the Panharmonicon doubler (a
# static that makes entering triggers fire twice) and from an activated-only copier
# (Rings of Brighthearth).
_TRIGGER_COPY_EXTRA = SubAvenue(
    "Trigger copiers",
    "copy a triggered ability you control (Strionic Resonator / Lithoform Engine)",
    serve=Serve(signal_idents=frozenset({"ability_copy|you|triggered"})),
)
# Self-recurring fodder: aristocrats wants creatures that bring THEMSELVES back from the
# graveyard (Bloodghast / Gravecrawler) — never Sun-Titan-style reanimation of OTHER
# cards. Search and serve read one predicate: the ``self-recurring-fodder`` preset is
# ``lanes.card_advantage.comes_back_from_graveyard`` over the fodder routes.
_SELF_RECUR_EXTRA = SubAvenue(
    "Self-recurring fodder",
    "creatures that bring themselves back from the graveyard — free, repeatable sac "
    "fodder (Bloodghast / Gravecrawler / Reassembling Skeleton)",
    serve=Serve(self_recur=FODDER_SELF_RETURNS),
    search={"preset_names": ("self-recurring-fodder",)},
)
# Aristocrats DRAIN payoff (CR 700.4 "dies"): the heart of the archetype — a permanent
# that pays off creatures dying with a drain, life swing, or token (Blood Artist /
# Zulaport Cutthroat / Cruel Celebrant / Pitiless Plunderer): the death_matters lane,
# whoever's creature it watches (an opponent's dies to your wipe too — Massacre
# Wurm). A token's own death trigger is the token's (Sedgemoor Witch's Pests).
# Shared by the death and sacrifice lanes (a sac-outlet commander opens
# sacrifice_outlets, not death_matters, but wants the same drain payoffs).
#: The death_matters payoffs, whoever's creature they watch.
_DEATH_PAYOFF_IDENTS: frozenset[str] = frozenset(
    {"death_matters|you|", "death_matters|any|", "death_matters|opponents|"}
)
_DEATH_DRAIN_EXTRA = SubAvenue(
    "Death payoffs / drain",
    "payoffs that punish creatures dying — drain, life swings, and tokens "
    "(Blood Artist / Zulaport Cutthroat / Pitiless Plunderer)",
    serve=Serve(signal_idents=_DEATH_PAYOFF_IDENTS),
)
# Board wipes are an aristocrats payoff: a mass-death event fires every dies-trigger and
# drain at once (Wrath of God + Blood Artist) — mass_removal's ``creature`` subject, a
# sweep whose creatures die. An exile sweep, a land or Aura sweep, and a one-type sweep
# (Tivadar's Crusade) are no board's mass death.
_BOARD_WIPE_EXTRA = SubAvenue(
    "Board wipes (mass death)",
    "sweepers that turn a board into a mass-death trigger for your aristocrats payoffs",
    serve=Serve(signal_idents=frozenset({"mass_removal|you|creature"})),
    search={"preset_names": ("board-wipe",)},
)
_LANDS_FROM_GRAVE_EXTRA = SubAvenue(
    "Lands from your graveyard",
    "recursion that replays sacrificed/milled lands for repeat landfall "
    "(Crucible of Worlds / Ramunap Excavator / Splendid Reclamation)",
    serve=Serve(signal_idents=frozenset({"permanent_recast|you|land"})),
)
# Deathtouch-granting gear (CR 702.2b): with a repeatable pinger, deathtouch + 1 damage
# kills anything — an Equipment's or Aura's standing deathtouch grant. One that grants
# it only as the creature attacks or blocks (Hunter's Axe, Wand of Orcus) misses a
# pinger's tap.
_DEATHTOUCH_GEAR_EXTRA = SubAvenue(
    "Deathtouch enablers",
    "Equipment/Auras that grant deathtouch so each ping kills (Basilisk Collar)",
    serve=Serve(signal_idents=frozenset({"aura_equip_kw_grant|you|deathtouch"})),
)
# Player/opponent-directed noncombat burn — the genuine payoff space for a damage
# DOUBLER (Solphim, Torbran): every source that deals damage to a player or opponent
# is doubled. The direct_damage lane: burn that reaches a player, "X" and "equal to"
# amounts included (Heartless Hidetsugu, Price of Progress); a creature-only sweeper
# (Pyroclasm, Languish) is none, and a damage doubler deals none itself.
_NONCOMBAT_BURN_EXTRA = SubAvenue(
    "Player-directed burn",
    "noncombat damage aimed at players/opponents — doubled by your damage doubler",
    serve=Serve(signal_idents=frozenset({"direct_damage|you|"})),
)
# Proliferate for any counter commander — adds another of EVERY counter: the
# keyword and the lane's makers (a granted "[0]: Proliferate" — Ichormoon Gauntlet).
# A "whenever you proliferate" payoff makes none.
_PROLIFERATE_EXTRA = SubAvenue(
    "Proliferate",
    "proliferate sources that add another counter of every kind you already have",
    serve=Serve(
        keywords=frozenset({"proliferate"}),
        signal_idents=frozenset({"proliferate_makers|you|"}),
    ),
    search={"preset_names": ("proliferate",)},
)
# The +1/+1 counter package as the lanes read it:
# the cards that put +1/+1 counters (plus_one_makers reads the keyword actions —
# bolster, adapt, explore, endure, awaken … — through
# ``crosswalk.keyword_counter_placements``; the amass / incubate / connive keys
# add the few whose clause phase drops), the payoffs, the board-wide spreaders and
# the counter doublers. What the regex served that this doesn't is a documented
# exclusion: a creature returned or blinked "with a +1/+1 counter on it", tribute
# (the opponent chooses), sunburst / riot grants, and the "no +1/+1 counter"
# negations — see docs/plans/serve-idents-and-avenue-support.md §2.
_PLUS_ONE_PLACERS: frozenset[str] = frozenset(
    {
        "plus_one_makers|you|",
        "plus_one_matters|you|",
        "counter_distribute|you|",
        "counter_doubling|you|",
        "amass_makers|you|",
        "incubate_makers|you|",
        "connive_makers|you|",
    }
)
# The +1/+1 avenue itself also serves proliferate (its avenue text names it).
_PLUS_ONE_SERVE_IDENTS: frozenset[str] = _PLUS_ONE_PLACERS | {"proliferate_makers|you|"}
# Amass and incubate serve the +1/+1 package (_PLUS_ONE_PLACERS) without
# proliferate (their regexes never named it); amass adds the Army payoffs.
_AMASS_SERVE_IDENTS: frozenset[str] = _PLUS_ONE_PLACERS | {"type_matters|you|Army"}
# Counter DOUBLERS / amplifiers: the universal payoff for ANY counters commander —
# Doubling Season, Hardened Scales, Corpsejack, Branching Evolution, Vorinclex, and the
# one-shot doublers (Vorel, Gilder Bairn, Evolution Vat's granted ability). Shared
# across every counter lane below, since a counters commander can open any of them.
# Devour's "twice that many +1/+1 counters" and an energy or rad doubler are none.
_COUNTER_DOUBLER_EXTRA = SubAvenue(
    "Counter doublers",
    "replacement effects that multiply every counter you place "
    "(Doubling Season / Hardened Scales / Corpsejack Menace / Vorinclex)",
    serve=Serve(signal_idents=frozenset({"counter_doubling|you|"})),
)
# +1/+1 counter PLACEMENT support: spells/abilities that drop +1/+1 counters on your
# creatures (the fuel a self-growth / counters commander wants alongside the
# doublers) — the +1/+1 package the lanes read. Tribute's counters are an opponent's
# choice.
_COUNTER_PLACE_EXTRA = SubAvenue(
    "Counter placement",
    "ways to drop more +1/+1 counters on your creatures (Hardened Scales fuel)",
    serve=Serve(signal_idents=_PLUS_ONE_PLACERS),
)
# Keyword counters (flying/trample/deathtouch/lifelink/indestructible/…) are counters
# too: a counters commander wants them for proliferate fuel and voltron protection, even
# with no +1/+1 — the keyword_counter lane.
_KEYWORD_COUNTER_EXTRA = SubAvenue(
    "Keyword counters",
    "cards that place keyword counters (flying / trample / deathtouch / lifelink / …) "
    "— counter synergy and proliferate fuel",
    serve=Serve(signal_idents=frozenset({"keyword_counter|any|"})),
)
# The shared +1/+1-counter package every counter-adjacent lane wants: SOURCES that
# place counters (Forgotten Ancient), DOUBLERS (Hardened Scales / Doubling Season),
# keyword-counter placers, and proliferate. The sweep fragments counter themes into
# many lanes (placement-triggers / keyword / doubling / movement / distribution); this
# package unifies what they all surface so a counters commander sees the whole package
# no matter which lane opened.
# +1/+1-counter KEYWORD creatures: the counter mechanic is in reminder text (stripped),
# so the oracle-based serves miss them — but a counters deck wants every Undying / Graft
# / Riot / Bloodthirst / Fabricate body (CR 702.x keyword abilities). Credit by the
# keyword itself.
_COUNTER_KEYWORDS = frozenset(
    {
        "undying",
        "persist",
        "graft",
        "riot",
        "bloodthirst",
        "fabricate",
        "sunburst",
        "tribute",
        "unleash",
        "ravenous",
        "reinforce",
        "scavenge",
        "mentor",
        "training",
        "modular",
        "evolve",
        "outlast",
        "adapt",
        "bolster",
        "renown",
        "dethrone",
        "devour",
    }
)
_COUNTER_KEYWORD_EXTRA = SubAvenue(
    "Counter-keyword creatures",
    "creatures whose +1/+1-counter mechanic is a keyword (Undying / Graft / Riot / "
    "Bloodthirst / Fabricate) — staples a counters deck wants",
    serve=Serve(keywords=_COUNTER_KEYWORDS),
)
# Counter RESILIENCE: save or relocate YOUR counters when a creature leaves, so a wrath
# (or the creature's own death) doesn't waste the investment (The Ozolith, Resourceful
# Defense, Fate Transfer): the counter_move lane. Counter removal (Aether Snap, Vampire
# Hexmage) is the opposite. A self-growing-counters commander (Wolverine) wants to
# protect its counters.
_COUNTER_RESILIENCE_EXTRA = SubAvenue(
    "Counter resilience",
    "save or relocate your counters when a creature leaves (The Ozolith)",
    serve=Serve(signal_idents=frozenset({"counter_move|you|"})),
)
_COUNTERS_PACKAGE = (
    _COUNTER_PLACE_EXTRA,
    _COUNTER_DOUBLER_EXTRA,
    _KEYWORD_COUNTER_EXTRA,
    _COUNTER_KEYWORD_EXTRA,
    _PROLIFERATE_EXTRA,
    _COUNTER_RESILIENCE_EXTRA,
)
# Discard-PUNISH payoffs (CR 701.9 discard): reward forcing opponents to discard —
# opponent_discard's ``punish`` subject, a trigger on an opponent's discard.
_DISCARD_PUNISH_EXTRA = SubAvenue(
    "Discard punishers",
    "payoffs that trigger when an opponent discards (Megrim / Liliana's Caress / "
    "Waste Not)",
    serve=Serve(signal_idents=frozenset({"opponent_discard|opponents|punish"})),
)
# Empty-hand (hellbent) OPPONENT punishers: the 8-Rack package a hand-attack deck wants
# once it strips opponents' hands (The Rack, Wheel of Torture, Shrieking Affliction,
# Rackling, Guul Draz Specter) — opponent_discard's ``empty_hand`` subject: a condition
# on an opponent's small hand, or damage scaled by "N minus the cards in their hand".
# A SELF-hellbent payoff ("YOU have no cards in hand") and a refill of the hellbent
# player's hand (Ghirapur Orrery) never qualify.
_HELLBENT_PUNISH_EXTRA = SubAvenue(
    "Empty-hand punishers",
    "8-Rack payoffs that punish an opponent's empty hand (The Rack, Wheel of Torture, "
    "Shrieking Affliction)",
    serve=Serve(signal_idents=frozenset({"opponent_discard|opponents|empty_hand"})),
)


# Reanimator PAYOFF (Celes, Rune Knight): a creature ENTERING from a graveyard
# (reanimation) or being CAST from one (escape/disturb) fires the payoff. (1)
# Reanimation effects that return a creature card from a graveyard to the battlefield
# — the reanimator spec's lanes (a creature, from your hand or graveyard included —
# Swift Warkite) and permanent_recast's ``reanimate`` (Sun Titan). One that puts the
# creature under an opponent's control (Immortal Obligation) is theirs.
_REANIMATION_EXTRA = SubAvenue(
    "Reanimation",
    "return creatures from your graveyard to the battlefield to rebuild after a wipe "
    "(Breath of Life / Resurrection)",
    serve=Serve(
        signal_idents=frozenset(
            {
                "reanimator|you|",
                "creature_recursion|you|battlefield",
                "permanent_recast|you|reanimate",
            }
        )
    ),
)
# Board protection: GRANT the whole team indestructible (Selfless Spirit, Heroic
# Intervention, Akroma's Will, Flawless Maneuver, Avacyn, Darksteel Forge) — the
# board_protection lane's ``indestructible`` team subject. Distinct from an
# indestructible CREATURE that merely survives a wipe (the lane's serve_keywords already
# credits those) — a granter lets you wrath one-sided and keep your board.
_BOARD_PROTECTION_EXTRA = SubAvenue(
    "Board protection",
    "give your whole board indestructible so you can wrath one-sided "
    "(Selfless Spirit / Heroic Intervention / Flawless Maneuver)",
    serve=Serve(signal_idents=frozenset({"board_protection|you|indestructible"})),
)
# Self-copy effects for a legend-rule-off / copy commander (Brothers Yamazaki): make
# copies of your own creatures (Helm of the Host / Blade of Selves / Mirror Box /
# Spark Double) — the copy lanes, myriad and an embalm grant, and a copier of creature
# spells (Double Major; spell_copy_makers' ``creature`` subject). A copy another
# player gets (Life of the Party) is theirs; a copier of any spell is a spell copier.
_COPY_EXTRA = SubAvenue(
    "Copy effects",
    "make token copies of your creatures (Helm of the Host / Blade of Selves / "
    "Mirror Box / Spark Double)",
    serve=Serve(
        signal_idents=frozenset(
            {
                "token_copy_makers|you|*",
                "clone_makers|you|",
                "copy_permanent|you|",
                "myriad_grant|you|",
                "keyword_grant_target|you|embalm",
                "spell_copy_makers|you|creature",
            }
        )
    ),
)
# High-value clone TARGETS: a creature with a strong self-DEATH trigger is worth
# copying — the (nonlegendary) token re-fires the death payoff when it dies (Kokusho
# drains, Keiga steals, Junji, The Scarab God): the self_death_payoff lane, AND mana
# value >= 5 so a cmc-1 dies-trigger body — which is no clone bomb — stays out. A
# dies-return (undying, persist, "return it to the battlefield") brings back no token
# (CR 111.8), and a token maker's tokens carry their own death triggers.
_CLONE_DIES_VALUE_EXTRA = SubAvenue(
    "High-value death triggers to copy",
    "high-mana-value creatures with a strong death trigger — clone them so the copy "
    "re-fires it on death (Kokusho, Keiga, Junji, The Scarab God)",
    serve=Serve(
        all_of=(
            Serve(signal_idents=frozenset({"self_death_payoff|you|"})),
            Serve(cmc_min=5),
        )
    ),
)
# Self-bounce (Cavern Harpy, Whitemane Lion): return YOUR creature to hand to RECAST it.
# For a recast-clone commander (The Master's Body Thief) that means copying a different/
# better creature again; for any clone deck it re-uses the copy ETB. Confirmed core for
# The Master. permanent_recast's ``replay``: a permanent you control returned to your
# hand, by an effect or a cost (web-slinging's tapped creature — CR 702.188a).
_SELF_BOUNCE_RECAST_EXTRA = SubAvenue(
    "Self-bounce (recast your clones)",
    "return your own creatures to hand to recast the clone and copy again "
    "(Cavern Harpy, Whitemane Lion)",
    serve=Serve(signal_idents=_REPLAY_IDENTS),
)
# Drawback creatures whose downside PUNISHES their controller — the donate target
# (Abyssal Persecutor "you can't win", Flesh Reaver "deals damage to you", Demonic
# Taskmaster "upkeep: sacrifice a creature"): hand them to an opponent for the downside.
# self_drawback's ``harm``: a permanent's mandatory trigger or static that hurts its
# controller. A spell (the pacts, Final Fortune) is nothing to hand over, a payoff that
# watches damage to you (Auntie Blyte) hurts no one, and a loss beside a draw (Dark
# Confidant) is card advantage.
_DRAWBACK_EXTRA = SubAvenue(
    "Drawback creatures to donate",
    "creatures whose downside hurts their controller — give them to an opponent "
    "(Abyssal Persecutor / Flesh Reaver / Demonic Taskmaster)",
    serve=Serve(signal_idents=frozenset({"self_drawback|you|harm"})),
)
# Force-feed: give opponents creatures that benefit YOU (the Hunted cycle, Forbidden
# Orchard) — a control-change/donate deck punishes its own gifts: donate_makers'
# ``token`` subject, a creature token an opponent creates. A gift (Parting Gust's
# Fish) is the opponent's promise, not your engine.
_FORCE_FEED_EXTRA = SubAvenue(
    "Force-feed creatures",
    "give opponents creatures that work for you (Forbidden Orchard, the Hunted cycle)",
    serve=Serve(signal_idents=frozenset({"donate_makers|you|token"})),
)
# Untap effects to reuse tap abilities / retrigger a tap-untap commander: the
# untap_engine lane — an untap of a permanent of yours other than the card itself,
# the enchanted creature (Freed from the Real, Pemmin's Aura), a granted "untap this"
# (Gauntlets of Light, Scuttling Sliver), "untap it" on the permanent a trigger
# watched (Amulet of Vigor), one-shot untaps (Twiddle, Cerulean Wisps). A self-untap
# (Blisterspit Gremlin, the {Q} costs), an untap of a creature you steal (Act of
# Treason) or an opponent's (Provoke), and "you may choose not to untap" are none.
_UNTAP_EXTRA = SubAvenue(
    "Untap effects",
    "untap your permanents to reuse their tap abilities or retrigger (Freed from the "
    "Real / Pemmin's Aura / Kiora's Follower)",
    serve=Serve(signal_idents=frozenset({"untap_engine|you|*", "untap_engine|each|*"})),
)
# (2) Cast-from-graveyard CREATURES recast themselves from the yard, re-firing the
# payoff each turn (CR 702.146 Disturb / Escape). The graveyard-cast umbrella preset is
# filtered to card_type Creature so the instant/sorcery flashback half (which never puts
# a creature into play) drops out; the serve credits the authoritative keywords.
_CAST_FROM_GY_EXTRA = SubAvenue(
    "Cast from your graveyard",
    "creatures with escape or disturb that recast themselves from your graveyard, "
    "re-firing the payoff each time (Woe Strider / Kroxa)",
    # Disturb by its route: the face it casts must be a creature (never Brine
    # Comber's Aura).
    serve=Serve(
        keywords=frozenset({"escape"}),
        self_recur=frozenset({"graveyard_to_stack"}),
    ),
    search={"preset_names": ("graveyard-cast",), "card_type": "Creature"},
)


def _sweep_spec_with_extras(
    key: str,
    extras: tuple[SubAvenue, ...] = (),
    *,
    serve_power_min: int | None = None,
    serve_toughness_min: int | None = None,
    serve_toughness_over_power: bool = False,
    serve_keywords: tuple[str, ...] = (),
    regex: str | None = None,
    serve_idents: frozenset[str] = frozenset(),
) -> SignalSpec:
    """Promote a mined sweep detector to a hand-spec that serves by its regex but
    fans out extra sub-avenues — used where a sweep-derived lane needs to surface
    payoffs its bare regex can't (e.g. every counter lane wants the counter
    doublers). ``serve_power_min`` / ``serve_toughness_min`` additionally credit big
    bodies (power doublers / toughness-as-power lanes want the stat-line they
    exploit); ``serve_keywords`` adds a keyword dimension. Reuses SWEEP_DETECTORS so
    the regex never drifts from the mine — UNLESS ``regex`` is given, for an
    ADR-0027-migrated key whose SWEEP_DETECTORS row is deleted (the serve keeps the
    old regex).

    ``serve_idents`` (the serve-ident pass, docs/plans/serve-idents-and-avenue-
    support.md): the serve's enabler arm is the lanes' own structural idents in
    place of the regex, and the theme pages by them too; the structured dims above
    are unaffected.
    """
    if serve_idents:
        d_regex = None
    elif regex is not None:
        d_regex = regex
    else:
        d_regex = next(x for x in SWEEP_DETECTORS if x["key"] == key)["regex"]
    label, avenue = SWEEP_LABELS[key]
    return _spec(
        label,
        avenue,
        d_regex,
        extras=extras,
        serve_power_min=serve_power_min,
        serve_toughness_min=serve_toughness_min,
        serve_toughness_over_power=serve_toughness_over_power,
        serve_keywords=serve_keywords,
        serve_idents=serve_idents,
    )


# Combat support shared by the combat lanes: gear that suits up the attacker plus the
# keyword-anthems that buff your attackers (double strike / trample / evasion). Every
# Equipment (by type: CR 301.5 — it exists to be attached to a creature), the Auras
# that pump or grant a keyword to the creature they enchant (voltron_makers' ``pump``,
# a bestow creature and an activated Aura pump included; aura_equip_kw_grant), the
# cards that make Equipment (voltron_makers' ``gear``) or attach it, an anthem or
# keyword grant to your equipped creatures ("Equipped creatures you control get +1/+1"
# — Stone Haven Outfitter; "… have indestructible" — Zamriel), and the team buffs and
# combat-keyword grants (team_buff). A shrinking Aura (Dead Weight) is removal, and an
# Equipment payoff that buffs no creature (Puresteel Paladin's equip discount, Syr
# Gwyn's draw) is a carer, not support.
_COMBAT_SUPPORT_KEYWORDS = (
    "double strike",
    "first strike",
    "trample",
    "menace",
    "deathtouch",
    "vigilance",
)
_COMBAT_SUPPORT_EXTRA = SubAvenue(
    "Combat support (gear & keyword anthems)",
    "equipment/auras and keyword-anthems that suit up and buff your attackers",
    serve=Serve(
        types=frozenset({"equipment"}),
        signal_idents=frozenset(
            {
                "voltron_makers|you|*",
                "aura_equip_kw_grant|you|*",
                "team_evasion_grant|you|*",
                "team_buff|you|",
                "team_buff|you|attackers",
                *(f"team_buff|you|{kw}" for kw in _COMBAT_SUPPORT_KEYWORDS),
            }
        ),
    ),
)
# Extra combats (Aggravated Assault, Relentless Assault, Seize the Day, Moraug): each
# added combat phase is another round of attack + combat-damage triggers, so a commander
# that rewards attacking / combat damage / a suited-up voltron threat wants them — the
# extra_combats lane.
_EXTRA_COMBAT_EXTRA = SubAvenue(
    "Extra combats",
    "additional-combat-phase enablers — another round of attack/combat-damage triggers",
    serve=Serve(signal_idents=frozenset({"extra_combats|you|"})),
)
# Symmetric group mana: a group-mana commander (Shizuko group-ramp, Yurlok mana-burn)
# wants the shared mana-doublers and mana-punishers keyed on "whenever a player taps a
# land for mana" (Mana Flare, Heartbeat of Spring, Manabarbs, Price of Glory) plus
# group ramp — every player searches for a land or makes a Treasure (Collective
# Voyage, New Frontiers, Marching Duodrone): every group_mana subject. One-sided dorks
# ("{T}: Add {G}") never match, nor a join-forces or each-player effect that hands out
# no mana (Minds Aglow's cards, Alliance of Arms' Soldiers, Elephant Resurgence).
_SYM_MANA_EXTRA = SubAvenue(
    "Symmetric mana (group ramp & mana-punishers)",
    "shared mana-doublers and mana-punishers that exploit the symmetry "
    "(Mana Flare, Heartbeat of Spring, Manabarbs, Collective Voyage)",
    serve=Serve(signal_idents=frozenset({"group_mana|each|*"})),
)
# Mana AMPLIFICATION for an unspent-mana commander (Omnath Locus of Mana, Kruphix): it
# keeps mana between steps, so it wants untap-all-lands (Bear Umbra, Wilderness
# Reclamation, Nature's Will) and mana-doublers (Mana Reflection, Mana Flare) to make
# more mana to bank — the mana_amplifier lane and its ``untap_lands`` subject. A
# one-sided dork ("{T}: Add {G}") never qualifies, nor a land-tap punisher
# (Manabarbs).
_MANA_AMP_EXTRA = SubAvenue(
    "Mana amplification (untap-lands & doublers)",
    "untap-all-lands and mana-doublers that grow the mana you keep "
    "(Bear Umbra, Wilderness Reclamation, Mana Reflection)",
    serve=Serve(
        signal_idents=frozenset(
            {"mana_amplifier|you|", "mana_amplifier|you|untap_lands"}
        )
    ),
)
# Paradox (CR 207.2c): "cast a spell from anywhere other than your hand" payoffs
# (Vega, Keeper of Secrets) — cast_from_exile's ``paradox`` subject. Shared by
# cast_from_exile AND impulse_top_play: an impulse deck casts its exiled cards, which
# IS "from anywhere other than your hand", so it fires these payoffs too. The
# cast-from-exile payoffs (Wild-Magic Sorcerer, Passionate Archaeologist, Nalfeshnee)
# are its ``payoff`` subject: a trigger on a spell cast from exile, or a keyword your
# spells cast from exile have.
_CAST_FROM_EXILE_EXTRA = SubAvenue(
    "Cast-from-exile payoffs",
    "payoffs that reward casting spells from exile (Wild-Magic Sorcerer, "
    "Passionate Archaeologist, Nalfeshnee)",
    serve=Serve(signal_idents=frozenset({"cast_from_exile|you|payoff"})),
)
_PARADOX_PAYOFF_EXTRA = SubAvenue(
    "Paradox payoffs",
    "zone-agnostic payoffs that reward casting/playing from anywhere other "
    "than your hand",
    serve=Serve(signal_idents=frozenset({"cast_from_exile|you|paradox"})),
)
# Heroic / targeting enablers: cheap spells that TARGET one of your creatures to fire
# the heroic payoff (Gods Willing, Brute Force, Defiant Strike). They must use "target"
# (CR 115.1a) and BUFF it: the pump_makers lane's ``target`` subject (a pump on one
# chosen creature) and keyword_grant_target — a keyword, a choice of keywords (Gideon
# Blackblade) or a quoted ability (Feign Death) given to a target creature. An "each
# creature" anthem doesn't target (so won't trigger heroic) and targeted REMOVAL
# ("gets -N/-N", destroy) isn't a self-buff, so both stay out.
_TARGETED_BUFF_EXTRA = SubAvenue(
    "Single-target pump / protection",
    "cheap spells that target one of your creatures to trigger heroic (Gods Willing / "
    "Brute Force / Defiant Strike)",
    serve=Serve(
        signal_idents=frozenset(
            {"keyword_grant_target|you|*", "pump_makers|you|target"}
        )
    ),
)
# Instant-speed pump (Giant Growth / Berserk) to push through extra combat damage and
# survive blocks: the pump_makers lane.
_PUMP_EXTRA = SubAvenue(
    "Combat tricks / pump",
    "instant-speed pump to push extra combat damage through and survive blocks",
    serve=Serve(signal_idents=frozenset({"pump_makers|you|"})),
)
# Damage / life-loss AMPLIFIERS — a commander that deals combat damage to opponents
# wants its damage doubled (Gratuitous Violence, Furnace of Rath, Angrath's Marauders,
# Gisela) or the resulting life loss reflected back (Wound Reflection, Fiendish Duo):
# every damage_doubling subject (a replacement that doubles it; ``repeat`` — the damage
# dealt again to the other opponents, Hydra Omnivore, Kediss; ``life_loss`` — Wound
# Reflection), the damage reflectors (Repercussion) and a double-strike grant to your
# creatures (CR 702.4b: a second combat damage step — Duelist's Heritage). A creature
# granting itself double strike doubles no one else's damage.
_DAMAGE_AMPLIFIER_EXTRA = SubAvenue(
    "Damage / life-loss amplifiers",
    "doublers that magnify the damage and life loss you push through (Gratuitous "
    "Violence, Furnace of Rath, Wound Reflection, Fiendish Duo)",
    serve=Serve(
        signal_idents=frozenset(
            {
                "damage_doubling|you|*",
                "damage_reflect|you|",
                "team_buff|you|double strike",
                "keyword_grant_target|you|double strike",
                "aura_equip_kw_grant|you|double strike",
                "all_creatures_kw_grant|any|double strike",
            }
        )
    ),
)
# Stacking cost reducers: a commander whose own text makes spells cost less (Stenn,
# Thryx, Danitha, Umori) wants to STACK more category reducers (Cloud Key, Etherium
# Sculptor, Helm of Awakening, Semblance Anvil) to go off — the cost_reduction lane
# otherwise serves only the expensive bombs that EXPLOIT the discount, not the reducers
# that compound it: every subject of the cost_reduction lane. A tax ("cost more") and a
# discount for an opponent's spells targeting the card are none.
_COST_REDUCER_EXTRA = SubAvenue(
    "Stack more cost reducers",
    "category cost reducers that compound your discount to go off (Cloud Key, Etherium "
    "Sculptor, Helm of Awakening, Baral)",
    serve=Serve(signal_idents=frozenset({"cost_reduction|you|*"})),
)
# Protecting the single suited-up threat IS the voltron support package (Mother of
# Runes, Bastion Protector, Avacyn, Vexilus Praetor are top-synergy on EDHREC for
# voltron commanders): the protection_grant lane — a shield keyword given to a creature
# or permanent of yours other than the card itself. A creature that shields only
# itself ("{U}: This creature gains shroud") protects no threat.
_VOLTRON_PROTECT_EXTRA = SubAvenue(
    "Protect the suited-up threat",
    "hexproof / protection / indestructible granters that keep your one big threat "
    "alive through removal (Mother of Runes / Bastion Protector / Avacyn)",
    serve=Serve(signal_idents=frozenset({"protection_grant|you|"})),
)
# Creature cost reducers (Goreclaw, Herald's Horn, Krosan Drover) for a creature-cast /
# ramp-into-fatties deck — they make every creature spell cheaper: cost_reduction's
# ``creature`` subject. A noncreature discount or a tax is none.
_CREATURE_COST_EXTRA = SubAvenue(
    "Creature cost reducers",
    "cards that make your creature spells cheaper so you deploy threats faster "
    "(Goreclaw)",
    serve=Serve(signal_idents=frozenset({"cost_reduction|you|creature"})),
)
# Power-as-damage payoffs: convert a big/pumped creature's power into damage (Fling,
# Chandra's Ignition, Soul's Fire): every damage_equal_power subject — to a player, and
# the bite to a creature (Bite Down, Polliwallop's twice its power) — the fights (CR
# 701.14a: each deals damage equal to its power to the other) and the granted
# "{T}: deal damage equal to its power" engines (power_tap_engine).
_POWER_FLING_EXTRA = SubAvenue(
    "Power-as-damage payoffs",
    "fling effects that turn your big creature's power into damage (Fling / Chandra's "
    "Ignition / Soul's Fire)",
    serve=Serve(
        signal_idents=frozenset(
            {"damage_equal_power|you|*", "fight_makers|you|", "power_tap_engine|you|"}
        )
    ),
)
# Force-block effects for a "becomes blocked" payoff commander (General Marhault
# Elsdragon: +3/+3 for each creature blocking the attacker). Forcing every able
# creature to block MAXES the per-blocker bonus (CR 509.1c): the lure_makers lane, and
# Provoke's single forced block.
_LURE_EXTRA = SubAvenue(
    "Force blocks (Lure)",
    "effects that force opponents' creatures to block your attacker, maxing a "
    '"becomes blocked" payoff (Lure / Nemesis Mask / Roar of Challenge)',
    serve=Serve(
        signal_idents=frozenset({"lure_makers|you|"}), keywords=frozenset({"provoke"})
    ),
)

# Wildcard tribal payoffs (task B-1): the chosen_type_matters lane's idents,
# both scopes it can emit ("you" — Door of Destinies; "each" — Urza's
# Incubator's symmetric discount). Every per-subject tribal serve carries
# these (a Sliver deck credits Herald's Horn exactly as a Goblin deck does),
# and the tribal payoff sub-avenue's serve does too — structural, so payoffs
# whose wording never says "choose a creature type" on the payoff sentence
# (Kindred Discovery) still credit.
_CHOSEN_TYPE_IDENTS = frozenset(
    {"chosen_type_matters|you|", "chosen_type_matters|each|"}
)


def _chosen_type_named_idents(subjects: tuple[str, ...]) -> frozenset[str]:
    """The chosen_type_matters idents a RESTRICTED chooser emits for *subjects*
    (Dawn-Blessed Pennant → ``chosen_type_matters|you|Goblin``): a tribe serve
    credits the wildcard ``_CHOSEN_TYPE_IDENTS`` plus its own named ones."""
    return frozenset(
        f"chosen_type_matters|{scope}|{subject}"
        for scope in ("you", "each")
        for subject in subjects
    )
