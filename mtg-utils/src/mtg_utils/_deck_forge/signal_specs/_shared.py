"""Signal specs — shared building blocks.

Serve/SubAvenue/SignalSpec dataclasses plus every builder-helper constant and
function the SPECS dict literal (split across ``data_1.py``..``data_4.py``)
consumes. Extracted from the original flat ``signal_specs.py`` (task: split
into a package) with zero logic changes. This module has no dependency on
the rest of the ``signal_specs`` package — only on ``signal_keys``,
``_sweep_detectors``, ``card_classify``, and stdlib.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mtg_utils._deck_forge._sweep_detectors import (
    DIES_RECURSION_REGEX,
    DIG_UNTIL_REGEX,
    DISCARD_OUTLET_REGEX,
    DRAW_FOR_EACH_REGEX,
    KEYWORD_COUNTER_REGEX,
    PUMP_MATTERS_REGEX,
    SWEEP_DETECTORS,
    SWEEP_LABELS,
    THEFT_MATTERS_REGEX,
    TOPDECK_SELECTION_REGEX,
)
from mtg_utils.card_classify import (
    card_pt_int,
    classifying_type_line,
    get_oracle_text,
    type_line_has,
)

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

# "Is-a" subtype hierarchies (CR 205.3g / 205.3h): every one of these subtypes IS an
# artifact / enchantment, so a card that makes or cares about one is an
# artifact-count / enchantment-count enabler. Used to widen the parent-type serves so a
# Vehicle / Equipment maker feeds artifacts_matter and a Saga / Aura feeds
# enchantments_matter (the generalization of the Food->artifact case).
_ART_SUBTYPES = (
    r"artifact|treasure|food|clue|blood|gold|map|powerstone|junk|lander"
    r"|equipment|vehicle|attraction|bobblehead|contraption|fortification"
    r"|incubator|spacecraft|mutagen"
)
_ENCH_SUBTYPES = (
    r"aura|saga|class|curse|shrine|background|cartouche|case|room|rune|shard"
)


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
    self_recur: bool = False  # serve a creature that returns/recasts ITSELF from a gy
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

    def matches(self, card: dict) -> bool:
        """True if the card feeds this signal on ANY structured/oracle dimension (or,
        when ``all_of`` is set, EVERY sub-serve) and isn't vetoed by ``not_oracle``."""
        oracle_text = get_oracle_text(card) or ""
        if self.not_oracle is not None and self.not_oracle.search(oracle_text):
            return False
        if self.all_of:
            return all(sub.matches(card) for sub in self.all_of)
        if self.names and (card.get("name") or "").lower() in self.names:
            return True
        if self.oracle is not None and self.oracle.search(oracle_text):
            return True
        # Transform-aware: classify by the FRONT face (what you play), so a transform
        # DFC's back-face type can't satisfy a ``types`` (card_type) serve — the same
        # leak that surfaced a Saga-front // Land-back card as a creature-land.
        # Word-boundary tokens, never substrings: a 'rat' tribal serve must not
        # match every Pirate ("pi[rat]e"), nor 'orc' every Sorcery.
        type_line = classifying_type_line(card).lower()
        if self.types and any(type_line_has(type_line, t) for t in self.types):
            return True
        if self.keywords:
            card_kw = {k.lower() for k in (card.get("keywords") or [])}
            if card_kw & self.keywords:
                return True
        if self.mana_cost is not None and self.mana_cost.search(
            card.get("mana_cost") or ""
        ):
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
            and len(_EVERGREEN_KW & {k.lower() for k in (card.get("keywords") or [])})
            >= self.keyword_count_min
        ):
            return True
        if (
            self.vanilla
            and "creature" in type_line
            and not re.sub(r"\([^)]*\)", "", oracle_text).strip()
        ):
            return True
        if self.self_recur and _self_recurs(card, oracle_text):
            return True
        if (
            self.min_devotion is not None
            and "instant" not in type_line
            and "sorcery" not in type_line
            and _max_color_pips(card.get("mana_cost") or "") >= self.min_devotion
        ):
            return True
        if self.signal_idents:
            # Costliest arm (a live crosswalk pass on a cold memo) — checked
            # last, only after every record-shape dimension has missed. Lazy
            # import: theme_presets imports _deck_forge.signals lazily for the
            # same cycle reason its own docstring records.
            from mtg_utils.theme_presets import _signal_idents_for

            if _signal_idents_for(card) & self.signal_idents:
                return True
        return False

    def as_dict(self) -> dict:
        """Serialize for an avenue dict (JSON-safe), so ranking can re-apply the
        SAME precise predicate to candidates it surfaced."""
        out: dict = {}
        if self.oracle is not None:
            out["oracle"] = self.oracle.pattern
        if self.types:
            out["types"] = sorted(self.types)
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
            out["self_recur"] = True
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


_ARTICLES_NAME = frozenset({"the", "a", "an", "of", "and"})


def _self_recurs(card: dict, oracle_text: str) -> bool:
    """True if ``card`` is a CREATURE that returns or recasts ITSELF from the graveyard
    (Bloodghast / Gravecrawler / Reassembling Skeleton) — the self-replacing aristocrats
    fodder. Name-aware: the returned object must be the card itself (its own name, "this
    card/creature", or "it"), so Sun-Titan-style reanimation of OTHER cards is excluded.
    """
    if "creature" not in (card.get("type_line") or "").lower():
        return False
    refs = ["this card", "this creature", r"\bit\b"]
    for w in re.split(r"\W+", card.get("name") or ""):
        if len(w) > 2 and w.lower() not in _ARTICLES_NAME:
            refs.append(re.escape(w))
            break
    pat = re.compile(
        rf"(?:return|cast) (?:{'|'.join(refs)})"
        r"(?:[^.]*?from (?:your|a) graveyard|[^.]*?graveyard[^.]*?to the battlefield)",
        _IC,
    )
    return pat.search(oracle_text) is not None


def _compile(pat: str | None) -> re.Pattern[str] | None:
    try:
        return re.compile(pat, _IC) if pat else None
    except re.error:
        return None


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
        self_recur=bool(data.get("self_recur")),
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
    own precise search, so one signal fans out into several explorable avenues.

    ``serve`` is the precise classifier for the sub-avenue; when None, ranking falls
    back to the sub-avenue's ``search`` (oracle + card_type), which is correct for the
    many sub-avenues whose effect genuinely only lives in oracle prose."""

    label: str
    avenue: str
    search: dict
    serve: Serve | None = None


@dataclass(frozen=True)
class SignalSpec:
    label: str
    avenue: str
    search: dict  # card_search kwargs fragment (oracle / preset_names / card_type)
    serve: Serve  # the precise classifier (type / keyword / oracle), CR-grounded
    extras: tuple[SubAvenue, ...] = ()  # additional precise sub-avenues (optional)


def _spec(
    label: str,
    avenue: str,
    search: dict,
    serve: str | None,
    extras: tuple[SubAvenue, ...] = (),
    *,
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
    serve_self_recur: bool = False,
    serve_mana_cost: str | None = None,
    serve_idents: frozenset[str] = frozenset(),
    serve_not: str | None = None,
) -> SignalSpec:
    return SignalSpec(
        label=label,
        avenue=avenue,
        search=search,
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
        ),
        extras=tuple(extras),
    )


# Spellslinger serve, shared by spellcast_matters and magecraft_matters (the SAME
# archetype — magecraft's reminder is "whenever you cast or copy an instant or sorcery
# spell", CR 207.2c). A card FEEDS it by TYPE (Instant/Sorcery — what you cast is fixed
# by the card's type, CR 601.2), by the prowess KEYWORD (CR 702.108a), or by a magecraft
# / cast-trigger in prose. Bare "draw a card" (mislabels ~1250 permanents) and bare
# "instant or sorcery" (mislabels counterspell-shelters like Boseiju and graveyard
# payoffs) are neither, so they are excluded.
_SLINGER_SERVE_ORACLE = (
    r"\bmagecraft\b|whenever you cast (?:an instant|a sorcery|a noncreature|your)"
    # Spell-type cost reducers (Goblin Electromancer) are core spellslinger glue.
    r"|(?:instant|sorcery|noncreature|instant and sorcery) spells? you cast cost"
)
_SLINGER_TYPES = ("instant", "sorcery")
_SLINGER_KEYWORDS = ("prowess",)
_SLINGER_SEARCH_ORACLE = (
    r"\bmagecraft\b|\bprowess\b"
    r"|whenever you cast (?:an instant|a sorcery|a noncreature|your)"
    r"|instant and sorcery spells you cast"
)
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
# goad/fog), so no combination predicate is needed here.
_PILLOWFORT_ORACLE = (
    r"can't attack you\b|no more than (?:one|two|\w+) creatures? can attack you"
)
_PILLOWFORT_EXTRA = SubAvenue(
    "Pillowfort",
    "taxes and limits that make attacking you costly (Ghostly Prison, Propaganda, "
    "Sphere of Safety, Crawlspace)",
    {"oracle": _PILLOWFORT_ORACLE},
    serve=Serve(oracle=re.compile(_PILLOWFORT_ORACLE, _IC)),
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
# The oracle gate requires the DOUBLING idiom ("double the number of ... counter" /
# "put(s) twice/that-many-plus-one ... counters") co-occurring with an UNRESTRICTED
# "permanent" object, and excludes any "+1/+1" mention — a kind-agnostic doubler that
# happens to ALSO be typed to creatures/artifacts/lands only (Winding Constrictor,
# Kami of Whispered Hopes) never reaches loyalty and correctly stays out. Measured
# over the full commander-legal corpus (34,555 cards): 6 matches, ALL genuine
# counter_doubling members, 0 false positives outside that lane — Doubling Season,
# Vorinclex Monstrous Raider, Gilder Bairn, Aetheric Amplifier, Doc Samson (Lae'zel
# is the 6th — already a full lane member, so serving it here is redundant-but-
# harmless). Known miss (documented, not chased): Innkeeper's Talent's Level-3
# ability is a genuine generic doubler, but an EARLIER clause on the same card
# ("+1/+1 counter on target creature") trips the whole-oracle "+1/+1" exclusion —
# a clause-scoped (not whole-card) exclusion would recover it; out of scope for a
# serve-layer SubAvenue (advisory, human-reviewed — not membership).
_LOYALTY_DOUBLER_ORACLE = (
    r"(?:double the number of (?:each kind of )?counter"
    r"|put(?:s)? (?:that many|twice that many|.{0,20}plus one)"
    r"[^.]*(?:kinds? of )?counters?)[^.]*\bpermanent\b"
)
_LOYALTY_DOUBLER_EXTRA = SubAvenue(
    "Loyalty doubling",
    "generic (any-permanent) counter doublers, which also double loyalty counters",
    {"oracle": _LOYALTY_DOUBLER_ORACLE},
    serve=Serve(
        oracle=re.compile(_LOYALTY_DOUBLER_ORACLE, _IC),
        not_oracle=re.compile(r"\+1/\+1", _IC),
    ),
)
# Damage-soak payoffs for a damage-PREVENTION commander (Oriss "{T}: prevent all damage
# to target creature"): a wall that blocks any number of attackers (block the whole
# team, then prevent its damage) or a redirect-to-one-body soak (Palisade Giant /
# Pariah, then prevent that body's damage) converts prevention into a hard lock.
_DAMAGE_SOAK_ORACLE = (
    r"can block any number of creatures"
    r"|all damage[^.]*dealt to[^.]*instead"
    r"|damage that would be dealt to you is dealt to [^.]*instead"
)
_DAMAGE_SOAK_EXTRA = SubAvenue(
    "Soak blockers",
    "creatures that block any number of attackers or soak all damage onto one body",
    {"oracle": _DAMAGE_SOAK_ORACLE},
    serve=Serve(oracle=re.compile(_DAMAGE_SOAK_ORACLE, _IC)),
)
# Cheap unblockable creatures (Vnwxt speed deck): CHEAP "can't be blocked" bodies
# connect early and reliably, so an opponent loses life every turn (advancing speed).
# cmc_max ANDs with the unblockable oracle so it's the cheap evasion package, not every.
_CHEAP_UNBLOCKABLE_RE = re.compile(
    r"can'?t be blocked(?!\s+(?:by|except|as long as a)\b)", _IC
)
_CHEAP_EVASION_EXTRA = SubAvenue(
    "Cheap unblockable",
    "cheap unblockable creatures that connect every turn to advance speed",
    {"oracle": r"can'?t be blocked", "cmc_max": 2},
    serve=Serve(
        all_of=(Serve(oracle=_CHEAP_UNBLOCKABLE_RE), Serve(cmc_max=2)),
    ),
)
# Force-the-attack: effects that make ALL / your opponents' creatures attack each combat
# (Goblin Diplomats, War's Toll, Warmonger Hellkite, Disrupt Decorum) — they feed a
# "rewards being attacked / any-player attack" payoff (Kazuul). Plural/symmetric anchors
# ("all creatures", "each creature", "creatures <opp> controls") exclude the self
# forced-attack drawback ("this creature attacks each combat if able" — Juggernaut).
_FORCE_ATTACK_ORACLE = (
    r"all creatures attack[^.]*if able|each creature attacks[^.]*if able"
    r"|creatures (?:that|an) (?:opponent|player)s? controls? attack[^.]*if able"
)
_FORCE_ATTACK_EXTRA = SubAvenue(
    "Force the attack",
    "effects that make all (or your opponents') creatures attack, feeding goad / "
    "rewards-for-being-attacked payoffs (Goblin Diplomats, War's Toll, goad)",
    {"oracle": _FORCE_ATTACK_ORACLE},
    serve=Serve(oracle=re.compile(_FORCE_ATTACK_ORACLE, _IC)),
)
_SPELLSLINGER_SPEC = _spec(
    "Spellslinger",
    "cheap instants/sorceries plus magecraft/prowess payoffs to chain casts",
    {"oracle": _SLINGER_SEARCH_ORACLE},
    _SLINGER_SERVE_ORACLE,
    serve_types=_SLINGER_TYPES,
    serve_keywords=_SLINGER_KEYWORDS,
    extras=(
        SubAvenue(
            "Cheap instants (fuel)",
            "cheap instants to chain casts and trigger your payoffs",
            {"card_type": "Instant", "cmc_max": 3},
            serve=Serve(types=frozenset({"instant"})),
        ),
        SubAvenue(
            "Cheap sorceries (fuel)",
            "cheap sorceries to chain casts and trigger your payoffs",
            {"card_type": "Sorcery", "cmc_max": 3},
            serve=Serve(types=frozenset({"sorcery"})),
        ),
    ),
)


# ── EDHREC-audit sub-avenues shared by the flood/token specs ──────────────────
# Creature/permanent-ETB PAYOFFS (CR 603.6 zone-change triggers): a flood or
# aristocrats commander runs Impact Tremors / Purphoros / Corpse Knight — a trigger on
# "a creature you control enters" with a damage/drain/power payoff — which the token-
# MAKER serves never surface. The (a|another|one or more) quantifier excludes self-ETBs
# ("when THIS creature enters"); the payoff clause excludes value-ETBs (Chupacabra).
_ETB_PAYOFF_ORACLE = (
    r"whenever (?:a|an|another|one or more)[^.]*"
    r"\b(?:creature|permanent|artifact|token)s?\b[^.]*enters[^.]*"
    r"(?:deals? (?:\d+|x) damage|deals? damage equal to"
    r"|each opponent loses|loses? \d+ life)"
)
_ETB_PAYOFF_EXTRA = SubAvenue(
    "Creature-ETB payoffs",
    "permanents that punish each creature entering — damage, drain, or power-based "
    "(Impact Tremors / Purphoros)",
    {"oracle": _ETB_PAYOFF_ORACLE},
    serve=Serve(oracle=re.compile(_ETB_PAYOFF_ORACLE, _IC)),
)
# Mass-death payoff serve (Tobias / Nevinyrral / Gadrak / Mahadi): board wipes — the
# maximal "creatures die this turn" engine — plus MASS-reanimation to refill the wiped
# board. Wipes: "destroy/exile all creatures", a damage-to-each-creature sweep
# (Blasphemous Act), or a mass -X/-X. Reanimation: "return ... all ... cards ...
# graveyard ... to the battlefield" (Storm of Souls / Faith's Reward) — the "all"
# anchor excludes single-target reanimation (Raise Dead / Reanimate), the reanimator
# lane, not a board refill.
_MASS_DEATH_PAYOFF_ORACLE = (
    r"destroy all creatures|exile all creatures"
    r"|deals \d+ damage to each creature|(?:all|each) creatures? gets? -\d"
    r"|returns? (?:to the battlefield )?all [^.]*cards?[^.]*"
    r"(?:from|in)[^.]*graveyard"
)
# Per-target payoff serve (Hinata): spells whose target COUNT is variable, so the
# per-target discount compounds — "any number of targets", "divided among ... targets",
# and "X target" spells. Single fixed-target spells (Doom Blade) give only one discount
# and are excluded.
_MULTI_TARGET_ORACLE = (
    r"any number of targets?"
    r"|divided[^.]*among[^.]*(?:any number|targets?)"
    r"|\bx target"
)
# Crippling-drawback oracle (Abigale ability-strip targets): self-negative clauses that
# make a big creature cheap/unplayable — the inefficiency a "loses all abilities" strip
# removes. ANDed with a power floor so it serves BIG bodies, not small drawback ones.
_CRIPPLING_DRAWBACK_ORACLE = (
    r"can't attack or block unless|can't attack unless|cumulative upkeep"
    r"|at the beginning of (?:your|each) upkeep, "
    r"(?:you )?(?:sacrifice|discard|lose \d|mill)"
    r"|gets? -\d/-\d for each|when this creature enters, sacrifice"
)
# Type-changer oracle (Gor Muldrak type_change): genuine creature-type CHANGERS — turn a
# creature INTO a chosen type — not the tribal anthems that merely "choose a creature
# type" then buff your own board.
_TYPE_CHANGER_ORACLE = (
    r"(?:target|each|all|that) creatures?[^.]{0,25}"
    r"becomes? (?:a creature type|that (?:creature )?type|the creature type)"
    r"|becomes a creature type of your choice"
    r"|replac\w+[^.]*one creature type with another"
    r"|creatures? (?:you control )?(?:are|become) the (?:chosen|creature) type"
)
# Enlist fodder (Aradesh): a big creature that stays back (a crippling drawback keeps it
# from attacking) is ideal to TAP for enlist — its full power is added with no downside.
# Reuses the crippling-drawback oracle ANDed with a power floor (Serve.all_of).
_ENLIST_FODDER_EXTRA = SubAvenue(
    "Enlist fodder",
    "big stay-back creatures to tap for their power (their drawback stops them "
    "attacking anyway)",
    {"oracle": _CRIPPLING_DRAWBACK_ORACLE},
    serve=Serve(
        all_of=(
            Serve(oracle=re.compile(_CRIPPLING_DRAWBACK_ORACLE, _IC)),
            Serve(power_min=5),
        )
    ),
)
# Token DOUBLERS (CR 616 replacement effect): a token-flood commander doubles output
# with Doubling Season / Parallel Lives / Mondrak. Phrasings: "create twice that many",
# "twice that many … are created", "one or more tokens would be created … twice".
_TOKEN_DOUBLER_ORACLE = (
    r"(?:create|put) twice that many[^.]*tokens?"
    r"|twice that many[^.]*tokens?[^.]*(?:created|instead)"
    r"|one or more tokens would be created[^.]*twice that many"
    r"|twice that many (?:of those tokens|tokens?) (?:are|instead)"
)
_TOKEN_DOUBLER_EXTRA = SubAvenue(
    "Token doublers",
    "replacement effects that double your token output (Doubling Season / Parallel "
    "Lives / Mondrak)",
    {"oracle": _TOKEN_DOUBLER_ORACLE},
    serve=Serve(oracle=re.compile(_TOKEN_DOUBLER_ORACLE, _IC)),
)
# Symmetric go-wide anthems: "creatures you control get +1/+1" (Glorious Anthem) and
# "creature tokens you control get …" (Intangible Virtue). SYMMETRIC ("you control"),
# not "target creature" single pumps (CR 115 — those needn't hit your team). A token /
# go-wide deck's tokens ARE creatures, so creature anthems pump them.
_GOWIDE_ANTHEM_ORACLE = (
    r"(?:creatures?|(?:creature )?tokens?) you control (?:gets?|have|has|gains?)\b"
)
_GOWIDE_ANTHEM_EXTRA = SubAvenue(
    "Go-wide anthems",
    "team anthems that pump every creature/token you control (Glorious Anthem, Dictate "
    "of Heliod, Intangible Virtue)",
    {"oracle": _GOWIDE_ANTHEM_ORACLE},
    serve=Serve(oracle=re.compile(_GOWIDE_ANTHEM_ORACLE, _IC)),
)
# Token-aristocrats drain: payoffs that fire on TOKEN creation / a token leaving and
# bleed the table (Mirkwood Bats, Nadier's Nightblade, Rotwidow Pack). A token-flood
# commander triggers these just by making tokens, so it wants them even without a sac
# outlet. Token-SPECIFIC trigger (not the generic "whenever a creature dies" Blood
# Artist, which needs deaths and is already served by the death/aristocrats lanes).
_TOKEN_ARISTOCRAT_ORACLE = (
    r"(?:create|sacrifice)s?[^.]*tokens?[^.]*each (?:opponent|player) loses"
    r"|tokens? you control (?:leaves|dies)[^.]*"
    r"(?:each (?:opponent|player)|that player) loses"
)
_TOKEN_ARISTOCRAT_EXTRA = SubAvenue(
    "Token-aristocrats drain",
    "payoffs that bleed the table whenever you make or lose a token (Mirkwood Bats, "
    "Nadier's Nightblade)",
    {"oracle": _TOKEN_ARISTOCRAT_ORACLE},
    serve=Serve(oracle=re.compile(_TOKEN_ARISTOCRAT_ORACLE, _IC)),
)
# MASS token makers — "create TWO/X creature tokens at once" (Battle Screech, Grand
# Crescendo, Secure the Wastes, Champions from Beyond). The go-wide BUILD-AROUND subset
# (~558), distinct from the ~2315 generic single-token makers the tokens_matter serve
# deliberately excludes: a single-maker is generically good (every deck runs a few), but
# "create X tokens in one card" is archetype-unique to go-wide. Within-avenue clean for
# flood commander; far narrower than the generic-maker flood.
_GOWIDE_MAKER_ORACLE = (
    r"create (?:two|three|four|five|six|seven|eight|nine|ten|x|\d{2,}) "
    r"[^.]*creature tokens?"
)
_GOWIDE_MAKER_EXTRA = SubAvenue(
    "Mass token makers",
    "cards that create two or more creature tokens at once to flood the board "
    "(Battle Screech, Secure the Wastes, Grand Crescendo)",
    {"oracle": _GOWIDE_MAKER_ORACLE},
    serve=Serve(oracle=re.compile(_GOWIDE_MAKER_ORACLE, _IC)),
)
# Protect the wide board: "creatures you control gain indestructible / hexproof /
# protection until end of turn" (Heroic Intervention, Rootborn Defenses, Boros Charm,
# Flawless Maneuver): a go-wide deck's answer to a board wipe. Distinct from the voltron
# SINGLE-threat protect ("target creature gains hexproof").
_TEAM_PROTECT_ORACLE = (
    r"creatures you control gain (?:indestructible|hexproof|protection|shroud)"
)
_TEAM_PROTECT_EXTRA = SubAvenue(
    "Protect the wide board",
    "team-wide indestructible / protection to survive a wrath (Heroic Intervention, "
    "Rootborn Defenses, Flawless Maneuver)",
    {"oracle": _TEAM_PROTECT_ORACLE},
    serve=Serve(oracle=re.compile(_TEAM_PROTECT_ORACLE, _IC)),
)
# Raw creature-token MAKERS — fuel for a token-COPY commander (Esix turns each token
# she'd create into a copy of a chosen creature, so the more tokens she'd have made,
# the more copies). Matches "create … creature token(s)" (Hornet Queen / Avenger of
# Zendikar / Deep Forest Hermit).
_TOKEN_MAKER_ORACLE = r"create [^.]*?\bcreature tokens?\b"
_TOKEN_MAKER_EXTRA = SubAvenue(
    "Token makers",
    "creature-token makers whose tokens become copies (Hornet Queen / Avenger of "
    "Zendikar / Deep Forest Hermit)",
    {"oracle": _TOKEN_MAKER_ORACLE},
    serve=Serve(oracle=re.compile(_TOKEN_MAKER_ORACLE, _IC)),
)
# Flicker enablers (CR 603.6e) for a repeated-ETB commander — re-use your own ETBs.
# Pronoun/"you control"-return anchor keeps reanimation (graveyard return) out.
_FLICKER_ORACLE = (
    r"exile[^.]*(?:creature|permanent)s?(?: you control)?[^.]*return "
    r"(?:it|them|that card|those cards|that permanent)[^.]*battlefield"
    # Two-sentence form: "exile … . Return it/that … battlefield" (Charming Prince,
    # Flickerwisp) — crosses one sentence boundary, anchored to a return-pronoun.
    r"|exile[^.]{0,90}?\.\s*returns? (?:it|them|that|those)[^.]{0,50}?battlefield"
)
_FLICKER_EXTRA = SubAvenue(
    "Blink / flicker",
    "exile-and-return your own ETB creatures to re-use their enter triggers "
    "(Ephemerate / Cloudshift / Conjurer's Closet)",
    {"preset_names": ("blink",)},
    serve=Serve(oracle=re.compile(_FLICKER_ORACLE, _IC)),
)
# Dies-recursion is a DISTINCT mechanic from flicker (CR: blink exiles to the exile
# zone, 400.1; dies puts to the graveyard, 700.4 — different zones, 603.6c). Both
# re-fire an ETB by making the creature leave and return, so an ETB-reuse / LTB
# commander wants BOTH — but as SEPARATE avenues, never lumped into the flicker serve.
# Mirrors the dies_recursion lane (bare dies-return grants + undying/persist).
# ADR-0027: dies_recursion migrated to the Card IR; its SWEEP_DETECTORS row is deleted,
# so reuse the shared DIES_RECURSION_REGEX constant (the serve keeps the old regex,
# kept in lockstep with the IR kept-mirror so serve and detection never drift).
_DIES_RECURSION_ORACLE = DIES_RECURSION_REGEX
_DIES_RECURSION_EXTRA = SubAvenue(
    "Dies-recursion",
    "creatures that come back when they die — re-fire enter triggers via death "
    "(Feign Death / Supernatural Stamina / undying / persist)",
    {"oracle": _DIES_RECURSION_ORACLE},
    serve=Serve(oracle=re.compile(_DIES_RECURSION_ORACLE, _IC)),
)
# Activated sacrifice OUTLETS (Viscera Seer / Ashnod's Altar / Carrion Feeder): a cost
# that sacs a creature/permanent, to kill a self-death-payoff commander on demand.
_SAC_OUTLET_ORACLE = (
    r"sacrifice (?:a|an|another|two|three|x|\d+) "
    r"(?:creature|permanent|artifact|nonland)[^:.]{0,40}?:"
)
_SAC_OUTLET_EXTRA = SubAvenue(
    "Sacrifice outlets",
    "free/cheap activated sac outlets to kill your commander on demand and re-fire "
    "its death trigger (Viscera Seer / Ashnod's Altar / Carrion Feeder)",
    {"oracle": _SAC_OUTLET_ORACLE},
    serve=Serve(oracle=re.compile(_SAC_OUTLET_ORACLE, _IC)),
)
# Self-bounce ETB creatures (Whitemane Lion / Kor Skyfisher / Stonecloaker): "when this
# creature enters, return a/another permanent you control to its owner's hand" — a
# RECAST engine. Recasting re-fires both the creature-cast trigger and the enter
# trigger, so a creature-cast / ETB commander wants them. Anchored to "you control" so
# a tempo bounce of an OPPONENT's permanent never registers.
_SELF_BOUNCE_ORACLE = (
    # ETB self-bounce (Whitemane Lion, Kor Skyfisher) AND the upkeep/end-step engines
    # (Mistbreath Elder, First Responder) that return your own creature each turn to
    # re-fire its enter trigger on recast. Loose middle catches "up to one other".
    r"(?:when this creature enters,?(?: you may)?"
    r"|at the beginning of (?:your|each) (?:upkeep|end step),?(?: you may)?) "
    r"return (?:a|an|another|target|up to one|up to two)[^.]{0,30}?"
    r"(?:creature|permanent|nonland permanent)s? you control to (?:its|their) owner"
)
_SELF_BOUNCE_EXTRA = SubAvenue(
    "Self-bounce recast engines",
    "creatures that return your own permanent on enter — recast to re-fire enter and "
    "cast triggers (Whitemane Lion / Kor Skyfisher / Stonecloaker)",
    {"oracle": _SELF_BOUNCE_ORACLE},
    serve=Serve(oracle=re.compile(_SELF_BOUNCE_ORACLE, _IC)),
)
# Self-SACRIFICING creatures (Spore Frog / Caustic Caterpillar / Selfless Spirit): the
# sac is the activation cost, so one use both yields a repeatable effect AND drops the
# creature into the graveyard — ideal fuel for a creature-recursion engine (loop: recur
# it, recast, sac again; no separate sac outlet). "this creature" is the Oracle self-
# reference, so this matches only creatures.
_SELF_SAC_CREATURE_ORACLE = (
    r"sacrifice (?:this creature|~|this permanent)\b[^:.]{0,20}?:"
)
_SELF_SAC_CREATURE_EXTRA = SubAvenue(
    "Self-sacrificing creatures",
    "creatures that sacrifice themselves for value — recur and re-sac them every turn "
    "(Spore Frog / Caustic Caterpillar / Sakura-Tribe Elder)",
    {"oracle": _SELF_SAC_CREATURE_ORACLE},
    serve=Serve(oracle=re.compile(_SELF_SAC_CREATURE_ORACLE, _IC)),
)
# Shared STAX-PIECES serve: a stax commander wants stax pieces regardless of whether its
# OWN stax is opponent-targeted (Gaddock) or symmetric (Hokori), so stax_taxes and
# symmetric_stax serve the same pool — opponent taxes + symmetric restrictions + the
# hatebears the opponent-only serve missed: global ability-shutoff (Collector Ouphe /
# Cursed Totem / Stony Silence), anti-cheat ETB replacement (Containment Priest /
# Hallowed Moonlight), and ETB/death trigger-hate (Hushbringer / Torpor Orb).
_STAX_SERVE_ORACLE = (
    r"opponents? can't"
    r"|(?:players?|that player|each player) can't (?:cast|activate|attack|block"
    r"|untap|search|draw|play|gain)"
    r"|spells?[^.]*cost \{?\d+\}? more|noncreature spells?[^.]*cost \{?\d"
    r"|creatures your opponents control"
    r"|(?:your opponents control|nonbasic lands?|other permanents) enters?"
    r"(?: the battlefield)? tapped"
    r"|can't attack you|unless [^.]*\bpays?\b|may pay \{"
    r"|if (?:a player|an opponent|that player|they) would search[^.]*library"
    r"|(?:doesn't|don't|does not) untap during (?:its|their|the)"
    # Forcing opponents to skip a step/phase/turn is stax (CR 500.11). Scope to an
    # opponent/that-player/the-player/each-player subject so "you skip your draw step"
    # self-drawbacks stay out (Fatespinner's skip clause subject is "The player").
    r"|(?:each opponent|that player|the player|each (?:other )?player|opponents?)"
    r"[^.]*\bskips?\b[^.]*(?:step|phase|turn)"
    # Land-DENIAL stax (Blood Moon archetype): "nonbasic lands are Mountains" (Magus),
    # "taps a nonbasic land" → punish (Burning Earth), "number of nonbasic lands" (Price
    # of Progress) — restricts opponents' mana, so a stax commander (Zhao, Thalia) wants
    # it. (The basic-land RAMP form has no "nonbasic", so it stays out.)
    r"|nonbasic lands? (?:are|become)\b|taps? a nonbasic land"
    r"|number of nonbasic lands"
    # Symmetric hatebears (the gap):
    r"|activated abilities of [^.]*can't be activated"
    r"|would enter[^.]*(?:exile it instead|isn't cast|wasn't cast)"
    r"|(?:entering|enters?|dying|die)[^.]*don't cause[^.]*abilities to trigger"
)
# Blink wants more than flicker effects: the ETB-VALUE creatures it re-flickers (CR
# 603.6 zone-change triggers) and the ETB-trigger DOUBLERS that multiply every enter
# (Panharmonicon / Yarok). The value regex requires an enter trigger PLUS a value verb,
# so a vanilla creature never registers.
_ETB_VALUE_ORACLE = (
    r"when[^.]*enters[^.]*(?:draw|return target|search your library"
    r"|create [^.]*token|destroy target|gain \d+ life|untap"
    r"|put [^.]*onto the battlefield|exile target"
    # Edict-ETB creatures (Plaguecrafter, Accursed Marauder) are ETB value worth
    # blinking/reanimating for repeated forced sacrifice.
    r"|each player sacrifices|sacrifices? a (?:creature|nontoken|permanent))"
)
_ETB_VALUE_EXTRA = SubAvenue(
    "ETB-value creatures",
    "creatures with strong enter triggers worth flickering "
    "(Mulldrifter / Eternal Witness / Reflector Mage)",
    {"card_type": "Creature", "oracle": _ETB_VALUE_ORACLE},
    serve=Serve(oracle=re.compile(_ETB_VALUE_ORACLE, _IC)),
)
_ETB_DOUBLER_ORACLE = (
    r"entering[^.]*causes a triggered ability[^.]*triggers an additional time"
)
_ETB_DOUBLER_EXTRA = SubAvenue(
    "ETB-trigger doublers",
    "permanents that double every enter trigger (Panharmonicon / Yarok)",
    {"oracle": _ETB_DOUBLER_ORACLE},
    serve=Serve(oracle=re.compile(_ETB_DOUBLER_ORACLE, _IC)),
)
# Trigger COPIERS (Strionic Resonator / Lithoform Engine): copy a triggered ability
# you control — a payoff for any trigger-heavy deck, ETB triggers included. Distinct
# from the Panharmonicon doubler (which keys on the "entering" wording).
_TRIGGER_COPY_ORACLE = r"copy target [^.]*triggered ability you control"
_TRIGGER_COPY_EXTRA = SubAvenue(
    "Trigger copiers",
    "copy a triggered ability you control (Strionic Resonator / Lithoform Engine)",
    {"oracle": _TRIGGER_COPY_ORACLE},
    serve=Serve(oracle=re.compile(_TRIGGER_COPY_ORACLE, _IC)),
)
# Self-recurring fodder (CR 603.6e): aristocrats wants creatures that return/recast
# THEMSELVES from the graveyard (Bloodghast / Gravecrawler). Name-aware serve (see
# _self_recurs) excludes Sun-Titan-style reanimation of OTHER cards.
_SELF_RECUR_EXTRA = SubAvenue(
    "Self-recurring fodder",
    "creatures that bring themselves back from the graveyard — free, repeatable sac "
    "fodder (Bloodghast / Gravecrawler / Reassembling Skeleton)",
    {"oracle": r"from your graveyard to the battlefield"},
    serve=Serve(self_recur=True),
)
# Aristocrats DRAIN payoff (CR 700.4 "dies"): the heart of the archetype — a permanent
# that punishes creatures dying with a drain, life swing, or token (Blood Artist /
# Zulaport Cutthroat / Cruel Celebrant / Pitiless Plunderer). Anchored on a "whenever …
# creature … dies" TRIGGER plus a payoff clause, so a bare death-draw creature ("when
# this dies, draw a card") or a removal spell does not register. Verified: 76 bulk hits,
# all genuine. Shared by the death and sacrifice lanes (a sac-outlet commander opens
# sacrifice_outlets, not death_matters, but wants the same drain payoffs).
_DEATH_DRAIN_ORACLE = (
    r"whenever [^.]*\bcreatures?\b[^.]*dies[^.]*"
    r"(?:each opponent loses|target player loses|loses? \d+ life|you (?:may )?gain"
    r"|create (?:a|one|two|x) [^.]*(?:treasure|blood|clue))"
)
_DEATH_DRAIN_EXTRA = SubAvenue(
    "Death payoffs / drain",
    "payoffs that punish creatures dying — drain, life swings, and tokens "
    "(Blood Artist / Zulaport Cutthroat / Pitiless Plunderer)",
    {"oracle": _DEATH_DRAIN_ORACLE},
    serve=Serve(oracle=re.compile(_DEATH_DRAIN_ORACLE, _IC)),
)
# On-death payoffs for a commander that repeatedly KILLS creatures (no sac outlet of
# its own): the drain set above PLUS the "deal damage to a player" variant (Vicious
# Shadows) the loses-life/gain-life drain regex misses. Narrow on-death-payoff serve,
# NOT the full aristocrats kit (no fodder / sac outlets a control commander won't want).
_KILL_DRAIN_ORACLE = (
    r"whenever [^.]*\bcreatures?\b[^.]*dies[^.]*"
    r"(?:each opponent loses|target player loses|loses? \d+ life|you (?:may )?gain"
    r"|create (?:a|one|two|x) [^.]*(?:treasure|blood|clue)"
    r"|deals? [^.]*damage to (?:target |each )?(?:player|opponent))"
)
# One-punch finishers for an extreme power-for-cost beater (Lord, Yargle): convert raw
# power into a kill by GRANTING infect (power -> poison) or double strike (2x damage).
# Granters only — "<target/equipped/enchanted/your> creature gains/has infect|double
# strike"; a vanilla double-striker (Boros Swiftblade) is not an amplifier for the
# commander, so the bare keyword line stays out.
_ONE_PUNCH_ORACLE = (
    r"(?:target creature|target attacking creature|equipped creature"
    r"|enchanted creature|creatures? you control|it) "
    r"(?:gains?|gets [^.]*and (?:gains?|has)|have|has) (?:infect|double strike)"
)
# Board wipes are an aristocrats payoff: a mass-death event fires every dies-trigger and
# drain at once (Wrath of God + Blood Artist). A death/sacrifice commander wants them.
_BOARD_WIPE_EXTRA = SubAvenue(
    "Board wipes (mass death)",
    "sweepers that turn a board into a mass-death trigger for your aristocrats payoffs",
    {"preset_names": ("board-wipe",)},
    serve=Serve(oracle=re.compile(r"destroy all|exile all (?:creatures|other)", _IC)),
)
# Landfall (CR 207.2c ability word; canonical "Landfall — whenever a land you control
# enters"): the payoffs PLUS the engines that fire them — extra land drops (Azusa /
# Dryad), land fetch, and graveyard land recursion (Crucible / Ramunap). One regex
# shared by the avenue's search and its serve.
_LANDFALL_ORACLE = (
    r"\blandfall\b"
    r"|search your library for [^.]*\bland\b"
    # Basic-type ramp names the type, not the word "land": Skyshroud Claim ("Forest
    # cards"), Farseek ("a Plains, Island, Swamp, or Mountain"), Nature's Lore. It must
    # PUT them onto the battlefield (ramp), not just fetch to hand.
    r"|search your library for [^.]*\b(?:forest|island|plains|mountain|swamp)\b"
    r"[^.]*onto the battlefield"
    r"|play (?:an|one|two|three|\d+) additional lands?"
    r"|play lands? from your graveyard"
    r"|put [^.]*\bland card[^.]*onto the battlefield"
)
# Graveyard-to-top recursion (Volrath's Stronghold, Haunted Crossroads, Hua Tuo): the
# top-stacking enabler a cheat-from-top / play-from-top deck wants -- it puts a chosen
# card on TOP of the library (not onto the battlefield, which is plain reanimation).
_GY_TO_TOP_ORACLE = (
    r"(?:put|return) (?:target |a )?(?:\w+ )?cards? from (?:your|a) graveyard "
    r"on top of (?:your|their)(?: owner.s)? library"
)
_LANDS_FROM_GRAVE_ORACLE = (
    r"play lands? from your graveyard"
    # Mass land-return puts lands straight onto the battlefield — a huge landfall
    # payoff (Splendid Reclamation, Titania, World Shaper, Lord Windgrace).
    r"|return [^.]*\bland cards?\b[^.]*from your graveyard to the battlefield"
)
_LANDS_FROM_GRAVE_EXTRA = SubAvenue(
    "Lands from your graveyard",
    "recursion that replays sacrificed/milled lands for repeat landfall "
    "(Crucible of Worlds / Ramunap Excavator / Splendid Reclamation)",
    {"oracle": _LANDS_FROM_GRAVE_ORACLE},
    serve=Serve(oracle=re.compile(_LANDS_FROM_GRAVE_ORACLE, _IC)),
)
# Deathtouch-granting gear (CR 702.2b): with a repeatable pinger, deathtouch + 1 damage
# kills anything. "(equipped|enchanted) creature … deathtouch" is Equipment/Aura-only.
_DEATHTOUCH_GEAR_ORACLE = r"(?:equipped|enchanted) creature[^.]*\bdeathtouch\b"
_DEATHTOUCH_GEAR_EXTRA = SubAvenue(
    "Deathtouch enablers",
    "Equipment/Auras that grant deathtouch so each ping kills (Basilisk Collar)",
    {"oracle": _DEATHTOUCH_GEAR_ORACLE},
    serve=Serve(oracle=re.compile(_DEATHTOUCH_GEAR_ORACLE, _IC)),
)
# Player/opponent-directed noncombat burn — the genuine payoff space for a damage
# DOUBLER (Solphim, Torbran): every source that deals damage to a player or opponent
# is doubled. The amount is OPTIONAL so "deals damage to each player equal to …"
# (Heartless Hidetsugu, Price of Progress) is caught alongside numbered/X burn; the
# player/opponent target list excludes creature-only sweepers (Pyroclasm, Languish).
_NONCOMBAT_BURN_ORACLE = (
    r"deals?(?: (?:\d+|x|that much))? (?:noncombat )?damage to "
    r"(?:each opponent|each player|target opponent|target player|that player)"
)
_NONCOMBAT_BURN_EXTRA = SubAvenue(
    "Player-directed burn",
    "noncombat damage aimed at players/opponents — doubled by your damage doubler",
    {"oracle": _NONCOMBAT_BURN_ORACLE},
    serve=Serve(oracle=re.compile(_NONCOMBAT_BURN_ORACLE, _IC)),
)
# Proliferate (CR 701.27) for any counter commander — adds another of EVERY counter.
_PROLIFERATE_EXTRA = SubAvenue(
    "Proliferate",
    "proliferate sources that add another counter of every kind you already have",
    {"preset_names": ("proliferate",)},
    serve=Serve(
        keywords=frozenset({"proliferate"}), oracle=re.compile(r"\bproliferate\b", _IC)
    ),
)
# Counter DOUBLERS / amplifiers (CR 122.3 + 614 replacement): the universal payoff for
# ANY counters commander — Doubling Season, Hardened Scales, Corpsejack, Branching
# Evolution, Vorinclex. Note Doubling Season says "counters" generically (not "+1/+1
# counter"), so the bare plus_one_matters serve missed it. Shared across every counter
# lane below, since a counters commander can open any of them. 94 genuine bulk hits.
_COUNTER_DOUBLER_ORACLE = (
    r"twice that many [^.]*counters?|that many plus (?:one|\d+) [^.]*counters?"
    r"|counters?[^.]*twice that many|double the number of [^.]*counters?"
    r"|if one or more (?:\+1/\+1 )?counters? would be put[^.]*instead"
)
_COUNTER_DOUBLER_EXTRA = SubAvenue(
    "Counter doublers",
    "replacement effects that multiply every counter you place "
    "(Doubling Season / Hardened Scales / Corpsejack Menace / Vorinclex)",
    {"oracle": _COUNTER_DOUBLER_ORACLE},
    serve=Serve(oracle=re.compile(_COUNTER_DOUBLER_ORACLE, _IC)),
)
# +1/+1 counter PLACEMENT support: spells/abilities that drop +1/+1 counters on your
# creatures (the fuel a self-growth / counters commander wants alongside the doublers).
_COUNTER_PLACE_ORACLE = r"put (?:a|one|two|three|x|\d+|that many)[^.]*\+1/\+1 counters?"
_COUNTER_PLACE_EXTRA = SubAvenue(
    "Counter placement",
    "ways to drop more +1/+1 counters on your creatures (Hardened Scales fuel)",
    {"oracle": _COUNTER_PLACE_ORACLE},
    serve=Serve(oracle=re.compile(_COUNTER_PLACE_ORACLE, _IC)),
)
# Keyword counters (flying/trample/deathtouch/lifelink/indestructible/…) are counters
# too: a counters commander wants them for proliferate fuel and voltron protection, even
# with no +1/+1. ADR-0027 tranche2-C: keyword_counter migrated to the Card IR and its
# SWEEP_DETECTORS row is deleted, so reuse the shared KEYWORD_COUNTER_REGEX constant
# (still the single source of truth — the IR kept mirror reads it too, so no drift).
_KEYWORD_COUNTER_ORACLE = KEYWORD_COUNTER_REGEX
_KEYWORD_COUNTER_EXTRA = SubAvenue(
    "Keyword counters",
    "cards that place keyword counters (flying / trample / deathtouch / lifelink / …) "
    "— counter synergy and proliferate fuel",
    {"oracle": _KEYWORD_COUNTER_ORACLE},
    serve=Serve(oracle=re.compile(_KEYWORD_COUNTER_ORACLE, _IC)),
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
# keyword itself (the keyword word also prints in the oracle, so search can find it).
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
    {"oracle": r"\b(?:" + "|".join(sorted(_COUNTER_KEYWORDS)) + r")\b"},
    serve=Serve(keywords=_COUNTER_KEYWORDS),
)
# Counter RESILIENCE: save or relocate YOUR counters when a creature leaves, so a wrath
# (or the creature's own death) doesn't waste the investment (The Ozolith, Resourceful
# Defense, Fate Transfer). Pro-counter only — "if it had counters ... put those" / "move
# ... counters from ... onto"; NOT counter-removal (Aether Snap, Vampire Hexmage), the
# opposite. A self-growing-counters commander (Wolverine) wants to protect its counters.
_COUNTER_RESILIENCE_ORACLE = (
    r"if it had counters on it[^.]*put those counters"
    r"|move (?:all|those|the) counters? from [^.]*onto"
)
_COUNTER_RESILIENCE_EXTRA = SubAvenue(
    "Counter resilience",
    "save or relocate your counters when a creature leaves (The Ozolith)",
    {"oracle": _COUNTER_RESILIENCE_ORACLE},
    serve=Serve(oracle=re.compile(_COUNTER_RESILIENCE_ORACLE, _IC)),
)
_COUNTERS_PACKAGE = (
    _COUNTER_PLACE_EXTRA,
    _COUNTER_DOUBLER_EXTRA,
    _KEYWORD_COUNTER_EXTRA,
    _COUNTER_KEYWORD_EXTRA,
    _PROLIFERATE_EXTRA,
    _COUNTER_RESILIENCE_EXTRA,
)
# Discard-PUNISH payoffs (CR 701.8 discard): reward forcing opponents to discard.
_DISCARD_PUNISH_ORACLE = (
    r"whenever (?:a player|an opponent|that player|each opponent|target opponent)"
    r"[^.]*discards?[^.]*(?:loses? \d+ life|deals? \d+ damage|you (?:may )?draw|create)"
)
_DISCARD_PUNISH_EXTRA = SubAvenue(
    "Discard punishers",
    "payoffs that trigger when an opponent discards (Megrim / Liliana's Caress / "
    "Waste Not)",
    {"oracle": _DISCARD_PUNISH_ORACLE},
    serve=Serve(oracle=re.compile(_DISCARD_PUNISH_ORACLE, _IC)),
)
# Empty-hand (hellbent) OPPONENT punishers: the 8-Rack package a hand-attack deck wants
# once it strips opponents' hands (The Rack, Wheel of Torture, Shrieking Affliction,
# Rackling, Guul Draz Specter). Opponent-anchored (that player / each opponent / their)
# so a SELF-hellbent madness payoff ("YOU have no cards in hand") and a plain draw spell
# never qualify.
_HELLBENT_PUNISH_ORACLE = (
    r"(?:that player|each opponent|target opponent|defending player|an opponent) "
    r"(?:has |have )?(?:one or fewer|no|zero) cards? in (?:their )?hand"
    r"|minus the number of cards in (?:that player's|their|an opponent's"
    r"|defending player's) hand"
)
_HELLBENT_PUNISH_EXTRA = SubAvenue(
    "Empty-hand punishers",
    "8-Rack payoffs that punish an opponent's empty hand (The Rack, Wheel of Torture, "
    "Shrieking Affliction)",
    {"oracle": _HELLBENT_PUNISH_ORACLE},
    serve=Serve(oracle=re.compile(_HELLBENT_PUNISH_ORACLE, _IC)),
)


# Reanimator PAYOFF (Celes, Rune Knight): a creature ENTERING from a graveyard
# (reanimation) or being CAST from one (escape/disturb) fires the payoff. Two enabler
# families. (1) Reanimation effects that return a creature card from a graveyard to the
# battlefield — the highest-leverage triggers (you pick the fattest target). Anchored on
# "creature card … from … graveyard … to/onto the battlefield", so a regrowth ("…to your
# hand") and a token-copy ("create a token that's a copy of…") never qualify.
_REANIMATE_ORACLE = (
    r"(?:return|put)[^.]*creature card[^.]*from (?:a|your|their)[^.]*graveyard"
    r"[^.]*(?:to|onto) the battlefield"
)
_REANIMATION_EXTRA = SubAvenue(
    "Reanimation",
    "return creatures from your graveyard to the battlefield to rebuild after a wipe "
    "(Breath of Life / Resurrection)",
    {"oracle": _REANIMATE_ORACLE},
    serve=Serve(oracle=re.compile(_REANIMATE_ORACLE, _IC)),
)
# Board protection: GRANT the whole team indestructible (Selfless Spirit, Heroic
# Intervention, Akroma's Will, Flawless Maneuver). Distinct from an indestructible
# CREATURE that merely survives a wipe (the lane's serve_keywords already credits
# those) — a granter lets you wrath one-sided and keep your board.
_BOARD_PROTECTION_ORACLE = (
    r"(?:creatures|permanents) you control (?:gain|have)[^.]*indestructible"
)
_BOARD_PROTECTION_EXTRA = SubAvenue(
    "Board protection",
    "give your whole board indestructible so you can wrath one-sided "
    "(Selfless Spirit / Heroic Intervention / Flawless Maneuver)",
    {"oracle": _BOARD_PROTECTION_ORACLE},
    serve=Serve(oracle=re.compile(_BOARD_PROTECTION_ORACLE, _IC)),
)
# Self-copy effects for a legend-rule-off / copy commander (Brothers Yamazaki): make
# token copies of your own creature (Helm of the Host / Blade of Selves / Mirror Box).
_COPY_ORACLE = (
    r"token that's a copy|tokens? that are copies|becomes a copy"
    r"|copy of (?:target|another|any|a)\b|as a copy of|\bmyriad\b|\bpopulate\b"
)
_COPY_EXTRA = SubAvenue(
    "Copy effects",
    "make token copies of your creatures (Helm of the Host / Blade of Selves / "
    "Mirror Box / Spark Double)",
    {"oracle": _COPY_ORACLE},
    serve=Serve(oracle=re.compile(_COPY_ORACLE, _IC)),
)
# High-value clone TARGETS: a creature with a strong self-DEATH trigger is worth
# copying — the (nonlegendary) token re-fires the death payoff when it dies (Kokusho
# drains, Keiga steals, Junji, The Scarab God). "When <Name> dies, <value>" is the
# self-death form (capital after "when" = the card's own name; aristocrats use lowercase
# "whenever a creature dies"). AND mana value >= 5 so a cmc-1 undying body (Young Wolf)
# — which has a dies trigger but is no clone bomb — stays out. The AND is why Serve
# grew all_of: power-6 (existing) catches big bodies; this catches the smaller
# high-VALUE death dragons (power 4-5).
_DIES_VALUE_ORACLE = (
    r"when [A-Z][\w\-, ']*? dies,[^.]*(?:each opponent|gain control|loses? \d+ life"
    r"|draws?|create|destroy|deals? \d+ damage|returns?)"
)
_CLONE_DIES_VALUE_EXTRA = SubAvenue(
    "High-value death triggers to copy",
    "high-mana-value creatures with a strong death trigger — clone them so the copy "
    "re-fires it on death (Kokusho, Keiga, Junji, The Scarab God)",
    {"oracle": _DIES_VALUE_ORACLE, "card_type": "Creature"},
    serve=Serve(
        all_of=(
            Serve(oracle=re.compile(_DIES_VALUE_ORACLE, _IC)),
            Serve(cmc_min=5),
        )
    ),
)
# Self-bounce (Cavern Harpy, Whitemane Lion): return YOUR creature to hand to RECAST it.
# For a recast-clone commander (The Master's Body Thief) that means copying a different/
# better creature again; for any clone deck it re-uses the copy ETB. Confirmed core for
# The Master. "creature you control to (its) owner's hand" — one-sided, not a symmetric
# both-players bounce (Run Away Together).
_SELF_BOUNCE_RECAST_ORACLE = (
    r"return [^.]*creatures? you control to (?:its|their) owner'?s? hand"
)
_SELF_BOUNCE_RECAST_EXTRA = SubAvenue(
    "Self-bounce (recast your clones)",
    "return your own creatures to hand to recast the clone and copy again "
    "(Cavern Harpy, Whitemane Lion)",
    {"oracle": _SELF_BOUNCE_RECAST_ORACLE},
    serve=Serve(oracle=re.compile(_SELF_BOUNCE_RECAST_ORACLE, _IC)),
)
# Drawback creatures whose downside PUNISHES their controller — the donate target
# (Abyssal Persecutor "you can't win", Flesh Reaver "deals damage to you", Demonic
# Taskmaster "upkeep: sacrifice a creature"): hand them to an opponent for the downside.
_DRAWBACK_ORACLE = (
    r"you can't win|you lose the game"
    r"|deals (?:that much )?damage to you\b"
    r"|at the beginning of (?:your )?upkeep, (?:sacrifice|you lose|discard)"
    r"|at the beginning of your (?:upkeep|end step)[^.]*(?:lose the game|lose \d+ life)"
)
_DRAWBACK_EXTRA = SubAvenue(
    "Drawback creatures to donate",
    "creatures whose downside hurts their controller — give them to an opponent "
    "(Abyssal Persecutor / Flesh Reaver / Demonic Taskmaster)",
    {"oracle": _DRAWBACK_ORACLE, "card_type": "Creature"},
    serve=Serve(oracle=re.compile(_DRAWBACK_ORACLE, _IC)),
)
# Force-feed: give opponents creatures that benefit YOU (the Hunted cycle, Forbidden
# Orchard) — a control-change/donate deck punishes its own gifts. Anchored to creating
# a creature for an opponent, so it doesn't pull Treasure/draw "gifts".
_FORCE_FEED_ORACLE = r"target opponent creates [^.]*creature"
_FORCE_FEED_EXTRA = SubAvenue(
    "Force-feed creatures",
    "give opponents creatures that work for you (Forbidden Orchard, the Hunted cycle)",
    {"oracle": _FORCE_FEED_ORACLE},
    serve=Serve(oracle=re.compile(_FORCE_FEED_ORACLE, _IC)),
)
# Untap effects to reuse tap abilities / retrigger a tap-untap commander — covers the
# "enchanted/this/that creature" forms (Freed from the Real) the bare target/all form
# missed, plus the untap symbol {Q}.
_UNTAP_ORACLE = (
    r"untap (?:target|all|another|each|enchanted|this|that|it|two|up to)|\{q\}"
)
_UNTAP_EXTRA = SubAvenue(
    "Untap effects",
    "untap your permanents to reuse their tap abilities or retrigger (Freed from the "
    "Real / Pemmin's Aura / Kiora's Follower)",
    {"oracle": _UNTAP_ORACLE},
    serve=Serve(oracle=re.compile(_UNTAP_ORACLE, _IC)),
)
# (2) Cast-from-graveyard CREATURES recast themselves from the yard, re-firing the
# payoff each turn (CR 702.146 Disturb / Escape). The graveyard-cast umbrella preset is
# filtered to card_type Creature so the instant/sorcery flashback half (which never puts
# a creature into play) drops out; the serve credits the authoritative keywords.
_CAST_FROM_GY_EXTRA = SubAvenue(
    "Cast from your graveyard",
    "creatures with escape or disturb that recast themselves from your graveyard, "
    "re-firing the payoff each time (Woe Strider / Kroxa)",
    {"preset_names": ("graveyard-cast",), "card_type": "Creature"},
    serve=Serve(keywords=frozenset({"escape", "disturb"})),
)
# Top-level serve credits BOTH enabler families plus self-recurring fodder, so any
# genuine reanimator piece reads as on-theme no matter which sub-avenue surfaced it.
_REANIMATOR_SERVE_ORACLE = (
    _REANIMATE_ORACLE
    + r"|\bescape\b|\bdisturb\b|cast [^.]*from (?:a|your|their) graveyard"
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
) -> SignalSpec:
    """Promote a mined sweep detector to a hand-spec that keeps its regex (as both
    search and serve) but fans out extra sub-avenues — used where a sweep-derived lane
    needs to surface payoffs its bare regex can't (e.g. every counter lane wants the
    counter doublers). ``serve_power_min`` / ``serve_toughness_min`` additionally credit
    big bodies (power doublers / toughness-as-power lanes want the stat-line they
    exploit); ``serve_keywords`` adds a keyword dimension. Reuses SWEEP_DETECTORS so the
    regex never drifts from the mine — UNLESS ``regex`` is given, for an ADR-0027-
    migrated key whose SWEEP_DETECTORS row is deleted (the serve keeps the old regex).
    """
    d_regex = (
        regex
        if regex is not None
        else next(x for x in SWEEP_DETECTORS if x["key"] == key)["regex"]
    )
    label, avenue = SWEEP_LABELS[key]
    return _spec(
        label,
        avenue,
        {"oracle": d_regex},
        d_regex,
        extras=extras,
        serve_power_min=serve_power_min,
        serve_toughness_min=serve_toughness_min,
        serve_toughness_over_power=serve_toughness_over_power,
        serve_keywords=serve_keywords,
    )


# Combat support shared by the combat lanes: gear that suits up the attacker plus the
# keyword-anthems that buff your attackers (double strike / trample / evasion).
_COMBAT_SUPPORT_ORACLE = (
    r"equipped creature|enchanted creature gets|\bequip \{"
    r"|(?:attacking )?creatures you control (?:have|gain|get)[^.]*"
    r"(?:double strike|first strike|trample|menace|deathtouch|vigilance"
    r"|can't be blocked)"
)
_COMBAT_SUPPORT_EXTRA = SubAvenue(
    "Combat support (gear & keyword anthems)",
    "equipment/auras and keyword-anthems that suit up and buff your attackers",
    {"oracle": _COMBAT_SUPPORT_ORACLE},
    serve=Serve(oracle=re.compile(_COMBAT_SUPPORT_ORACLE, _IC)),
)
# Extra combats (Aggravated Assault, Relentless Assault, Seize the Day, Moraug): each
# added combat phase is another round of attack + combat-damage triggers, so a commander
# that rewards attacking / combat damage / a suited-up voltron threat wants them.
# attack_matters serves "additional combat phase" inline; this shared extra gives the
# same to combat_damage_matters / combat_damage_to_opp / voltron_matters. "additional
# combat phase" is unambiguous (zero false positives: burn/pump never match).
_EXTRA_COMBAT_ORACLE = r"additional combat phase|extra combat phase"
_EXTRA_COMBAT_EXTRA = SubAvenue(
    "Extra combats",
    "additional-combat-phase enablers — another round of attack/combat-damage triggers",
    {"oracle": _EXTRA_COMBAT_ORACLE},
    serve=Serve(oracle=re.compile(_EXTRA_COMBAT_ORACLE, _IC)),
)
# Symmetric group mana: a group-mana commander (Shizuko group-ramp, Yurlok mana-burn)
# wants the shared mana-doublers and mana-punishers keyed on "whenever a player taps a
# land for mana" (Mana Flare, Heartbeat of Spring, Manabarbs, Overabundance) plus join-
# forces group ramp (Collective Voyage). The sweep serve only credited "each player adds
# {", so these went unserved. One-sided dorks ("{T}: Add {G}") never match.
_SYM_MANA_ORACLE = (
    r"(?:whenever|if) a player taps a land for mana"
    r"|whenever a land is tapped for mana"
    r"|\bjoin forces\b|each player may (?:pay|search)"
    r"|for each untapped land[^.]*deals"
    r"|each player (?:creates|may draw)"
)
_SYM_MANA_EXTRA = SubAvenue(
    "Symmetric mana (group ramp & mana-punishers)",
    "shared mana-doublers and mana-punishers that exploit the symmetry "
    "(Mana Flare, Heartbeat of Spring, Manabarbs, Collective Voyage)",
    {"oracle": _SYM_MANA_ORACLE},
    serve=Serve(oracle=re.compile(_SYM_MANA_ORACLE, _IC)),
)
# Mana AMPLIFICATION for an unspent-mana commander (Omnath Locus of Mana, Kruphix): it
# keeps mana between steps, so it wants untap-all-lands (Bear Umbra, Wilderness
# Reclamation, Nature's Will) and mana-doublers (Mana Reflection, Mana Flare) to make
# more mana to bank. Tight (untap-ALL-lands / produce-twice / tap-a-land-for-mana adds),
# so a one-sided dork ("{T}: Add {G}") never qualifies.
_MANA_AMP_ORACLE = (
    r"untap all lands you control"
    r"|produces twice as much(?: of (?:that|the) mana)?"
    r"|if you (?:tap|would tap) a (?:permanent|land) for mana, it produces twice"
    r"|whenever a player taps a land for mana"
)
_MANA_AMP_EXTRA = SubAvenue(
    "Mana amplification (untap-lands & doublers)",
    "untap-all-lands and mana-doublers that grow the mana you keep "
    "(Bear Umbra, Wilderness Reclamation, Mana Reflection)",
    {"oracle": _MANA_AMP_ORACLE},
    serve=Serve(oracle=re.compile(_MANA_AMP_ORACLE, _IC)),
)
# Instant-speed pump (Giant Growth / Berserk) to push through extra combat damage and
# survive blocks — reuses the pinned pump_makers regex so it never drifts. ADR-0027 β:
# pump_makers migrated to the Card IR (its SWEEP_DETECTORS row is deleted), so the
# constant comes from PUMP_MATTERS_REGEX, not the (now-absent) sweep row.
_PUMP_ORACLE = PUMP_MATTERS_REGEX
# ADR-0027 β: edict_makers migrated to the Card IR — its SWEEP_DETECTORS row is
# deleted (detection moved to the structural arm + a kept _IR_KEPT_DETECTORS mirror).
# The SERVE pool stays oracle-defined, so the deleted regex is inlined here (byte-
# identical to the old sweep row, so the served fodder/payoff pool never drifts).
_EDICT_SWEEP_REGEX = (
    "each opponent sacrifices|whenever an opponent sacrifices"
    "|target opponent sacrifices|each player sacrifices"
    "|(?:each player|that player|each opponent|target player"
    "|target opponent) sacrifices? (?:a|an|two|\\d+|half)"
    "|that player sacrifices|controller sacrifices"
)
# Basic-land-TYPE fetches (Skyshroud Claim, Nature's Lore, Farseek) search for
# "Forest/Plains/… cards" — no "land" in the text, so the bare "search … land" missed
# them. These ARE land ramp.
_BASIC_LAND_FETCH = (
    r"search your library for [^.]*\b(?:forest|plains|island|swamp|mountain)s?\b"
)
# ADR-0027 t2b5-C → SIDECAR v40: targeting_matters DETECTION reads structure (phase's
# `BecomesTarget` mode → event=='becomes_target') plus a residue mirror for the
# granted/quoted/player-targeted forms (see _IR_KEPT_DETECTORS). The SERVE pool (which
# candidate cards FIT the lane — heroic enablers, becomes-target payoffs, cast-that-
# targets spells) stays oracle-defined, so the becomes-target + heroic + cast phrasing
# is inlined here (this is the serve regex, not the detection path). CR 702.83 / 115.6.
_TARGETING_SWEEP_REGEX = (
    "becomes the target of a spell or ability"
    "|whenever [^.]{0,60}?becomes? the target of|\\bheroic\\b"
    "|whenever you cast (?:an instant or sorcery spell |a spell )?that targets"
)
# "Exile a card, then you may cast/play it for as long as it remains exiled" — the
# impulse / cast-from-exile / steal-and-cast engine (Gonti, Hostage Taker, Thief of
# Sanity, Kheru Spellsnatcher, Court of Locthwain). Distinct from "play those cards
# THIS TURN" impulse: this keeps the card castable until it's used.
_STEAL_CAST_ORACLE = (
    r"you may (?:cast|play|look at and play) "
    r"(?:that (?:card|spell)|it|them|those cards?)[^.]*?"
    r"for as long as (?:it|they) remains? exiled"
)
# Opponent-library theft: dig into a specific opponent's library (Gonti, Black Cat,
# Thief of Sanity, Lord of the Void). Opponent-anchored so a SELF-impulse engine
# (Valakut Exploration — "exile the top card of YOUR library") never reads as theft.
_OPP_LIBRARY_THEFT_ORACLE = (
    r"(?:top (?:\w+|\d+) cards?|the top card) of "
    r"(?:target |an |each )?(?:opponent's|that player's) library"
)
# ADR-0027 β: the SWEEP_DETECTORS row for impulse_top_play is deleted (detection moved
# to the Card IR — a non-static cast_from_zone Effect carrying from:library + a
# per-clause mirror). Its SERVE pool stays oracle-defined, so the exact deleted regex is
# pinned here verbatim and the hand-registered spec below reuses it (the sweep auto-
# register loop no longer builds it; byte-identical to the signals.py mirror regex).
_IMPULSE_SWEEP_REGEX = (
    r"exile the top [^.]*card[^.]*(?:you may play|may play (?:it|that card|them))"
    r"|until (?:your next end step|end of turn|the end of your next turn)"
    r"[^.]*you may play"
    r"|exile the top [^.]*card[^.]*your library[^.]*\.?\s*you may (?:play|cast)"
    r"|you may play (?:that|the exiled|those|that card) cards?"
    r"|you may (?:cast|play) (?:the|those|that) (?:exiled )?cards? this turn"
    r"|top [^.]*card[^.]*of your library\.?[^.]*you may (?:cast|play) "
    r"(?:it|them|that card)[^.]*this turn"
    r"|you may play (?:that card|those cards?|them) (?:this turn|until)"
    r"|cast (?:up to two |a )?spells? from among"
    r"|top card of your library is[^.]*you may[^.]*(?:cast|play)"
    r"|play (?:lands? )?(?:and |or )?cast [^.]*from among cards you exiled"
    r"|you may look at (?:it )?and (?:play|cast)"
)
# ADR-0027: theft_matters migrated to the Card IR (its SWEEP_DETECTORS row deleted).
# The serve pool stays oracle-defined, so it reuses the shared THEFT_MATTERS_REGEX
# constant (the EXACT deleted detector regex) — serve and the kept-mirror detector
# never drift.
_THEFT_SWEEP_REGEX = THEFT_MATTERS_REGEX
# ADR-0027 discard-discarder scope (SIDECAR v26): discard_outlet migrated to the Card IR
# (its SWEEP_DETECTORS row deleted). The serve pool stays oracle-defined, so it reuses
# the shared DISCARD_OUTLET_REGEX constant (the EXACT deleted detector regex) — serve
# and the kept-mirror detector never drift.
_DISCARD_OUTLET_SWEEP_REGEX = DISCARD_OUTLET_REGEX
# ADR-0027 dig library-owner scope (SIDECAR v27): dig_until migrated to the Card IR (its
# SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds the serve).
# The serve pool stays oracle-defined, so it reuses the shared DIG_UNTIL_REGEX constant
# (the EXACT deleted detector regex) — serve and the kept-mirror detector never drift.
_DIG_UNTIL_SWEEP_REGEX = DIG_UNTIL_REGEX
# ADR-0027 topdeck library-owner scope (SIDECAR v28): topdeck_selection migrated to the
# Card IR (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds
# the serve). The serve pool stays oracle-defined, so it reuses the shared
# TOPDECK_SELECTION_REGEX constant (the EXACT deleted detector regex) — serve and the
# kept-mirror detector never drift.
_TOPDECK_SELECTION_SWEEP_REGEX = TOPDECK_SELECTION_REGEX
# ADR-0027 per-clause draw raw (SIDECAR v32): draw_for_each migrated to the Card IR
# (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds the
# serve). The serve pool stays oracle-defined, so it reuses the shared
# DRAW_FOR_EACH_REGEX constant (the EXACT deleted detector regex) — serve and the
# kept-mirror detector never drift.
_DRAW_FOR_EACH_SWEEP_REGEX = DRAW_FOR_EACH_REGEX
# ADR-0027 (tranche2-C): the SWEEP_DETECTORS rows for self_pump / tapper_engine /
# count_anthem are deleted (detection moved to the Card IR). Their SERVE pools stay
# oracle-defined, so the regexes are pinned here verbatim and the specs below reuse
# them (self_pump via _sweep_spec_with_extras(regex=…); tapper_engine / count_anthem
# hand-registered, since the sweep auto-register loop no longer builds them).
_SELF_PUMP_SWEEP_REGEX = (
    r"\{[^}]*\}(?:, \{t\})?: [^.]* gets \+[0-9x]/\+[0-9x] until end of turn"
    r"|\{[wubrgc]\}: [^.:]*gets \+\d+/\+\d+ until end of turn"
    r"|\{[^}]*\}(?:, \{t\})?: put a \+1/\+1 counter on (?:it|this creature|[A-Z][a-z]+)"
)
_TAPPER_ENGINE_SWEEP_REGEX = (
    r":\s*tap (?:target|up to (?:one|two|\d+) target|all|each|two target|x target)"
    r"|(?:at the beginning of|whenever)[^.:]*,[^.]*\btap "
    r"(?:up to (?:one|two|\d+) target|target)"
    r"|\btap up to (?:one|two|\d+) target (?:creature|permanent)\b"
    r"|when [^.]* enters, tap (?:up to )?(?:one|two|\d+|target)"
    r"|(?:doesn't|don't|does not) untap during (?:its|their|the)"
)
_COUNT_ANTHEM_SWEEP_REGEX = (
    r"(?:creatures you control get|each creature you control gets) "
    r"[+]\d+/[+]\d+ for each"
)
# ADR-0027: the SWEEP_DETECTORS rows for tribal_etb_multi / typed_enters_punish are
# deleted (detection moved to the Card IR — an etb trigger with a creature-subtype
# subject / an etb trigger whose consequence burns the opponents). Their SERVE pools
# stay oracle-defined, so the regexes are pinned here verbatim and hand-registered
# below (the sweep auto-register loop no longer builds them).
_TRIBAL_ETB_MULTI_SWEEP_REGEX = (
    r"whenever [^.]*or another [A-Z][a-z]+(?:, [A-Z][a-z]+)*,? "
    r"(?:or [A-Z][a-z]+ )?enters"
)
_TYPED_ENTERS_PUNISH_SWEEP_REGEX = (
    r"whenever another (?:outlaw|ally|\w+) you control enters, "
    r"[^.]*deals \d+ damage to (?:target opponent|each opponent|any target)"
)
# Paradox (CR 207.2c): "cast a spell / play a card from anywhere other than your hand"
# payoffs (Vega, Iraxxa, Keeper of Secrets). Shared by cast_from_exile AND
# impulse_top_play: an impulse deck casts its exiled cards, which IS "from anywhere
# other than your hand", so it fires these payoffs too.
_PARADOX_PAYOFF_ORACLE = (
    r"(?:cast a spell|play a land|play a card)[^.]*?from anywhere other than your hand"
)
_PARADOX_PAYOFF_EXTRA = SubAvenue(
    "Paradox payoffs",
    "zone-agnostic payoffs that reward casting/playing from anywhere other "
    "than your hand",
    {"oracle": r"from anywhere other than your hand"},
    serve=Serve(oracle=re.compile(_PARADOX_PAYOFF_ORACLE, _IC)),
)
# Heroic / targeting enablers: cheap spells that TARGET one of your creatures to fire
# the heroic payoff (Gods Willing, Brute Force, Defiant Strike). They must use "target"
# (CR 115.1a) and BUFF it (gets +/gains) — an "each creature" anthem doesn't target (so
# won't trigger heroic) and targeted REMOVAL ("gets -N/-N", destroy) isn't a self-buff,
# so both stay out.
_TARGETED_BUFF_ORACLE = r"target creature (?:you control )?(?:gets? \+|gains?\b)"
_TARGETED_BUFF_EXTRA = SubAvenue(
    "Single-target pump / protection",
    "cheap spells that target one of your creatures to trigger heroic (Gods Willing / "
    "Brute Force / Defiant Strike)",
    {"oracle": _TARGETED_BUFF_ORACLE},
    serve=Serve(oracle=re.compile(_TARGETED_BUFF_ORACLE, _IC)),
)
_PUMP_EXTRA = SubAvenue(
    "Combat tricks / pump",
    "instant-speed pump to push extra combat damage through and survive blocks",
    {"oracle": _PUMP_ORACLE},
    serve=Serve(oracle=re.compile(_PUMP_ORACLE, _IC)),
)
# Damage / life-loss AMPLIFIERS — a commander that deals combat damage to opponents
# wants its damage doubled (Gratuitous Violence, Furnace of Rath, Angrath's Marauders,
# Gisela) or the resulting life loss reflected back (Wound Reflection, Fiendish Duo).
# Combat damage IS life loss, so these are the payoff a combat-damage-to-opponents deck
# is built to exploit.
_DAMAGE_AMPLIFIER_ORACLE = (
    r"loses? life equal to the life [^.]*lost this turn"
    r"|would deal damage[^.]*(?:deals?|that source deals?) (?:double|twice)"
    r"|deals? double that (?:much )?damage"
    r"|deals? (?:that much|twice that much) damage to that "
    r"(?:player|creature'?s controller)"
    # Pinged-to-the-whole-table amplifiers (Kediss, Hydra Omnivore, Kosei, Imodane):
    # "deals that much damage to each (other) opponent" copies your combat damage onto
    # every opponent — the same push-through amplifier role for a multiplayer board.
    r"|deals? that much damage to each (?:other )?opponent"
    # Granting DOUBLE STRIKE doubles the combat damage (and the combat-damage triggers)
    # you push through — the same amplifier role (Duelist's Heritage, Berserkers'
    # Onslaught). Keyed on the GRANT ("gains/have double strike"), so a bare vanilla
    # double-striker's keyword line ("Double strike") isn't mistaken for an amplifier.
    r"|(?:gains?|have) double strike"
)
_DAMAGE_AMPLIFIER_EXTRA = SubAvenue(
    "Damage / life-loss amplifiers",
    "doublers that magnify the damage and life loss you push through (Gratuitous "
    "Violence, Furnace of Rath, Wound Reflection, Fiendish Duo)",
    {"oracle": _DAMAGE_AMPLIFIER_ORACLE},
    serve=Serve(oracle=re.compile(_DAMAGE_AMPLIFIER_ORACLE, _IC)),
)
# Stacking cost reducers: a commander whose own text makes spells cost less (Stenn,
# Thryx, Danitha, Umori) wants to STACK more category reducers (Cloud Key, Etherium
# Sculptor, Helm of Awakening, Semblance Anvil) to go off — the cost_reduction lane
# otherwise serves only the expensive bombs that EXPLOIT the discount, not the reducers
# that compound it. Matches "<your/type> spells … cost {N} less"; the plural "spells"
# excludes the self-only "this spell costs {X} less" (Ghalta), and "less" (not "more")
# excludes the cost-increase taxes.
_COST_REDUCER_ORACLE = r"\bspells\b[^.]{0,50}?\bcost \{?\d+\}? less"
_COST_REDUCER_EXTRA = SubAvenue(
    "Stack more cost reducers",
    "category cost reducers that compound your discount to go off (Cloud Key, Etherium "
    "Sculptor, Helm of Awakening, Baral)",
    {"oracle": _COST_REDUCER_ORACLE},
    serve=Serve(oracle=re.compile(_COST_REDUCER_ORACLE, _IC)),
)
# Protecting the single suited-up threat IS the voltron support package (Mother of
# Runes, Bastion Protector, Avacyn, Vexilus Praetor are top-synergy on EDHREC for
# voltron commanders). Gate on GRANTING a shield keyword — hexproof / shroud /
# protection / indestructible / "can't be the target" — to a creature/permanent YOU
# control. Plain anthems (flying, +1/+1) never match: the keyword list is shield-only.
_VOLTRON_PROTECT_ORACLE = (
    r"(?:target creature|equipped creature|enchanted creature|creatures? you control"
    r"|permanents? you control|commanders? (?:creatures? )?you control)"
    r"[^.]{0,40}(?:gains?|have|has|get)[^.]{0,25}"
    r"(?:hexproof|shroud|indestructible|protection)"
    r"|(?:target creature|creature you control|it) can't be (?:the )?target"
)
_VOLTRON_PROTECT_EXTRA = SubAvenue(
    "Protect the suited-up threat",
    "hexproof / protection / indestructible granters that keep your one big threat "
    "alive through removal (Mother of Runes / Bastion Protector / Avacyn)",
    {"oracle": _VOLTRON_PROTECT_ORACLE},
    serve=Serve(oracle=re.compile(_VOLTRON_PROTECT_ORACLE, _IC)),
)
# Creature cost reducers (Goreclaw, Cloud Key for creatures) for a creature-cast /
# ramp-into-fatties deck — they make every creature spell cheaper.
_CREATURE_COST_ORACLE = (
    r"creature spells? you cast[^.]*\bcost\b|creature spells? cost \{?\d"
)
_CREATURE_COST_EXTRA = SubAvenue(
    "Creature cost reducers",
    "cards that make your creature spells cheaper so you deploy threats faster "
    "(Goreclaw)",
    {"oracle": _CREATURE_COST_ORACLE},
    serve=Serve(oracle=re.compile(_CREATURE_COST_ORACLE, _IC)),
)
# Power-as-damage payoffs: convert a big/pumped creature's power into damage (Fling,
# Chandra's Ignition, Soul's Fire). Matches single-target AND board-sweep forms — the
# mined fling regex only had single-target ("to any target"), missing Ignition's "to
# each other creature and player".
_POWER_FLING_ORACLE = r"deals? damage equal to (?:its|that creature's|[^.]{0,30}) power"
_POWER_FLING_EXTRA = SubAvenue(
    "Power-as-damage payoffs",
    "fling effects that turn your big creature's power into damage (Fling / Chandra's "
    "Ignition / Soul's Fire)",
    {"oracle": _POWER_FLING_ORACLE},
    serve=Serve(oracle=re.compile(_POWER_FLING_ORACLE, _IC)),
)
# Force-block effects for a "becomes blocked" payoff commander (General Marhault
# Elsdragon: +3/+3 for each creature blocking the attacker). Forcing every able
# creature to block MAXES the per-blocker bonus (CR 509.1c). The canonical Lure phrase
# is "all creatures able to block … do so"; Provoke (CR 702.39) forces a single block.
_LURE_ORACLE = r"able to block [^.]*?\bdo so\b"
_LURE_EXTRA = SubAvenue(
    "Force blocks (Lure)",
    "effects that force opponents' creatures to block your attacker, maxing a "
    '"becomes blocked" payoff (Lure / Nemesis Mask / Roar of Challenge)',
    {"oracle": _LURE_ORACLE},
    serve=Serve(oracle=re.compile(_LURE_ORACLE, _IC), keywords=frozenset({"provoke"})),
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
_CHOSEN_TYPE_ORACLE = r"choose a (?:creature|kindred) type"
# The redirect-instrument idiom set (task B-4), shared by the target_redirect
# payoff spec and the spell_redirect doer spec — one home (verified-review
# F9), so widening an alternate can never split the two specs.
_REDIRECT_SERVE_ORACLE = (
    r"change (?:a|the) target of target spell or ability"
    r"|change (?:the|a) target of target spell"
    r"|change (?:that|the) spell'?s target to"
    r"|new target.{0,30}this (?:creature|permanent)"
    r"|choose new targets for target\b"
)


