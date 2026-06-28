"""Signal specs: how each scoped signal maps to cards that FEED it.

For every signal the engine recognizes, a ``SignalSpec`` carries:
  - a human ``label`` + an ``avenue`` blurb (the exploration-avenue text),
  - a ``search`` fragment (``card_search`` kwargs that FIND enablers in-identity),
  - a ``serve`` regex (does a given card oracle feed this signal?).

Scope drives the discriminator that matters most: an *opponents'-graveyard* signal
is fed by milling opponents, not yourself — so self-mill does not register as
serving it. This is the deterministic encoding of the Tinybones guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._sweep_detectors import (
    ABILITY_COPY_REGEX,
    ANIMATE_ARTIFACT_REGEX,
    BASE_PT_SET_REGEX,
    BLOCKED_MATTERS_REGEX,
    COMBAT_BUFF_ENGINE_SWEEP_REGEX,
    COMBAT_DAMAGE_TO_CREATURE_REGEX,
    COMBAT_DAMAGE_TO_OPP_REGEX,
    COPY_LIMIT_REGEX,
    COUNTER_DISTRIBUTE_SERVE_REGEX,
    CREATURE_PING_REGEX,
    DAMAGE_EQUAL_POWER_REGEX,
    DAMAGE_PREVENTION_REGEX,
    DEBUFF_SWEEP_REGEX,
    DIES_RECURSION_REGEX,
    DIG_UNTIL_REGEX,
    DISCARD_OUTLET_REGEX,
    DRAW_FOR_EACH_REGEX,
    FLASH_GRANT_REGEX,
    FORCED_ATTACK_SWEEP_REGEX,
    FREE_CAST_REGEX,
    GLOBAL_ABILITY_GRANT_REGEX,
    GROUP_HUG_DRAW_REGEX,
    KEYWORD_COUNTER_REGEX,
    KEYWORD_GRANT_TARGET_REGEX,
    LURE_MATTERS_REGEX,
    NAMED_PERMANENT_REGEX,
    NONCOMBAT_DAMAGE_PAYOFF_REGEX,
    NONCREATURE_CAST_PUNISH_REGEX,
    OPPONENT_COUNTER_GRANT_REGEX,
    PROTECTION_GRANT_REGEX,
    PUMP_MATTERS_REGEX,
    SCALING_PUMP_SWEEP_REGEX,
    SELF_COUNTER_GROW_SWEEP_REGEX,
    SPELL_KEYWORD_GRANT_REGEX,
    STATION_MATTERS_REGEX,
    STICKERS_MATTER_REGEX,
    SWEEP_DETECTORS,
    SWEEP_LABELS,
    TAP_DOWN_REGEX,
    TARGET_PLAYER_DRAWS_REGEX,
    THEFT_MATTERS_REGEX,
    TOPDECK_SELECTION_REGEX,
    TOPDECK_STACK_SWEEP_REGEX,
    TOUGHNESS_COMBAT_REGEX,
    TRIBE_DAMAGE_TRIGGER_REGEX,
    UNSPENT_MANA_REGEX,
    VARIABLE_PT_SWEEP_REGEX,
    VOID_WARP_MATTERS_REGEX,
)
from mtg_utils.card_classify import (
    card_pt_int,
    classifying_type_line,
    get_oracle_text,
)

if TYPE_CHECKING:
    from mtg_utils._deck_forge.signals import Signal

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
      - ``types``: type-line words (lowercased substring, mirroring ``card_search``'s
        ``card_type``) — ``{"instant", "sorcery"}`` is the gate the bare ``draw a
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
        type_line = classifying_type_line(card).lower()
        if self.types and any(t in type_line for t in self.types):
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
        return (
            self.min_devotion is not None
            and "instant" not in type_line
            and "sorcery" not in type_line
            and _max_color_pips(card.get("mana_cost") or "") >= self.min_devotion
        )

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


SPECS: dict[tuple[str, str], SignalSpec] = {
    ("creature_etb", "you"): _spec(
        "Creatures entering — yours",
        "cheap ways to flood your board with creatures",
        {
            "oracle": (
                r"create .*creature token"
                r"|put .*creature card.*onto the battlefield"
            )
        },
        (r"create .*creature token|put .*creature.*onto the battlefield"),
        # An ETB commander wants the high-value ETB creatures and the doublers, not just
        # the punisher payoffs — same extras the blink lane uses (A3).
        extras=(
            _ETB_PAYOFF_EXTRA,
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _TRIGGER_COPY_EXTRA,
            _FLICKER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
    ),
    # Serve was `opponent.*creature.*enters` — which requires "opponent" BEFORE
    # "creature", so it matched Bloodthirst ("an opponent was dealt damage … this
    # creature enters") and MISSED the real punisher, "a creature an opponent controls
    # enters" (creature before opponent). Align serve to the (correct) search anchor.
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        {"oracle": r"whenever a creature an opponent controls enters"},
        r"creature an opponent controls enters"
        r"|creatures? your opponents control enter",
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
        {"oracle": r"create .*creature token"},
        # Also credit team anthems ("creatures you control have/gain …"), token anthems
        # (Intangible Virtue: "creature tokens you control get …"), and the ETB-value
        # creatures a creatures deck fills its board with.
        r"create .*creature token|creatures you control (?:get|have|gain)"
        r"|(?:creature )?tokens? you control (?:get|have|gain)"
        # Board-scaling lord: a creature that "gets +X/+Y for each other creature
        # you control" (Leonardo, Big Brother) — a go-wide payoff that grows wide.
        r"|gets \+[0-9x]+/\+[0-9x]+ for each other creature you control"
        # Creature-spell cost reducers (Goreclaw, Herald's Horn, the Monuments) let a
        # creatures deck deploy more bodies; board-scaled finishers (Ghalta) are what it
        # casts off a wide board. Both are creatures-deck enablers/payoffs.
        r"|creature spells? (?:you cast )?[^.]*cost \{?\d+\}?(?:\{[wubrgc]\})* less"
        r"|costs? \{x\} less to cast, where x is the (?:total |greatest )?power",
        # A go-wide board full of creature ETBs also wants the doubler (Panharmonicon).
        extras=(_ETB_PAYOFF_EXTRA, _ETB_VALUE_EXTRA, _ETB_DOUBLER_EXTRA),
    ),
    # Creature-recursion engine (Hua Tuo, Adun, Othelm): repeatably return/put a
    # creature card from your graveyard. Wants loop fuel — SELF-SACRIFICING creatures
    # (the sac is value AND refuels the graveyard, Spore Frog), ETB-value bodies, and
    # self-recur fodder. The full self-sac pool is on-theme (like a tribe), not
    # over-broad: the LANE is narrow (~21 recursion commanders).
    ("creature_recursion", "you"): _spec(
        "Creature recursion",
        "loop fuel for a graveyard creature-recursion engine — self-sacrificing "
        "creatures, ETB-value bodies, and self-recurring fodder",
        {"oracle": _SELF_SAC_CREATURE_ORACLE},
        _SELF_SAC_CREATURE_ORACLE,
        extras=(_SELF_SAC_CREATURE_EXTRA, _ETB_VALUE_EXTRA, _SELF_RECUR_EXTRA),
    ),
    # Power matters (CR 208): a commander whose engine keys on creature POWER — cost
    # reduction by total/greatest power (Ghalta) or a power-N-or-greater threshold
    # (Goreclaw, Gargos). The structured `power_min` serve credits genuine big bodies
    # regardless of oracle text; the search proxies them by high CMC (no `power` search
    # key exists). serve_power_min=4 = the canonical Goreclaw "power 4 or greater".
    ("power_matters", "you"): _spec(
        "Big creatures / power matters",
        "high-power bodies to exploit your power-based payoffs (cost reduction, "
        "power thresholds) — big beaters, not utility dorks",
        {"card_type": "Creature", "cmc_min": 5},
        # Credit the power-threshold PAYOFFS/enablers too (Garruk's Uprising, ferocious
        # dorks: "creature with power 4 or greater"), not just the big bodies.
        r"power \d+ or (?:greater|more)|with power \d+ or|\bferocious\b",
        serve_power_min=4,
        extras=(_POWER_FLING_EXTRA,),
    ),
    # Land-creatures theme (e.g. Jyoti, Moag Ancient). Three precise, disjoint
    # angles — proven clean against bulk so a Plant-token maker (Avenger) or a
    # clone (Silent Hallcreeper) is never surfaced:
    #   main   — creature-lands: a Land that "becomes a … creature" (manlands)
    #   extra  — payoffs: cards that reference "land creature(s)" (anthems)
    #   extra  — animators: effects that turn YOUR lands into creatures
    ("land_creatures_matter", "you"): _spec(
        "Creature-lands",
        "lands that are or become creatures — the backbone of a land-creatures deck",
        {"card_type": "Land", "oracle": r"becomes a [^.]*creature"},
        r"\bland creatures?\b",
        extras=(
            SubAvenue(
                "Land-creature payoffs",
                "anthems and abilities that specifically pump land creatures",
                {"oracle": r"\bland creatures?\b"},
            ),
            SubAvenue(
                "Animate your lands",
                "effects that turn lands you control into creatures",
                # second alt catches mass animators that name the land type
                # directly ("All Forests ... are 1/1 ... creatures" - Life and
                # Limb, Living Plane), the Yedora-Forest-lands payoff.
                {
                    "oracle": r"(?:lands?|forests?) you control[^.]*become[^.]*creature"
                    r"|all (?:lands?|forests?)[^.]*(?:are|become)[^.]*creature"
                },
            ),
            SubAvenue(
                "Forest-bounce untap engines",
                # Quirion/Scryb Ranger family: bounce a Forest/land you control
                # to untap a creature -- or, with Oboro Breezecaller, an animated
                # land, re-tapping it for mana. Narrow but real in forest-animation
                # decks; the bounce cost is the precision gate (a plain {T}: untap
                # is not this).
                "bounce a Forest/land you control to untap a creature or land",
                {
                    "oracle": r"return a (?:forest|land) you control to its "
                    r"owner's hand[^.]*untap"
                },
            ),
        ),
    ),
    # Widen to recover graveyard-HATE payoffs (exile an opponent's graveyard, count
    # cards in opponents' graveyards) the mill-only serve missed — still scoped to
    # OPPONENTS (self-mill never qualifies, the Tinybones guard).
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"(?:each opponent|target opponent|an opponent|that player|target player"
        # "each player mills" is SYMMETRIC mill — it fills opponents' graveyards too
        # (Breach the Multiverse, Dread Summons, Syr Konrad fuel).
        r"|each player) mills"
        r"|opponent[^.]*\bmill|mill[^.]*opponent"
        r"|exile (?:target player'?s?|each opponent'?s?|a) graveyard"
        r"|(?:cards?|creature cards?)[^.]*in [^.]*opponents'? graveyards?"
        r"|each opponent'?s graveyard"
        # Reanimation/cast that pulls from ANOTHER player's graveyard — "[creature card]
        # in/from a/each/target/that player's (or opponent's) graveyard" (Sepulchral /
        # Diluvian Primordial, Ink-Eyes, Breach the Multiverse). The opponent-graveyard
        # reanimator (Tariel, Valgavoth) wants these; anchored to a player/opponent
        # graveyard so a self-graveyard reanimator ("from your graveyard") stays out.
        r"|(?:creature|planeswalker|permanent|those|that)[^.]*"
        r"\b(?:in|from) (?:a|each|target|that) (?:player|opponent)(?:'?s)? graveyard"
        # Exile-mill artifacts (Pyxis, Mesmeric Orb-style): a player-subject exiling the
        # top of a LIBRARY is an exile-mill enabler (Circu).
        r"|(?:each player|target player|an opponent|each opponent|that player)"
        r"[^.]*exiles?[^.]*\blibrar"
        # Old reveal-mill (Mind Funeral, Mind Grind, Telemin Performance, Mirko's own
        # ability): "reveals cards from the top of THEIR library until … then puts them
        # into their graveyard" — pre-keyword mill that never says "mills". Anchored on
        # an opponent-owned library ("their/that player's/each opponent's") so a self-
        # mill ("from YOUR library", Avenging Druid) stays out of the opponents lane.
        r"|reveals? cards? from the top of "
        r"(?:their|that player'?s?|each opponent'?s?) library until"
        r"[\s\S]{0,140}?\bput[\s\S]{0,70}?graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard, plus the high-ETB and "
        "self-recurring creatures worth putting there and bringing back",
        {"oracle": r"into your graveyard|surveil"},
        # "in your graveyard" catches recursion spells that pick a target there before
        # returning it (Victimize: "creature cards in your graveyard … return those").
        r"into your graveyard|from your graveyard|in your graveyard"
        r"|surveil\b|self-mill",
        # A graveyard/reanimator deck recurs creatures with strong ETBs (Fleshbag
        # Marauder, Eternal Witness), self-recurring fodder (Gravecrawler), and
        # self-sacrificing creatures it loops for repeated value (Spore Frog).
        extras=(_ETB_VALUE_EXTRA, _SELF_RECUR_EXTRA, _SELF_SAC_CREATURE_EXTRA),
        # Cards whose graveyard mechanic is a KEYWORD (reminder text, stripped) — every
        # one uses your graveyard, so a graveyard deck wants them (CR 702.x).
        serve_keywords=(
            "dredge",
            "flashback",
            "jump-start",
            "retrace",
            "aftermath",
            "encore",
            "escape",
            "disturb",
            "unearth",
            "embalm",
            "eternalize",
            "scavenge",
            "recover",
            "soulshift",
            "delve",
            "gravestorm",
            "haunt",
        ),
    ),
    # The PAYOFF that pairs with the FUEL above: reanimation effects + cast-from-grave
    # creatures, because Celes-style commanders reward a creature re-entering play from
    # the graveyard, not merely a full graveyard. See _REANIMATE_ORACLE above.
    ("reanimator", "you"): _spec(
        "Reanimation",
        "reanimation effects that return a creature from your graveyard to the "
        "battlefield — each one fires your payoff and you choose the target",
        {"oracle": _REANIMATE_ORACLE},
        _REANIMATOR_SERVE_ORACLE,
        # persist/undying (CR 702.79/702.93) return the creature FROM THE GRAVEYARD on
        # death, so it re-enters from a graveyard and fires the reanimator payoff.
        serve_keywords=("escape", "disturb", "persist", "undying"),
        serve_self_recur=True,
        # A reanimator deck wants the high-ETB creatures it reanimates (Mulldrifter,
        # Plaguecrafter), not just the reanimation spells.
        extras=(_CAST_FROM_GY_EXTRA, _SELF_RECUR_EXTRA, _ETB_VALUE_EXTRA),
    ),
    # Lifegain. The bare `lifelink` oracle word matched any card listing it (Crystalline
    # Giant's random-counter menu, reminder text). Lifelink is a keyword (CR 702.15), so
    # gate on keywords[]; a card that GRANTS lifelink to the team still serves via the
    # grant oracle branch. Keep the actual gain-life clauses.
    ("lifegain_matters", "you"): _spec(
        "Lifegain",
        "incidental and repeatable lifegain",
        {"oracle": r"gain .* life"},
        r"gain \d+ life|gain x life|gains? [^.]*\blife\b"
        r"|whenever[^.]*gain[^.]*life"
        r"|(?:creatures? you control|enchanted creature|equipped creature|they)"
        r"[^.]*\blifelink\b|(?:gain|gains|have|has) lifelink",
        serve_keywords=("lifelink",),
    ),
    ("plus_one_matters", "any"): _spec(
        "+1/+1 counters",
        "counter generators, doublers, and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        # Credit generic-counter doublers (Doubling Season) the bare "+1/+1 counter"
        # serve missed.
        r"\+1/\+1 counter|proliferate|" + _COUNTER_DOUBLER_ORACLE,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _KEYWORD_COUNTER_EXTRA,
            _COUNTER_KEYWORD_EXTRA,
            _PROLIFERATE_EXTRA,
            _COUNTER_RESILIENCE_EXTRA,
        ),
    ),
    # ADR-0027 — any_counter_matters: the KIND-AGNOSTIC counter lane (CR 701.34a —
    # proliferate adds "one counter of each kind already there", so it cares about
    # counters generically). The "has any counter" / "for each counter on" / move-
    # double-remove-a-counter payoffs (Bulwark Ox, Innkeeper's Talent, Iroh, Cleopatra,
    # The Swarmlord) want proliferate, counter-doublers, and any-kind counter sources,
    # NOT only +1/+1. Distinct from plus_one_matters (the +1/+1-specific lane) and the
    # per-kind oil/rad/named lanes. CR 122.1 / 701.34a.
    ("any_counter_matters", "you"): _spec(
        "Any counters",
        "proliferate, counter doublers, and any-counter sources",
        {"oracle": r"proliferate|for each counter|move .* counter|\bcounter on\b"},
        r"proliferate|for each counter on|" + _COUNTER_DOUBLER_ORACLE,
        extras=(
            _COUNTER_DOUBLER_EXTRA,
            _PROLIFERATE_EXTRA,
        ),
    ),
    # Hand spec (overrides the mined sweep detector) so the avenue can fan out a
    # dedicated "Flip fixing" sub-avenue. The flat coin-flip search returns ~60 generic
    # "flip a coin" payoffs and buries Krark's-Thumb-style fixers past the package cap,
    # even though fixing flips is the whole point of a coin-flip deck.
    ("coin_flip", "any"): _spec(
        "Coin flips",
        "coin-flip payoffs and outlets",
        {
            "oracle": (
                r"flip a coin|flip (?:two|three|\d+) coins"
                r"|flip (?:one or more|a number of) coins"
                r"|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip"
                r"|come up heads"
            )
        },
        (
            r"flip a coin|flip (?:two|three|\d+) coins"
            r"|flip (?:one or more|a number of) coins"
            r"|wins? (?:the|a) (?:coin )?flip|lose (?:the|a) (?:coin )?flip"
            r"|come up heads"
        ),
        extras=(
            # A flip FIXER either re-flips/ignores (the Krark's Thumb family) or
            # declaratively GRANTS the result ("come up heads AND you win", Edgar). The
            # bare branches `come up heads` / `you win … flip` (e21b7d6) wrongly caught
            # PAYOFFS that reference a flip result as a CONDITION: Mana Clash ("come up
            # heads on the same flip"), Two-Headed Giant ("if both come up heads"),
            # Squee's Revenge ("if you win all the flips, draw"). A regex can't separate
            # a grant from a condition, so we match only the declarative grant. Verified
            # against bulk: this yields EXACTLY {Krark's Thumb, Edgar}.
            SubAvenue(
                "Flip fixing",
                "cards that bias, repeat, or ignore unfavorable coin flips "
                "(Krark's Thumb effects)",
                {
                    "oracle": (
                        r"instead flip [^.]*coin|\breflip"
                        r"|flip [^.]*coins? again|flip an additional coin"
                        r"|come up heads and you win"
                    )
                },
            ),
        ),
    ),
    ("draw_matters", "you"): _spec(
        "Draw triggers / wheels",
        "draw-trigger payoffs and extra-draw engines (Nekusar / Chasm Skulker space)",
        {"oracle": r"whenever you draw|draw an additional card"},
        r"whenever you draw|draws? (?:your )?(?:second|an additional) card",
    ),
    # Spellslinger. A card FEEDS this iff casting it is "casting an instant or sorcery"
    # — fixed by its TYPE (CR 601.2), OR it has prowess (CR 702.108a, a keyword payoff),
    # OR it carries a magecraft / "whenever you cast a (noncreature|instant|sorcery)
    # spell" trigger (magecraft is an ability word — CR 207.2c — so it lives ONLY in
    # prose). Bare "draw a card" is none of these: it mislabeled ~1250 value permanents
    # (Rhystic Study, Esper Sentinel, The One Ring) as Spellslinger. Copies aren't cast
    # (CR 707.10), so spell-copy payoffs belong to spell_copy, not here.
    ("spellcast_matters", "you"): _SPELLSLINGER_SPEC,
    # `create .*token` was type-blind — it served every Treasure/Clue/Food maker
    # (~428 in WBR), none of which are sacrifice fodder. Require the literal "creature
    # token" (CR 111.10 token types); and exclude "sacrifice a land" (fetchlands) from
    # the outlet branch.
    ("sacrifice_outlets", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create [^.]*creature token|sacrifice"},
        # Also credit the death-DRAIN payoff: a sac deck wants Blood Artist / Zulaport,
        # which trigger on creatures dying, not on the act of sacrificing. "sacrifices?"
        # (3rd person) also catches edicts ("each player sacrifices a creature").
        r"create [^.]*creature token|sacrifices? (?:a|an|another)(?! land\b)"
        r"|whenever [^.]*\bdies\b"
        r"|whenever [^.]*(?:creatures?|permanents?|tokens?|they) die\b"
        # Death-VALUE fodder: a permanent that replaces itself when it dies / is put
        # into a graveyard (Ichor Wellspring, Filigree Familiar, Mycosynth Wellspring).
        # Keyed on "dies"/"put into a graveyard" + a value verb — artifacts use "put
        # into a graveyard" (not "dies"), "When … dies" isn't "whenever". (Audit:
        # Sacrifice lane, 9.2x lift.)
        r"|(?:dies|put into a graveyard)[^.]{0,45}?"
        r"(?:draws? (?:a|an|\d+|x)|creates?|investigate|search your library"
        r"|gains? \d+ life)"
        # Death-trigger DOUBLER (Teysa Karlov, Drivnod) — the deaths-Panharmonicon, the
        # aristocrats payoff multiplier. "creature dying" anchors it (ETB doublers say
        # "entering"; the wipe-replacement "if a creature would die" lacks "causes a
        # triggered ability").
        r"|creature dying causes a triggered abilit",
        extras=(
            _SELF_RECUR_EXTRA,
            _DEATH_DRAIN_EXTRA,
            _BOARD_WIPE_EXTRA,
            _SELF_SAC_CREATURE_EXTRA,
            # Dies-return GRANTERS (Feign Death, Supernatural Stamina, Undying Evil):
            # loop a key creature with a sac outlet — core aristocrats fuel.
            _DIES_RECURSION_EXTRA,
        ),
    ),
    # Self-death PAYOFF (Kokusho / Junji / Ryusei / Lord Xander): the commander's OWN
    # "when ~ dies, <value>" trigger is the engine, so it wants to re-fire that death.
    # Serves dies-recursion (return it after the trigger → repeat), sac outlets (kill it
    # on demand), and reanimation (recast). Distinct from death_matters (aristocrats,
    # OTHER creatures dying). Verified: Kokusho/Junji's top EDHREC synergy cards are
    # exactly these dies-return grants.
    ("self_death_payoff", "you"): _spec(
        "Self-death payoff",
        "ways to re-fire your commander's own death trigger — return it after death, "
        "sacrifice it on demand, reanimate it",
        {"oracle": _DIES_RECURSION_ORACLE},
        _DIES_RECURSION_ORACLE,
        extras=(_DIES_RECURSION_EXTRA, _SAC_OUTLET_EXTRA, _REANIMATION_EXTRA),
    ),
    # A forced/symmetric-sacrifice commander (Braids, Endrek Sahr — "each player
    # sacrifices") loses its OWN board too, so it wants recurring fodder to survive:
    # recurring token makers ("create … creature token") and self-recurring creatures
    # (Reassembling Skeleton). The opponent-only-edict half is rare among commanders.
    ("edict_makers", "each"): _spec(
        *SWEEP_LABELS["edict_makers"],
        {"oracle": _EDICT_SWEEP_REGEX},
        _EDICT_SWEEP_REGEX + r"|create [^.]*creature token",
        extras=(_SELF_RECUR_EXTRA, _DEATH_DRAIN_EXTRA),
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create [^.]*creature token|whenever .* dies"},
        r"create [^.]*creature token|sacrifices? (?:a|an|another)(?! land\b)"
        r"|whenever .* dies"
        r"|whenever [^.]*(?:creatures?|permanents?|tokens?|they) die\b"
        # Death-trigger DOUBLER (Teysa Karlov, Drivnod) — see sacrifice_outlets.
        r"|creature dying causes a triggered abilit",
        extras=(
            _SELF_RECUR_EXTRA,
            _DEATH_DRAIN_EXTRA,
            _BOARD_WIPE_EXTRA,
            _SELF_SAC_CREATURE_EXTRA,
            # Dies-return granters (Feign Death, Undying Evil) — aristocrats loop fuel.
            _DIES_RECURSION_EXTRA,
        ),
    ),
    # The bare word `haste` matched its reminder text and incidental mentions ("loses
    # haste"). Gate on the Haste keyword (CR 702.10) + the team-grant phrasing; anchor
    # the token branch to the literal "creature token".
    # The serve once credited only haste-grant + token-makers — 40/223 (18%) of the
    # attack-trigger payoff axis. Widen with the "whenever you attack" / "whenever a
    # creature you control attacks" alternation (CR 508 declare-attackers triggers) so
    # the avenue surfaces attack-trigger payoffs (Hellrider, Adeline, Shared Animosity),
    # not just speed. Anchored on "you attack" / "you control attacks" so a defensive
    # "whenever a creature attacks you" trigger never matches.
    ("attack_matters", "you"): _spec(
        "Combat",
        "attack-trigger payoffs, haste enablers, and aggressive bodies",
        {
            "oracle": r"haste|create .*creature token"
            r"|whenever you attack|you control attacks"
        },
        r"(?:gains?|gain|have|has) haste|create [^.]*creature token"
        r"|whenever you attack\b"
        r"|whenever (?:a|an|another|one or more)[^.]*creatures? you control attacks?"
        # Single-creature attack triggers + combat-damage riders are the aggro payoff
        # bodies (Vicious Conquistador, Hellrider); "(?! you)" keeps defensive
        # "attacks you" triggers out.
        r"|whenever [^.]*\battacks\b(?! you)"
        r"|whenever [^.]*deals combat damage to "
        r"(?:a player|an opponent|each opponent|that player)"
        # Combat keyword-anthems that buff your attackers (Blade Historian, Odric:
        # "attacking creatures you control have double strike" / "gain first strike").
        r"|(?:attacking )?creatures you control (?:have|gain|get)[^.]*"
        r"(?:double strike|first strike|trample|menace|deathtouch|vigilance"
        r"|indestructible|can't be blocked)"
        # Equipment/Auras suit up the attacker (a combat deck wants the gear).
        r"|equipped creature|enchanted creature gets|\bequip \{"
        # Extra combats (Combat Celebrant, Moraug, Aggravated Assault): every added
        # combat phase is another round of attack triggers — a top attack payoff. The
        # narrow extra_combats lane already served these, but attack-trigger commanders
        # (Winota, Johan, Umaro) open attack_matters, not extra_combats. An extra TURN
        # (Time Warp) is the strict superset — a whole turn, combat included, so the
        # attack replays; Narset (free-casts on attack) snowballs hardest off it.
        r"|additional combat phase"
        r"|takes? (?:an?|two|another|that many)?\s*extra turns?",
        serve_keywords=("haste",),
    ),
    # The bare `onto the battlefield` branch matched every cheat-into-play and
    # reanimation effect (Sneak Attack, Reanimate). Anchor it to a LAND card, mirroring
    # lands_matter (CR 305 — landfall fires on a land entering, not any permanent).
    # The landfall lane wants the PAYOFFS most of all (Lotus Cobra / Scute Swarm /
    # Tatyova — "Landfall — whenever a land you control enters …"), then the enablers
    # that fire them repeatedly: extra land drops (Azusa / Dryad) and land recursion
    # (Crucible / Ramunap — "play lands from your graveyard"). The old serve credited
    # only fetch + extra-lands, so every landfall payoff read as off-theme.
    ("landfall", "you"): _spec(
        "Landfall",
        "landfall payoffs plus the extra land drops, fetch, and recursion firing them",
        {"oracle": _LANDFALL_ORACLE},
        _LANDFALL_ORACLE,
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        # Also credit token ANTHEMS (Intangible Virtue, Cathars' Crusade): "creature
        # tokens you control get/have …" — the go-wide "creatures you control" branch
        # misses the "creature TOKENS" phrasing.
        r"create [^.]*creature token"
        r"|(?:creature )?tokens? you control (?:get|have|gain)",
        # Offspring (CR keyword) makes a 1/1 token copy of the creature — token-making
        # in stripped reminder text, so credit it via the Scryfall keyword.
        serve_keywords=("offspring",),
        extras=(_TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA, _GOWIDE_ANTHEM_EXTRA),
    ),
    ("treasure_matters", "you"): _spec(
        "Treasure",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        r"\btreasure\b",
    ),
    # Pariah combo (Cho-Manno, Anti-Venom): an unkillable commander that prevents damage
    # to itself wants the redirect effects (Pariah / Pariah's Shield: "damage dealt to
    # you is dealt to enchanted/equipped creature instead") plus the indestructible /
    # protection grants that keep the redirect target alive.
    ("damage_redirect", "you"): _spec(
        "Damage redirection",
        "redirect-all-damage effects (Pariah) onto your unkillable creature, damage "
        "prevention to blank it, plus indestructible/protection to keep it alive",
        {"oracle": r"damage that would be dealt to you|prevent [^.]*damage"},
        r"damage that would be dealt to you is dealt to [^.]*creature instead"
        r"|all damage[^.]*dealt to you[^.]*dealt to [^.]*instead"
        # Damage PREVENTION (Battlefield Medic, Worship) blanks the soaked damage — a
        # redirect-to-self commander (Hazduhr, Cho-Manno) wants it.
        r"|prevent (?:the next |all )?[^.]*damage"
        r"|damage that would (?:reduce|be dealt)[^.]*(?:instead|prevented)"
        # PROFIT from the soaked damage: a redirect-to-self commander (Daughter of
        # Autumn) takes the redirected hit HERSELF (CR 614.9 — redirection replacement),
        # so payoffs watching "a creature you control is dealt damage" (Rite of Passage)
        # or an Aura on the soak creature (Druid's Call) fire. NOT generic enrage
        # ("whenever THIS creature is dealt damage") — the original creature is never
        # dealt the redirected damage, so its own trigger can't fire.
        r"|whenever a creature you control is dealt damage"
        r"|whenever enchanted creature is dealt damage",
        extras=(_VOLTRON_PROTECT_EXTRA,),
    ),
    # Vanilla (Ruxa, Muraganda Petroglyphs): creatures with NO rules text (the tribe)
    # plus the "creatures with no abilities" payoffs.
    ("vanilla_matters", "you"): _spec(
        "Vanilla beaters",
        "efficient creatures with no abilities plus the payoffs that reward them",
        {"card_type": "Creature"},
        r"creatures? with no abilities",
        serve_vanilla=True,
    ),
    # Banding (CR 702.21): a banding commander (Ayesha, Jarkeld) wants other banding
    # creatures to form attacking/blocking bands. Keyword[]-anchored + the oracle word.
    ("has_banding", "you"): _spec(
        "Banding",
        "creatures with banding to form attacking and blocking bands",
        {"oracle": r"\bbanding\b"},
        r"\bbands? with other|\bbanding\b",
        serve_keywords=("banding",),
    ),
    # Outlaw tribal (Vial Smasher): the 5 outlaw creature types plus "outlaws you
    # control" anthems/payoffs. (CR: outlaw = Assassin/Mercenary/Pirate/Rogue/Warlock.)
    ("outlaw_matters", "you"): _spec(
        "Outlaws",
        "outlaws (Assassins / Mercenaries / Pirates / Rogues / Warlocks) plus the "
        "anthems and payoffs that reward a board of them",
        {
            "oracle": (
                r"\boutlaws?\b"
                r"|create[s]?[^.]*\b(?:mercenary|pirate|rogue|assassin|warlock)\b"
                r"[^.]*\btoken"
            )
        },
        # ALSO serve outlaw-TOKEN makers ("create a 1/1 red Mercenary token" — those
        # tokens are outlaws) and outlaw RECURSION ("return … outlaw creature cards"),
        # not just cards whose own type line is an outlaw subtype.
        r"\boutlaws? you control\b|another outlaw"
        r"|create[s]?[^.]*\b(?:mercenary|pirate|rogue|assassin|warlock)\b[^.]*\btoken"
        r"|\boutlaw creature cards?\b"
        r"|\b(?:mercenary|pirate|rogue|assassin|warlock) creature cards?\b",
        serve_types=("assassin", "mercenary", "pirate", "rogue", "warlock"),
    ),
    # Snow (Isu the Abominable): snow permanents (Snow type), snow payoffs ("number of
    # snow permanents"), and snow mana. "snow" is essentially only the MTG supertype.
    ("snow_matters", "you"): _spec(
        "Snow",
        "snow permanents, snow lands, and snow-count payoffs",
        {"oracle": r"\bsnow\b"},
        r"\bsnow\b",
        serve_types=("snow",),
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        {"card_type": "Artifact"},
        r"artifacts? you control|for each artifact|\bmetalcraft\b|\baffinity\b"
        r"|artifact spells? you cast cost"
        # Type-GRANTERS that turn your stuff into artifacts enable the whole deck
        # (Mycosynth Lattice, Liquimetal Coating, March of the Machines).
        r"|becomes? an? artifact|(?:are|is an?) artifacts?"
        # Every artifact subtype (CR 205.3g) IS an artifact: makers ("create a Treasure
        # / Vehicle / Equipment … token"), references ("Equipment/Vehicles you control",
        # "for each Treasure"), and Investigate (makes a Clue) all feed artifact-count /
        # affinity / metalcraft.
        r"|create [^.]*\b(?:" + _ART_SUBTYPES + r")\b[^.]*token"
        r"|\b(?:" + _ART_SUBTYPES + r")s? you control\b"
        r"|for each (?:an? )?(?:" + _ART_SUBTYPES + r")\b"
        r"|\binvestigate\b"
        # Artifact dig/tutor: "reveal an artifact card … put it into your hand"
        # (Casey Jones, Glint-Nest Crane, Ingenious Smith) finds the deck's payoffs.
        r"|reveal an artifact card[^.]*put it into your hand",
        # BEING an artifact is on-theme: an artifact-count / affinity / metalcraft deck
        # counts every artifact — lands (Seat of the Synod), rocks (Mind Stone),
        # Equipment, Vehicles — even with no "artifact" in the oracle. The oracle-only
        # serve missed these and wrongly read them as generic "good stuff".
        serve_types=("artifact",),
    ),
    # Serve augmented with "whenever you cast an enchantment" so the 14 plain CREATURES
    # that trigger on enchantment casts (Verduran/Mesa Enchantress, Sythis) — missed by
    # both the {card_type:Enchantment} type-serve and the count regex — are credited.
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b"
        r"|whenever you cast an enchantment"
        # Enchantment-GRANTERS (Enchanted Evening, Nyx: "are enchantments in addition").
        r"|(?:are|is|becomes?) (?:an? )?enchantments? in addition"
        # Every enchantment subtype (CR 205.3h) IS an enchantment: Role/Shard/Aura
        # token makers plus references ("Auras/Sagas you control", "for each Saga",
        # "whenever a Class you control …") all feed constellation / enchantment-count.
        r"|create [^.]*(?:" + _ENCH_SUBTYPES + r"|enchantment)[^.]*token"
        r"|\b(?:" + _ENCH_SUBTYPES + r")s? you control\b"
        r"|for each (?:an? )?(?:" + _ENCH_SUBTYPES + r")\b"
        r"|whenever (?:a|an|another) (?:" + _ENCH_SUBTYPES + r")\b",
        # BEING an enchantment is on-theme: constellation / enchantment-count counts
        # every enchantment (Auras, Sagas, enchantment creatures like Spirited
        # Companion), even with no "enchantment" in the oracle.
        serve_types=("enchantment",),
    ),
    # A color-hoser commander (color_hoser) wants the color-changing "Painter" toolbox
    # so its color payoff (bounce/restrict/punish a named color) applies to EVERY
    # permanent: making opponents' creatures blue makes Llawan's "blue creatures"
    # clauses catch them (color is a layer-5 characteristic the hoser checks: CR 105.2).
    # Serve is the change-a-color toolbox: Painter's Servant ("are the chosen color"),
    # the -lace / -Wisps cycles + Distorting Lens ("becomes the color of your choice"),
    # and the text-changers (Mind Bend / Sleight of Mind / Glamerdye / Alter Reality:
    # "replacing all instances of one color"). Anchored on a CHANGE verb so a
    # protection-from-color trick (Gods Willing) or mana fixer never matches.
    ("color_hoser", "you"): _spec(
        "Color-bending",
        "color-changing 'Painter' cards that force your color payoff onto everything",
        {
            "oracle": r"becomes the color of your choice|are the chosen color"
            r"|replacing all instances of one color"
        },
        r"becomes the color of your choice"
        r"|(?:spell or permanent|permanent or spell|target permanent|target creature) "
        r"becomes (?:white|blue|black|red|green)\b"
        r"|are the chosen color"
        r"|replacing all instances of one color"
        # Anti-color HATE is what these commanders (Major Teroh, Ascendant Evincar,
        # Crovax, Dromar, Llawan) actually want — make/keep everything a color, then
        # hose it. Only the 6 color_hoser commanders open the lane, so the narrow
        # color-hate stays scoped to the decks that exploit it.
        r"|(?:destroy|exile|return) all (?:non)?(?:white|blue|black|red|green) "
        r"(?:creature|permanent)s?"
        r"|protection from (?:white|blue|black|red|green)"
        r"|(?:white|blue|black|red|green) creatures? can't (?:attack|block|be)"
        r"|can't cast (?:white|blue|black|red|green)",
    ),
    # ADR-0027: tokens_matter migrated to the Card IR via a byte-identical kept-mirror
    # (the lane fires from _TOKENS_MATTER_MIRROR in _signals_ir). This serve spec was
    # always hand-registered and independent of the two deleted _HAND_FLOOR producers,
    # so it survives unchanged — its curated SEARCH regex below differs from the
    # detector (the detector's go-wide count-scaler + token-doubler arms are supplied
    # here as the _GOWIDE_*/_TOKEN_DOUBLER_EXTRA avenues instead).
    # The greedy `whenever .*token.*enters` spanned clauses and matched attack-trigger
    # token-makers and NONtoken-ETB payoffs (Darksteel Splicer). Anchor the entering
    # object to a token in the SAME clause.
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b"
        r"|whenever (?:a|one or more|another)[^.]*?\btokens?\b[^.]*?\benters\b"
        r"|\bpopulate\b"
        # Amass creates or grows an Army CREATURE token (CR 701.47), so an amass card is
        # a token maker (Mouth of Sauron / Grishnákh want the amass package). Like
        # Mobilize, its token-making lives in stripped reminder text, so credit it.
        r"|\bamass\b",
        # NB: GENERIC single-token makers are deliberately NOT in the serve — a single
        # maker is generically good (every deck runs some), not archetype-UNIQUE, so
        # serving all 2315 floods the lane. But MASS makers ("create 2+/X tokens at
        # once" — _GOWIDE_MAKER_EXTRA) ARE the go-wide build-around and kind-agnostic
        # here (this lane has no subject; Leonardo/Adeline count ANY creature), so they
        # belong. They stay OFF the per-subject token_maker lane, where kind matters
        # (Krenko wants Goblin makers, not Saprolings).
        # EXCEPTION: Mobilize is a bounded (~28-card) Warrior-token SWARM keyword whose
        # token-making lives in stripped reminder text — credit the keyword so a
        # Mobilize/go-wide commander (Zurgo) covers the rest of its swarm package.
        serve_keywords=("mobilize",),
        extras=(
            _TOKEN_DOUBLER_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _GOWIDE_ANTHEM_EXTRA,
            _GOWIDE_MAKER_EXTRA,
            _TEAM_PROTECT_EXTRA,
        ),
    ),
    # The bare `your opponents` alternative matched any card that merely names opponents
    # (Edric's draw trigger, Telepathy's hand reveal). Serve the actual restriction/tax
    # SHAPES instead (CR 601.2f cost increases, prohibitions) — which also recovers the
    # symmetric taxes the old regex missed (Thalia: "Noncreature spells cost {1} more").
    ("stax_taxes", "opponents"): _spec(
        "Stax & taxes",
        "tax and restriction effects — opponent taxes, symmetric locks, and hatebears",
        {
            "oracle": (
                r"opponents? can't"
                r"|spells your opponents cast cost"
                r"|creatures your opponents control"
            )
        },
        _STAX_SERVE_ORACLE,
    ),
    # Symmetric-stax commander (Hokori, Winter Orb-style locks): wants the SAME stax
    # piece pool — it runs opponent-taxes + symmetric locks + hatebears alike. Shares
    # the stax serve; hand-written so the auto-register doesn't bind a narrower one.
    ("symmetric_stax", "each"): _spec(
        "Symmetric stax",
        "stax pieces a symmetric-lock deck runs — taxes, locks, and hatebears",
        {"oracle": r"players? can't|enters?(?: the battlefield)? tapped|can't be"},
        _STAX_SERVE_ORACLE,
    ),
    # ADR-0027: symmetric_damage_each's SWEEP_DETECTORS row was deleted (detection
    # moved to the Card IR — the v22 damage Effect scope=='each' arm + each-player
    # mirror). The serve keeps a board-wide each-everyone regex via regex= (the
    # strangler pattern) so the "sweepers and pingers that hit everyone" pool still
    # surfaces; serve is a SEARCH (find symmetric sweepers/pingers to run alongside),
    # so it intentionally keeps the each-opponent/each-creature reach the DETECTOR
    # split dropped — a Pestilence deck wants Pyrohemia AND Sizzle-style group burn.
    ("symmetric_damage_each", "each"): _sweep_spec_with_extras(
        "symmetric_damage_each",
        regex=(
            r"deals \d+ damage to each (?:player|opponent and|"
            r"creature and each player)"
            r"|deals \d+ damage to each opponent"
            r"|deals \d+ damage to each player"
            r"|deals (?:\d+|x) damage to each (?:creature|nonartifact creature)"
            r"[^.]*and each player"
        ),
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects, the high-ETB creatures worth re-using, and the "
        "doublers that multiply each enter trigger",
        {"preset_names": ("blink",)},
        # Same-sentence "exile … then return … battlefield" (Restoration Angel), PLUS
        # the two-sentence form "exile … . Return it/that/those … battlefield"
        # (Flickerwisp, Charming Prince). The pronoun anchor + single-period limit keep
        # an unrelated exile-removal-then-return-a-land off the lane.
        r"exile[^.]*?return[^.]*?battlefield"
        r"|exile[^.]{0,90}?\.\s*returns? (?:it|them|that|those)[^.]{0,50}?battlefield",
        # Death-return is a distinct mechanic (dies_recursion), offered as its own
        # avenue here — a blink deck re-uses ETBs via death too, but it isn't flicker.
        # Self-bounce recast engines (Whitemane Lion, Kor Skyfisher, Jeskai Barricade)
        # re-fire an ETB by returning your own creature and recasting — staple
        # blink-deck value, so they belong here too.
        extras=(
            _ETB_VALUE_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _DIES_RECURSION_EXTRA,
            _SELF_BOUNCE_EXTRA,
        ),
    ),
    ("mill_makers", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        {"preset_names": ("mill",)},
        r"\bmills?\b",
    ),
    ("goad_makers", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        {"preset_names": ("goad",)},
        r"\bgoad",
        # politics: make yourself a bad target too; force-attack: feed the payoff by
        # making opponents swing (Kazuul rewards being attacked).
        extras=(_PILLOWFORT_EXTRA, _FORCE_ATTACK_EXTRA),
    ),
    # Fog / damage-prevention commanders durdle defensively — pillowfort is a top
    # EDHREC pick for them (4 commanders in the evidence). Keep the mined fog regex
    # (ADR-0027: damage_prevention migrated, SWEEP_DETECTORS row deleted, so pass the
    # pinned DAMAGE_PREVENTION_REGEX explicitly — the serve never drifts from the mine).
    ("damage_prevention", "you"): _sweep_spec_with_extras(
        "damage_prevention",
        (_PILLOWFORT_EXTRA, _DAMAGE_SOAK_EXTRA),
        regex=DAMAGE_PREVENTION_REGEX,
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate plus any-kind counter sources and doublers (Vorinclex)",
        {"preset_names": ("proliferate",)},
        r"\bproliferate\b|(?:poison|loyalty|charge|oil|\+1/\+1) counter",
        extras=(_COUNTER_DOUBLER_EXTRA, _KEYWORD_COUNTER_EXTRA),
    ),
    # Hand-promote EVERY mined +1/+1-counter lane with the shared counters package so a
    # counters commander surfaces sources (Forgotten Ancient), doublers (Hardened
    # Scales), keyword counters, and proliferate no matter which fragmented lane opened.
    # ADR-0027 β: self_counter_grow migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted — a structural SelfRef-marker arm + a narrowed mirror), so the serve keeps
    # the old regex via the pinned SELF_COUNTER_GROW_SWEEP_REGEX (strangler pattern).
    ("self_counter_grow", "you"): _sweep_spec_with_extras(
        "self_counter_grow", _COUNTERS_PACKAGE, regex=SELF_COUNTER_GROW_SWEEP_REGEX
    ),
    # ADR-0027 tranche2-B: counter_manipulation's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — counter_move/remove_counter effects + a kept
    # cost mirror). The serve keeps the old regex via regex= (strangler pattern).
    ("counter_manipulation", "you"): _sweep_spec_with_extras(
        "counter_manipulation",
        _COUNTERS_PACKAGE,
        regex=(
            r"(?:remove|move) (?:a|one|any number of|x|\d+) "
            r"(?:\+1/\+1|-1/-1) counters?|(?:remove|move) "
            r"(?:a|one|any number of|x|\d+) [^.]{0,20}?"
            r"(?:\+1/\+1|-1/-1) counters?"
        ),
    ),
    # ADR-0027 β: counter_distribute's SWEEP_DETECTORS row was deleted (detection moved
    # to the Card IR — the MassEach structural arm + narrowed mirror). The serve keeps a
    # board-wide regex via regex= (the strangler pattern), DROPPING the deleted regex's
    # plain self-enters arm (a self-grower doesn't spread) and ADDING the tribal-mass
    # "each <tribe> you control" form the structural arm catches via PutCounterAll.
    ("counter_distribute", "you"): _sweep_spec_with_extras(
        "counter_distribute",
        _COUNTERS_PACKAGE,
        regex=COUNTER_DISTRIBUTE_SERVE_REGEX,
    ),
    # ADR-0027 tranche2-B: counter_place_trigger's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_added trigger event). The serve
    # keeps the old regex via regex= (strangler pattern).
    ("counter_place_trigger", "you"): _sweep_spec_with_extras(
        "counter_place_trigger",
        _COUNTERS_PACKAGE,
        regex=(
            r"whenever (?:you put|.*put) (?:one or more )?\+1/\+1 counters? on"
            r"|whenever one or more \+1/\+1 counters? (?:are|is) put on"
            r"|whenever you put (?:a|one or more|two|\d+) [^.]*counters? on"
            r"|whenever (?:a|one or more) [^.]*counters? (?:is|are) put on"
        ),
    ),
    # ADR-0027 tranche2-C: keyword_counter's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR); reuse the shared KEYWORD_COUNTER_REGEX for the serve pool.
    ("keyword_counter", "you"): _sweep_spec_with_extras(
        "keyword_counter", _COUNTERS_PACKAGE, regex=KEYWORD_COUNTER_REGEX
    ),
    # ADR-0027 tranche2-B-3: spell_keyword_grant / target_player_draws had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — the whole
    # cast_with_keyword category, and a draw effect with scope=='any'). The SERVE pool
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing each deleted regex (now a shared _sweep_detectors constant).
    ("spell_keyword_grant", "you"): _spec(
        *SWEEP_LABELS["spell_keyword_grant"],
        {"oracle": SPELL_KEYWORD_GRANT_REGEX},
        SPELL_KEYWORD_GRANT_REGEX,
    ),
    # ADR-0027: flash_grant's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a cast_with_keyword{flash} static + the byte-identical FLASH_GRANT_REGEX
    # kept mirror). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing the deleted regex (now the shared
    # FLASH_GRANT_REGEX constant) so the served flash-enabler pool never drifts.
    ("flash_grant", "you"): _spec(
        *SWEEP_LABELS["flash_grant"],
        {"oracle": FLASH_GRANT_REGEX},
        FLASH_GRANT_REGEX,
    ),
    ("target_player_draws", "any"): _spec(
        *SWEEP_LABELS["target_player_draws"],
        {"oracle": TARGET_PLAYER_DRAWS_REGEX},
        TARGET_PLAYER_DRAWS_REGEX,
    ),
    # ADR-0027: group_hug_draw's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a `draw` effect with scope=='each', plus a byte-identical kept word
    # mirror for the 4 cards phase under-structures). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex (now the shared GROUP_HUG_DRAW_REGEX constant)
    # so the served group-hug pool never drifts.
    ("group_hug_draw", "each"): _spec(
        *SWEEP_LABELS["group_hug_draw"],
        {"oracle": GROUP_HUG_DRAW_REGEX},
        GROUP_HUG_DRAW_REGEX,
    ),
    # ADR-0027: dies_recursion's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — the undying/persist keyword bearers via _IR_KEYWORD_MAP plus a
    # byte-identical DIES_RECURSION_REGEX kept word mirror for the bare dies-return
    # grants / keyword-less granters). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex (now the shared DIES_RECURSION_REGEX constant) so the served
    # dies-recursion pool never drifts. CR 700.4 / 603.6c.
    ("dies_recursion", "you"): _spec(
        *SWEEP_LABELS["dies_recursion"],
        {"oracle": DIES_RECURSION_REGEX},
        DIES_RECURSION_REGEX,
    ),
    # Task #19 SPLIT — named_synergy (the named-card SYNERGY half of the old
    # named_permanent lane). Detection lives in the Card IR (a NAMED_PERMANENT_REGEX
    # kept word mirror in signals._IR_KEPT_DETECTORS — phase drops the referenced name).
    # The SERVE pool stays oracle-defined, so hand-register the spec the sweep auto-
    # register loop used to build (scope "you"), reusing NAMED_PERMANENT_REGEX so the
    # served named-card pool never drifts. SWEEP_LABELS keeps the human label. CR 201.4
    # (named references) / 201.5 (self-reference).
    ("named_synergy", "you"): _spec(
        *SWEEP_LABELS["named_synergy"],
        {"oracle": NAMED_PERMANENT_REGEX},
        NAMED_PERMANENT_REGEX,
    ),
    # Task #19 SPLIT — copy_limit (the COPY-LIMIT half, CR 100.2a). Detection is
    # STRUCTURAL (the IR `many_copies` field, read in extract_signals_ir), but the SERVE
    # pool stays oracle-defined: a copy-limit deck wants MORE cards sharing the relaxed
    # name + go-wide-on-one-name payoffs, found by the COPY_LIMIT_REGEX scan ("A deck
    # can have any number of / up to N cards named X"). Scope "you". CR 100.2a.
    ("copy_limit", "you"): _spec(
        *SWEEP_LABELS["copy_limit"],
        {"oracle": COPY_LIMIT_REGEX},
        COPY_LIMIT_REGEX,
    ),
    # ADR-0027: topdeck_stack's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a STRUCTURAL arm over phase's `topdeck_stack` Effect + a byte-identical
    # TOPDECK_STACK_SWEEP_REGEX kept word mirror). The SERVE pool stays oracle-defined,
    # so hand-register the spec the sweep auto-register loop used to build (scope "you",
    # the deleted SWEEP row's scope), reusing the EXACT deleted regex (pinned as
    # TOPDECK_STACK_SWEEP_REGEX) so the served put-on-top pool never drifts.
    # SWEEP_LABELS keeps the human label. CR 401.4.
    ("topdeck_stack", "you"): _spec(
        *SWEEP_LABELS["topdeck_stack"],
        {"oracle": TOPDECK_STACK_SWEEP_REGEX},
        TOPDECK_STACK_SWEEP_REGEX,
    ),
    # ADR-0027 (q2-D3): noncreature_cast_punish's SWEEP_DETECTORS row is deleted
    # (detection moved to the Card IR — a cast_spell trigger scope=='opp' over a
    # noncreature subject, plus a kept word mirror for the symmetric "a player casts"
    # half). The SERVE pool stays oracle-defined, so hand-register the spec the sweep
    # auto-register loop used to build, reusing the deleted regex so the serve pool
    # never drifts. SWEEP_LABELS still carries the human label.
    ("noncreature_cast_punish", "any"): _spec(
        *SWEEP_LABELS["noncreature_cast_punish"],
        {"oracle": NONCREATURE_CAST_PUNISH_REGEX},
        NONCREATURE_CAST_PUNISH_REGEX,
    ),
    # ADR-0027 β: global_ability_grant's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the board_grant + counter_kind="grant_ability" marker read by the
    # extract_signals_ir arm). The SERVE pool stays oracle-defined, so hand-register the
    # spec the sweep auto-register loop used to build (scope "any", the deleted SWEEP
    # row's scope), reusing the EXACT deleted regex (pinned as
    # GLOBAL_ABILITY_GRANT_REGEX) so the serve never drifts. SWEEP_LABELS keeps label.
    ("global_ability_grant", "any"): _spec(
        *SWEEP_LABELS["global_ability_grant"],
        {"oracle": GLOBAL_ABILITY_GRANT_REGEX},
        GLOBAL_ABILITY_GRANT_REGEX,
    ),
    # ADR-0027 β: keyword_grant_target's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR — the single_target_grant marker read by the extract_signals_ir
    # arm). The SERVE pool stays oracle-defined (the creatures worth granting evasion
    # /protection to), so hand-register the spec the sweep loop built (scope
    # "you", the deleted SWEEP row's scope), reusing the EXACT deleted regex (pinned as
    # KEYWORD_GRANT_TARGET_REGEX) so the serve never drifts. SWEEP_LABELS keeps label.
    ("keyword_grant_target", "you"): _spec(
        *SWEEP_LABELS["keyword_grant_target"],
        {"oracle": KEYWORD_GRANT_TARGET_REGEX},
        KEYWORD_GRANT_TARGET_REGEX,
    ),
    # ADR-0027 Cluster D: protection_grant's SWEEP_DETECTORS row is deleted (detection
    # moved to the Card IR — the structural protective-keyword grant arm in
    # extract_signals_ir UNION a byte-identical PROTECTION_GRANT_REGEX kept mirror). The
    # SERVE pool stays oracle-defined (the creatures worth protecting with
    # hexproof/protection), so hand-register the spec the sweep auto-register loop used
    # to build (scope "you", the deleted SWEEP row's scope), reusing the EXACT deleted
    # regex (pinned as PROTECTION_GRANT_REGEX) so the serve never drifts. SWEEP_LABELS
    # keeps the human label.
    ("protection_grant", "you"): _spec(
        *SWEEP_LABELS["protection_grant"],
        {"oracle": PROTECTION_GRANT_REGEX},
        PROTECTION_GRANT_REGEX,
    ),
    # ADR-0027 β: debuff_makers's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the negative-pump (factor<0) / non-self m1m1 structural arm + a
    # byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool stays oracle-defined,
    # so hand-register the spec the sweep auto-register loop used to build (scope "any",
    # the deleted SWEEP row's scope), reusing the EXACT deleted regex (pinned as
    # DEBUFF_SWEEP_REGEX) so the serve pool never drifts. SWEEP_LABELS keeps the label.
    ("debuff_makers", "any"): _spec(
        *SWEEP_LABELS["debuff_makers"],
        {"oracle": DEBUFF_SWEEP_REGEX},
        DEBUFF_SWEEP_REGEX,
    ),
    # ADR-0027 β: pump_makers's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR — a byte-identical _IR_KEPT_DETECTORS mirror; the lane is unstructurable,
    # so no structural arm). The SERVE pool stays oracle-defined, so hand-register the
    # spec the sweep auto-register loop used to build (scope "you", the deleted SWEEP
    # row's scope), reusing the EXACT deleted regex (pinned as PUMP_MATTERS_REGEX, ==
    # _PUMP_ORACLE the _PUMP_EXTRA SubAvenue reuses) so the serve pool never drifts.
    # SWEEP_LABELS keeps the label.
    ("pump_makers", "you"): _spec(
        *SWEEP_LABELS["pump_makers"],
        {"oracle": PUMP_MATTERS_REGEX},
        PUMP_MATTERS_REGEX,
    ),
    # ADR-0027 β: animate_artifact's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR via a byte-identical _ANIMATE_ARTIFACT_MIRROR; no clean structural arm
    # — phase parses "artifacts become creatures" inconsistently as base_pt_set /
    # board_grant / becomes_type, none separable from generic become / type-conferral).
    # The SERVE pool stays oracle-defined, so hand-register the spec the sweep auto-
    # register loop used to build (scope "you", the deleted SWEEP row's scope), reusing
    # the EXACT deleted regex (pinned as ANIMATE_ARTIFACT_REGEX) so the serve pool never
    # drifts. SWEEP_LABELS keeps the label.
    ("animate_artifact", "you"): _spec(
        *SWEEP_LABELS["animate_artifact"],
        {"oracle": ANIMATE_ARTIFACT_REGEX},
        ANIMATE_ARTIFACT_REGEX,
    ),
    # ADR-0027 β: free_cast's SWEEP_DETECTORS row is deleted (detection moved to the
    # Card IR via a byte-identical _FREE_CAST_MIRROR; the IR has no 'free' flag, so no
    # structural arm). The SERVE pool stays oracle-defined, so hand-register the
    # spec the sweep auto-register loop used to build (scope "you"), reusing the EXACT
    # deleted regex (pinned as FREE_CAST_REGEX). SWEEP_LABELS keeps the label.
    ("free_cast", "you"): _spec(
        *SWEEP_LABELS["free_cast"],
        {"oracle": FREE_CAST_REGEX},
        FREE_CAST_REGEX,
    ),
    # ADR-0027 β: tribe_damage_trigger's SWEEP_DETECTORS row is deleted (detection moved
    # to the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build (scope "you", the deleted SWEEP row's scope), reusing the shared
    # TRIBE_DAMAGE_TRIGGER_REGEX so the serve pool never drifts. SWEEP_LABELS still
    # carries the human label.
    ("tribe_damage_trigger", "you"): _spec(
        *SWEEP_LABELS["tribe_damage_trigger"],
        {"oracle": TRIBE_DAMAGE_TRIGGER_REGEX},
        TRIBE_DAMAGE_TRIGGER_REGEX,
    ),
    # ADR-0027 β: timing_control's SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR via a byte-identical _IR_KEPT_DETECTORS mirror). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build (scope "any", the deleted SWEEP row's scope), reusing the deleted regex so
    # the serve pool never drifts. SWEEP_LABELS still carries the human label.
    ("timing_control", "any"): _spec(
        *SWEEP_LABELS["timing_control"],
        {
            "oracle": (
                r"cast spells (?:and activate abilities )?only during their own"
                r"|spells? only any time they could cast a sorcery"
                r"|can cast spells only"
            )
        },
        r"cast spells (?:and activate abilities )?only during their own"
        r"|spells? only any time they could cast a sorcery"
        r"|can cast spells only",
    ),
    # ADR-0027 tranche2-batch-5 (t2b5-B): sacrifice_protection / secret_writedown had
    # their SWEEP_DETECTORS rows deleted (detection moved to the Card IR — kept_detector
    # word mirrors), so the sweep auto-register loop no longer builds their serve. Hand-
    # register each at scope "you", reusing the deleted regex as both search and serve
    # so the SERVE pool never drifts. SWEEP_LABELS still carries the human label.
    # secret_writedown reuses the NARROWED mirror (without the companion "your
    # sideboard" arm) so its serve no longer surfaces the companion-reminder cards
    # companion_keyword owns.
    ("sacrifice_protection", "you"): _spec(
        *SWEEP_LABELS["sacrifice_protection"],
        {"oracle": r"can't cause you to sacrifice|can't be sacrificed"},
        r"can't cause you to sacrifice|can't be sacrificed",
    ),
    ("secret_writedown", "you"): _spec(
        *SWEEP_LABELS["secret_writedown"],
        {
            "oracle": (
                r"secretly (?:write|choose|name)"
                r"|before the game begins[^.]*(?:write|name|choose)"
                r"|from outside the game"
            )
        },
        r"secretly (?:write|choose|name)"
        r"|before the game begins[^.]*(?:write|name|choose)"
        r"|from outside the game",
    ),
    # ADR-0027 tranche2-B (t2b3-B): opponent_counter_grant's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR — a detrimental bounty/stun counter on an
    # opponent's permanent). Hand-register the serve at the "opponents" scope it fires
    # at, reusing the shared OPPONENT_COUNTER_GRANT_REGEX so the serve pool never drifts
    # (the sweep auto-register loop no longer builds it).
    ("opponent_counter_grant", "opponents"): _spec(
        *SWEEP_LABELS["opponent_counter_grant"],
        {"oracle": OPPONENT_COUNTER_GRANT_REGEX},
        OPPONENT_COUNTER_GRANT_REGEX,
    ),
    # ADR-0027 tranche2-B: counter_replace_bonus's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — the counter_doubling replacement category).
    # The serve keeps the old regex via regex= (strangler pattern).
    ("counter_replace_bonus", "you"): _sweep_spec_with_extras(
        "counter_replace_bonus",
        _COUNTERS_PACKAGE,
        regex=(
            r"that many plus (?:one|two|\d+) [^.]*counters? are put"
            r"|put that many plus"
            r"|if (?:one or more )?\+1/\+1 counters? would be put on"
            r"|one or more counters? would be (?:put|placed)"
            r"[^.]*(?:that many plus|twice that many)"
        ),
    ),
    # ADR-0027: counter_move's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — phase's MoveCounters effect). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec reusing the deleted regex as the
    # serve pattern, keeping the counter-doubler fan-out package.
    ("counter_move", "you"): _spec(
        *SWEEP_LABELS["counter_move"],
        {
            "oracle": (
                r"\bmove (?:a|one|that|any number of|all|x|\d+|one or more) "
                r"[^.]{0,30}?counters?\b (?:from|onto|to)"
            )
        },
        r"\bmove (?:a|one|that|any number of|all|x|\d+|one or more) "
        r"[^.]{0,30}?counters?\b (?:from|onto|to)",
        extras=_COUNTERS_PACKAGE,
    ),
    # Beginning-of-combat / attack-buff commanders are combat decks — surface the gear
    # and keyword-anthems that grow their attackers. ADR-0027 Cluster D: combat_buff_
    # engine migrated to the IR (its SWEEP_DETECTORS row is deleted), so the serve keeps
    # the pinned COMBAT_BUFF_ENGINE_SWEEP_REGEX.
    ("combat_buff_engine", "you"): _sweep_spec_with_extras(
        "combat_buff_engine",
        (_COMBAT_SUPPORT_EXTRA,),
        regex=COMBAT_BUFF_ENGINE_SWEEP_REGEX,
    ),
    # A "becomes blocked" payoff (General Marhault: +3/+3 for each creature blocking it)
    # wants Lure effects — forcing every able creature to block maxes the per-blocker
    # bonus. ADR-0027 Cluster D: the SWEEP_DETECTORS row is deleted (detection moved to
    # the Card IR — the structural becomes_blocked arm UNION a byte-identical
    # BLOCKED_MATTERS_REGEX kept mirror), so pass the pinned regex explicitly (the
    # auto-register loop no longer reaches the deleted row); the serve pool is the same.
    ("blocked_matters", "you"): _sweep_spec_with_extras(
        "blocked_matters", (_LURE_EXTRA,), regex=BLOCKED_MATTERS_REGEX
    ),
    # Heroic / target-matters: the payoff fires when YOU target your own creature, so
    # surface the single-target pumps/protection that do it (Gods Willing, Brute Force).
    ("targeting_matters", "any"): _spec(
        *SWEEP_LABELS["targeting_matters"],
        {"oracle": _TARGETING_SWEEP_REGEX},
        _TARGETING_SWEEP_REGEX,
        extras=(_TARGETED_BUFF_EXTRA,),
    ),
    # Green creature-cast commanders (Gwenna, Runadi, Eshki) ramp into fatties: surface
    # creature cost reducers (Goreclaw) and genuine bombs (Ghalta — power_min=6 keeps it
    # to true fatties, not every 5/5 the trigger would also accept).
    # ADR-0027: creature_cast_trigger migrated to the Card IR (a cast_spell trigger with
    # a Creature subject + an effect-raw / face-oracle "whenever/when [player] casts a …
    # creature spell" scan). Its SWEEP_DETECTORS row is deleted; the serve keeps the old
    # regex (passed explicitly so the spec no longer depends on the deleted row).
    ("creature_cast_trigger", "you"): _sweep_spec_with_extras(
        "creature_cast_trigger",
        (_CREATURE_COST_EXTRA, _SELF_BOUNCE_EXTRA),
        serve_power_min=6,
        regex=(
            r"whenever (?:you|a player|an opponent|each opponent) casts? a creature "
            r"spell|whenever (?:a|another) creature spell is cast"
        ),
    ),
    # Toughness-as-power (Doran, Arcades) and damage-reflection (Boros Reckoner) decks
    # want big-TOUGHNESS bodies and Walls — credit them by toughness>=4 and Defender.
    # ADR-0027 β: toughness_combat migrated to the Card IR (both regex producers' rows
    # are deleted); the serve keeps the deleted regexes via the pinned
    # TOUGHNESS_COMBAT_REGEX constant, so the high-toughness / Defender serve pool is
    # unchanged.
    ("toughness_combat", "you"): _sweep_spec_with_extras(
        "toughness_combat",
        serve_toughness_min=4,
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
        regex=TOUGHNESS_COMBAT_REGEX,
    ),
    # ADR-0027 β: ability_copy migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds its serve).
    # Hand-register the same serve the loop used to build, reusing the pinned
    # ABILITY_COPY_REGEX constant (no extra serve dimensions — byte-identical to the
    # auto-built spec), so the ability-copy serve pool is unchanged. SWEEP_LABELS still
    # carries the label.
    ("ability_copy", "you"): _sweep_spec_with_extras(
        "ability_copy",
        regex=ABILITY_COPY_REGEX,
    ),
    # ADR-0027: damage_reflect's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the on-card damage_received+damage co-occurrence + a damage_reflect
    # marker for the quoted reflection grant). _sweep_spec_with_extras read that
    # now-gone row, so re-home to a literal spec reusing the deleted regex as the serve
    # pattern, keeping the high-toughness/defender serve dimensions.
    ("damage_reflect", "you"): _spec(
        *SWEEP_LABELS["damage_reflect"],
        {
            "oracle": (
                r"whenever [^.]*is dealt damage, (?:it|this creature) "
                r"deals that much damage"
            )
        },
        r"whenever [^.]*is dealt damage, (?:it|this creature) deals that much damage",
        serve_toughness_min=4,
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
    ),
    # Power doublers (Rhonas, Mr. Orfeo) want high BASE power to double; power-as-damage
    # pingers/fighters (Itzquinth) want high power for more damage. Both lanes credit
    # the fat bodies they exploit (Ghalta / Worldspine Wurm), not just the engine cards.
    # ADR-0027: power_double migrated to the Card IR (a pump/pump_target effect whose
    # raw carries the "double … power" word-mirror); its SWEEP_DETECTORS row is deleted,
    # so the serve passes the deleted regex explicitly to keep the serve pool.
    ("power_double", "you"): _sweep_spec_with_extras(
        "power_double",
        (_POWER_FLING_EXTRA,),
        serve_power_min=5,
        regex=(
            r"double the power|doubles? the power and toughness"
            r"|power(?: and toughness)? (?:is|are) doubled|double [A-Z][a-z']+ power"
            r"|doubles? [^.]*power until end of turn"
        ),
    ),
    # Firebreathing / variable-P/T decks pump power, then fling it for damage.
    # ADR-0027: self_pump migrated to the Card IR (its SWEEP_DETECTORS row is deleted);
    # the serve keeps the old regex via the `regex=` arg.
    ("self_pump", "you"): _sweep_spec_with_extras(
        "self_pump", (_POWER_FLING_EXTRA,), regex=_SELF_PUMP_SWEEP_REGEX
    ),
    # ADR-0027: tapper_engine migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a `tap` Effect with a target subject + a "doesn't
    # untap" restriction raw), so hand-register the spec the sweep loop used to build,
    # reusing the deleted regex as both search and serve.
    ("tapper_engine", "any"): _spec(
        *SWEEP_LABELS["tapper_engine"],
        {"oracle": _TAPPER_ENGINE_SWEEP_REGEX},
        _TAPPER_ENGINE_SWEEP_REGEX,
    ),
    # ADR-0027: count_anthem migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to a team +N/+N pump scaling with a board count over a
    # generic creature Filter you control), so hand-register the spec the sweep loop
    # used to build, reusing the deleted regex.
    ("count_anthem", "you"): _spec(
        *SWEEP_LABELS["count_anthem"],
        {"oracle": _COUNT_ANTHEM_SWEEP_REGEX},
        _COUNT_ANTHEM_SWEEP_REGEX,
    ),
    # ADR-0027 #24g: scaling_pump migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection is the structural _is_scaling_count `pump` arm reading the
    # supplement-recovered op=count operand; the kept word mirror is now DELETED too),
    # so the auto-register loop no longer builds this spec. Hand-register the spec the
    # sweep loop used to build, reusing the pinned regex as the search/serve candidate
    # surface only (NOT a detection path).
    ("scaling_pump", "you"): _spec(
        *SWEEP_LABELS["scaling_pump"],
        {"oracle": SCALING_PUMP_SWEEP_REGEX},
        SCALING_PUMP_SWEEP_REGEX,
    ),
    # ADR-0027 Cluster C: base_pt_set migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to the structural cat=="base_pt_set" arm UNION the
    # carved BASE_PT_SET_REGEX kept word mirror), so the auto-register loop no longer
    # builds this spec. Hand-register the spec the sweep loop used to build, reusing the
    # CARVED regex (base-P/T-set-only, not the 4-mechanic umbrella) as both search and
    # serve — the serve pool is set-P/T effects + the creatures that exploit a set base
    # P/T. Scope 'any' (the deleted SWEEP row's scope).
    ("base_pt_set", "any"): _spec(
        *SWEEP_LABELS["base_pt_set"],
        {"oracle": BASE_PT_SET_REGEX},
        BASE_PT_SET_REGEX,
    ),
    # ADR-0027: tribal_etb_multi migrated to the Card IR — its SWEEP_DETECTORS row is
    # deleted (detection moved to an etb trigger with a creature-subtype subject), so
    # hand-register the spec the sweep loop used to build, reusing the deleted regex as
    # both search and serve.
    ("tribal_etb_multi", "you"): _spec(
        *SWEEP_LABELS["tribal_etb_multi"],
        {"oracle": _TRIBAL_ETB_MULTI_SWEEP_REGEX},
        _TRIBAL_ETB_MULTI_SWEEP_REGEX,
    ),
    # ADR-0027: typed_enters_punish migrated to the Card IR — its SWEEP_DETECTORS row
    # is deleted (detection moved to an etb trigger whose consequence burns the
    # opponents), so hand-register the spec the sweep loop used to build, reusing the
    # deleted regex.
    ("typed_enters_punish", "you"): _spec(
        *SWEEP_LABELS["typed_enters_punish"],
        {"oracle": _TYPED_ENTERS_PUNISH_SWEEP_REGEX},
        _TYPED_ENTERS_PUNISH_SWEEP_REGEX,
    ),
    # Force-attack / goad commander (Kratos) wants extra combats to swing again.
    # ADR-0027: forced_attack migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted), so pass the deleted SWEEP regex explicitly — the serve pool stays
    # oracle-defined (the IR arm + DET kept mirror drive the firing).
    ("forced_attack", "you"): _sweep_spec_with_extras(
        "forced_attack",
        (_EXTRA_COMBAT_EXTRA, _COMBAT_SUPPORT_EXTRA),
        regex=FORCED_ATTACK_SWEEP_REGEX,
    ),
    # Donate commander (Jon Irenicus, Harmless Offering) wants drawback creatures to
    # hand to opponents for the downside.
    # ADR-0027: donate_makers had its SWEEP_DETECTORS row deleted (detection moved to
    # the Card IR — a gain_control raw-recipient discriminator). The serve pool stays
    # oracle-defined, so pass the deleted regex explicitly.
    ("donate_makers", "you"): _sweep_spec_with_extras(
        "donate_makers",
        (_DRAWBACK_EXTRA, _FORCE_FEED_EXTRA),
        regex=(
            r"(?:target opponent|another player|target player|that player"
            r"|each opponent|each other player) gains control of[^.]*you control"
            r"|(?:target opponent|another player|target player|that player) "
            r"gains control of"
        ),
    ),
    # ADR-0027 t2b4-C: damage_to_you_punish's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — an _IR_KEPT_DETECTORS word mirror; phase drops
    # the opp-source filter and the "to you" recipient). The serve was auto-registered
    # from the SWEEP row (scope "opponents"), so hand-register it with the old regex.
    ("damage_to_you_punish", "opponents"): _sweep_spec_with_extras(
        "damage_to_you_punish",
        regex=(
            r"whenever a source an opponent controls deals damage to you"
            r"|whenever (?:a|an) (?:opponent|source[^.]*opponent)[^.]*deals "
            r"(?:combat )?damage to you"
        ),
    ),
    # ADR-0027 t2b5-A: the SWEEP_DETECTORS rows for draft_spellbook / each_mode_player
    # / flip_self / miracle_grant were deleted (detection moved to the Card IR — each is
    # a signals._IR_KEPT_DETECTORS word mirror). Their serves were auto-registered from
    # the SWEEP rows, so hand-register each with the old regex + scope so the
    # auto-register loop's missing-row lookup never runs and the serve never drifts.
    ("draft_spellbook", "you"): _sweep_spec_with_extras(
        "draft_spellbook", regex=r"\bdraft a card\b|spellbook"
    ),
    ("each_mode_player", "each"): _sweep_spec_with_extras(
        "each_mode_player", regex=r"each mode must target a different player"
    ),
    ("flip_self", "you"): _sweep_spec_with_extras(
        "flip_self", regex=r"\bflip this creature\b"
    ),
    ("miracle_grant", "you"): _sweep_spec_with_extras(
        "miracle_grant",
        regex=r"(?:cards?|spells?) (?:in your hand )?ha(?:s|ve) miracle",
    ),
    # Legend-rule-off commander (Brothers Yamazaki) wants self-copy effects to run
    # multiple copies of itself. ADR-0027 β: legend_rule_off's SWEEP_DETECTORS row is
    # deleted (detection moved to the Card IR via a byte-identical _IR_KEPT_DETECTORS
    # mirror), so pass the deleted regex explicitly (the serve pool stays oracle-
    # defined and never drifts from the deleted SWEEP row).
    ("legend_rule_off", "you"): _sweep_spec_with_extras(
        "legend_rule_off",
        (_COPY_EXTRA,),
        regex=r"the .legend rule. doesn't apply",
    ),
    # A self-blinking commander (Norin) re-enters constantly, firing "whenever a
    # creature enters" payoffs (Impact Tremors) and doublers (Panharmonicon).
    # ADR-0027 t2b4-C: self_blink's SWEEP_DETECTORS row was deleted (detection moved to
    # the Card IR — the name-aware fulltext detector + the per-clause
    # _SELF_BLINK_SWEEP_RE mirror). The serve pool stays oracle-defined, so pass the
    # deleted regex explicitly.
    ("self_blink", "you"): _sweep_spec_with_extras(
        "self_blink",
        (_ETB_PAYOFF_EXTRA, _ETB_VALUE_EXTRA, _ETB_DOUBLER_EXTRA),
        regex=(
            r"exile (?:up to one |another |a |target )?(?:other )?target "
            r"(?:creature|permanent)[^.]*\.?\s*return (?:that|those|it|the[^.]*)"
            r"[^.]*to the battlefield"
            r"|exile (?:any number of|all|each)[^.]*creatures[^.]*return"
            r"|exile [A-Z][a-z']+\.\s*return (?:it|that card|them)[^.]*"
            r"to the battlefield"
        ),
    ),
    # A repeatable-wrath commander (Mageta) wants to rebuild after the sweep:
    # reanimation (Breath of Life) plus indestructible bombs (Zetalpa) that survive it.
    # ADR-0027: mass_removal migrated to the Card IR (detection moved to the structural
    # counter_kind=='all' destroy/exile/damage + negative-pump arms; its SWEEP_DETECTORS
    # row is deleted). The SERVE pool stays oracle-defined (board wipes + the
    # rebuild-after-wrath package), so pass the deleted regex inline so the
    # auto-register loop's missing-row lookup never runs.
    ("mass_removal", "you"): _sweep_spec_with_extras(
        "mass_removal",
        (_REANIMATION_EXTRA, _BOARD_PROTECTION_EXTRA),
        serve_keywords=("indestructible",),
        regex=(
            "destroy all (?:other )?(?:nonland )?(?:permanents|creatures|artifacts"
            "|enchantments|other creatures)|deals? \\d+ damage to each (?:creature"
            "|nonlegendary creature|other creature)|exile all (?:creatures|permanents)"
            "|exile all (?:black|white|blue|red|green) creatures|all creatures get -\\d"
            "|destroy all [^.]*creatures except|destroy all other creatures"
        ),
    ),
    # ADR-0027 β: variable_pt migrated to the Card IR (SWEEP row deleted); the serve
    # keeps the deleted regex via the pinned VARIABLE_PT_SWEEP_REGEX constant.
    ("variable_pt", "you"): _sweep_spec_with_extras(
        "variable_pt", (_POWER_FLING_EXTRA,), regex=VARIABLE_PT_SWEEP_REGEX
    ),
    # ADR-0027 β: creature_ping migrated to the Card IR (SWEEP row deleted); the serve
    # keeps the deleted regex via the pinned CREATURE_PING_REGEX constant.
    ("creature_ping", "you"): _sweep_spec_with_extras(
        "creature_ping",
        (_DEATHTOUCH_GEAR_EXTRA,),
        serve_power_min=5,
        regex=CREATURE_PING_REGEX,
    ),
    # Extra upkeep STEPS (Obeka, The Ninth Doctor): each added upkeep step is another
    # instance every "at the beginning of your/each upkeep" ability triggers in (CR
    # 500.7 / 503 / 603.2), so the whole upkeep-trigger pool IS the payoff package.
    # The narrow OPEN regex lives in the sweep detector; this hand-spec exists so the
    # auto-register doesn't bind the serve to that 4-card open regex — it serves the
    # broad upkeep-trigger pool instead. The lane opens for only the ~2 extra-upkeep
    # commanders, so the broad serve never floods an unrelated deck.
    ("extra_upkeep", "you"): _spec(
        "Extra upkeeps",
        "repeatable upkeep-trigger payoffs, multiplied by every added upkeep step",
        {"oracle": r"at the beginning of (?:your|each) upkeep"},
        r"at the beginning of (?:your|each) upkeep",
    ),
    # Extra end steps (Y'shtola Rhul): every "at the beginning of your/each end step"
    # payoff (Agent of Treachery, Chimil, the Inner Sun) re-triggers in each added end
    # step (CR 513). Same open-gated-narrow / serve-broad split as Extra upkeeps.
    ("extra_end_step", "you"): _spec(
        "Extra end steps",
        "end-step-trigger payoffs, multiplied by every added end step",
        {"oracle": r"at the beginning of (?:your|each) end step"},
        r"at the beginning of (?:your|each) end step",
    ),
    # Extra draw steps (opened by a beginning-phase grant, CR 501/504): "at the
    # beginning of your draw step" payoffs re-trigger in each added draw step.
    ("extra_draw_step", "you"): _spec(
        "Extra draw steps",
        "draw-step-trigger payoffs, multiplied by every added draw step",
        {"oracle": r"at the beginning of (?:your|each) draw step"},
        r"at the beginning of (?:your|each) draw step",
    ),
    # Deathtouch gear (Basilisk Collar) makes any ping / power-as-damage lethal — credit
    # it on the noncombat-damage and power-fling lanes too, not only the Burn lane.
    # ADR-0027: noncombat_damage_payoff migrated to the Card IR (SWEEP row deleted); the
    # serve keeps the deleted regex via the pinned NONCOMBAT_DAMAGE_PAYOFF_REGEX
    # constant.
    ("noncombat_damage_payoff", "you"): _sweep_spec_with_extras(
        "noncombat_damage_payoff",
        (_DEATHTOUCH_GEAR_EXTRA, _NONCOMBAT_BURN_EXTRA),
        regex=NONCOMBAT_DAMAGE_PAYOFF_REGEX,
    ),
    # Power-as-damage / fling commander (Brion Stoutarm) wants big bodies as fling
    # fodder (power_min) plus the power-fling payoffs and deathtouch gear.
    # ADR-0027 β: damage_equal_power migrated to the Card IR (SWEEP row deleted); the
    # serve keeps the deleted regex via the pinned DAMAGE_EQUAL_POWER_REGEX constant.
    ("damage_equal_power", "you"): _sweep_spec_with_extras(
        "damage_equal_power",
        (_DEATHTOUCH_GEAR_EXTRA, _POWER_FLING_EXTRA),
        serve_power_min=6,
        regex=DAMAGE_EQUAL_POWER_REGEX,
    ),
    # Repeatable "deals N damage to each creature" board pinger (Tibor, Pestilence,
    # Pyrohemia): deathtouch on the source makes each ping lethal (CR 702.2b) -- a
    # recurring one-sided board wipe. The lane's whole point IS that enabler, so it
    # serves the same gear the Burn/fling lanes do, via the shared constant.
    ("aoe_ping", "you"): _spec(
        "Deathtouch board sweep",
        "your recurring damage to each creature + deathtouch on the source = a "
        "repeatable one-sided wipe (CR 702.2b)",
        {"oracle": _DEATHTOUCH_GEAR_ORACLE},
        _DEATHTOUCH_GEAR_ORACLE,
    ),
    # Same archetype as spellcast_matters (a magecraft commander triggers off the same
    # instants/sorceries as a prowess one), so it shares the one _SPELLSLINGER_SPEC — a
    # commander firing both detectors now renders a single "Spellslinger" avenue, not
    # two near-identical lanes (Phase C). CR 207.2c: magecraft = the cast trigger.
    ("magecraft_matters", "you"): _SPELLSLINGER_SPEC,
    ("extra_combats", "you"): _spec(
        "Extra combats",
        "additional combat phases and the attackers to exploit them",
        {"oracle": r"additional combat phase|extra combat"},
        r"additional combat|extra combat",
    ),
    ("extra_turns", "you"): _spec(
        "Extra turns",
        "additional-turn effects",
        {"oracle": r"extra turn|additional turn|take an extra"},
        r"extra turn|additional turn",
    ),
    # ── Rules mined from the zero-signal commander tail ─────────────────────────
    # Serve the payoff trigger (CR 510 combat damage) + true-unblockable enablers. The
    # bare `\bmenace\b` matched every menace creature AND the menace/flying REMINDER
    # "can't be blocked except by …" — surfacing vanilla evasive bodies, not connect
    # payoffs. Drop it; gate `can't be blocked` against the "except" reminder.
    ("combat_damage_matters", "opponents"): _spec(
        "Combat damage",
        "evasive attackers and extra-combat enablers to keep connecting",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals combat damage to (?:a player|an opponent|one of your opponents"
        r"|each opponent)|can't be blocked(?! except)|\bunblockable\b",
        # A combat-damage-trigger commander needs to CONNECT and survive: gear to suit
        # up (Ojutai), instant pump to push through / survive blocks (Benton), and extra
        # combats to multiply the trigger (Neheb -> Relentless Assault, Seize the Day).
        extras=(_COMBAT_SUPPORT_EXTRA, _PUMP_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # ADR-0027 β: combat_damage_to_opp migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted, so the serve hand-spec passes the pinned
    # COMBAT_DAMAGE_TO_OPP_REGEX (the EXACT deleted regex) so serve / mirror
    # never drift.
    ("combat_damage_to_opp", "opponents"): _sweep_spec_with_extras(
        "combat_damage_to_opp",
        (
            _COMBAT_SUPPORT_EXTRA,
            _PUMP_EXTRA,
            _DAMAGE_AMPLIFIER_EXTRA,
            _EXTRA_COMBAT_EXTRA,
        ),
        regex=COMBAT_DAMAGE_TO_OPP_REGEX,
    ),
    # ADR-0027 β: combat_damage_to_creature migrated to the Card IR; its
    # SWEEP_DETECTORS row is deleted (the auto-loop used to register a plain spec —
    # search == serve == its regex, no extras). Hand-register the byte-identical
    # plain spec reusing the pinned regex so the avenue resolves exactly as before
    # (connect-with-creatures payoffs — Ohran Viper, the basilisks, Toxin Sliver).
    ("combat_damage_to_creature", "any"): _spec(
        *SWEEP_LABELS["combat_damage_to_creature"],
        {"oracle": COMBAT_DAMAGE_TO_CREATURE_REGEX},
        COMBAT_DAMAGE_TO_CREATURE_REGEX,
    ),
    # Group-mana commanders (Shizuko, Yurlok) want symmetric mana-doublers / punishers +
    # join-forces ramp beyond the bare "each player adds {" the sweep regex credits.
    # Unspent-mana commander (Omnath, Kruphix) keeps mana between steps -> wants mana
    # amplification (untap-all-lands + doublers) to bank more. The sweep's bare "unspent
    # mana" serve credited none; promote it to a hand-spec with the amp extra.
    # ADR-0027 β: unspent_mana migrated to the Card IR via a kept-mirror — its
    # SWEEP_DETECTORS row is deleted, so pass the EXACT deleted regex via ``regex=``
    # (pinned as UNSPENT_MANA_REGEX) so the serve search/serve pool never drifts.
    ("unspent_mana", "you"): _sweep_spec_with_extras(
        "unspent_mana",
        (_MANA_AMP_EXTRA,),
        regex=UNSPENT_MANA_REGEX,
    ),
    # ADR-0027: group_mana migrated to the Card IR — its SWEEP_DETECTORS row is deleted
    # (detection moved to a non-controller-recipient discriminator on phase's ramp
    # effect raw), so hand-register the spec the sweep loop used to build, inlining the
    # deleted regex + the symmetric-mana extra.
    ("group_mana", "each"): _spec(
        *SWEEP_LABELS["group_mana"],
        {
            "oracle": (
                r"each player adds \{|that player adds \{"
                r"|the active player[^.]*adds? \{"
                r"|a player (?:loses?|losing)[^.]*mana[^.]*lose"
            )
        },
        (
            r"each player adds \{|that player adds \{"
            r"|the active player[^.]*adds? \{"
            r"|a player (?:loses?|losing)[^.]*mana[^.]*lose"
        ),
        extras=(_SYM_MANA_EXTRA,),
    ),
    # The discount-exploiting target set is defined by high cmc (structured) + X-spells
    # — not the generic words "mana value", which matched 453 cards (Disdainful Stroke,
    # Abrupt Decay). Drop that branch; gate on cmc (expensive bombs) + {x} + storm.
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount, plus more cost "
        "reducers to stack the discount",
        {"oracle": r"\{x\}|with mana value"},
        r"\{x\}|\bstorm\b",
        serve_cmc_min=7,
        extras=(_COST_REDUCER_EXTRA,),
    ),
    # Cast-from-exile MATTERS: payoffs + explicit "cast/play from exile" enablers (plot,
    # suspend, "whenever you cast a spell from exile", paradox). NOT impulse draw (its
    # own avenue, the impulse_top_play sweep) and NOT play-from-top-of-library
    # (`play_from_top` below) — both are different mechanics. The "you may play … from
    # exile" branch REQUIRES the literal "from exile", so a bare impulse "you may play
    # those cards" reads as impulse, not as this payoff lane.
    ("cast_from_exile", "you"): _spec(
        "Cast-from-exile",
        "payoffs and enablers that cast or play cards from exile (plot, suspend, "
        '"whenever you cast a spell from exile")',
        {"oracle": r"from exile|\b(?:plot|suspend|foretell|rebound)\b"},
        r"spells? you cast from exile"
        r"|whenever you cast a spell from exile"
        r"|you may (?:play|cast) (?:it|that card|those cards?|them|the exiled)"
        r"[^.]*?from exile"
        r"|" + _STEAL_CAST_ORACLE + r"|\bplot\b",
        # Suspend (CR 702.62a), Foretell (702.143), Rebound (702.88a), and Plot all CAST
        # the card from exile — authoritative Scryfall keywords, not regex-from-prose.
        serve_keywords=("plot", "suspend", "foretell", "rebound"),
        extras=(_PARADOX_PAYOFF_EXTRA,),
    ),
    # Impulse (top-of-YOUR-library exile-and-play): hand-written so the serve also
    # credits the "exile then cast it for as long as it remains exiled" engines
    # (Gonti, Hostage Taker, Thief of Sanity) the bare "play those cards this turn"
    # sweep regex missed, plus the cast-from-exile PAYOFFS an impulse deck triggers by
    # casting its exiled cards (Wild-Magic Sorcerer: "the first spell you cast from
    # exile … has cascade"). Detector regex (commander side) is unchanged.
    ("impulse_top_play", "you"): _spec(
        *SWEEP_LABELS["impulse_top_play"],
        {"oracle": _IMPULSE_SWEEP_REGEX},
        _IMPULSE_SWEEP_REGEX
        + r"|"
        + _STEAL_CAST_ORACLE
        + r"|spells? you cast from exile|first spell you cast from exile"
        # The bare "Whenever you cast a spell from exile" trigger payoff (Passionate
        # Archaeologist, Nalfeshnee) the impulse deck fires by casting its exiled cards.
        + r"|whenever you cast a spell from exile",
        # Paradox payoffs (Keeper of Secrets) — casting from exile IS from-anywhere-
        # other-than-hand, so an impulse deck triggers them too.
        extras=(_PARADOX_PAYOFF_EXTRA,),
    ),
    # X-spells matter (CR 107.3 / 202.1): an X-matters commander (Zaxara, Rosheen,
    # Zimone) is built from spells whose printed mana cost contains {X} and wants the
    # X-doublers / copy-the-X-spell payoffs (Unbound Flourishing). The serve credits
    # {X}-cost cards via the structured mana_cost dimension (the X-spells themselves)
    # PLUS oracle X-payoffs. A broad but genuinely on-theme pool — an X deck wants the
    # universe of X-spells, so breadth here is coverage, not noise.
    ("xspell_matters", "you"): _spec(
        "X spells",
        "X-spells (cards with {X} in their cost) plus the X-doublers and "
        "copy-the-X-spell payoffs an X-matters deck is built around",
        {
            "oracle": r"\{X\} in (?:its|their) (?:mana )?cost"
            r"|cost (?:that )?contains \{X\}"
        },
        r"\{x\} in (?:its|their) (?:mana )?cost"
        r"|cost (?:that )?contains? \{x\}"
        r"|spells? you cast with \{x\}",
        serve_mana_cost=r"\{X\}",
    ),
    # Theft (steal an OPPONENT's cards and cast them): serve credits the opponent-
    # library dig (Gonti, Black Cat, Thief of Sanity) and the steal-and-cast engines
    # (Hostage Taker). Opponent-anchored / "remains exiled"-anchored so a self-impulse
    # engine (Valakut Exploration — your own library, "until end of next turn") stays
    # out. Detector regex unchanged.
    ("theft_matters", "opponents"): _spec(
        *SWEEP_LABELS["theft_matters"],
        {"oracle": _THEFT_SWEEP_REGEX},
        _THEFT_SWEEP_REGEX
        + r"|"
        + _OPP_LIBRARY_THEFT_ORACLE
        + r"|"
        + _STEAL_CAST_ORACLE,
    ),
    # ADR-0027: void_warp_matters migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the sweep auto-register loop no longer builds this spec). The serve
    # pool stays oracle-defined, so it reuses the shared VOID_WARP_MATTERS_REGEX
    # constant (the EXACT deleted detector regex) — serve / kept mirror never drift.
    ("void_warp_matters", "you"): _spec(
        *SWEEP_LABELS["void_warp_matters"],
        {"oracle": VOID_WARP_MATTERS_REGEX},
        VOID_WARP_MATTERS_REGEX,
    ),
    # Play from the TOP OF YOUR LIBRARY — Future Sight / Bolas's Citadel / Oracle of Mul
    # Daya. Casts from the LIBRARY zone (not exile), so it's its own avenue, distinct
    # from cast-from-exile and impulse. Needs a play/cast verb so look/scry/mill don't
    # match. ADR-0027 β: detection moved to the Card IR (a STATIC cast_from_zone+from:
    # library Effect over phase's TopOfLibraryCastPermission mode + a per-clause
    # mirror);
    # this SERVE pool stays oracle-defined, so the regex is pinned inline here (the
    # sweep
    # auto-register no longer builds it — its SWEEP_DETECTORS row is deleted).
    ("play_from_top", "you"): _spec(
        "Play from the top of your library",
        "engines that let you play or cast off the top of your library (Future Sight, "
        "Bolas's Citadel) — top-of-library control and extra-land effects amplify them",
        {"oracle": r"(?:play|cast)\b[^.]*?\bfrom the top of your library"},
        r"(?:play|cast)\b[^.]*?\bfrom the top of your library",
    ),
    ("discard_matters", "you"): _spec(
        "Discard",
        "loot/connive discard outlets and discard payoffs",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard"
        # Self-discard OUTLETS the loot/connive forms missed: wheels ("discard all the
        # cards in your hand") and "discard X/N cards" as a cost (Turbulent Dreams,
        # Firestorm). Imperative "discard " (no trailing s) keeps forced-OPPONENT
        # discard ("target player discardS") out — the opponent_discard lane.
        r"|\bdiscard (?:x|\d+|two|three|four|all)\b",
    ),
    # Discard OUTLET commander (a loot/rummage engine): hand-written so the serve adds
    # the discard PAYOFFS it powers ("whenever you discard …" — Containment Construct,
    # Rielle, Glint-Horn Buccaneer) alongside the outlets the sweep regex already
    # credits. Detector regex unchanged (same key → auto-register skips it).
    ("discard_outlet", "you"): _spec(
        *SWEEP_LABELS["discard_outlet"],
        {"oracle": _DISCARD_OUTLET_SWEEP_REGEX},
        _DISCARD_OUTLET_SWEEP_REGEX + r"|whenever you discard",
    ),
    # ADR-0027 dig library-owner scope (SIDECAR v27): dig_until migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label / avenue
    # / oracle, reusing the shared DIG_UNTIL_REGEX constant so serve and the kept-mirror
    # detector never drift.
    ("dig_until", "you"): _spec(
        *SWEEP_LABELS["dig_until"],
        {"oracle": _DIG_UNTIL_SWEEP_REGEX},
        _DIG_UNTIL_SWEEP_REGEX,
    ),
    # ADR-0027 per-clause draw raw (SIDECAR v32): draw_for_each migrated to the Card IR
    # (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer builds this
    # serve). Hand-register the spec the sweep loop used to build — same label / avenue
    # / oracle, reusing the shared DRAW_FOR_EACH_REGEX constant so serve and the
    # kept-mirror detector never drift.
    ("draw_for_each", "you"): _spec(
        *SWEEP_LABELS["draw_for_each"],
        {"oracle": _DRAW_FOR_EACH_SWEEP_REGEX},
        _DRAW_FOR_EACH_SWEEP_REGEX,
    ),
    # ADR-0027 topdeck library-owner scope (SIDECAR v28): topdeck_selection migrated to
    # the Card IR (its SWEEP_DETECTORS row deleted, so the auto-register loop no longer
    # builds this serve). Hand-register the spec the sweep loop used to build — same
    # label / avenue / oracle, reusing the shared TOPDECK_SELECTION_REGEX constant so
    # serve and the kept-mirror detector never drift.
    ("topdeck_selection", "you"): _spec(
        *SWEEP_LABELS["topdeck_selection"],
        {"oracle": _TOPDECK_SELECTION_SWEEP_REGEX},
        _TOPDECK_SELECTION_SWEEP_REGEX,
    ),
    # Drain. The serve required "opponent" adjacent to "loses", so it MISSED the
    # keystone aristocrats drains worded "target/that player loses N life" (Blood
    # Artist, Falkenrath Noble). Add the player-loses branch; "each player" is excluded
    # to keep symmetric self-damage out of the opponents-drain avenue.
    # Serve/search widened with the past-tense "lost life this turn" THRESHOLD wording
    # (Spectacle / Rakdos payoffs — Stromkirk Bloodthief, Rakdos Lord of Riots) the
    # continuous "loses life" branches missed. Opponent-anchored so a self "you lost
    # life this turn" payoff (Ludevic) never matches.
    ("lifeloss_matters", "opponents"): _spec(
        "Drain",
        "repeatable life-drain and aristocrats payoffs",
        {
            "oracle": r"each opponent loses|target opponent loses|whenever .* dies"
            r"|(?:an? |each )?opponents? lost life this turn"
        },
        r"opponent[^.]*loses [^.]*life|whenever an opponent loses life|\bextort\b"
        r"|(?:target player|that player|a player) loses? [^.]*\blife\b"
        r"|(?:an? opponent|each opponent|opponents?|a player|each player)"
        r"(?: who)? lost life this turn"
        # Damage to a player IS life loss (CR 120.3a), so pingers / group-slug that deal
        # damage to opponents (Kessig Flamebreather, Mogis) are drain payoffs too —
        # including symmetric group-slug "that player" / "each player" (Sulfuric Vortex,
        # Roiling Vortex), a drain/aggro staple.
        r"|deals (?:\d+|x|that much) damage to "
        r"(?:each opponent|target opponent|each of your opponents"
        r"|that player|each player)",
    ),
    # The bare `pay \d+ life` matched 39 painlands/fetchlands (Blood Crypt, Sacred
    # Foundry) that are mana fixing, not a life-as-resource engine. VETO lands; keep the
    # lose-life payoff/enabler clauses.
    ("lifeloss_matters", "you"): _spec(
        "Self life-loss",
        "ways to pay or lose life on demand to fuel your payoffs, plus the life-total "
        "swaps/resets and recovery that turn a low life total into an advantage",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you (?:gain or )?lose life|you lose (?:\d+|x) life"
        r"|pay (?:\d+|x) life"
        # Life-as-a-resource payoffs (Selenia): swap/reset your low life total (Axis of
        # Mortality / Repay in Kind / Magus of the Mirror), recover it (Children of
        # Korlis), or win from it (Near-Death Experience).
        r"|exchange life totals?|life totals? becomes?|lowest life total"
        r"|gain life equal to[^.]*lost|life you(?:'ve| have)? lost this turn"
        r"|if you have [^.]*life[^.]*win the game",
        serve_not=r"\bas this land enters\b|enters tapped",
    ),
    # Celebration (WOE): all 11 cards carry the exact phrase, so serve == open. A
    # Celebration commander floods nonland permanents each turn to switch the payoffs
    # on; the lane surfaces the other Celebration cards (Grand Ball Guest, Raging
    # Battle Mouse). Niche by design — the phrase appears nowhere else.
    ("celebration_matters", "you"): _spec(
        "Celebration",
        "ways to deploy two or more nonland permanents a turn, plus the payoffs",
        {
            "oracle": (
                r"two or more nonland permanents entered the battlefield "
                r"under your control this turn"
            )
        },
        r"two or more nonland permanents entered the battlefield "
        r"under your control this turn",
    ),
    # Tapped-creatures-matter: tap your team freely, then cash in the count (Throne of
    # the God-Pharaoh, Dragonscale General, Harvest Season) — backed by the grants that
    # make tapping safe (Masako: block while tapped; Saryth: deathtouch; Oak Street
    # Innkeeper: hexproof). \btapped excludes convoke's "untapped creatures".
    ("tapped_matters", "you"): _spec(
        "Tapped creatures matter",
        "payoffs that scale with tapped creatures, plus grants that make tapping safe",
        {
            "oracle": (
                r"number of tapped creatures you control"
                r"|\btapped creatures you control (?:have|get|gain|are|can|with)"
                r"|or more tapped creatures|for each tapped creature you control"
            )
        },
        r"number of tapped creatures you control"
        r"|\btapped creatures you control (?:have|get|gain|are|can|with)"
        r"|or more tapped creatures|for each tapped creature you control",
    ),
    # Land sacrifice (Gitrog, Titania, Slogurk): lands hitting the graveyard is the
    # payoff, so repeatable "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb)
    # are the engine. Distinct from sacrifice_outlets (which excludes "sacrifice a land"
    # — the fetchland guard) and from landfall (lands ENTERING).
    ("land_sacrifice_matters", "you"): _spec(
        "Land sacrifice",
        "repeatable sac-a-land outlets and the payoffs for lands hitting the graveyard",
        {
            "oracle": (
                r"sacrifice a land(?: card)?:"
                r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
                r"put into[^.]*graveyard"
            )
        },
        r"sacrifice a land(?: card)?:"
        r"|whenever (?:a|one or more|another) lands?(?: cards?)?[^.]*"
        r"put into[^.]*graveyard"
        r"|whenever you sacrifice (?:a|one or more|another) lands?",
    ),
    # Keyword soup (Odric Lunarch Marshal, Akroma Vision): shares many evergreen
    # keywords across the team, so it wants creatures stacked with keywords. Serve any
    # creature with >=3 evergreen keywords (Aerial Responder, Zetalpa, Danitha) — the
    # structural keyword_count_min dimension, since "has 3+ keywords" is in keywords[],
    # not prose. Only the >=5-keyword soup-sharers open it, so the broad serve is on-
    # theme breadth, not over-fire.
    ("keyword_soup_makers", "you"): _spec(
        "Keyword soup",
        "creatures stacked with evergreen keywords to share across your team",
        {"oracle": r"\b(?:flying|first strike|double strike|trample|vigilance)\b"},
        None,
        serve_keyword_count_min=3,
    ),
    # The SWEEP also fires a separate `keyword_soup` signal (Rayami absorbs keywords
    # from dead creatures; Akroma Vision / Indominus Rex share them) — same payoff, so
    # give it the same keyword-dense-creature serve, not the narrow sweep regex it'd
    # otherwise auto-register. Hand-speccing the key makes the sweep loop skip it.
    ("keyword_soup", "you"): _spec(
        "Keyword soup",
        "creatures stacked with evergreen keywords to share or absorb",
        {"oracle": r"\b(?:flying|first strike|double strike|trample|vigilance)\b"},
        None,
        serve_keyword_count_min=3,
    ),
    ("lands_matter", "you"): _spec(
        "Lands matter",
        "ramp, extra land drops, and recursion to maximize your land count",
        {
            "oracle": (
                r"search your library for .*land"
                r"|play an additional land"
                r"|put .*land card.*onto the battlefield"
            )
        },
        # The "number of lands" PAYOFF (Molimo's P/T) PLUS the land ramp / fetch /
        # recursion that grows the count — lands_matter is the same archetype as
        # landfall, so it wants the same enablers (reuse _LANDFALL_ORACLE). Also the
        # creature pump that scales with a basic-land subtype "you control" (Blanchwood
        # Armor, Primal Bellow) — the mono-color go-tall payoff scales the same way as
        # Molimo's own P/T. Anchored to "you control" so opponent-basic pumps
        # (Crusading Knight) stay out.
        r"the number of lands you control|for each land you control"
        r"|(?:gets?|get) \+[\dx]+/\+[\dx]+[^.]{0,40}?(?:for each|number of) "
        r"(?:plains|islands?|swamps?|mountains?|forests?) you control|"
        + _LANDFALL_ORACLE,
        extras=(_LANDS_FROM_GRAVE_EXTRA,),
    ),
    # An ENGINE is recurring or bulk draw — NOT a one-shot cantrip. The serve's
    # `draw \w+ cards?` let \w+ eat the article in "draw a card", mislabeling ~753
    # one-shot cantrips (Remand, Cryptic Command) as engines — contradicting the
    # extractor's own _CARD_DRAW_RE. Mirror that: a recurring "at the beginning of …
    # draw" OR a bulk 2+ / additional draw. (Single-draw permanents like Rhystic Study
    # are surfaced by their own triggers' signals, not this avenue.)
    ("card_draw_engine", "you"): _spec(
        "Card-advantage engine",
        "protection, recursion, and payoffs for a repeatable draw engine",
        {"preset_names": ("card-draw",)},
        r"at the beginning of [^.]*\bdraws? "
        r"(?:a|an|two|three|four|five|six|seven|eight|nine|ten|x|\d+)[^.]*\bcard"
        r"|draws? (?:two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?"
        r"|draw cards equal to|draws? an additional card",
    ),
    # Drop the self-only `draws? an additional card` (it belongs to the YOU engine); the
    # EACH avenue is symmetric/group draw only.
    ("card_draw_engine", "each"): _spec(
        "Group draw / wheel",
        "symmetric draw with punisher payoffs (Nekusar-style)",
        {"oracle": r"each player draws|whenever .* draws a card"},
        r"each player[^.]*draws?|that player draws|whenever a player draws",
    ),
    # Serve the damage DOUBLERS the blurb already promises — replacement effects (CR
    # 701.10g) worded "deals double/twice that much damage" / "deals that much damage
    # plus" / "if a source … would deal damage … instead" (Furnace of Rath, Gratuitous
    # Violence, Torbran). The old `double the damage` literal missed all of them.
    ("direct_damage", "you"): _spec(
        "Burn / pingers",
        "repeatable direct damage — pingers, burn, and damage doublers",
        {"preset_names": ("burn",)},
        r"deals \d+ damage to any target|\{t\}[^.]*deals .*damage"
        r"|deals (?:double|twice) that (?:much )?damage|deals that much damage plus"
        r"|if a source[^.]*would deal damage[^.]*instead"
        # Burn-redirect: convert creature damage into player damage (Repercussion) —
        # a ping/wipe deck turns it into reach (ping/wipe + this = burn the table).
        r"|creature is dealt damage[^.]*deals? that (?:much )?damage to"
        # Symmetric "punisher" burn enchantments (Manabarbs, Roiling Vortex,
        # Spellshock): recurring damage to each/that player.
        r"|deals \d+ damage to (?:each|that|target) (?:player|opponent|creature)"
        r"|whenever (?:a|an|each) (?:player|opponent)[^.]*deals \d+ damage"
        # Land-enter / tap-a-land punishers (Ankh of Mishra, Zo-Zu, War's Toll).
        r"|whenever (?:a|each) (?:player taps a )?land(?: enters| for mana)?"
        r"[^.]*deals \d+ damage",
        extras=(_DEATHTOUCH_GEAR_EXTRA,),
    ),
    # `add .* mana of any` captured fixing (Birds, City of Brass), not amplification.
    # Serve the doublers/triplers (a "tap … for mana" trigger that adds/produces extra)
    # plus the {x} X-spend payoffs.
    ("mana_amplifier", "you"): _spec(
        "Big mana",
        "mana doublers plus the X-spells and expensive bombs to spend it on",
        {"oracle": r"\{x\}|add .* mana|search your library for .*land"},
        r"you tap [^.]*for mana[^.]*(?:add|produces?)"
        r"|produces? (?:twice|three times|\w+ times|an additional|double)"
        r"|doubles?[^.]*mana|\{x\}",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    # Voltron suits up one creature with Equipment (CR 301.5) and BUFF Auras (CR 303).
    # Gate on the Equipment/Aura subtype, but VETO pure-control Auras (Pacifism /
    # Faith's Fetters — ~167 of them) that pacify rather than buff. Keep the oracle as a
    # residual for equip-cost reducers / tutors that aren't themselves Equipment.
    ("voltron_matters", "you"): _spec(
        "Voltron / equipment & auras",
        "equipment, auras, equip-cost reducers, and tutors to suit up one creature",
        {"preset_names": ("equip",)},
        r"equipped creature|enchanted creature gets|equip \{"
        r"|attach [^.]*(?:equipment|aura)"
        r"|equipment you control|for each (?:equipment|aura)"
        r"|cast an? (?:aura|equipment)|cast aura and equipment"
        # Aura/Equipment cost reducers (Danitha) and tutors (Open the Armory,
        # Steelshaper's Gift) are top-synergy voltron payoffs that aren't Equipment.
        r"|(?:aura|equipment)s?[^.]*spells? you cast cost"
        r"|search your library for an? (?:aura|equipment)",
        serve_types=("equipment", "aura"),
        serve_keywords=("reconfigure",),
        # Voltron buffs YOUR creature (CR 303.4 / 702.5). An Aura that enchants a
        # PLAYER (a Curse, CR 205.3h) or a LAND (a ramp/utility aura) never attaches
        # to your creature, so it isn't voltron — veto it so the type gate (which
        # credits any Aura) can't manufacture a phantom voltron theme from curses
        # and land-auras.
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls"
        r"|enchant (?:player|land|forest|island|swamp|mountain|plains)",
        # Extra combats let the suited-up threat swing again — a top voltron payoff.
        extras=(_VOLTRON_PROTECT_EXTRA, _EXTRA_COMBAT_EXTRA),
    ),
    # An extreme power-for-cost beater (Lord of Tresserhorn 10/4, Yargle 18/6) wins by
    # connecting ONCE for lethal — serve the damage amplifiers that convert raw power
    # into a kill: grant infect (power -> poison) and grant double strike (2x). Distinct
    # from voltron (equipment/auras): these are the combat tricks/auras that close.
    ("one_punch", "you"): _spec(
        "One-punch finishers",
        "amplify your huge body into a one-shot kill — grant infect or double strike "
        "(Tainted Strike, Temur Battle Rage, Grafted Exoskeleton)",
        {"oracle": _ONE_PUNCH_ORACLE},
        _ONE_PUNCH_ORACLE,
    ),
    # A non-Human-attack-trigger engine (Winota) wants evasive attackers that reliably
    # connect — fliers, a useful ~25% narrowing (Dan's own line: "non-Humans" at 96% is
    # not a useful avenue, "fliers at 25%" is). Serve the Flying keyword (the bodies:
    # Ornithopter, Aven Mindcensor, Archon of Emeria) plus flying-granting anthems; the
    # flying Humans it surfaces are premium cheat-into-play targets, also wanted.
    ("nonhuman_attackers", "you"): _spec(
        "Evasive attackers",
        "fliers that connect to trigger your non-Human attack payoff (and flying "
        "Humans to cheat into play)",
        {"card_type": "Creature", "keyword": "flying"},
        r"(?:gains?|have|has) flying|creatures you control[^.]*flying",
        serve_keywords=("flying",),
    ),
    # A reclaim-OWNED commander (Meneldor, The Neutrinos) profits from control-EXCHANGE:
    # donate a dud you own, take their bomb, then reclaim your dud (you still own it).
    # Serve the swaps ("exchange control of …" — Puca's Mischief, Switcheroo, Gilded
    # Drake), NOT one-way theft ("gain control") — you don't OWN a stolen creature, so
    # the commander can't reclaim it.
    ("control_exchange", "you"): _spec(
        "Control swaps",
        "exchange-control effects — donate a dud you own, take their bomb, then "
        "reclaim your dud (Puca's Mischief, Perplexing Chimera, Spawnbroker)",
        {"oracle": r"exchange control of"},
        r"exchange control of"
        r"|exchange (?:control of )?(?:that|those) (?:creature|permanent)",
    ),
    # Kira shields your creatures from removal, so PERMANENT theft sticks: a contingent
    # steal (Sower, Roil — lost if the thief dies) can't be undone, and a theft engine
    # (Empress Galina) survives. Serve the non-temporary theft; the `until end of turn`
    # veto drops Threaten-style steals, which gain nothing from protection.
    ("theft_protection", "you"): _spec(
        "Protected theft",
        "theft creatures whose steal sticks because you shield them from removal — "
        "Sower of Temptation, Roil Elemental, Empress Galina",
        {"oracle": r"gain control of [^.]*target (?:creature|permanent)"},
        r"gain control of (?:up to one )?target "
        r"(?:creature|permanent|nonland permanent|legendary permanent)",
        serve_not=r"until end of turn",
    ),
    # A big-mana commander (Neheb, Sunastian) wants X-spell mana SINKS to dump its mana
    # into. Serve X-damage spells that scale with the mana paid (Fireball, Crackle with
    # Power, Jaya's Immolating Inferno); a fixed-cost burn (Lightning Bolt) and a mana
    # GENERATOR (Mana Flare) are not sinks. (Dan: big-mana-generators -> X-spells.)
    ("big_mana", "you"): _spec(
        "X-spell sinks",
        "X-spells to pour your big mana into — Fireball, Comet Storm, Crackle with "
        "Power, Jaya's Immolating Inferno",
        {"oracle": r"deals x damage|x damage to|times x damage"},
        r"deals x damage|x damage to|deals [^.]*times x damage"
        r"|of up to x target|to each of up to x",
    ),
    # A commander that exiles/takes opponents' library TOPS (Circu, Ragavan, Grenzo)
    # wants to SEE those tops — play-with-top-revealed shows what it will exile/steal.
    # A shuffle-peek (Psychic Surgery) isn't a continuous top-reveal and stays out.
    ("opp_top_exile", "you"): _spec(
        "See opponents' tops",
        "reveal opponents' library tops so you exile/steal the best card — Field of "
        "Dreams, Wizened Snitches, Lantern of Insight",
        {"oracle": r"top card of their (?:library|libraries) revealed"},
        r"plays? with the top card of their (?:libraries|library) revealed"
        r"|look at the top card of (?:each|target|that) (?:opponent|player)",
    ),
    # Fblthp makes 0-cost cards free to plot off the top, fueling the artifact-combo /
    # storm engine. Serve cards whose mana cost is exactly {0} (Ornithopter, Memnite,
    # Welding Jar) — matching on mana_cost excludes lands (no mana cost) for free, and a
    # 1-cost card (Sol Ring) is not a free plot. NOT a raw-stat vanilla-body serve: his
    # ability specifically makes mana-value-0 the relevant property.
    ("free_plot", "you"): _spec(
        "Free plots (0-cost)",
        "0-cost cards — free to plot off the top, the artifact-combo / storm fuel "
        "(Ornithopter, Memnite, Welding Jar)",
        {"card_type": "Artifact", "cmc_max": 0},
        None,
        serve_mana_cost=r"^\{0\}$",
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, support, and creatures to crew them",
        {"preset_names": ("crew",)},
        # Also credit vehicle SUPPORT: cheat a Vehicle into play, ramp/cost-reduction
        # for Vehicle spells (Oviya, Intrepid Stablemaster), not just core text.
        r"\bvehicles? you control\b|\bcrew\b|create [^.]*vehicle artifact"
        r"|\bvehicles? (?:card|spell)s?\b",
    ),
    ("low_power_matters", "you"): _spec(
        "Small creatures matter",
        "payoffs and anthems that reward your low-power creatures attacking and going "
        "wide (Raid Bombardment, Reconnaissance Mission)",
        {
            "oracle": r"creatures? you control with power \d+ or (?:less|fewer)"
            r"|creature spells?[^.]*with power \d+ or (?:less|fewer)"
        },
        # Oracle-only: the "you control with power N or less" anchor is what the payoffs
        # share; NO power_max serve (it would flood the lane with vanilla small bodies).
        # Also the casting-ENABLER form "cast a creature spell with power N or less"
        # (Assemble the Players) — a low-power build-around, still not a vanilla body.
        r"creatures? you control with power \d+ or (?:less|fewer)"
        r"|creature spells?[^.]*with power \d+ or (?:less|fewer)",
    ),
    ("scry_surveil_matters", "you"): _spec(
        "Scry / surveil matters",
        "scry and surveil to fire these payoffs — note surveil also fills your "
        "graveyard (see Your graveyard), while scry is pure top-of-library selection",
        {"oracle": r"\b(?:scry|surveil)\b"},
        r"\b(?:scry|surveil)\b",
    ),
    # ── Named-mechanic long tail ────────────────────────────────────────────────
    ("monarch_matters", "you"): _spec(
        "Monarch",
        "become and defend the monarch — evasion and combat-damage triggers",
        {"oracle": r"\bthe monarch\b|becomes? the monarch"},
        r"\bthe monarch\b",
        extras=(_PILLOWFORT_EXTRA,),
    ),
    # _matters sweep (ADR-0034): the MAKER side of the initiative split — cards that
    # TAKE the initiative (CR 720). The avenue it opens is the full initiative package
    # (takers + the "have the initiative" payoffs + Undercity venture), so the search
    # stays broad; only the lane KEY encodes the doer role.
    ("initiative_makers", "you"): _spec(
        "Initiative (take)",
        "take the initiative; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "hold the initiative payoffs; venture through the Undercity",
        {"oracle": r"\bthe initiative\b|undercity"},
        r"\bthe initiative\b",
    ),
    ("ring_matters", "you"): _spec(
        "The Ring",
        "Ring-bearer payoffs and ways to tempt you with the Ring",
        {"oracle": r"ring tempts you|ring-bearer"},
        r"ring tempts you|ring-bearer",
    ),
    ("venture_matters", "you"): _spec(
        "Venture / dungeons",
        "venture enablers and dungeon-completion payoffs",
        {"oracle": r"venture into the dungeon|\bdungeon\b"},
        r"venture into the dungeon|\bdungeon\b",
    ),
    ("energy_matters", "you"): _spec(
        "Energy",
        "energy makers and energy sinks",
        {"oracle": r"\{e\}|energy counter"},
        r"\{e\}|energy counter",
    ),
    # Devotion (CR 700.5) counts single-color mana SYMBOLS among permanents you control,
    # so the enablers are structurally heavy-pip permanents — a dimension oracle text
    # can't express. Keep `devotion to` for the payoffs; add the pip gate (≥2 of one
    # color, nonland permanent) for the enablers the old serve was blind to.
    ("devotion_matters", "you"): _spec(
        "Devotion",
        "heavy colored pips to grow devotion and devotion payoffs",
        {"oracle": r"devotion to"},
        r"devotion to",
        serve_min_devotion=2,
    ),
    # The central body of the archetype IS the planeswalkers (type) and the proliferate
    # payoffs (keyword) — both authoritative Scryfall fields the oracle-only serve named
    # none of (43/303 → 303/303 served, zero added FPs per the audit).
    ("superfriends_matters", "you"): _spec(
        "Superfriends",
        "planeswalkers plus proliferate and loyalty payoffs to protect them",
        {"oracle": r"planeswalker|loyalty"},
        r"planeswalkers? you control|loyalty counters?",
        serve_types=("planeswalker",),
        serve_keywords=("proliferate",),
        extras=(_PILLOWFORT_EXTRA,),  # protect the walkers (EDHREC: 3 commanders)
    ),
    # Historic (CR 700.6) = artifact, legendary, OR Saga — all type_line tokens. The
    # serve named only the keyword; gate on the three structural categories.
    ("historic_matters", "you"): _spec(
        "Historic",
        "artifacts, legendaries, and Sagas — the historic permanents that trigger it",
        {"oracle": r"\bhistoric\b|\blegendary\b|\bsaga\b"},
        r"\bhistoric\b",
        serve_types=("legendary", "artifact", "saga"),
    ),
    ("legends_matter", "you"): _spec(
        "Legends matter",
        "legendary creatures and the payoffs that reward a board of legends",
        {"oracle": r"\blegendary\b"},
        r"legendary creatures? you control|another legendary|for each legendary",
        serve_types=("legendary",),
    ),
    # The bare `cards in your hand` matched stax/hand-size references (Ensnaring Bridge,
    # Ivory Tower). Require a no-max-hand-size or a full-grip payoff/scaling phrase.
    ("big_hand_matters", "you"): _spec(
        "Big hand / no max hand size",
        "card draw and no-max-hand-size payoffs that reward a full grip",
        {"oracle": r"cards in your hand|no maximum hand size"},
        r"maximum hand size"
        r"|(?:\d+|five|six|seven|eight) or more cards in (?:your )?hand"
        r"|for each card in your hand|equal to the number of cards in your hand",
    ),
    # A party (CR 700.x) is one each of Cleric/Rogue/Warrior/Wizard — those creature
    # SUBTYPES are the members. The bare `\bparty\b` caught 3 flavor FPs; gate the
    # members on the subtype field, keep the party-phrase oracle for the payoffs.
    ("party_matters", "you"): _spec(
        "Party",
        "Clerics, Rogues, Warriors, and Wizards to assemble a full party",
        {"oracle": r"your party|assemble.*party|\bcleric|\brogue|\bwarrior|\bwizard"},
        r"your party|members? of your party|full party|creatures? in your party"
        r"|assemble[^.]*party",
        serve_types=("cleric", "rogue", "warrior", "wizard"),
    ),
    ("exile_matters", "you"): _spec(
        "Exile pile matters",
        "impulse/foretell exile enablers and payoffs for cards in exile",
        {"oracle": r"exile the top|in exile|from exile"},
        r"cards? (?:you own )?in exile|for each card[^.]*exile",
    ),
    # _matters sweep (ADR-0034): split the conflated experience lane by role.
    # experience_makers = the MAKER arm (cards that GAIN experience counters —
    # Ezuri, Mizzix, Kalemne); experience_matters = the PAYOFF arm (cards that
    # SCALE off your experience count — Atreus draw-X, Azula pump-X). Both reuse
    # the same {"oracle": "experience counter"} search pool.
    ("experience_makers", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    ("experience_matters", "you"): _spec(
        "Experience payoffs",
        "payoffs that scale with experience counters",
        {"oracle": r"experience counter"},
        r"experience counter",
    ),
    ("poison_matters", "opponents"): _spec(
        "Poison / infect",
        "infect and toxic threats plus proliferate to finish with poison",
        {"oracle": r"\binfect\b|\btoxic\b|poison counter|proliferate"},
        r"poison counter|\binfect\b|\btoxic\b",
    ),
    # "Modified" (CR 122) = a creature with a +1/+1 counter, Aura, OR Equipment. The
    # serve named only the literal word (the payoffs); the ENABLERS are structurally
    # Equipment/Aura permanents and counter-placers. Add those dimensions.
    ("modified_matters", "you"): _spec(
        "Modified",
        "counters, Auras, and Equipment to keep creatures modified",
        {"oracle": r"\bmodified\b|\+1/\+1 counter|aura or equipment"},
        r"\bmodified\b|\+1/\+1 counters?",
        serve_types=("equipment", "aura"),
    ),
    ("has_mutate", "you"): _spec(
        "Mutate",
        "mutate creatures and mutate-trigger payoffs",
        {"oracle": r"\bmutate\b"},
        r"\bmutate\b",
    ),
    ("food_matters", "you"): _spec(
        "Food",
        "Food makers plus sacrifice outlets and lifegain payoffs",
        {"oracle": r"\bfood token|foods? you control|sacrifice a food"},
        # Food-GRANTERS (Ragost, The Food Court, Ygra: "are Foods in addition").
        r"\bfood token|foods? you control|sacrifice a food"
        r"|(?:are|is|becomes?) (?:an? )?foods? in addition",
    ),
    # Hand-spec overriding the mined sweep detector so the serve also credits color
    # GRANTERS / fixers — "are the chosen color" (Painter's Servant, Shifting Sky) and
    # "<color> in addition to its colors" (Indigo Faerie) — not just "becomes the color
    # of your choice / all colors". Kept precise (no bare "becomes blue") to avoid
    # mana-color false positives.
    # Type change (the TYPE analog of color_change): a creature-type hoser (Gor Muldrak
    # "protection from Salamanders") wants the type-CHANGING toolbox — turn opponents'
    # creatures into the punished type so the hoser blanks them. Genuine changers only
    # ("target/each creature becomes <type>"), NOT the tribal anthems that merely
    # "choose a creature type" then buff your own.
    ("type_change", "you"): _spec(
        "Type change",
        "creature-type changers to force opponents into the punished type",
        {"oracle": _TYPE_CHANGER_ORACLE},
        _TYPE_CHANGER_ORACLE,
    ),
    # ADR-0027 β: color_change migrated to the Card IR via a byte-identical kept-mirror
    # (the lane fires from _COLOR_CHANGE_MIRROR in _signals_ir). This serve spec was
    # always hand-registered with its own curated SEARCH regex (broader than the
    # detector — it also credits color GRANTERS / fixers and color-conditional PAYOFFS),
    # independent of the deleted SWEEP producer, so it survives unchanged.
    ("color_change", "you"): _spec(
        "Color change",
        "effects that add or change colors — fixing plus color-matters enablers",
        {
            "oracle": r"becomes the color of your choice|the chosen color"
            r"|in addition to (?:its|their) (?:other )?colors?"
        },
        r"becomes the color of your choice|becomes? (?:the color|all colors)"
        r"|(?:are|is) the chosen color"
        r"|(?:is|are|becomes?) [^.]*(?:white|blue|black|red|green) "
        r"in addition to (?:its|their)"
        # Color-conditional PAYOFFS a color-CHANGER enables (make everything one color,
        # then "destroy/return all [color]" is a board wipe — CR 105/613, color is
        # continuously checked). Only the 2 color-change commanders see this serve, so
        # the narrow color-hosers stay scoped to the decks that turn them on.
        r"|(?:return|destroy|exile) all (?:white|blue|black|red|green) "
        r"(?:creature|permanent)s?"
        r"|return all permanents of the (?:chosen )?colou?r"
        r"|(?:white|blue|black|red|green) creatures? (?:can't|get [+\-])",
    ),
    # Hand-spec overriding the mined sweep detector so the serve also credits the Domain
    # ENABLERS — "lands you control are every basic land type" (Prismatic Omen, Dryad of
    # the Ilysian Grove) — not just the "domain" / "basic land types among" payoffs. The
    # `... in addition to` tail also credits the additive type-of-choice granter
    # (Navigator's Compass) WITHOUT the replacement color-fixers ("becomes X until
    # end of turn", no "in addition to") or anti-domain hosers (Blood Moon).
    ("domain_matters", "you"): _spec(
        "Domain",
        "basic land types and fixing to grow domain",
        {"oracle": r"\bdomain\b|basic land types?"},
        r"\bdomain\b|number of basic land types?|basic land types? among"
        r"|every basic land type|basic land types?[^.]*in addition to",
    ),
    ("clue_matters", "you"): _spec(
        "Clues / investigate",
        "investigate enablers and artifact/draw payoffs for Clues",
        {"oracle": r"\bclue\b|investigate"},
        r"\bclue\b|investigate",
    ),
    ("blood_matters", "you"): _spec(
        "Blood tokens",
        "Blood makers plus rummage and sacrifice payoffs",
        {"oracle": r"blood token"},
        r"blood token",
    ),
    ("daynight_matters", "you"): _spec(
        "Day / Night",
        "daybound/nightbound creatures and day-night transition payoffs",
        {"oracle": r"\bdaybound\b|\bnightbound\b|\bday\b|\bnight\b"},
        r"daybound|nightbound|becomes night|becomes day",
    ),
    ("voting_matters", "each"): _spec(
        "Voting / council",
        "will-of-the-council and vote effects — multiplayer politics",
        {"oracle": r"\bvote\b|will of the council|council's dilemma"},
        r"\bvote\b|will of the council",
    ),
    ("coven_matters", "you"): _spec(
        "Coven",
        "creatures with different powers to turn on coven",
        {"oracle": r"\bcoven\b|different powers"},
        r"\bcoven\b",
    ),
    # ADR-0027 β: conjure_makers migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted — detection moved to a byte-identical `\bconjure\b` kept word mirror in
    # signals._IR_KEPT_DETECTORS). The SERVE pool stays oracle-defined (Arena/Alchemy
    # conjure makers and payoffs), so hand-register the spec the sweep auto-register
    # loop used to build (scope "you", the deleted SWEEP row's scope), reusing the EXACT
    # deleted regex so the serve never drifts. SWEEP_LABELS keeps the human label.
    ("conjure_makers", "you"): _spec(
        *SWEEP_LABELS["conjure_makers"],
        {"oracle": r"\bconjure\b"},
        r"\bconjure\b",
    ),
    # Token doubling: a token doubler wants the token MAKERS it multiplies (Hornet
    # Queen), other token doublers to stack (Parallel Lives), and the go-wide / ETB
    # payoffs every doubled token feeds. Distinct from counter doubling.
    ("token_doubling", "you"): _spec(
        "Token doubling",
        "token makers to multiply, plus other token doublers and go-wide payoffs",
        {"oracle": r"create [^.]*creature token|twice that many[^.]*tokens?"},
        r"create [^.]*creature token"
        r"|(?:twice that many|double the number of) [^.]*tokens?",
        extras=(
            _TOKEN_MAKER_EXTRA,
            _TOKEN_DOUBLER_EXTRA,
            _GOWIDE_ANTHEM_EXTRA,
            _ETB_PAYOFF_EXTRA,
        ),
    ),
    # Counter doubling: a +1/+1-counter doubler wants the counter SOURCES it multiplies
    # — things that PUT counters (Hardened Scales fuel), creatures that ENTER WITH them
    # (Master Biomancer, Hangarback), proliferate, and other counter doublers to stack.
    ("counter_doubling", "you"): _spec(
        "Counter doubling",
        "+1/+1 counter sources to multiply, plus other counter doublers",
        {"oracle": r"\+1/\+1 counters?|double the number of [^.]*counters?"},
        r"(?:twice that many|double the number of) [^.]*counters?"
        # Creatures that ENTER WITH +1/+1 counters are counter sources — including the
        # variable "a number of" / "X" forms a digit-keyed regex misses (Master
        # Biomancer, Hangarback Walker).
        r"|enters with (?:a|an|one|two|three|x|\d+|a number of)[^.]*?\+1/\+1 counters?",
        extras=_COUNTERS_PACKAGE,
    ),
    # Serve is precise (the second-spell payoff). The SEARCH carried the same bare
    # "draw a card" FP; narrow it to the payoffs (second/third spell, multi-spell,
    # storm) so the avenue stops crediting every value permanent that draws.
    ("second_spell_matters", "you"): _spec(
        "Second-spell / storm-lite",
        "second-spell, multi-spell, and storm payoffs that reward chaining casts",
        {
            "oracle": (
                r"(?:second|third) spell you cast|cast your (?:second|third) spell"
                r"|cast two or more spells|\bstorm\b"
            )
        },
        r"(?:second|third) spell you cast|cast your (?:second|third) spell",
    ),
    # ── Mechanics recovered from the "rejected" families ────────────────────────
    # ADR-0027 β: token_copy_makers migrated to the Card IR via a byte-identical kept-
    # mirror (the lane fires from _TOKEN_COPY_MATTERS_MIRROR in _signals_ir). This serve
    # spec was always hand-registered and independent of the deleted _HAND_FLOOR
    # producer, so it survives unchanged — its curated SEARCH regex is intentionally
    # narrower than the detector (it omits the "twice that many … tokens" doubler arm,
    # which the _TOKEN_DOUBLER_EXTRA below already supplies as a separate avenue).
    ("token_copy_makers", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        {"oracle": r"token that's a copy|tokens? that are copies|\bpopulate\b"},
        r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|\bpopulate\b",
        # Deliver on "strong creatures to copy": a token-copy deck wants big bombs to
        # copy (Etali). power_min=6 keeps it to genuine bombs, mirroring clone_makers.
        serve_power_min=6,
        # A token-copy commander (Esix) turns each token it would create into a copy —
        # so it also wants raw token MAKERS (more tokens → more copies) and token
        # DOUBLERS (double the copies).
        # A token-copy deck floods the board with creatures that ENTER — so it's an ETB
        # deck too: ETB payoffs (Impact Tremors) and doublers (Panharmonicon) fire on
        # every copy.
        extras=(
            _TOKEN_MAKER_EXTRA,
            _TOKEN_DOUBLER_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _ETB_DOUBLER_EXTRA,
        ),
    ),
    ("specialize_matters", "you"): _spec(
        "Specialize",
        "specialize payoffs to swap a creature's stat/ability line "
        "(Backgrounds are a separate axis — see Partner / Background)",
        {"oracle": r"\bspecialize\b"},
        r"\bspecialize\b",
    ),
    # ADR-0027: ki_counter_matters + seek_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — phase's
    # counter-kind / effect-category projection). The SERVE pool (the cards that
    # ARE the thing) is still oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build — reusing the deleted regex as the
    # serve pattern. (SWEEP_LABELS still carries the human label.)
    ("ki_counter_makers", "you"): _spec(
        *SWEEP_LABELS["ki_counter_makers"],
        {"oracle": r"\bki counters?\b"},
        r"\bki counters?\b",
    ),
    ("ki_counter_matters", "you"): _spec(
        *SWEEP_LABELS["ki_counter_matters"],
        {"oracle": r"\bki counters?\b"},
        r"\bki counters?\b",
    ),
    ("seek_matters", "you"): _spec(
        *SWEEP_LABELS["seek_matters"],
        {"oracle": r"\bseek\b"},
        r"\bseek\b",
    ),
    # ADR-0027: mass_bounce + destroy_legendary had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — the bounce/destroy effect shape).
    # The SERVE pool (the cards that ARE the thing) is still oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex as the serve pattern. (SWEEP_LABELS still carries the human label.)
    ("mass_bounce", "any"): _spec(
        *SWEEP_LABELS["mass_bounce"],
        {
            "oracle": (
                r"return each (?:other )?(?:nonland )?permanent[^.]*to (?:its|their) "
                r"owner's hand|return each (?:other )?[^.]*?creatures?[^.]*?to "
                r"(?:its|their) owner's hand|return all[^.]*to (?:its|their) "
                r"owners' hands"
            )
        },
        (
            r"return each (?:other )?(?:nonland )?permanent[^.]*to (?:its|their) "
            r"owner's hand|return each (?:other )?[^.]*?creatures?[^.]*?to "
            r"(?:its|their) owner's hand|return all[^.]*to (?:its|their) owners' hands"
        ),
    ),
    ("destroy_legendary", "any"): _spec(
        *SWEEP_LABELS["destroy_legendary"],
        {"oracle": r"destroy (?:up to one )?target legendary (?:permanent|creature)"},
        r"destroy (?:up to one )?target legendary (?:permanent|creature)",
    ),
    # ADR-0027: the four bending lanes had their oracle-regex SWEEP_DETECTORS rows
    # deleted (detection moved to the Card IR — the kept word-detector mirror in
    # signals._IR_KEPT_DETECTORS). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build, reusing
    # each deleted regex as the serve pattern. (SWEEP_LABELS still carries the
    # human label.)
    ("airbend_makers", "you"): _spec(
        *SWEEP_LABELS["airbend_makers"],
        {"oracle": r"\bairbend(?:ing|s)?\b"},
        r"\bairbend(?:ing|s)?\b",
    ),
    ("earthbend_matters", "you"): _spec(
        *SWEEP_LABELS["earthbend_matters"],
        {"oracle": r"\bearthbend(?:ing|s)?\b"},
        r"\bearthbend(?:ing|s)?\b",
    ),
    # _matters sweep (ADR-0034): waterbend split. The DOER arm (waterbend_makers,
    # keyword bearers) and the PAYOFF arm (waterbend_matters) both serve the same
    # oracle pool — clone-pilot precedent: the serve avenue legitimately offers
    # makers + payoffs together; only membership splits by role.
    ("waterbend_makers", "you"): _spec(
        *SWEEP_LABELS["waterbend_makers"],
        {"oracle": r"\bwaterbend(?:ing|s)?\b"},
        r"\bwaterbend(?:ing|s)?\b",
    ),
    ("waterbend_matters", "you"): _spec(
        *SWEEP_LABELS["waterbend_matters"],
        {"oracle": r"\bwaterbend(?:ing|s)?\b"},
        r"\bwaterbend(?:ing|s)?\b",
    ),
    # _matters sweep (ADR-0034): firebending split. The MAKER arm (firebending_makers,
    # Firebending-keyword bearers) and the PAYOFF arm (firebending_matters, keyword-less
    # Fire-Nation references) both serve the same oracle pool — clone-pilot precedent:
    # the serve avenue legitimately offers makers + payoffs together; only membership
    # splits by role.
    ("firebending_makers", "you"): _spec(
        *SWEEP_LABELS["firebending_makers"],
        {"oracle": r"\bfirebend(?:ing|s)?\b"},
        r"\bfirebend(?:ing|s)?\b",
    ),
    ("firebending_matters", "you"): _spec(
        *SWEEP_LABELS["firebending_matters"],
        {"oracle": r"\bfirebend(?:ing|s)?\b"},
        r"\bfirebend(?:ing|s)?\b",
    ),
    # ADR-0027 (t2b2-A): aura_equip_kw_grant / counter_grants_kw /
    # conditional_self_protection had their oracle-regex SWEEP_DETECTORS rows deleted
    # (detection moved to the Card IR — the grant_keyword effect shape gated on the
    # subject Filter + the granted keyword). The SERVE pool (the cards that ARE the
    # thing) stays oracle-defined, so hand-register the spec the sweep auto-register
    # loop used to build, reusing each deleted regex as the serve pattern.
    # (SWEEP_LABELS still carries each human label.)
    ("aura_equip_kw_grant", "you"): _spec(
        *SWEEP_LABELS["aura_equip_kw_grant"],
        {
            "oracle": (
                r"(?:auras?|equipment) you control have (?:exalted|flying|trample"
                r"|deathtouch|lifelink|vigilance|haste|first strike|double strike"
                r"|hexproof|ward|menace|reach|indestructible)"
            )
        },
        (
            r"(?:auras?|equipment) you control have (?:exalted|flying|trample"
            r"|deathtouch|lifelink|vigilance|haste|first strike|double strike"
            r"|hexproof|ward|menace|reach|indestructible)"
        ),
    ),
    ("counter_grants_kw", "you"): _spec(
        *SWEEP_LABELS["counter_grants_kw"],
        {
            "oracle": (
                r"creature you control with a \+1/\+1 counter on it (?:has|have) "
                r"(?:haste|flying|trample|menace|vigilance|lifelink)"
            )
        },
        (
            r"creature you control with a \+1/\+1 counter on it (?:has|have) "
            r"(?:haste|flying|trample|menace|vigilance|lifelink)"
        ),
    ),
    ("conditional_self_protection", "you"): _spec(
        *SWEEP_LABELS["conditional_self_protection"],
        {
            "oracle": (
                r"has hexproof (?:if|while|as long as|during)"
                r"|during your turn,[^.]*has (?:hexproof|indestructible|protection)"
                r"|has (?:hexproof|indestructible) if"
            )
        },
        (
            r"has hexproof (?:if|while|as long as|during)"
            r"|during your turn,[^.]*has (?:hexproof|indestructible|protection)"
            r"|has (?:hexproof|indestructible) if"
        ),
    ),
    # ADR-0027: attractions_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to an _IR_KEPT_DETECTORS word mirror). The SERVE pool stays
    # oracle-defined (Attraction openers / visit payoffs), so hand-register the spec
    # the sweep auto-register loop used to build, reusing the deleted regex.
    ("attractions_matter", "you"): _spec(
        *SWEEP_LABELS["attractions_matter"],
        {"oracle": r"\battraction\b|open an attraction"},
        r"\battraction\b|open an attraction",
    ),
    # ADR-0027: stickers_matter had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to a byte-identical STICKERS_MATTER_REGEX _IR_KEPT_DETECTORS word
    # mirror). The SERVE pool stays oracle-defined (the {TK}/sticker effects), so
    # hand-register the spec the sweep auto-register loop used to build, reusing the
    # deleted regex (now the shared STICKERS_MATTER_REGEX constant) so serve / mirror /
    # detector never drift.
    ("stickers_matter", "you"): _spec(
        *SWEEP_LABELS["stickers_matter"],
        {"oracle": STICKERS_MATTER_REGEX},
        STICKERS_MATTER_REGEX,
    ),
    # ADR-0027 tranche2-C: extra_land_drop had its oracle-regex SWEEP_DETECTORS row
    # deleted (detection moved to the Card IR — cheat_play / topdeck_select with a Land
    # subject + a kept word mirror). The SERVE pool (the put-a-land-into-play effects)
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing the deleted regex.
    ("extra_land_drop", "you"): _spec(
        *SWEEP_LABELS["extra_land_drop"],
        {
            "oracle": (
                r"put a land(?: card)? from your hand onto the battlefield"
                r"|you may put a land [^.]*onto the battlefield"
            )
        },
        r"put a land(?: card)? from your hand onto the battlefield"
        r"|you may put a land [^.]*onto the battlefield",
    ),
    # ADR-0027: companion_keyword had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Scryfall `companion` keyword). The SERVE pool stays
    # oracle-defined (a companion's starting-deck restriction text), so
    # hand-register the spec the sweep auto-register loop used to build, reusing
    # the deleted regex as the serve pattern.
    ("companion_keyword", "you"): _spec(
        *SWEEP_LABELS["companion_keyword"],
        {
            "oracle": (
                r"companion —|each (?:creature |permanent )?card in your "
                r"starting deck|your starting deck contains"
            )
        },
        r"companion —|each (?:creature |permanent )?card in your starting deck"
        r"|your starting deck contains",
    ),
    # ADR-0027: has_soulbond had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `soulbond` keyword + a
    # `soulbond` effect marker for non-keyword references). The SERVE pool (the
    # creatures that ARE the thing — they carry the soulbond keyword) stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex as the serve pattern.
    ("has_soulbond", "you"): _spec(
        *SWEEP_LABELS["has_soulbond"],
        {"oracle": r"\bsoulbond\b"},
        r"\bsoulbond\b",
    ),
    # ADR-0027: has_devour had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall `devour` keyword + phase's
    # `devour` effect category). The SERVE pool (the cards that ARE devourers /
    # token fodder to devour) stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing the deleted regex as the
    # serve pattern. (SWEEP_LABELS still carries the human label.)
    ("has_devour", "you"): _spec(
        *SWEEP_LABELS["has_devour"],
        {"oracle": r"\bdevour\b"},
        r"\bdevour\b",
    ),
    # ADR-0027 tail-supplement: boast/exhaust/explore/phasing/end_the_turn/
    # trigger_doubling each had their oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — keyword array + effect-category + supplement
    # markers). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing each deleted regex.
    # _matters sweep (ADR-0034): the MAKER arm of the boast split — boast creatures
    # (cards carrying the Boast ability). Same \bboast\b serve pool as the payoff arm.
    ("boast_makers", "you"): _spec(
        *SWEEP_LABELS["boast_makers"],
        {"oracle": r"\bboast\b"},
        r"\bboast\b",
    ),
    ("boast_matters", "you"): _spec(
        *SWEEP_LABELS["boast_matters"],
        {"oracle": r"\bboast\b"},
        r"\bboast\b",
    ),
    ("exhaust_matters", "you"): _spec(
        *SWEEP_LABELS["exhaust_matters"],
        {"oracle": r"\bexhaust\b"},
        r"\bexhaust\b",
    ),
    ("explore_matters", "you"): _spec(
        *SWEEP_LABELS["explore_matters"],
        {"oracle": r"\bexplores?\b"},
        r"\bexplores?\b",
    ),
    ("phasing_makers", "you"): _spec(
        *SWEEP_LABELS["phasing_makers"],
        {"oracle": r"phase out|phases out|phased out"},
        r"phase out|phases out|phased out",
    ),
    # ADR-0027: station_matters migrated to the Card IR (its SWEEP_DETECTORS row is
    # deleted, so the auto-register loop no longer builds this spec). Hand-register it
    # reusing the pinned STATION_MATTERS_REGEX so the serve pool never drifts from the
    # (now-deleted) detector. SWEEP_LABELS still carries the human label.
    ("station_matters", "you"): _spec(
        *SWEEP_LABELS["station_matters"],
        {"oracle": STATION_MATTERS_REGEX},
        STATION_MATTERS_REGEX,
    ),
    # ADR-0027: tap_down migrated to the Card IR (its SWEEP_DETECTORS row is deleted, so
    # the auto-register loop no longer builds this spec). Hand-register it reusing the
    # pinned TAP_DOWN_REGEX so the serve pool never drifts from the (now-deleted)
    # detector. Scope 'opponents' (the deleted SWEEP row's forced scope). SWEEP_LABELS
    # still carries the human label.
    ("tap_down", "opponents"): _spec(
        *SWEEP_LABELS["tap_down"],
        {"oracle": TAP_DOWN_REGEX},
        TAP_DOWN_REGEX,
    ),
    ("end_the_turn", "you"): _spec(
        *SWEEP_LABELS["end_the_turn"],
        {"oracle": r"\bend the turn\b"},
        r"\bend the turn\b",
    ),
    ("trigger_doubling", "you"): _spec(
        *SWEEP_LABELS["trigger_doubling"],
        {"oracle": r"triggers? an additional time|trigger an additional time"},
        r"triggers? an additional time|trigger an additional time",
    ),
    # ADR-0027: cant_block_grant had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `cant_block` effect category + a
    # modal/granted-quoted dropped-static face marker). The SERVE pool stays
    # oracle-defined, so hand-register the spec the sweep auto-register loop used to
    # build, reusing the deleted regex.
    ("cant_block_grant", "you"): _spec(
        *SWEEP_LABELS["cant_block_grant"],
        {"oracle": r"target creature can't block"},
        r"target creature can't block",
    ),
    # ADR-0027: convoke_matters / myriad_grant / typed_anthem_multi / life_total_set
    # each had their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the
    # Card IR — keyword array + effect-category + supplement markers). The SERVE pool
    # stays oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing each deleted regex.
    ("convoke_matters", "you"): _spec(
        *SWEEP_LABELS["convoke_matters"],
        {"oracle": r"\bconvoke\b"},
        r"\bconvoke\b",
    ),
    # ADR-0027 t2b4a-B: win_lose_game / alt_cost_keyword / partner_background each had
    # their oracle-regex SWEEP_DETECTORS row deleted (detection moved to the Card IR —
    # win/lose Effect categories; the alt-cost & partner-family Scryfall keyword
    # arrays). The SERVE pool stays oracle-defined, so hand-register the spec the sweep
    # auto-register loop used to build, reusing each deleted regex. (SWEEP_LABELS still
    # carries each human label.)
    ("win_lose_game", "any"): _spec(
        *SWEEP_LABELS["win_lose_game"],
        {
            "oracle": (
                r"you win the game|(?:that player|each opponent"
                r"|target (?:player|opponent)) loses the game"
            )
        },
        r"you win the game|(?:that player|each opponent"
        r"|target (?:player|opponent)) loses the game",
    ),
    ("alt_cost_keyword", "you"): _spec(
        *SWEEP_LABELS["alt_cost_keyword"],
        {"oracle": r"\bweb-slinging\b|\bsneak\b|\bmayhem\b"},
        r"\bweb-slinging\b|\bsneak\b|\bmayhem\b",
        serve_keywords=("web-slinging", "sneak", "mayhem"),
    ),
    # partner_background's avenue REPLACES this serve with a partner-legality search
    # (engine.partner_search + the ADR-0019 color-widening flag); this spec is the
    # fallback pool — the cards that carry a partner-family keyword.
    ("partner_background", "you"): _spec(
        *SWEEP_LABELS["partner_background"],
        {
            "oracle": (
                r"choose a background|partner with|\bpartner\b(?! with)"
                r"|\bfriends forever\b|\bdoctor's companion\b"
            )
        },
        r"choose a background|partner with|\bpartner\b(?! with)"
        r"|\bfriends forever\b|\bdoctor's companion\b",
        serve_keywords=(
            "partner",
            "partner with",
            "choose a background",
            "doctor's companion",
            "friends",
        ),
    ),
    # ADR-0027 t2b5-C: named_counter_misc / powerup_matters each had their oracle-regex
    # SWEEP_DETECTORS row deleted (detection moved to the Card IR — named_counter_misc
    # to the kept word mirror; powerup_matters to the Scryfall Power-up keyword array).
    # Each had no hand spec, so the sweep auto-register loop built its serve; reproduce
    # that spec here, reusing SWEEP_LABELS + the deleted regex (byte-identical pool).
    ("named_counter_misc", "you"): _spec(
        *SWEEP_LABELS["named_counter_misc"],
        {
            "oracle": (
                r"\b(?:egg|divinity|prey|bounty|bribery|page|study|knowledge"
                r"|silver|gold|fate|incubation) counters?\b"
            )
        },
        r"\b(?:egg|divinity|prey|bounty|bribery|page|study|knowledge"
        r"|silver|gold|fate|incubation) counters?\b",
    ),
    ("powerup_matters", "you"): _spec(
        *SWEEP_LABELS["powerup_matters"],
        {"oracle": r"power-up —"},
        r"power-up —",
        serve_keywords=("power-up",),
    ),
    # ADR-0027: rad_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's `rad_counter` effect / rad place_counter
    # + a "rad counter(s)" face marker). The IR fires scope "opponents" (rad counters go
    # on players as a kill clock). Serve hand-registered reusing the deleted regex.
    ("rad_counter_makers", "opponents"): _spec(
        *SWEEP_LABELS["rad_counter_makers"],
        {"oracle": r"\brad counters?\b"},
        r"\brad counters?\b",
    ),
    # ADR-0027: oil_counter_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter(counter_kind='oil') placer
    # + an "oil counter(s)" payoff marker). Serve hand-registered reusing the deleted
    # regex so the lane still surfaces oil sources and payoffs.
    ("oil_counter_matters", "you"): _spec(
        *SWEEP_LABELS["oil_counter_matters"],
        {"oracle": r"\boil counters?\b"},
        r"\boil counters?\b",
    ),
    # ADR-0027: shield_counter_makers had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — phase's place_counter / hascounters
    # counter_kind='shield' structural arm + a byte-identical kept word mirror). The
    # SERVE pool (the cards that ARE the thing — shield-counter sources and payoffs) is
    # still oracle-defined, so hand-register the spec the sweep auto-register loop used
    # to build, reusing the deleted regex as the serve pattern. CR 122.1c.
    ("shield_counter_makers", "you"): _spec(
        *SWEEP_LABELS["shield_counter_makers"],
        {"oracle": r"\bshield counters?\b"},
        r"\bshield counters?\b",
    ),
    # ADR-0027: fight_makers had its oracle-regex SWEEP_DETECTORS row deleted (moved to
    # the Card IR — phase's fight effect + a granted/quoted/modal fight marker). Serve
    # hand-registered reusing the deleted regex (the lane wants big creatures to fight
    # with — surface fatties via power_min, plus the gear/buffs that suit them up).
    ("fight_makers", "you"): _sweep_spec_with_extras(
        "fight_makers",
        serve_power_min=4,
        regex=(
            r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
            r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature|\bfight each "
            r"other\b|\bfights? it\b|\bfights? (?:another|each)"
        ),
    ),
    # ADR-0027: has_changeling had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — the Scryfall changeling keyword + a "changeling"
    # / "is every creature type" all-tribes marker). Serve hand-registered reusing the
    # deleted regex (plus the changeling keyword dimension for the bearers).
    ("has_changeling", "you"): _spec(
        *SWEEP_LABELS["has_changeling"],
        {"oracle": r"is every creature type|\bchangeling\b"},
        r"is every creature type|\bchangeling\b",
        serve_keywords=("changeling",),
    ),
    # ADR-0027: starting_life_matters had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a "starting life total" compare marker). Serve
    # hand-registered reusing the deleted regex.
    ("starting_life_matters", "you"): _spec(
        *SWEEP_LABELS["starting_life_matters"],
        {
            "oracle": (
                r"(?:greater than|less than|above|below|equal to|more than) your "
                r"starting life total|starting life total"
            )
        },
        (
            r"(?:greater than|less than|above|below|equal to|more than) your "
            r"starting life total|starting life total"
        ),
    ),
    ("myriad_grant", "you"): _spec(
        *SWEEP_LABELS["myriad_grant"],
        {"oracle": r"gains? myriad|\bmyriad\b"},
        r"gains? myriad|\bmyriad\b",
    ),
    ("typed_anthem_multi", "you"): _spec(
        *SWEEP_LABELS["typed_anthem_multi"],
        {
            "oracle": (
                r"each (?:other )?creature (?:you control )?that's (?:a |an )\w+"
                r"[^.]*(?:gets?|have|has|gains?)"
            )
        },
        (
            r"each (?:other )?creature (?:you control )?that's (?:a |an )\w+"
            r"[^.]*(?:gets?|have|has|gains?)"
        ),
    ),
    ("life_total_set", "any"): _spec(
        *SWEEP_LABELS["life_total_set"],
        {
            "oracle": (
                r"life total (?:becomes|equal to)|equal to half (?:that|your|a) "
                r"(?:player'?s? )?life|exchange (?:your )?life total"
                r"|exchange life totals?|set your life total to"
                r"|double target player's life total"
            )
        },
        (
            r"life total (?:becomes|equal to)|equal to half (?:that|your|a) "
            r"(?:player'?s? )?life|exchange (?:your )?life total"
            r"|exchange life totals?|set your life total to"
            r"|double target player's life total"
        ),
    ),
    # ADR-0027: all_creatures_kw_grant + facedown_matters had their oracle-regex
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # GrantKeyword effect / the manifest-cloak-morph effect categories + kept word
    # mirror). The SERVE pool stays oracle-defined, so hand-register the spec the
    # sweep auto-register loop used to build, reusing each deleted regex.
    ("all_creatures_kw_grant", "any"): _spec(
        *SWEEP_LABELS["all_creatures_kw_grant"],
        {
            "oracle": (
                r"all creatures have (?:haste|flying|trample|vigilance|menace"
                r"|hexproof|deathtouch|first strike|double strike|reach|lifelink)"
            )
        },
        r"all creatures have (?:haste|flying|trample|vigilance|menace|hexproof"
        r"|deathtouch|first strike|double strike|reach|lifelink)",
    ),
    ("facedown_matters", "you"): _spec(
        *SWEEP_LABELS["facedown_matters"],
        {
            "oracle": (
                r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
                r"|face-?down creatures?|as a 2/2 face-?down"
                r"|turn (?:it|that creature|this creature|them"
                r"|a permanent you control) face up|turn target [^.]*?face up"
                r"|turned face up this turn"
            )
        },
        r"\bmorph\b|\bmegamorph\b|\bmanifest\b|\bdisguise\b|\bcloak\b"
        r"|face-?down creatures?|as a 2/2 face-?down"
        r"|turn (?:it|that creature|this creature|them|a permanent you control) "
        r"face up|turn target [^.]*?face up|turned face up this turn",
    ),
    # ADR-0027: affinity_type + evasion_denial had their oracle-regex SWEEP_DETECTORS
    # rows deleted (detection moved to the Card IR — affinity ← the Scryfall keyword +
    # an `affinity` conferred-grant marker; evasion_denial ← phase's named-walk
    # evasion_denial effect + a generic-landwalk-umbrella marker). The auto-register
    # sweep loop used to build their serve specs from the now-gone rows, so hand-
    # register them reusing each deleted regex as the serve pattern.
    ("affinity_type", "you"): _spec(
        *SWEEP_LABELS["affinity_type"],
        {"oracle": r"\baffinity\b|spells you cast have affinity"},
        r"\baffinity\b|spells you cast have affinity",
    ),
    ("evasion_denial", "opponents"): _spec(
        *SWEEP_LABELS["evasion_denial"],
        {"oracle": r"can be blocked as though (?:it|they) didn't have"},
        r"can be blocked as though (?:it|they) didn't have",
    ),
    # ADR-0027: lure_makers had its oracle-regex SWEEP_DETECTORS row deleted (detection
    # moved to the Card IR — a structural `lure` arm + a byte-identical kept mirror for
    # the Aftermath-DFC back face phase drops). The SERVE pool stays oracle-defined, so
    # hand-register the spec the sweep auto-register loop used to build (scope 'you'),
    # reusing the pinned LURE_MATTERS_REGEX so the serve never drifts from the deleted
    # detector. CR 509.1c.
    ("lure_makers", "you"): _spec(
        *SWEEP_LABELS["lure_makers"],
        {"oracle": LURE_MATTERS_REGEX},
        LURE_MATTERS_REGEX,
    ),
    # ADR-0027: damage_doubling had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the damage_doubling DamageDone-replacement category, now
    # covering triple + the nested AddTargetReplacement / CreateDamageReplacement
    # amplifiers, plus a face marker for the dropped modification). The auto-register
    # sweep loop used to build its serve spec from the now-gone row, so hand-register
    # it reusing the deleted regex as the serve pattern (minus the halving over-fire —
    # the serve still wants double/triple doublers, not Dark Sphere's prevention).
    ("damage_doubling", "you"): _spec(
        *SWEEP_LABELS["damage_doubling"],
        {
            "oracle": (
                r"deals? (?:double|triple) that damage"
                r"|deals? twice that (?:much|damage)"
                r"|double (?:all damage|the (?:next )?damage)"
                r"|deals that much damage plus"
            )
        },
        r"deals? (?:double|triple) that damage"
        r"|deals? twice that (?:much|damage)"
        r"|double (?:all damage|the (?:next )?damage)"
        r"|deals that much damage plus",
    ),
    # ADR-0027: commander_matters / hand_disruption / opponent_exile_matters had their
    # SWEEP_DETECTORS rows deleted (detection moved to the Card IR — a structural
    # predicate/trigger bind + a kept word mirror per key). The auto-register sweep loop
    # used to build their serve specs from the now-gone rows, so hand-register them
    # reusing each deleted regex as the serve pattern.
    ("commander_matters", "you"): _spec(
        *SWEEP_LABELS["commander_matters"],
        {
            "oracle": (
                r"commanders? you (?:control|own) "
                r"(?:have|has|get|gets|gain|gains)"
                r"|commander creatures? you (?:own|control)"
                r"|whenever your commander\b|whenever a commander\b"
                r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
                r"|is your commander|it'?s your commander"
                r"|while [^.]*your commander|it's a copy of your other commander"
                r"|copy of any of your commanders|each commander you (?:control|own)"
                r"|for each commander|commander damage"
            )
        },
        r"commanders? you (?:control|own) (?:have|has|get|gets|gain|gains)"
        r"|commander creatures? you (?:own|control)"
        r"|whenever your commander\b|whenever a commander\b"
        r"|your commander (?:has|have|deals|enters|attacks|gets|gains)"
        r"|is your commander|it'?s your commander|while [^.]*your commander"
        r"|it's a copy of your other commander|copy of any of your commanders"
        r"|each commander you (?:control|own)|for each commander|commander damage",
    ),
    ("hand_disruption", "opponents"): _spec(
        *SWEEP_LABELS["hand_disruption"],
        {
            "oracle": (
                r"look at (?:target player|that player|an opponent|each opponent"
                r"|target opponent)'?s?'? hands?"
                r"|plays? with (?:their|his or her) hands? revealed"
                r"|reveals? (?:their|his or her) hands?"
                r"|reveals? (?:\w+ )?cards? (?:at random )?from "
                r"(?:their|his or her|that player's) hand"
                r"|reveals?[^.]*until you say stop"
            )
        },
        r"look at (?:target player|that player|an opponent|each opponent"
        r"|target opponent)'?s?'? hands?"
        r"|plays? with (?:their|his or her) hands? revealed"
        r"|reveals? (?:their|his or her) hands?"
        r"|reveals? (?:\w+ )?cards? (?:at random )?from "
        r"(?:their|his or her|that player's) hand"
        r"|reveals?[^.]*until you say stop",
    ),
    ("opponent_exile_matters", "opponents"): _spec(
        *SWEEP_LABELS["opponent_exile_matters"],
        {
            "oracle": (
                r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
                r"|for each card your opponents own in exile"
                r"|opponents own in exile"
                r"|exile (?:target player's|target opponent's|each opponent's"
                r"|that player's) graveyard"
                r"|if a card would be put into an opponent's graveyard"
            )
        },
        r"cards? (?:your opponents own|an opponent owns)[^.]*in exile"
        r"|for each card your opponents own in exile|opponents own in exile"
        r"|exile (?:target player's|target opponent's|each opponent's"
        r"|that player's) graveyard"
        r"|if a card would be put into an opponent's graveyard",
    ),
    ("villainous_choice", "you"): _spec(
        "Villainous choice",
        "villainous-choice cards (the punisher pool a villainous-choice commander — "
        "The Valeyard, Davros, Missy — is built to present and double)",
        {"oracle": r"villainous choice"},
        r"villainous choice",
    ),
    ("curse_matters", "you"): _spec(
        "Curses",
        "Curse cards to recur, attach, and pile onto opponents (Lynde, Cheerful "
        "Tormentor) — served by the Curse subtype, not oracle prose",
        {"card_type": "Curse"},
        None,
        serve_types=("curse",),
    ),
    ("dice_matters", "you"): _spec(
        "Dice rolling",
        "dice-rolling enablers and roll-result payoffs",
        {"oracle": r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|\bd20\b"},
        r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)|whenever you roll",
    ),
    # A crime (CR 700.13) targets opponents / their permanents / spells they control —
    # i.e. targeted removal + explicit-opponent-target. The SEARCH's bare
    # `target.*spell` credited every counterspell; drop it for concrete removal shapes.
    ("crimes_matter", "you"): _spec(
        "Crimes",
        "targeted removal and abilities that count as committing a crime",
        {
            "oracle": (
                r"commit(?:s|ted)? a crime|whenever you commit"
                r"|target (?:opponent|player|opponents)"
                r"|destroy target|exile target (?:creature|permanent|nonland)"
                r"|deals? (?:\d+|x) damage to target (?:creature|player|opponent)"
            )
        },
        r"commit(?:s|ted)? a crime|whenever you commit",
    ),
    ("connive_makers", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        {"oracle": r"\bconnives?\b|draw a card, then discard"},
        r"\bconnives?\b",
    ),
    ("spell_copy_makers", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        {"oracle": r"copy (?:target|that)|instant or sorcery|\bstorm\b"},
        r"copy target (?:instant|sorcery|spell)|\bcopy that spell\b|\bstorm\b",
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp", "you"): _spec(
        "Ramp / big mana",
        "mana rocks, dorks, and land ramp to accelerate into your payoffs",
        {"oracle": r"add \{|search your library for .*\bland\b|" + _BASIC_LAND_FETCH},
        r"\{t\}[^.]*:\s*add|add .* mana|search your library for .*\bland\b|"
        + _BASIC_LAND_FETCH,
        # Deliver on "accelerate into your payoffs": the big bombs (Ghalta) and creature
        # cost reducers (Goreclaw). Only ~3% of commanders open this big-mana lane, so
        # crediting power-6+ fatties is on-theme, not noise.
        serve_power_min=6,
        extras=(_CREATURE_COST_EXTRA,),
    ),
    # The `deals .* damage to target creature` branch missed every burn spell pointed at
    # ANY target (Lightning Bolt, Shock — "deals N damage to any target"). Broaden the
    # damage clause to any-target / player burn; constrain `.*` to a single clause.
    ("removal", "you"): _spec(
        "Removal / interaction",
        "destroy and burn removal — note indestructible/regeneration blank it",
        {"oracle": r"destroy target|deals .* damage to target"},
        r"destroy target (?:creature|permanent|artifact|enchantment|planeswalker|land"
        r"|nonland)"
        r"|deals? (?:\d+|x|that much) [^.\n]*damage to "
        r"(?:target (?:creature|permanent|planeswalker)|any target)",
    ),
    # VETO exile-and-return (blink): a card that exiles a creature then returns it is a
    # flicker engine, not removal (Ephemerate, Cloudshift) — CR 603.6e.
    ("exile_removal", "you"): _spec(
        "Exile removal",
        "exile-based removal that bypasses indestructible and stops recursion",
        {"oracle": r"exile target (?:creature|permanent|artifact|enchantment)"},
        r"exile target (?:creature|permanent|artifact|enchantment|nonland)",
        serve_not=r"return (?:it|them|that card|those cards|that permanent)"
        r"[^.]*battlefield",
    ),
    # ADR-0027 tranche2-B: exile_until_leaves's SWEEP_DETECTORS row was deleted
    # (detection moved to the Card IR — _is_exile_until_leaves). It used to be
    # auto-registered from that row (the SWEEP→SPECS fallback below), so hand-register
    # it now, keeping the old regex as the serve pattern.
    ("exile_until_leaves", "you"): _spec(
        *SWEEP_LABELS["exile_until_leaves"],
        {"oracle": r"exile [^.]*until [^.]*leaves the battlefield"},
        r"exile [^.]*until [^.]*leaves the battlefield",
    ),
    ("counter_control", "you"): _spec(
        "Counterspells / control",
        "counterspells and stack interaction",
        {"oracle": r"counter target"},
        r"counter target",
    ),
    # The bare `… (gain|have)` tail matched any "creatures you control gain/have X". Tie
    # it to the actual keyword-grant list or a static (+N/+N, not "until end of turn")
    # anthem, so a one-shot pump or a non-keyword clause doesn't read as a team grant.
    ("team_buff", "you"): _spec(
        "Team keyword grants",
        "keyword grants and anthems for your board",
        {"oracle": r"creatures you control (?:gain|have)"},
        r"creatures? you control (?:gain|gains|have|has) (?:flying|trample|menace"
        r"|hexproof|indestructible|protection|deathtouch|lifelink|double strike"
        r"|first strike|vigilance|haste|ward|reach)"
        r"|creatures you control get \+\d+/\+\d+",
        serve_not=r"creatures you control get \+\d+/\+\d+ until end of turn",
    ),
    ("tutor", "you"): _spec(
        "Tutors",
        "tutors to assemble your key pieces and combos",
        {"oracle": r"search your library for"},
        r"search your library for",
    ),
    ("untap_engine", "you"): _spec(
        "Untap engine",
        "untap effects to reuse tap abilities and generate value",
        {"oracle": _UNTAP_ORACLE},
        _UNTAP_ORACLE,
    ),
    # Tap/untap commander (Tui and La) wants the untap effects that retrigger it.
    # ADR-0027: tap_untap_matters had its SWEEP_DETECTORS row deleted (detection moved
    # to the Card IR — the `taps` trigger + a "becomes tapped/untapped" kept mirror).
    # The serve pool stays oracle-defined, so pass the deleted regex explicitly.
    ("tap_untap_matters", "you"): _sweep_spec_with_extras(
        "tap_untap_matters",
        (_UNTAP_EXTRA,),
        regex=(r"whenever [^.]*becomes? (?:tapped|untapped)|becomes? untapped, put"),
    ),
    # Activated-ability engine: the support package for a {T}: commander — activated-
    # ability cost reducers (Training Grounds), untappers + haste-for-abilities
    # (Thousand-Year Elixir, Ioreth), and ability copiers (Rings of Brighthearth,
    # Illusionist's Bracers — keyed on "isn't a mana ability", their shared marker).
    ("activated_ability", "you"): _spec(
        "Activated-ability engine",
        "cost reducers, untappers, haste-for-abilities, and copiers that power your "
        "commander's activated abilities",
        {"oracle": r"activated abilit|untap (?:target|another)"},
        r"activated abilities[^.]*\bcost\b"
        r"|untap (?:target|all|another|each)"
        # Untap-enablers re-tap a {T}: commander for extra activations (CR 302.6). The
        # bare clause above misses the aura/equipment forms that untap a single creature
        # — Freed from the Real / Pemmin's Aura "untap enchanted creature", Sting "untap
        # equipped creature" — and the "buff your creature, untap it" tricks (Shore Up).
        # Both are anchored to a CREATURE so land-untap ramp (Rude Awakening, "untap two
        # lands") stays out.
        r"|untap (?:enchanted|equipped) creature"
        r"|target creature you control[\s\S]{0,120}?untap it"
        r"|activate (?:its |their )?abilit(?:y|ies)[^.]*as though"
        r"|as though (?:those creatures|it|they) (?:had|have) haste"
        # Haste-GRANTERS lift summoning sickness (CR 302.6 / 702.10) so a {T}: commander
        # activates the turn it enters or re-enters (blink/reanimate). Anchored to a
        # grant clause ("<your/equipped/enchanted/target creature> ... gains/has haste")
        # so a vanilla creature with innate haste (just "Haste") does NOT match.
        r"|(?:creatures? you control|equipped creature|enchanted creature"
        r"|target creature)[^.]*(?:gains?|have|has) haste"
        r"|isn't a mana ability"
        # The PAYOFF targets: creatures with an expensive mana-cost activated ability
        # ("{8}:", "{3}{R}:", "{X}, {T}:") the cost-reducer/untapper exploits. Requires
        # a mana symbol in the cost (a {T}-only dork gains nothing from a discount).
        r"|\{(?:\d+|x)\}[^.:\n]{0,25}:",
    ),
    # YOU must be the one gaining control — VETO the donate shapes where an OPPONENT
    # gains control of your stuff (Sky Swallower). Add the exile-and-cast theft form.
    # ADR-0027 β: gain_control migrated to the Card IR (the lane fires from a gated
    # structural arm in extract_signals_ir + a narrowed _GAIN_CONTROL_MIRROR + a facade
    # cross-open reconciliation). This serve spec was always hand-registered with its
    # own curated SEARCH regex (broader than the deleted `gain control of` detector — it
    # also
    # credits "you control enchanted permanent" Auras and Bribery/Acquire library-
    # seizes), independent of the deleted producer, so it survives unchanged.
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        {"oracle": r"gain control of"},
        r"you (?:gain|may gain) control of"
        r"|gain control of (?:target|all|each|another|that|them|those)"
        r"|you control enchanted (?:creature|permanent)"
        r"|you may (?:play|cast)[^.]*from (?:that|target) (?:player|opponent)"
        # Bribery / Acquire: seize a card out of an OPPONENT's library and seat it
        # onto the battlefield UNDER YOUR CONTROL — you now control a permanent you
        # don't own (genuine gain-control), just sourced from a library. Anchored to
        # "opponent's library" so a graveyard reanimator is excluded. NOT the same as
        # the borrow-and-cast engines (Gonti / Hostage Taker / Thief): those exile a
        # card and let you CAST it — playing what you don't own (theft_matters), never
        # a battlefield control change — so they stay out of this lane.
        r"|opponent's library for [^.]*onto the battlefield under your control",
        serve_not=r"(?:opponent|another player|target player|that player) "
        r"gains control of",
    ),
    # Align the serve with the extraction regex so the wheel-punishers and "each
    # opponent/player discards" forms (Bottomless Pit, Hymn) are recovered.
    ("opponent_discard", "opponents"): _spec(
        "Hand attack",
        "forced discard and hand disruption aimed at opponents",
        {"oracle": r"opponent discards|each player discards|target player discards"},
        r"(?:each opponent|target opponent|an opponent|that opponent|each player"
        r"|target player|that player) discards|opponent[^.]*discards",
        extras=(_DISCARD_PUNISH_EXTRA, _HELLBENT_PUNISH_EXTRA),
    ),
    # Bare `can't be blocked` matched the menace/flying REMINDER "can't be blocked
    # except by …" on vanilla evasive creatures (~673). Exclude the "except" form (a
    # conditional restriction, CR 509.1b, not true unblockable) and add landwalk.
    ("evasion_self", "you"): _spec(
        "Evasion / unblockable",
        "unblockable and evasion to keep connecting — strong for voltron",
        {"oracle": r"can't be blocked|\bunblockable\b"},
        r"can't be blocked(?! except)|\bunblockable\b"
        r"|\b(?:forest|island|mountain|plains|swamp)walk\b",
        # Keyword-only evasion (horsemanship/menace/fear/intimidate/shadow/skulk) trips
        # the "can't be blocked except" lookahead, so credit it by Scryfall keyword[].
        serve_keywords=(
            "horsemanship",
            "menace",
            "fear",
            "intimidate",
            "shadow",
            "skulk",
        ),
        extras=(_COMBAT_SUPPORT_EXTRA,),
    ),
    # Ninjutsu (CR 702.49) returns an UNBLOCKED attacker to hand and puts the ninja in,
    # so a ninjutsu commander (Satoru Umezawa, Yuriko) wants cheap unblockable/evasive
    # creatures to reliably connect (Slither Blade, Mist-Cloaked Herald, Tormented Soul,
    # Ornithopter). Reuses the evasion_self classifier — unconditional unblockable +
    # hard-evasion keywords; flying is excluded (soft/blockable).
    ("has_ninjutsu", "you"): _spec(
        "Ninjutsu",
        "ninja creatures plus the cheap unblockable/evasive creatures to carry them in",
        {"oracle": r"can't be blocked|\bunblockable\b|\bninjutsu\b"},
        r"can't be blocked(?! except)|\bunblockable\b"
        r"|\b(?:forest|island|mountain|plains|swamp)walk\b",
        # The NINJA creatures themselves are the payoff (swapped in via ninjutsu off an
        # unblocked attacker), not just the evasion carriers.
        serve_keywords=(
            "ninjutsu",
            "horsemanship",
            "menace",
            "fear",
            "intimidate",
            "shadow",
            "skulk",
        ),
    ),
    ("clone_makers", "you"): _spec(
        "Clones / copies",
        "clone effects plus strong creatures worth copying",
        {
            "oracle": r"becomes a copy|copy of (?:target|another|any|a|that)\b"
            r"|as a copy of"
        },
        r"becomes a copy|copy of (?:target|another|any|a|that)\b|as a copy of",
        # Deliver on "strong creatures worth copying": a clone/token-copy deck wants big
        # bombs to copy (Etali, power 6). power_min=6 keeps it to genuine bombs.
        serve_power_min=6,
        # The token-copy GEAR is the same archetype: Helm of the Host ("a token that's
        # a copy of equipped creature"), Blade of Selves (myriad), Rite of Replication —
        # forms the bare "copy of target/that" serve missed (equipped/it/myriad). A copy
        # also ENTERS, so ETB payoffs (Impact Tremors) and doublers (Panharmonicon) hit.
        # The dies-value extra adds the smaller high-VALUE death dragons (cmc>=5, power
        # 4-5 — Kokusho/Keiga/Junji) the power-6 body floor missed.
        extras=(
            _COPY_EXTRA,
            _ETB_PAYOFF_EXTRA,
            _ETB_DOUBLER_EXTRA,
            _CLONE_DIES_VALUE_EXTRA,
            _SELF_BOUNCE_RECAST_EXTRA,
        ),
    ),
    # _matters sweep: the benefit side of the clone split. wants_cloning fires when the
    # commander/deck is itself a worth-copying target (a repeatable engine or a big
    # ETB/dies bomb — the include_membership cross-open). The avenue it OPENS is the
    # clone ENABLERS to copy that target (Clone, Spark Double, Sakashima) plus the
    # token-copy gear (Helm of the Host, Rite of Replication). Same clone-effect search
    # as clone_makers, minus the power-6 bomb floor (here we want the copiers, not more
    # bodies to copy).
    ("wants_cloning", "you"): _spec(
        "Wants cloning",
        "clone enablers — your commander/creatures are worth copying",
        {
            "oracle": r"becomes a copy|copy of (?:target|another|any|a|that)\b"
            r"|as a copy of"
        },
        r"becomes a copy|copy of (?:target|another|any|a|that)\b|as a copy of",
        extras=(_COPY_EXTRA,),
    ),
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put big creatures onto the battlefield from hand or library",
        {"oracle": r"onto the battlefield"},
        r"onto the battlefield from your (?:hand|library)"
        r"|put .*creature card.*onto the battlefield",
        # The PAYOFF of a cheat-into-play deck is the fat creatures it cheats in
        # (Craterhoof, Worldspine Wurm, Eldrazi) — credit big bodies as on-theme.
        serve_power_min=5,
    ),
    # Greedy `return target .*owner's hand` matched "return target spell" (Reprieve →
    # counterspell space) and spanned clauses. Constrain the object + the dot.
    ("bounce_tempo", "you"): _spec(
        "Bounce / tempo",
        "bounce effects for tempo and ETB re-use",
        {"oracle": r"return target .*to (?:its|their) owner's hand"},
        r"return (?:up to \w+ )?target (?:creature|permanent|nonland permanent)"
        r"[^.\n]*to (?:its|their) owner's hand",
    ),
    ("cascade_matters", "you"): _spec(
        "Cascade",
        "high-value spells to hit off cascade plus more cascade enablers",
        {"oracle": r"\bcascade\b"},
        r"\bcascade\b",
        # Cascade cheats big nonland bombs into play for free — credit genuine fatties
        # (Ghalta, Etali) as the payoff, not just more cascade sources.
        serve_power_min=6,
    ),
    ("regenerate_makers", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        {"oracle": r"\bregenerate\b"},
        r"\bregenerate\b",
        # A regenerating/resilient beater is a voltron plan — surface the gear, buff
        # Auras (Rancor, Bear Umbra), and protection (Alpha Authority) you suit it with.
        extras=(_COMBAT_SUPPORT_EXTRA, _VOLTRON_PROTECT_EXTRA),
    ),
    # Drop the bare `opponents? cast` — only the TRIGGER/tax forms are punishers.
    ("opponent_cast_matters", "opponents"): _spec(
        "Punish opponents' spells",
        "taxes and punishers that trigger when opponents cast",
        {"oracle": r"whenever an opponent casts|spells? your opponents cast"},
        r"whenever an opponent casts|whenever a player casts"
        r"|spells? your opponents cast",
    ),
    # Drop the bare `opponents? draws?` — it matched group-hug GIFT effects (Master of
    # the Feast) that HAND opponents cards rather than punishing the draw.
    ("opponent_draw_matters", "opponents"): _spec(
        "Punish opponents' draw",
        "wheels and draw-denial punishers that trigger on opponents drawing",
        {"oracle": r"whenever an opponent draws|each opponent draws|each player draws"},
        r"whenever an opponent draws|whenever each opponent draws"
        r"|whenever a player (?:other than you )?draws"
        r"|whenever a player draws a card (?:except|other than)"
        # The ENABLERS that make opponents draw extra (so the punish fires): symmetric
        # group-draw (Temple Bell, Howling Mine, Dictate of Kruphix), forced opponent
        # draw (Forced Fruition), and wheels (Windfall). NOT "target player draws" or
        # your own cantrip — those needn't benefit opponents.
        r"|each player draws|all players draw|each opponent draws"
        r"|target (?:player|opponent) draws|that player draws"
        r"|each player's draw step"
        r"|discards? (?:their|his or her) hand[^.]*draws?",
    ),
    # Drop the bare `search their library` — your OWN tutor reads "search their
    # library" too (Path to Exile). Require an opponent/player subject.
    ("opponent_search_matters", "opponents"): _spec(
        "Punish opponents' tutors / selection",
        "stax and punishers for opponents who search, scry, or surveil",
        {"oracle": r"opponent[^.]*(?:search|scry|surveil)|search(?:es)? their library"},
        r"(?:opponent|each player|a player)[^.]*(?:scries|surveils|searches "
        r"(?:their|a) library)"
        r"|whenever (?:an opponent|each opponent|a player)[^.]*search"
        r"|if an opponent would search",
    ),
    ("damage_to_opp_matters", "opponents"): _spec(
        "Damage to opponents",
        "evasion, pingers, and extra combats to keep connecting and fire these "
        "damage-to-opponent triggers (any damage, not just combat)",
        {"oracle": r"can't be blocked|\bmenace\b|\bflying\b|additional combat"},
        r"deals (?:noncombat )?damage to (?:a player|an opponent|one of your opponents"
        r"|that player|each opponent)|can't be blocked(?! except)|\bunblockable\b",
    ),
    # `enters the battlefield` is a DEAD branch — Scryfall templated the phrase down to
    # bare "enters" years ago (CR glossary), so it matched ~1 card and the serve missed
    # every Panharmonicon/Yarok ETB-engine. Key on the ETB-trigger / flicker clauses.
    ("permanent_etb", "you"): _spec(
        "Permanents entering",
        "cheap permanents, token makers, and flicker to repeatedly trigger your "
        "permanent enters-the-battlefield value engine",
        {"oracle": r"create [^.]*token|enters the battlefield"},
        r"create [^.]*token|put [^.]*onto the battlefield"
        r"|when (?:this|[A-Z][\w']+)[^.]*enters"
        r"|(?:a|an|another|one or more)[^.]*permanents? you control enters"
        r"|(?:artifact or creature|creature or artifact)[^.]*enter",
        extras=(_FLICKER_EXTRA, _DIES_RECURSION_EXTRA, _SELF_BOUNCE_EXTRA),
    ),
    # Serve was `…|\bequipment\b|whenever[^.]*attacks`, which matched any creature
    # that merely mentions equipment or attacks (~1104). The avenue is Equipment-for-a-
    # dasher: gate on the Equipment TYPE (CR 301.5 — the persistent buff) and the dash /
    # reconfigure KEYWORD (CR 702.109/702.151), plus a small oracle branch for cards
    # that move/cheat Equipment without the subtype.
    ("has_dash", "you"): _spec(
        "Dash / hit-and-run Equipment",
        "Equipment — it stays on the battlefield when Dash returns the creature to "
        "your hand at end of turn (Auras and counters don't), so it's the resilient "
        "buff for a recurring haste attacker; plus haste enablers and cheap recursion",
        {"preset_names": ("equip",)},
        r"equip \{|attach [^.]*equipment",
        serve_types=("equipment",),
        serve_keywords=("dash", "reconfigure"),
    ),
    # ── Hand-spec overrides for mined sweep keys that need a STRUCTURED serve ────
    # (a keyword/veto dimension the auto-registered oracle-only sweep serve can't carry;
    #  the sweep regex still drives EXTRACTION, these refine the classifier).
    #
    # excess_damage: the "excess damage" phrase is the payoff; the ENABLERS are trample
    # bodies (CR 702.19) — add the keyword so the 940 trample creatures become servable.
    ("excess_damage", "you"): _spec(
        "Excess damage",
        "trample and big hits to exploit excess damage",
        {"oracle": r"\bexcess damage\b"},
        r"\bexcess damage\b",
        serve_keywords=("trample",),
    ),
    # anthem_static: a STATIC anthem, not a one-shot pump — VETO "until end of turn"
    # (those are pump_makers). Oracle-with-temporal-guard (no structured 'is-static').
    ("anthem_static", "you"): _spec(
        "Static anthem",
        "go-wide creatures to ride the anthem",
        {
            "oracle": (
                r"(?:other [a-z]+ creatures|creatures you control"
                r"|[a-z]+ creatures you control|nonblack creatures|other creatures"
                r"|(?:white|blue|black|red|green) creatures"
                r"|creatures you control of the chosen colou?r)"
                r" get \+\d/\+\d"
            )
        },
        r"(?:other [a-z]+ creatures|creatures you control"
        r"|[a-z]+ creatures you control|nonblack creatures|other creatures"
        r"|(?:white|blue|black|red|green) creatures"
        r"|creatures you control of the chosen colou?r)"
        r" get \+\d/\+\d",
        serve_not=r"get \+\d/\+\d[^.]*until end of turn",
    ),
    # ADR-0027: activated_draw had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the structural tap-cost + draw-effect IR arm). It had NO
    # hand-written serve, so the sweep auto-register loop built it; now that the row is
    # gone, hand-register the spec the loop used to build, reusing SWEEP_LABELS + the
    # deleted regex (the SERVE pool stays oracle-defined — repeatable {T}:Draw engines).
    ("activated_draw", "you"): _spec(
        *SWEEP_LABELS["activated_draw"],
        {"oracle": r"\{t\}: draw a card"},
        r"\{t\}: draw a card",
    ),
    # free_creature_payoff (Satoru): the "no mana was spent to cast" payoff wants 0-cost
    # CREATURES (Ornithopter / Memnite / Phyrexian Walker / Kobolds / Shield Sphere) —
    # not 0-cost mana rocks (Lotus Petal). AND mana_cost {0} with a creature type: each
    # alone is imprecise (mana_cost {0} alone serves Mishra's Bauble; the type alone
    # serves every creature).
    ("free_creature_payoff", "you"): SignalSpec(
        label="Free creatures",
        avenue="0-cost creatures (cast for no mana) to trigger the payoff",
        search={"card_type": "Creature", "cmc_max": 0},
        serve=Serve(
            all_of=(
                Serve(types=frozenset({"creature"})),
                Serve(mana_cost=re.compile(r"^\{0\}$")),
            )
        ),
    ),
    # Mass-death payoff (Tobias, Nevinyrral, Gadrak, Mahadi): a reward that SCALES with
    # creatures dying this turn wants board wipes (force the big turn) + mass-reanim
    # (refill after). The "for each ... died this turn" floor detector opens it; the
    # serve is wipes + whole-graveyard reanimation (single-target Reanimate excluded —
    # that's the reanimator lane, not a board refill).
    ("mass_death_payoff", "you"): _spec(
        "Mass-death payoff",
        "board wipes that force a mass-death turn, plus mass-reanimation to refill the "
        "board after",
        {"oracle": _MASS_DEATH_PAYOFF_ORACLE},
        _MASS_DEATH_PAYOFF_ORACLE,
    ),
    # Per-target payoff (Hinata): the discount scales with target count, so serve spells
    # whose target count is VARIABLE — "any number of targets" (Aurelia's Fury) and
    # "X target" spells (Distorting Wake). A single fixed-target removal (Doom Blade) is
    # only a {1} discount, not the payoff, so it isn't credited.
    ("per_target_payoff", "you"): _spec(
        "Multi-target spells",
        "variable / X-target spells whose per-target discount compounds (any number of "
        "targets, X target permanents)",
        {"oracle": _MULTI_TARGET_ORACLE},
        _MULTI_TARGET_ORACLE,
    ),
    # Ability-strip targets (Abigale): big creatures with a crippling drawback she
    # strips then buffs. ANDs the drawback clause with power >= 5 (Serve.all_of), so a
    # big vanilla beater (no drawback) and a small drawback creature are both excluded.
    ("ability_strip_payoff", "you"): SignalSpec(
        label="Ability-strip targets",
        avenue="big creatures whose crippling drawback gets stripped, then buffed into "
        "a beater",
        search={"oracle": _CRIPPLING_DRAWBACK_ORACLE},
        serve=Serve(
            all_of=(
                Serve(oracle=re.compile(_CRIPPLING_DRAWBACK_ORACLE, _IC)),
                Serve(power_min=5),
            )
        ),
    ),
    # Arcane tribal (The Unspeakable + the Kamigawa Kirins / Spiritcraft legends): the
    # Arcane-subtype instants & sorceries (CR 205.3k) the commander recurs / pays off,
    # plus the splice-onto-Arcane cards that ride them.
    ("arcane_matters", "you"): _spec(
        "Arcane spells",
        "Arcane-subtype instants and sorceries (Kamigawa) plus splice-onto-Arcane",
        {"card_type": "Arcane"},
        r"splice onto arcane",
        serve_types=("arcane",),
    ),
    # Enlist (Aradesh): other enlist creatures (the keyword bearers) plus the big
    # stay-back fodder to tap for their power.
    ("has_enlist", "you"): _spec(
        "Enlist",
        "enlist creatures plus big stay-back fodder to tap for their power",
        {"oracle": r"\benlist\b"},
        r"\benlisted? (?:a|another) creature",
        serve_keywords=("enlist",),
        extras=(_ENLIST_FODDER_EXTRA,),
    ),
    # Power-scaling tap engine (Mona Lisa, Marwyn, Selvala, Alena): UNTAP effects re-tap
    # the engine for another payoff; ranking surfaces the repeatable untappers first.
    ("power_tap_engine", "you"): _spec(
        "Untap effects",
        "untap effects that re-tap the power-scaling ability for another activation",
        {"oracle": r"untap (?:another )?target (?:creature|permanent)|\buntap it\b"},
        r"untap (?:another )?target (?:creature|permanent)|\buntap it\b"
        r"|untap all [^.]*you control",
    ),
    # Recastable ETB aggressors (Oroku Saki + the TMNT Sneak legends): cheap creatures
    # whose ENTER trigger bleeds opponents (each opponent discards / loses life), so
    # bouncing and recasting them repeats the bleed. The aggressive-ETB subset is the
    # precise recast payoff (color identity filters it per commander) — NOT every ETB
    # creature, which would be goodstuff.
    ("recast_etb", "you"): _spec(
        "Recastable ETB aggressors",
        "cheap creatures whose enter-trigger bleeds opponents, to bounce and recast",
        {"oracle": r"when[^.]*enters[^.]*each opponent (?:discards|loses|sacrifices)"},
        r"when[^.]*enters[^.]*each opponent (?:discards|loses|sacrifices)",
    ),
    # Exert (Johan, Heliod God of the Sun): when your team has vigilance / never taps to
    # attack, an exert creature's only downside (won't untap) vanishes, so serve the
    # exert creatures (the Scryfall keyword is the precise gate).
    ("exert_matters", "you"): _spec(
        "Exert",
        "exert creatures — their 'won't untap' cost is free when your team doesn't tap",
        {"oracle": r"\bexert\b"},
        r"you may exert this creature",
        serve_keywords=("exert",),
    ),
    # Target redirect (Rayne draws when an opponent targets your stuff): shunt the
    # opponent's spell onto a cheap permanent so you still draw but the real target is
    # safe (Spellskite, Misdirection, Bolt Bend).
    ("target_redirect", "you"): _spec(
        "Target redirection",
        "redirect an opponent's spell onto a cheap permanent (still triggers, stays "
        "safe)",
        {
            "oracle": r"change (?:a|the) target of target spell"
            r"|change (?:that|the) spell'?s target to"
        },
        r"change (?:a|the) target of target spell or ability"
        r"|change (?:the|a) target of target spell"
        r"|change (?:that|the) spell'?s target to"
        r"|new target.{0,30}this (?:creature|permanent)",
    ),
    # Free-spell storm (Thrasta): cost drops per spell cast this turn, so it wants FREE
    # (0-cost) NONLAND spells to chain. all_of(cmc<=0, spell-type) excludes 0-mv basics
    # (a land is not a spell cast).
    ("free_spell_storm", "you"): SignalSpec(
        label="Free spells",
        avenue="0-cost spells to chain so the commander's cost keeps dropping",
        search={"cmc_max": 0},
        serve=Serve(
            all_of=(
                Serve(cmc_max=0),
                Serve(
                    types=frozenset(
                        {
                            "instant",
                            "sorcery",
                            "artifact",
                            "creature",
                            "enchantment",
                            "planeswalker",
                        }
                    )
                ),
            )
        ),
    ),
    # Scavenge fuel (Varolz): scavenge turns a graveyard creature's POWER into +1/+1
    # counters, so it wants the highest-power creatures as the biggest payloads.
    ("scavenge_fuel", "you"): _spec(
        "High-power scavenge fuel",
        "high-power creatures to scavenge for big +1/+1-counter payloads",
        {"card_type": "Creature"},
        None,
        serve_power_min=7,
    ),
    # Land control / exchange (Sharkey): a land-control commander wants land-EXCHANGE
    # effects to swap a weak land for an opponent's best while it taxes the rest.
    ("land_exchange", "you"): _spec(
        "Land exchange",
        "swap control of lands to steal opponents' best while you tax the rest",
        {"oracle": r"exchange control of[^.]*\bland\b"},
        r"exchange control of[^.]*\bland\b",
    ),
    # Self-life-payment insurance (Selenia, Beledros, Vilis): a commander that pays its
    # own life repeatedly wants life-loss insurance so the payments don't kill it
    # (Phyrexian Unlife, Angel's Grace, Platinum Angel).
    ("life_payment_insurance", "you"): _spec(
        "Life-loss insurance",
        "cards that stop you losing the game from heavy self-life-payment",
        {
            "oracle": r"don'?t lose the game for having|can'?t lose the game"
            r"|your life total can'?t change"
        },
        r"don'?t lose the game for having|can'?t lose the game"
        r"|your life total can'?t change|you don'?t lose the game",
    ),
    # Target-your-own payoff (Monk Gyatso): free ways to target your own creatures so a
    # "when targeted" payoff fires on demand (en-Kor cycle, {0}-equip like Shuko).
    ("target_own_payoff", "you"): _spec(
        "Target-your-own enablers",
        "free/cheap ways to target your own creatures (en-Kor, {0}-equip)",
        {
            "oracle": r"\{0\}:[^.]*target (?:a |another )?creature you control"
            r"|equip \{0\}"
        },
        r"\{0\}:[^.]*target (?:a |another )?(?:creature|permanent) you control"
        r"|equip \{0\}",
    ),
    # Multicolor matters (Niv-Mizzet Reborn + the gold-cards commanders): the multicolor
    # PAYOFFS — "whenever you cast a multicolored spell", converge, "multicolored
    # creatures you control" — not every gold card (which would be the whole deck).
    ("multicolor_matters", "you"): _spec(
        "Multicolor payoffs",
        "cards that reward casting multicolored spells, plus converge",
        {
            "oracle": r"whenever you cast a multicolored|\bconverge\b"
            r"|multicolored (?:creature|permanent|spell)s? you"
        },
        r"whenever you cast a multicolored"
        r"|multicolored (?:creature|permanent|spell)s? you (?:control|cast)"
        r"|\bconverge\b|cast (?:a|your) multicolored",
    ),
    # A repeatable land-destruction commander (Numot) wants the LD support package:
    # more land destruction (main), own-land recursion to survive symmetric LD (reuse
    # the lands-from-graveyard extra), and land-loss PUNISHERS that turn each destroyed
    # land into damage/value (Dingus Egg, Price of Glory).
    ("land_destruction", "you"): _spec(
        "Land destruction",
        "blow up lands repeatedly — the Armageddon/Numot stax-LD plan",
        {"oracle": r"destroy (?:up to (?:one|two|three) )?target lands?"},
        r"destroy (?:up to (?:one|two|three) )?target lands?"
        r"|destroy all lands|destroy target nonbasic land"
        r"|each (?:player|opponent)[^.]*sacrifices? a land",
        extras=(
            SubAvenue(
                "Punish land loss",
                "turn every destroyed land into damage or value (Dingus Egg, "
                "Price of Glory)",
                {
                    "oracle": r"whenever a land(?: card)? is put into a graveyard"
                    r"|whenever a player taps a land[^.]*destroy"
                },
            ),
            _LANDS_FROM_GRAVE_EXTRA,
        ),
    ),
    # A cheat-from-top commander (Vaevictis, Hans Eriksson) reveals its top card and
    # puts a permanent into play, so it wants to STACK its top with a bomb: graveyard-
    # to-top recursion and deliberate put-on-top effects choose what gets cheated in.
    ("cheat_from_top", "you"): _spec(
        "Stack your top",
        "put a bomb on top of your library to be cheated in — graveyard-to-top "
        "recursion and put-on-top effects",
        {"oracle": _GY_TO_TOP_ORACLE},
        _GY_TO_TOP_ORACLE
        + r"|put (?:a|two|three|\w+) cards? from your hand on top of your library"
        + r"|on top of your library in any order",
    ),
    # A repeatable creature-KILLER (Diaochan {T}-destroy, Visara, Kalitas) is an
    # aristocrats-style death engine with no sac outlet of its own: every kill it makes
    # fires on-death payoffs. Serve the drain/damage payoffs (Blood Artist, Zulaport,
    # Vicious Shadows) only — NOT the full aristocrats kit (fodder/sac outlets), which a
    # control-removal commander doesn't want.
    ("kill_engine", "you"): _spec(
        "Death payoffs",
        "your repeatable creature kills fire on-death drain/damage every turn — "
        "Blood Artist, Zulaport Cutthroat, Vicious Shadows",
        {"oracle": _KILL_DRAIN_ORACLE},
        _KILL_DRAIN_ORACLE,
    ),
    # Phasing-lands (Taniwha): your lands phase back each turn, so symmetric land-denial
    # stax (Mana Breach / Overburden — every player bounces/sacs a land) hits opponents
    # permanently while you recover. Asymmetric land denial.
    ("land_denial", "you"): _spec(
        "Land denial",
        "symmetric land-bounce/sac stax that hits opponents while your lands phase",
        {
            "oracle": r"whenever a player[^.]*(?:returns? a land|sacrifices? a land)"
            r"|that player (?:returns?|sacrifices?) a land"
        },
        r"whenever a player[^.]*(?:returns? a land|sacrifices? a land)"
        r"|that player (?:returns?|sacrifices?) a land"
        r"|each player sacrifices a land",
    ),
    # Cast-from-hand-or-lose (Phage): negate the drawback — command-zone-to-hand so it's
    # cast normally, "can't lose the game" backstops, and "ETBs don't trigger" silences
    # the lose-trigger when the commander is cheated into play.
    ("lose_unless_hand", "you"): _spec(
        "Drawback negation",
        "command-zone-to-hand, can't-lose, and ETB-silencers for a cast-from-hand-or-"
        "lose commander",
        {
            "oracle": r"can'?t lose the game|into your hand from the command zone"
            r"|creatures entering[^.]*don'?t (?:cause|trigger)"
        },
        r"can'?t lose the game|into your hand from the command zone"
        r"|from the command zone[^.]*your hand"
        r"|creatures entering[^.]*don'?t (?:cause|trigger)"
        r"|abilities (?:don'?t|do not) trigger",
    ),
    # Land protection (Noyan Dar, Kamahl, the Tophs): a land-animation commander's
    # creature-lands die to creature removal / wraths / land destruction, so it wants
    # indestructible-lands, untargetable-lands, and land recursion to keep them.
    ("land_protection", "you"): _spec(
        "Land protection",
        "keep your animated lands alive: indestructible, untargetable, land recursion",
        {
            "oracle": r"all lands[^.]*indestructible|lands?[^.]*can'?t be[^.]*target"
            r"|lands?[^.]*hexproof"
        },
        r"lands?[^.]*(?:have|gain|with)[^.]*indestructible|all lands[^.]*indestructible"
        r"|lands?[^.]*can'?t be[^.]*target|lands?[^.]*hexproof"
        r"|whenever[^.]*causes? a land[^.]*graveyard",
    ),
    # Newly-entered attacker payoff (Samut): wants HASTE + ETB-pump anthems so a
    # creature that entered this turn can attack at once for value. Ogre Battledriver /
    # Primal Forcemage pump entering creatures; mass-haste lets them swing.
    ("entered_attacker", "you"): _spec(
        "Haste + ETB pump",
        "haste and enter-trigger pump so freshly-entered creatures attack at once",
        {
            "oracle": r"creature you control enters[^.]*(?:gets? \+|gains? haste|and "
            r"haste)|creatures you control (?:get|have|gain)[^.]*haste"
        },
        r"(?:another |a )?creature you control enters[^.]*(?:gets? \+|gains? haste|and "
        r"haste)|creatures you control (?:get|have|gain)[^.]*haste",
    ),
    # Island matters (Zhou Yu, islandwalk commanders): effects that turn opponents'
    # lands into Islands (so the attack restriction is met / islandwalk connects), plus
    # more islandwalk and island-count payoffs.
    ("island_matters", "you"): _spec(
        "Island matters",
        "make opponents' lands Islands, plus islandwalk and island-count payoffs",
        {
            "oracle": r"lands?[^.]*are islands|becomes? an island|flood counter"
            r"|\bislandwalk\b"
        },
        r"(?:nonbasic |all )?lands?[^.]*are islands|becomes? an island|flood counter"
        r"|\bislandwalk\b|number of islands",
    ),
    # Tap down blockers (Tromokratis): effects that tap OPPONENTS' creatures (Sleep,
    # Blustersquall) so the defender can't field enough blockers, letting the
    # "unblockable unless all block" commander through.
    ("tap_down_blockers", "you"): _spec(
        "Tap down blockers",
        "effects that tap opponents' creatures so they can't all block",
        {
            "oracle": r"tap all creatures (?:target|that|defending) player"
            r"[^.]*control|tap target creature you don'?t control"
        },
        r"tap all creatures (?:target|that|defending) player[^.]*control"
        r"|tap all creatures target opponent[^.]*control"
        r"|tap target creature you don'?t control"
        r"|tap all creatures you don'?t control",
    ),
    # ltb_matters: VETO the O-Ring exile-until-leaves removal (Banishing Light) — that
    # already routes to exile_until_leaves, so excluding it here is lossless.
    # ADR-0027 β: ltb_matters migrated to the Card IR (a structural `leaves`-trigger arm
    # + a narrowed _LTB_MATTERS_MIRROR, SIDECAR v11). This serve spec was always hand-
    # registered with its own curated SEARCH regex + serve_not O-Ring veto, independent
    # of the deleted SWEEP detector, so it survives unchanged. CR 603.6e.
    ("ltb_matters", "you"): _spec(
        "Leaves-the-battlefield",
        "sacrifice and blink fodder to trigger LTB",
        {
            "oracle": (
                r"left the battlefield[^.]*this turn"
                r"|whenever [^.]*(?:leaves|leave) the battlefield"
                r"|when [^.]* leaves the battlefield"
            )
        },
        r"a permanent (?:you controlled )?left the battlefield"
        r"|whenever [^.]*(?:leaves the battlefield|leave the battlefield)"
        r"|when [^.]* leaves the battlefield",
        serve_not=r"exile [^.]*until [^.]*leaves the battlefield",
        # Flicker your own permanents to FIRE the LTB trigger (and a fresh ETB) on
        # demand — the "blink fodder" the blurb promises (Ghostly Flicker / Eerie
        # Interlude). Reuses the precise flicker classifier. Death (dies) is also an LTB
        # event (CR 603.6c), so dies-recursion is offered as its own avenue too.
        extras=(_FLICKER_EXTRA, _DIES_RECURSION_EXTRA),
    ),
    # ── Keyword-coverage audit (CR 702/701) keyword[]-anchored avenues ──────────
    # Serve the keyword[] bearers via serve_keywords (Scryfall's authoritative field —
    # maximally precise, never matches reminder text) plus the payoff/grant phrasing.
    ("madness_matters", "you"): _spec(
        "Madness",
        "madness cards (discard them to cast for their madness cost) plus the discard "
        "outlets and madness-granters that enable the loop",
        {"oracle": r"\bmadness\b"},
        r"\bmadness\b|if it has madness",
        serve_keywords=("madness",),
    ),
    ("speed_matters", "you"): _spec(
        "Speed / Max speed",
        "Start-your-engines and Max-speed payoffs, plus the your-turn life-loss "
        "sources that advance your speed",
        {"oracle": r"max speed|start your engines"},
        r"max speed|start your engines|your speed",
        serve_keywords=("start your engines!", "max speed"),
        extras=(_CHEAP_EVASION_EXTRA,),
    ),
    ("discover_makers", "you"): _spec(
        "Discover",
        "discover sources to dig for free, plus low-mana-value nonland spells worth "
        "flipping into",
        {"oracle": r"\bdiscover \d|\bdiscover x\b"},
        r"\bdiscover \d|\bdiscover x\b|whenever you discover",
        serve_keywords=("discover",),
    ),
    ("foretell_matters", "you"): _spec(
        "Foretell",
        "foretell cards to bank in exile plus the payoffs that reward foretold cards",
        {"oracle": r"\bforetell\b|foretold"},
        r"\bforetell\b|foretold",
        serve_keywords=("foretell",),
    ),
    ("has_undying_persist", "you"): _spec(
        "Undying / Persist",
        "Undying and Persist bodies (free, repeatable death-return fodder) plus the "
        "anthems and grants that hand out the keyword",
        {"oracle": r"\b(?:undying|persist)\b"},
        r"\b(?:undying|persist)\b|(?:have|gain|gains|with) (?:undying|persist)",
        serve_keywords=("undying", "persist"),
    ),
    # ── Two-regex payoff avenues (serve = the broad axis, search = enabler pool) ──
    ("minus_counters_matter", "you"): _spec(
        "-1/-1 counters",
        "Wither/Infect bearers and -1/-1 placers plus the payoffs that reward a board "
        "shrinking under -1/-1 counters (Hapatra, Necroskitter, Nest of Scarabs)",
        {"oracle": r"-1/-1 counter"},
        r"-1/-1 counter",
        serve_keywords=("wither", "infect"),
    ),
    ("cycling_matters", "you"): _spec(
        "Cycling",
        "cycling cards to churn through your deck plus the payoffs that reward each "
        "cycle (Astral Slide, Drake Haven, Faith of the Devoted)",
        {"preset_names": ("cycling",)},
        r"whenever you cycle|cycles? or discard"
        r"|whenever (?:a player|another player) cycles",
        serve_keywords=("cycling",),
    ),
    ("kicked_spell_matters", "you"): _spec(
        "Kicked spells",
        "kicker/multikicker spells plus the payoffs that trigger on casting a kicked "
        "spell (Verazol, Hallar, Rumbling Aftershocks)",
        {"oracle": r"\bkicker\b|\bkicked\b"},
        r"whenever you cast a kicked spell|if (?:that|it) (?:spell )?was kicked",
        serve_keywords=("kicker", "multikicker"),
    ),
    # colorless-hate counterspells ("Counter target colorless spell" — Ceremonious
    # Rejection, Consign to Memory) match the oracle arm but are NOT payoffs: veto them.
    ("colorless_matters", "you"): _spec(
        "Colorless / Eldrazi",
        "Devoid and Eldrazi colorless bodies plus the anthems, cost reducers, and "
        "cast-triggers that reward casting colorless creatures and spells",
        {"oracle": r"colorless (?:creature|spell|permanent)"},
        r"colorless (?:creature|spell|permanent)s?",
        serve_keywords=("devoid",),
        serve_types=("eldrazi",),
        serve_not=r"counter target colorless",
    ),
    # ADR-0027 #24n G1 — base_power_matters (NEW niche lane). The payoffs that REWARD /
    # SCALE WITH / SELECT creatures by their BASE power or toughness (CR 613.4b refer,
    # not set): Bess Soul Nourisher's 1/1 ETB count, Zinnia's base-power-1 go-wide
    # scale, Duskana's draw-per base-2/2, Primo's base-0 combat trigger, Rapid
    # Augmenter's base-1 haste grant, Sword of the Squeak's equip scale. SERVE/SEARCH on
    # the base-reference grammar (a base-power/toughness count/condition); the kept
    # word mirror retired in favor of the structural `BasePtRef` read.
    ("base_power_matters", "you"): _spec(
        "Base power/toughness",
        "the small base-P/T tribe — anthems and triggers that reward creatures by "
        "their base power or toughness (Bess, Zinnia, Duskana, Primo, Rapid Augmenter, "
        "Sword of the Squeak)",
        {"oracle": r"with base (?:power|toughness)"},
        r"with base (?:power|toughness)",
    ),
    ("exalted_lone_attacker", "you"): _spec(
        "Exalted / lone attacker",
        "Exalted enablers plus the payoffs that reward a single attacker connecting "
        "(Rafiq, Sublime Archangel, Angelic Exaltation)",
        {"oracle": r"attacks alone|\bexalted\b"},
        r"attacks alone",
        serve_keywords=("exalted",),
    ),
    ("flash_matters", "you"): _spec(
        "Flash",
        "flash creatures to ambush-cast plus the flash-granters and opponent-turn "
        "payoffs that build the deck around instant-speed play",
        {"preset_names": ("flash",)},
        r"cast[^.]{0,60}spells?[^.]{0,30}as though they had flash"
        r"|whenever you cast (?:a |your first )?spells? "
        r"during (?:an|each|any) opponent",
        serve_keywords=("flash",),
    ),
    ("team_evasion_grant", "you"): _spec(
        "Team evasion grant",
        "effects that hand an evasion keyword (menace / fear / flying / can't be "
        "blocked) to your whole board for a go-wide alpha strike",
        {
            "oracle": r"creatures you control (?:gain|have)[^.]{0,40}?"
            r"(?:menace|fear|intimidate|horsemanship|flying|can't be blocked)"
        },
        r"(?:other |attacking )?creatures you control (?:gain|have)\b"
        r"[^.]{0,40}?\b(?:menace|fear|intimidate|shadow|horsemanship|skulk"
        r"|flying|can't be blocked)\b"
        r"|(?:other |attacking )?creatures you control[^.]*can't be blocked",
    ),
    # Override the auto-registered saga_matters sweep spec: surface the FULL Saga pool
    # via a subtype search (the sweep spec only found lore-counter cards), and serve the
    # Sagas (serve_types) plus the lore-counter/chapter payoffs (Tom Bombadil, Narci).
    ("saga_matters", "you"): _spec(
        "Sagas",
        "Sagas to chain chapter abilities, plus the lore-counter and chapter-retrigger "
        "payoffs that reward them",
        {"card_type": "Saga"},
        r"lore counter|sagas? you control|chapter abilit|read ahead",
        serve_types=("saga",),
    ),
    ("lessons_matter", "you"): _spec(
        "Lessons",
        "Lesson spells (your wishboard payload) plus the Learn enablers and Lesson "
        "payoffs that reward casting them",
        {"card_type": "Lesson"},
        r"lesson spells?|cast (?:an? )?(?:artifact or )?lesson|lesson card",
        serve_types=("lesson",),
    ),
    # Override the auto-registered suspend_matters sweep spec (serve was `\bsuspend\b`
    # only): widen to the whole time-counter superstructure — Suspend (702.62),
    # Vanishing (702.63), Impending, and time-counter/time-travel manipulation (701.56).
    ("suspend_matters", "you"): _spec(
        "Suspend / time counters",
        "suspend, vanishing, and impending cards plus the time-counter manipulators "
        "and payoffs (As Foretold, Jhoira, Dust of Moments) that exploit them",
        {"oracle": r"\bsuspend\b|time counter"},
        r"\bsuspend\b|\bvanishing\b|\bimpending\b|time counter|time travel"
        # Suspend removes a TIME counter each upkeep (CR 702.62), so extra upkeeps /
        # beginning phases (Paradox Haze, Sphinx of the Second Sun) accelerate it.
        r"|additional upkeep step|additional beginning phase"
        # Counter-manipulation that references suspended cards (Clockspinning, Dust of
        # Moments, Timebender) — direct suspend support, generic "counter" not "time".
        r"|suspended cards?",
        serve_keywords=("suspend", "vanishing", "impending"),
    ),
    ("saddle_matters", "you"): _spec(
        "Saddle / Mounts",
        "Mounts to ride plus the cheap wide creatures that pay the Saddle cost and the "
        "attacks-while-saddled payoffs (Calamity, Gitrog Ravenous Ride)",
        {"oracle": r"\bsaddle\b|\bsaddled\b|\bmount\b"},
        r"\bsaddled\b|whenever you saddle|while saddled",
        serve_keywords=("saddle",),
    ),
    ("suspect_makers", "you"): _spec(
        "Suspect makers",
        "cards that suspect creatures (menace + can't block) to fuel your "
        "suspected-creature payoffs",
        {"oracle": r"\bsuspect\b"},
        r"\bsuspects?\b",
    ),
    ("suspect_matters", "you"): _spec(
        "Suspect payoffs",
        "payoffs that reward having suspected creatures",
        {"oracle": r"\bsuspected\b"},
        r"\bsuspected\b",
    ),
    # ADR-0027: cmdzone_ability had its oracle-regex SWEEP_DETECTORS row deleted
    # (detection moved to the Card IR — a 'command' ability-zone / condition-zone
    # structural arm + a kept word mirror for the static-Eminence cost-reducer). The
    # SERVE pool stays oracle-defined, so hand-register the spec the sweep auto-
    # register loop used to build, reusing the deleted regex.
    ("cmdzone_ability", "you"): _spec(
        *SWEEP_LABELS["cmdzone_ability"],
        {
            "oracle": (
                r"is (?:on the battlefield or )?in the command zone"
                r"|activate this ability only if[^.]*command zone"
            )
        },
        (
            r"is (?:on the battlefield or )?in the command zone"
            r"|activate this ability only if[^.]*command zone"
        ),
    ),
}

# Subject-bearing signal keys: their spec is built dynamically from the captured
# subject (a Goblin lord and a Sliver lord must not share one static spec).
_SUBJECT_KEYS = signal_keys.SUBJECT_KEYS
# Two distinct sub-avenues are always offered for a subject: the *cards* (the tribe
# members, or the token-makers) and the *payoffs* (lords/anthems that reward a board of
# them). Keeping them clearly separate — and never folding "payoffs" into the cards
# avenue's blurb — is what stops "X tribal" / "X payoffs" reading as the same thing.
_SUBJECT_TEMPLATES = {
    signal_keys.TYPE_MATTERS: (
        "{s} tribal",
        "{s} creatures (and changelings) — the bodies that make up the tribe",
    ),
    signal_keys.TYPED_SPELLCAST: (
        "{s} spells",
        "{s} spells to cast and chain",
    ),
}


# Type-GRANT phrasing (B1). _GRANT_VETO (broad) drops any type-grant from the payoff
# lane. _ENABLER_GRANT (tight) requires a GROUP subject ("creatures you control ... are
# the chosen type"), so board-wide granters (Xenograft, Arcane Adaptation, Maskwood
# Nexus, Leyline of Transformation) count as enablers, but a lone CHANGELING ("this card
# is every creature type") does not — it's a tribe member, surfaced by the bodies lane.
_GRANT_VETO = r"(?:is|are) (?:the chosen type|every creature type)"
_ENABLER_GRANT = (
    r"(?:creature|permanent)s? you control[^.]*?"
    r"(?:is|are) (?:the chosen type|every creature type)"
)


def _payoff_extra(subj: str, esc: str) -> SubAvenue:
    # Lords/anthems that REWARD a board of {subj}s. Positive shapes:
    #   - the tribe's own lords ("{subj}s you control"),
    #   - "shares a creature type" pumps (Shared Animosity, Coat of Arms) — any tribe,
    #   - OPEN type-of-choice payoffs ("choose a creature type" then reward it:
    #     Vanquisher's Banner, Door of Destinies) — work for ANY tribe,
    #   - RESTRICTED type-of-choice payoffs that name an explicit list ("choose Elf,
    #     Goblin, …") — credited ONLY when THIS subject is named (so Dawn-Blessed
    #     Pennant counts for Goblin/Elf, never an unlisted tribe like Scarecrow).
    # not_oracle drops type-GRANTERS ("are the chosen type") — enablers, not payoffs.
    positive = (
        rf"{esc}s? you control"
        r"|shares (?:a|at least one) creature type"
        r"|choose a (?:creature|kindred) type"
        rf"|choose\b[^.]*\b{esc}s?\b"
    )
    return SubAvenue(
        f"{subj} payoffs",
        f"lords and anthems that reward a board of {subj}s, plus type-agnostic tribal "
        "payoffs (Coat of Arms, Door of Destinies) that work for any chosen tribe",
        {"oracle": positive},
        serve=Serve(
            oracle=re.compile(positive, _IC),
            not_oracle=re.compile(_GRANT_VETO, _IC),
        ),
    )


def _enabler_extra(subj: str) -> SubAvenue:
    # Type-changers (Xenograft, Arcane Adaptation) turn OTHER creatures into {subj}s, so
    # the tribe grows and your {subj} payoffs hit more bodies. A distinct lane: an
    # enabler is NOT a payoff or a tribe member (B1). The open grant ("the chosen
    # type") is subject-agnostic, so it credits every {subj} lane.
    return SubAvenue(
        f"{subj} enablers",
        f"cards that make your other creatures {subj}s (type-changers like Xenograft), "
        f"growing the tribe so your {subj} lords and payoffs reach more of the board",
        {"oracle": _ENABLER_GRANT},
        serve=Serve(oracle=re.compile(_ENABLER_GRANT, _IC)),
    )


# Tribal SYNONYM-GROUPS: creature types that share one tribal identity because no card
# rewards any member ALONE — they are always named together. The "sea monster" group is
# the canonical case (Quest for Ula's Temple, Slinn Voda, Whelming Wave, Kenessos all
# enumerate "Kraken, Leviathan, Octopus, and Serpent"), so a commander of any one type
# (Lorthos = Octopus, Tromokratis = Kraken, Koma = Serpent) wants the whole group. ONLY
# groups whose members have NO standalone tribe belong here: Angel/Demon/Dragon and
# Vampire/Werewolf/Zombie are deliberately EXCLUDED — each is a real solo tribe (Lyra
# Angels, Edgar vampires), so grouping them would over-fire a mono-tribe commander.
_TRIBAL_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"kraken", "leviathan", "octopus", "serpent"}),
)


def _tribal_group(subj: str) -> frozenset[str] | None:
    sl = subj.lower()
    for grp in _TRIBAL_GROUPS:
        if sl in grp:
            return grp
    return None


def _subject_spec(signal: Signal) -> SignalSpec:
    """Build a spec for a subject-bearing signal by interpolating the subject."""
    subj = signal.subject
    esc = re.escape(subj)
    # keyword-tribe: the subject is an ability keyword (Flying), not a creature type —
    # find creatures that HAVE the keyword (oracle), not a type-line match.
    if signal.key == signal_keys.KEYWORD_TRIBE:
        return SignalSpec(
            label=f"{subj} matters",
            avenue=f"creatures with {subj} plus anthems and payoffs that reward them",
            search={"oracle": rf"\b{esc.lower()}\b"},
            serve=Serve(oracle=re.compile(rf"\b{esc}\b", _IC)),
        )
    # meld: the subject is THIS commander's own name. Its single meld partner names it
    # ("(Melds with <name>.)" on the back piece, "a creature named <name>" on the front
    # piece, CR 701.42), so serve exactly that one partner — not every meld half.
    if signal.key == signal_keys.MELD_PAIR:
        partner_re = rf"(?:melds with|creature named) {esc}"
        return SignalSpec(
            label=f"Meld partner of {subj}",
            avenue=(
                f"the specific card that melds with {subj} (plus tutors/recursion to "
                "assemble the pair)"
            ),
            search={"oracle": partner_re},
            serve=Serve(oracle=re.compile(partner_re, _IC)),
        )
    # token-maker: the deck CREATES {s} tokens, so find cards that *make* them (not the
    # tribe — searching the type line surfaced {s} creatures that don't make tokens).
    if signal.key == signal_keys.TOKEN_MAKER:
        token_re = rf"create\b[^.]*\b{esc}\b[^.]*token"
        # A token-maker commander (Krenko → token_maker:Goblin) is a flood deck: offer
        # the creature-ETB payoffs and token doublers alongside the tribe-token payoffs.
        return SignalSpec(
            label=f"{subj} tokens",
            avenue=f"cards that create {subj} tokens to go wide",
            search={"oracle": token_re},
            serve=Serve(oracle=re.compile(token_re, _IC)),
            extras=(
                _payoff_extra(subj, esc),
                _TOKEN_DOUBLER_EXTRA,
                _ETB_PAYOFF_EXTRA,
                _GOWIDE_ANTHEM_EXTRA,
                _TOKEN_ARISTOCRAT_EXTRA,
            ),
        )
    # tribal (type_matters) / typed spellcast: the cards themselves (type-line match),
    # plus a distinct "{s} payoffs" sub-avenue for the lords/anthems that reward them.
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    # Changelings (CR 702.73a) are every creature type, so they count for EVERY tribe —
    # but they type-line as "Shapeshifter", so the {card_type: subj} search misses every
    # one. Fold them (the keyword bearers + the "is/are every creature type" granters)
    # into the type-tribal serve so a Goblin/Elf/Zombie deck credits its changelings.
    is_type_tribal = signal.key == signal_keys.TYPE_MATTERS
    # Synonym-GROUP tribes (sea monsters): a member type's serve covers the WHOLE group,
    # by type-line AND by the group-naming payoff oracle (Whelming Wave). card_search's
    # card_type is substring-only (no OR), so each OTHER member gets its own search
    # sub-avenue to pull its bodies; the widened serve credits them all.
    group = _tribal_group(subj) if is_type_tribal else None
    members = sorted(group) if group else [subj.lower()]
    type_alt = "|".join(re.escape(m) for m in members)
    # Bodies serve: the tribe's own members (type-line) PLUS changelings ("is/are every
    # creature type", CR 702.73a — a changeling IS a member of every tribe). NOT the
    # type-GRANTERS ("is/are the chosen type"): Xenograft & co. don't BECOME a member,
    # they turn your OTHER creatures into the tribe — surfaced by the separate enabler
    # sub-avenue (_enabler_extra), never counted as a body or payoff (B1).
    serve_oracle = rf"\b(?:{type_alt})s?\b" + (
        r"|(?:is|are) every creature type" if is_type_tribal else ""
    )
    group_extras: tuple[SubAvenue, ...] = ()
    if group:
        group_extras = tuple(
            SubAvenue(
                f"{m.capitalize()}s",
                f"{m.capitalize()} bodies in the {subj} group",
                {"card_type": m},
                serve=Serve(types=frozenset({m})),
            )
            for m in members
            if m != subj.lower()
        )
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        search={"card_type": subj},
        serve=Serve(
            oracle=re.compile(serve_oracle, _IC),
            # A creature IS a member of its own tribe (CR 205.3) — match by TYPE-LINE,
            # not only the oracle "Xs you control" payoff phrasing. Without this,
            # vanilla / oracle-silent members (Dread Shade, Llanowar Elves) were
            # dropped — fatal for lord-less tribes (Shade/Kraken/Yeti read 0/10).
            types=frozenset(members) if is_type_tribal else frozenset(),
            keywords=frozenset({"changeling"}) if is_type_tribal else frozenset(),
        ),
        extras=(
            _payoff_extra(subj, esc),
            # Type-changers (Xenograft) are enablers, not payoffs/members — a distinct
            # lane, only for true tribes (type_matters), not typed-spellcast (B1).
            *((_enabler_extra(subj),) if is_type_tribal else ()),
            *group_extras,
        ),
    )


# Auto-register an avenue for every exhaustively-mined sweep key that doesn't
# already have a hand-written spec (the same-key widens reuse their existing spec).
def _humanize(key: str) -> str:
    base = key.replace("_matters", "").replace("_", " ").strip()
    return (base[:1].upper() + base[1:]) if base else key


_SPECCED_KEYS = {k for (k, _scope) in SPECS}
for _d in SWEEP_DETECTORS:
    if _d["key"] in _SPECCED_KEYS:
        continue  # hand-written spec already covers this axis
    _ident = (_d["key"], _d["scope"])
    if _ident in SPECS:
        continue
    _polished = SWEEP_LABELS.get(_d["key"])
    if _polished:
        _label, _avenue = _polished
    else:
        _label = _humanize(_d["key"])
        _avenue = f"support and payoffs for the {_label.lower()} axis"
    SPECS[_ident] = _spec(_label, _avenue, {"oracle": _d["regex"]}, _d["regex"])


# ── ADR-0026: payoff/source avenue split ──────────────────────────────────────
# A `<mechanic>_matters` serve fuses an oracle PAYOFF pattern with a type/keyword
# SOURCE (the cards that ARE the thing). These are the source-role dimensions whose
# cards form a browsable pool — CR-verified gear/membership, NOT property/payoff
# keywords. Excluded by design: prowess (CR 702.108, a payoff), exalted (702.83,
# payoff), proliferate (701.34, an enabler), and modifier keywords
# (haste/indestructible/trample/the evasion set) that describe a property, not a pool.
SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "equipment",
        "aura",  # voltron — CR 702.6 (equip) / 702.5 (enchant)
        "artifact",
        "enchantment",  # artifacts / enchantments matter
        "planeswalker",  # superfriends
        "legendary",
        "snow",
        "saga",
        "arcane",
        "lesson",
        "eldrazi",
        "instant",
        "sorcery",  # spellslinger fuel (prowess stays on the payoff side)
        "rogue",
        "wizard",
        "warrior",
        "cleric",  # party members
        "assassin",
        "pirate",
        "warlock",
        "mercenary",  # outlaws
    }
)
SOURCE_KEYWORDS: frozenset[str] = frozenset({"reconfigure"})  # CR 702.151 — it is gear

_SOURCE_TYPE_LABELS = {
    "aura": "Auras",
    "equipment": "Equipment",
    "artifact": "Artifacts",
    "enchantment": "Enchantments",
    "planeswalker": "Planeswalkers",
    "saga": "Sagas",
    "instant": "Instants",
    "sorcery": "Sorceries",
    "legendary": "Legendaries",
    "snow": "Snow permanents",
    "arcane": "Arcane spells",
    "lesson": "Lessons",
    "eldrazi": "Eldrazi",
}


def source_split(spec: SignalSpec) -> tuple[Serve, dict] | None:
    """ADR-0026: if a payoff spec's serve carries a membership-source TYPE, return the
    (source_serve, source_search) for a derived Source avenue — the cards that ARE the
    thing the payoff wants. None when there's no source type or no payoff oracle (a
    pure-membership spec is already a single source-ish lane; don't split it). The
    caller strips the same dims from the payoff avenue (see ``payoff_serve``)."""
    srv = spec.serve
    if srv.oracle is None:
        return None
    st = srv.types & SOURCE_TYPES
    if not st:
        return None
    sk = srv.keywords & SOURCE_KEYWORDS  # rides along (reconfigure cards are Equipment)
    source_serve = Serve(types=st, keywords=sk, not_oracle=srv.not_oracle)
    return source_serve, {"card_type": tuple(sorted(st))}


def payoff_serve(spec: SignalSpec) -> Serve:
    """The payoff avenue's serve once source dims are split out (ADR-0026): the oracle
    payoff + any non-source types/keywords (e.g. prowess stays), minus the source
    type/keyword the Source avenue now owns."""
    srv = spec.serve
    return replace(
        srv,
        types=srv.types - SOURCE_TYPES,
        keywords=srv.keywords - SOURCE_KEYWORDS,
    )


def _pluralize(t: str) -> str:
    # -y → -ies (mercenary → mercenaries), else +s; explicit labels win first.
    if t in _SOURCE_TYPE_LABELS:
        return _SOURCE_TYPE_LABELS[t]
    base = t.title()
    return base[:-1] + "ies" if base.endswith("y") else base + "s"


def source_label(source_types: frozenset[str]) -> str:
    """A human label for a Source avenue from its types ("Auras & Equipment")."""
    return " & ".join(_pluralize(t) for t in sorted(source_types))


def payoff_search(search: dict, serve: Serve) -> dict:
    """The payoff avenue's pool fetch (ADR-0026): drop the type/preset fetch (that
    pulled the source pool) and fall back to the serve's oracle payoff pattern, so the
    payoff lane surfaces payoffs (Sram, equip-cost reducers) not vanilla gear."""
    drop = ("card_type", "preset_names", "presets")
    out = {k: v for k, v in search.items() if k not in drop}
    if "oracle" not in out and serve.oracle is not None:
        out["oracle"] = serve.oracle.pattern
    return out


def spec_for(signal: Signal) -> SignalSpec | None:
    """Resolve a spec. Subject-bearing signals build a per-subject spec; otherwise
    exact (key, scope) → (key, any) → first entry by key."""
    if signal.key in _SUBJECT_KEYS and signal.subject:
        return _subject_spec(signal)
    exact = SPECS.get((signal.key, signal.scope))
    if exact is not None:
        return exact
    any_scope = SPECS.get((signal.key, "any"))
    if any_scope is not None:
        return any_scope
    return next((spec for (key, _), spec in SPECS.items() if key == signal.key), None)


def serves(card: dict, signal: Signal) -> bool:
    """True if ``card`` feeds ``signal`` (scope-aware), on any structured/oracle
    dimension of the spec's precise ``Serve`` predicate — no longer oracle-only."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.matches(card)


def search_filters(signal: Signal, *, color_identity: str, fmt: str) -> dict:
    """Build ``card_search`` kwargs to find cards that feed ``signal`` in-identity."""
    spec = spec_for(signal)
    base = dict(spec.search) if spec else {}
    base["color_identity"] = color_identity
    base["format"] = fmt
    return base


def _assert_every_producible_key_resolves() -> None:
    """Key-agreement gate (ADR-0014). Every subject-less key a detector can produce
    must resolve to a spec. A detector key with no spec used to be a silent no-avenue
    (extraction worked, ``spec_for`` returned None, the avenue was dropped); now it
    fails loudly at import — which ``app.py`` / ``ranking.py`` / every test trigger
    transitively. ``signals`` is imported lazily to keep the module import order
    one-way (signals never imports signal_specs)."""
    from mtg_utils._deck_forge.signals import Signal, producible_static_keys

    orphans = sorted(
        key
        for key in producible_static_keys()
        if spec_for(Signal(key=key, scope="any", subject="", text="", source=""))
        is None
    )
    if orphans:
        msg = (
            f"signal keys produced by a detector but resolved by no spec: {orphans} — "
            "add a SPECS entry (or sweep row), or exclude a subject key."
        )
        raise AssertionError(msg)


_assert_every_producible_key_resolves()
