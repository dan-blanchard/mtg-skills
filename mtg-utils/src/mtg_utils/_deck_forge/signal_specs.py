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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS, SWEEP_LABELS
from mtg_utils.card_classify import get_oracle_text

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
    min_devotion: int | None = None
    produces_mana: bool = False  # serve if the card has a non-empty produced_mana
    power_min: int | None = None  # serve a creature whose power >= this (big-creature)
    toughness_min: int | None = None  # serve a creature whose toughness >= this (Doran)
    toughness_over_power: bool = False  # serve a "butt": toughness > power (>=3 floor)
    keyword_count_min: int | None = None  # serve a creature with >=N EVERGREEN keywords
    vanilla: bool = False  # serve a creature with NO rules text (Muraganda / Ruxa)
    self_recur: bool = False  # serve a creature that returns/recasts ITSELF from a gy
    names: frozenset[str] = frozenset()  # serve if the card NAME is in this set
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
        type_line = (card.get("type_line") or "").lower()
        if self.types and any(t in type_line for t in self.types):
            return True
        if self.keywords:
            card_kw = {k.lower() for k in (card.get("keywords") or [])}
            if card_kw & self.keywords:
                return True
        if self.cmc_min is not None and (card.get("cmc") or 0) >= self.cmc_min:
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
    try:
        return int(str(card.get("power", "0")))
    except ValueError:
        return 0  # */X or non-numeric power doesn't count toward a power threshold


def _toughness(card: dict) -> int:
    try:
        return int(str(card.get("toughness", "0")))
    except ValueError:
        return 0  # */X or non-numeric toughness doesn't count toward a threshold


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
        min_devotion=data.get("min_devotion"),
        produces_mana=bool(data.get("produces_mana")),
        power_min=data.get("power_min"),
        toughness_min=data.get("toughness_min"),
        toughness_over_power=bool(data.get("toughness_over_power")),
        keyword_count_min=data.get("keyword_count_min"),
        vanilla=bool(data.get("vanilla")),
        self_recur=bool(data.get("self_recur")),
        names=frozenset(n.lower() for n in (data.get("names") or ())),
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
    serve_min_devotion: int | None = None,
    serve_produces_mana: bool = False,
    serve_power_min: int | None = None,
    serve_toughness_min: int | None = None,
    serve_toughness_over_power: bool = False,
    serve_keyword_count_min: int | None = None,
    serve_vanilla: bool = False,
    serve_self_recur: bool = False,
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
            min_devotion=serve_min_devotion,
            produces_mana=serve_produces_mana,
            power_min=serve_power_min,
            toughness_min=serve_toughness_min,
            toughness_over_power=serve_toughness_over_power,
            keyword_count_min=serve_keyword_count_min,
            vanilla=serve_vanilla,
            self_recur=serve_self_recur,
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
_DIES_RECURSION_ORACLE = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "dies_recursion"
)
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
    r"when this creature enters,(?: you may)? return "
    r"(?:a|an|another|target|up to one|up to two)(?: target| other)? "
    r"(?:creature|permanent|nonland permanent)s? you control to its owner"
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
# sacrifice_matters, not death_matters, but wants the same drain payoffs).
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
# counter"), so the bare counters_matter serve missed it. Shared across every counter
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
# with no +1/+1. Reuse the mined keyword_counter regex so it never drifts.
_KEYWORD_COUNTER_ORACLE = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "keyword_counter"
)
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
_COUNTERS_PACKAGE = (
    _COUNTER_PLACE_EXTRA,
    _COUNTER_DOUBLER_EXTRA,
    _KEYWORD_COUNTER_EXTRA,
    _COUNTER_KEYWORD_EXTRA,
    _PROLIFERATE_EXTRA,
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
_EXTRA_COMBAT_EXTRA = SubAvenue(
    "Extra combats",
    "additional combat phases so your forced/incentivized attackers swing again "
    "(World at War / Aggravated Assault)",
    {"oracle": r"additional combat|extra combat"},
    serve=Serve(oracle=re.compile(r"additional combat|extra combat", _IC)),
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
) -> SignalSpec:
    """Promote a mined sweep detector to a hand-spec that keeps its regex (as both
    search and serve) but fans out extra sub-avenues — used where a sweep-derived lane
    needs to surface payoffs its bare regex can't (e.g. every counter lane wants the
    counter doublers). ``serve_power_min`` / ``serve_toughness_min`` additionally credit
    big bodies (power doublers / toughness-as-power lanes want the stat-line they
    exploit); ``serve_keywords`` adds a keyword dimension. Reuses SWEEP_DETECTORS so the
    regex never drifts from the mine.
    """
    d = next(x for x in SWEEP_DETECTORS if x["key"] == key)
    label, avenue = SWEEP_LABELS[key]
    return _spec(
        label,
        avenue,
        {"oracle": d["regex"]},
        d["regex"],
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
# Instant-speed pump (Giant Growth / Berserk) to push through extra combat damage and
# survive blocks — reuses the mined pump_matters regex so it never drifts.
_PUMP_ORACLE = next(d["regex"] for d in SWEEP_DETECTORS if d["key"] == "pump_matters")
_EDICT_SWEEP_REGEX = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "edict_matters"
)
# Basic-land-TYPE fetches (Skyshroud Claim, Nature's Lore, Farseek) search for
# "Forest/Plains/… cards" — no "land" in the text, so the bare "search … land" missed
# them. These ARE land ramp.
_BASIC_LAND_FETCH = (
    r"search your library for [^.]*\b(?:forest|plains|island|swamp|mountain)s?\b"
)
_TARGETING_SWEEP_REGEX = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "targeting_matters"
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
_IMPULSE_SWEEP_REGEX = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "impulse_top_play"
)
_THEFT_SWEEP_REGEX = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "theft_matters"
)
_DISCARD_OUTLET_SWEEP_REGEX = next(
    d["regex"] for d in SWEEP_DETECTORS if d["key"] == "discard_outlet"
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
                {"oracle": r"lands? you control[^.]*become[^.]*creature"},
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
    ("counters_matter", "any"): _spec(
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
    ("sacrifice_matters", "you"): _spec(
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
    ("edict_matters", "each"): _spec(
        *SWEEP_LABELS["edict_matters"],
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
        # Death-trigger DOUBLER (Teysa Karlov, Drivnod) — see sacrifice_matters.
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
        # (Winota, Johan, Umaro) open attack_matters, not extra_combats.
        r"|additional combat phase",
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
        r"|damage that would (?:reduce|be dealt)[^.]*(?:instead|prevented)",
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
    ("banding_matters", "you"): _spec(
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
        {"oracle": r"\boutlaws?\b"},
        r"\boutlaws? you control\b|another outlaw",
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
    # The greedy `whenever .*token.*enters` spanned clauses and matched attack-trigger
    # token-makers and NONtoken-ETB payoffs (Darksteel Splicer). Anchor the entering
    # object to a token in the SAME clause.
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b"
        r"|whenever (?:a|one or more|another)[^.]*?\btokens?\b[^.]*?\benters\b"
        r"|\bpopulate\b",
        # NB: token MAKERS are deliberately NOT in the serve — they're found by the
        # search dict (build-time) but a maker is generically good (every deck runs
        # some), not archetype-UNIQUE like a Goblin is to Goblins; serving all 2315
        # would flood the lane (and broke the token-enters anchor guard + ranking sort).
        extras=(_TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA, _GOWIDE_ANTHEM_EXTRA),
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
    ("mill_matters", "any"): _spec(
        "Mill",
        "cards that mill — fuel a graveyard or grind a library",
        {"preset_names": ("mill",)},
        r"\bmills?\b",
    ),
    ("goad_matters", "opponents"): _spec(
        "Goad & politics",
        "goad and forced-attack effects that point creatures at your opponents",
        {"preset_names": ("goad",)},
        r"\bgoad",
        extras=(_PILLOWFORT_EXTRA,),  # politics: make yourself a bad target too
    ),
    # Fog / damage-prevention commanders durdle defensively — pillowfort is a top
    # EDHREC pick for them (4 commanders in the evidence). Keep the mined fog regex.
    ("damage_prevention", "you"): _sweep_spec_with_extras(
        "damage_prevention", (_PILLOWFORT_EXTRA,)
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
    ("self_counter_grow", "you"): _sweep_spec_with_extras(
        "self_counter_grow", _COUNTERS_PACKAGE
    ),
    ("counter_manipulation", "you"): _sweep_spec_with_extras(
        "counter_manipulation", _COUNTERS_PACKAGE
    ),
    ("counter_distribute", "you"): _sweep_spec_with_extras(
        "counter_distribute", _COUNTERS_PACKAGE
    ),
    ("counter_place_trigger", "you"): _sweep_spec_with_extras(
        "counter_place_trigger", _COUNTERS_PACKAGE
    ),
    ("keyword_counter", "you"): _sweep_spec_with_extras(
        "keyword_counter", _COUNTERS_PACKAGE
    ),
    ("counter_replace_bonus", "you"): _sweep_spec_with_extras(
        "counter_replace_bonus", _COUNTERS_PACKAGE
    ),
    ("counter_move", "you"): _sweep_spec_with_extras("counter_move", _COUNTERS_PACKAGE),
    # Beginning-of-combat / attack-buff commanders are combat decks — surface the gear
    # and keyword-anthems that grow their attackers.
    ("combat_buff_engine", "you"): _sweep_spec_with_extras(
        "combat_buff_engine", (_COMBAT_SUPPORT_EXTRA,)
    ),
    # A "becomes blocked" payoff (General Marhault: +3/+3 for each creature blocking it)
    # wants Lure effects — forcing every able creature to block maxes the per-blocker
    # bonus.
    ("blocked_matters", "you"): _sweep_spec_with_extras(
        "blocked_matters", (_LURE_EXTRA,)
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
    ("creature_cast_trigger", "you"): _sweep_spec_with_extras(
        "creature_cast_trigger",
        (_CREATURE_COST_EXTRA, _SELF_BOUNCE_EXTRA),
        serve_power_min=6,
    ),
    # Toughness-as-power (Doran, Arcades) and damage-reflection (Boros Reckoner) decks
    # want big-TOUGHNESS bodies and Walls — credit them by toughness>=4 and Defender.
    ("toughness_combat", "you"): _sweep_spec_with_extras(
        "toughness_combat",
        serve_toughness_min=4,
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
    ),
    ("damage_reflect", "you"): _sweep_spec_with_extras(
        "damage_reflect",
        serve_toughness_min=4,
        serve_toughness_over_power=True,
        serve_keywords=("defender",),
    ),
    # Power doublers (Rhonas, Mr. Orfeo) want high BASE power to double; power-as-damage
    # pingers/fighters (Itzquinth) want high power for more damage. Both lanes credit
    # the fat bodies they exploit (Ghalta / Worldspine Wurm), not just the engine cards.
    ("power_double", "you"): _sweep_spec_with_extras(
        "power_double", (_POWER_FLING_EXTRA,), serve_power_min=5
    ),
    # Firebreathing / variable-P/T decks pump power, then fling it for damage.
    ("self_pump", "you"): _sweep_spec_with_extras("self_pump", (_POWER_FLING_EXTRA,)),
    # Force-attack / goad commander (Kratos) wants extra combats to swing again.
    ("forced_attack", "you"): _sweep_spec_with_extras(
        "forced_attack", (_EXTRA_COMBAT_EXTRA, _COMBAT_SUPPORT_EXTRA)
    ),
    # Donate commander (Jon Irenicus, Harmless Offering) wants drawback creatures to
    # hand to opponents for the downside.
    ("donate_matters", "you"): _sweep_spec_with_extras(
        "donate_matters", (_DRAWBACK_EXTRA,)
    ),
    # Legend-rule-off commander (Brothers Yamazaki) wants self-copy effects to run
    # multiple copies of itself.
    ("legend_rule_off", "you"): _sweep_spec_with_extras(
        "legend_rule_off", (_COPY_EXTRA,)
    ),
    # A self-blinking commander (Norin) re-enters constantly, firing "whenever a
    # creature enters" payoffs (Impact Tremors) and doublers (Panharmonicon).
    ("self_blink", "you"): _sweep_spec_with_extras(
        "self_blink", (_ETB_PAYOFF_EXTRA, _ETB_VALUE_EXTRA, _ETB_DOUBLER_EXTRA)
    ),
    # A repeatable-wrath commander (Mageta) wants to rebuild after the sweep:
    # reanimation (Breath of Life) plus indestructible bombs (Zetalpa) that survive it.
    ("mass_removal", "you"): _sweep_spec_with_extras(
        "mass_removal",
        (_REANIMATION_EXTRA, _BOARD_PROTECTION_EXTRA),
        serve_keywords=("indestructible",),
    ),
    ("variable_pt", "you"): _sweep_spec_with_extras(
        "variable_pt", (_POWER_FLING_EXTRA,)
    ),
    ("creature_ping", "you"): _sweep_spec_with_extras(
        "creature_ping", (_DEATHTOUCH_GEAR_EXTRA,), serve_power_min=5
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
    ("noncombat_damage_payoff", "you"): _sweep_spec_with_extras(
        "noncombat_damage_payoff", (_DEATHTOUCH_GEAR_EXTRA, _NONCOMBAT_BURN_EXTRA)
    ),
    # Power-as-damage / fling commander (Brion Stoutarm) wants big bodies as fling
    # fodder (power_min) plus the power-fling payoffs and deathtouch gear.
    ("damage_equal_power", "you"): _sweep_spec_with_extras(
        "damage_equal_power",
        (_DEATHTOUCH_GEAR_EXTRA, _POWER_FLING_EXTRA),
        serve_power_min=6,
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
        # up (Ojutai) and instant pump to push through / survive blocks (Benton).
        extras=(_COMBAT_SUPPORT_EXTRA, _PUMP_EXTRA),
    ),
    ("combat_damage_to_opp", "opponents"): _sweep_spec_with_extras(
        "combat_damage_to_opp",
        (_COMBAT_SUPPORT_EXTRA, _PUMP_EXTRA, _DAMAGE_AMPLIFIER_EXTRA),
    ),
    # The discount-exploiting target set is defined by high cmc (structured) + X-spells
    # — not the generic words "mana value", which matched 453 cards (Disdainful Stroke,
    # Abrupt Decay). Drop that branch; gate on cmc (expensive bombs) + {x} + storm.
    ("cost_reduction", "you"): _spec(
        "Cost reduction",
        "expensive bombs and X-spells that exploit the discount",
        {"oracle": r"\{x\}|with mana value"},
        r"\{x\}|\bstorm\b",
        serve_cmc_min=7,
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
        {"oracle": r"from exile"},
        r"spells? you cast from exile"
        r"|whenever you cast a spell from exile"
        r"|you may (?:play|cast) (?:it|that card|those cards?|them|the exiled)"
        r"[^.]*?from exile"
        r"|" + _STEAL_CAST_ORACLE + r"|\bplot\b",
        extras=(
            # Paradox (CR 207.2c): "cast a spell / play a card from anywhere other than
            # your hand" payoffs (Vega, Iraxxa) the literal-"from exile" serve misses.
            SubAvenue(
                "Paradox payoffs",
                "zone-agnostic payoffs that reward casting/playing from anywhere other "
                "than your hand",
                {"oracle": r"from anywhere other than your hand"},
                serve=Serve(
                    oracle=re.compile(
                        r"(?:cast a spell|play a land|play a card)[^.]*?"
                        r"from anywhere other than your hand",
                        _IC,
                    )
                ),
            ),
        ),
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
        + r"|spells? you cast from exile|first spell you cast from exile",
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
    # Play from the TOP OF YOUR LIBRARY — Future Sight / Bolas's Citadel / Oracle of Mul
    # Daya. Casts from the LIBRARY zone (not exile), so it's its own avenue, distinct
    # from cast-from-exile and impulse. Needs a play/cast verb so look/scry/mill don't
    # match.
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
        r"(?: who)? lost life this turn",
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
            )
        },
        r"number of tapped creatures you control"
        r"|\btapped creatures you control (?:have|get|gain|are|can|with)",
    ),
    # Land sacrifice (Gitrog, Titania, Slogurk): lands hitting the graveyard is the
    # payoff, so repeatable "Sacrifice a land:" outlets (Sylvan Safekeeper, Zuran Orb)
    # are the engine. Distinct from sacrifice_matters (which excludes "sacrifice a land"
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
    ("keyword_soup_matters", "you"): _spec(
        "Keyword soup",
        "creatures stacked with evergreen keywords to share across your team",
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
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls",
        extras=(_VOLTRON_PROTECT_EXTRA,),
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
    ("initiative_matters", "you"): _spec(
        "Initiative",
        "take and hold the initiative; venture through the Undercity",
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
    ("experience_matters", "you"): _spec(
        "Experience counters",
        "ways to gain experience counters and scale with them",
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
    ("mutate_matters", "you"): _spec(
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
        r"in addition to (?:its|their)",
    ),
    # Hand-spec overriding the mined sweep detector so the serve also credits the Domain
    # ENABLERS — "lands you control are every basic land type" (Prismatic Omen, Dryad of
    # the Ilysian Grove) — not just the "domain" / "basic land types among" payoffs.
    ("domain_matters", "you"): _spec(
        "Domain",
        "basic land types and fixing to grow domain",
        {"oracle": r"\bdomain\b|basic land types?"},
        r"\bdomain\b|number of basic land types?|basic land types? among"
        r"|every basic land type",
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
    ("token_copy_matters", "you"): _spec(
        "Token copies",
        "strong creatures to copy plus token-copy and populate engines",
        {"oracle": r"token that's a copy|tokens? that are copies|\bpopulate\b"},
        r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of|\bpopulate\b",
        # Deliver on "strong creatures to copy": a token-copy deck wants big bombs to
        # copy (Etali). power_min=6 keeps it to genuine bombs, mirroring clone_matters.
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
    ("connive_matters", "you"): _spec(
        "Connive",
        "connive enablers and counter/discard payoffs",
        {"oracle": r"\bconnives?\b|draw a card, then discard"},
        r"\bconnives?\b",
    ),
    ("spell_copy_matters", "you"): _spec(
        "Spell copy",
        "impactful instants/sorceries plus copy effects to multiply your spells",
        {"oracle": r"copy (?:target|that)|instant or sorcery|\bstorm\b"},
        r"copy target (?:instant|sorcery|spell)|\bcopy that spell\b|\bstorm\b",
    ),
    # ── Effect-axis specs ───────────────────────────────────────────────────────
    ("ramp_matters", "you"): _spec(
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
    ("removal_matters", "you"): _spec(
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
    ("tutor_matters", "you"): _spec(
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
    ("tap_untap_matters", "you"): _sweep_spec_with_extras(
        "tap_untap_matters", (_UNTAP_EXTRA,)
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
        extras=(_DISCARD_PUNISH_EXTRA,),
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
    ("ninjutsu_matters", "you"): _spec(
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
    ("clone_matters", "you"): _spec(
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
        ),
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
    ("regenerate_matters", "you"): _spec(
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
    ("dash_matters", "you"): _spec(
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
    # (those are pump_matters). Oracle-with-temporal-guard (no structured 'is-static').
    ("anthem_static", "you"): _spec(
        "Static anthem",
        "go-wide creatures to ride the anthem",
        {
            "oracle": (
                r"(?:other [a-z]+ creatures|creatures you control"
                r"|[a-z]+ creatures you control|nonblack creatures|other creatures)"
                r" get \+\d/\+\d"
            )
        },
        r"(?:other [a-z]+ creatures|creatures you control"
        r"|[a-z]+ creatures you control|nonblack creatures|other creatures)"
        r" get \+\d/\+\d",
        serve_not=r"get \+\d/\+\d[^.]*until end of turn",
    ),
    # ltb_matters: VETO the O-Ring exile-until-leaves removal (Banishing Light) — that
    # already routes to exile_until_leaves, so excluding it here is lossless.
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
    ),
    ("discover_matters", "you"): _spec(
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
    ("undying_persist_matters", "you"): _spec(
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
    ("suspect_matters", "you"): _spec(
        "Suspect",
        "cards that suspect creatures (menace + can't block) plus the payoffs that "
        "reward having suspected creatures",
        {"oracle": r"\bsuspect\b|\bsuspected\b"},
        r"\bsuspects?\b|\bsuspected\b",
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
    signal_keys.TYPE_MATTERS: ("{s} tribal", "{s} creatures to grow the tribe"),
    signal_keys.TYPED_SPELLCAST: ("{s} spells", "{s} spells to cast"),
}


def _payoff_extra(subj: str, esc: str) -> SubAvenue:
    return SubAvenue(
        f"{subj} payoffs",
        f"lords and anthems that reward a board of {subj}s",
        # The tribe's own lords ("{subj}s you control") PLUS the type-AGNOSTIC tribal
        # anthems that reward ANY tribe: "choose a creature type … of the chosen type"
        # (Vanquisher's Banner, Herald's Horn, Door of Destinies) and "shares a creature
        # type" pumps (Shared Animosity, Coat of Arms).
        {
            "oracle": rf"{esc}s? you control"
            r"|\bthe chosen type\b|shares (?:a|at least one) creature type"
        },
    )


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
    # Type-agnostic tribal enablers grant the chosen type to your board (Xenograft,
    # Arcane Adaptation), so they count for EVERY tribe — credit the "every creature
    # type" / "the chosen type" grant phrasings, not just changelings.
    serve_oracle = rf"\b{esc}s?\b" + (
        r"|(?:is|are) every creature type|(?:is|are) the chosen type"
        if is_type_tribal
        else ""
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
            types=frozenset({subj.lower()}) if is_type_tribal else frozenset(),
            keywords=frozenset({"changeling"}) if is_type_tribal else frozenset(),
        ),
        extras=(_payoff_extra(subj, esc),),
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
