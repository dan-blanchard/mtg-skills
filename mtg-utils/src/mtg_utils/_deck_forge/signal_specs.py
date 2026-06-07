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

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS, SWEEP_LABELS
from mtg_utils.card_classify import get_oracle_text

_IC = re.IGNORECASE


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
    self_recur: bool = False  # serve a creature that returns/recasts ITSELF from a gy
    names: frozenset[str] = frozenset()  # serve if the card NAME is in this set
    not_oracle: re.Pattern[str] | None = None

    def search(self, text: str):
        """Back-compat: raw oracle-regex search over a string (legacy call sites)."""
        return self.oracle.search(text) if self.oracle is not None else None

    def matches(self, card: dict) -> bool:
        """True if the card feeds this signal on ANY structured/oracle dimension and is
        not vetoed by ``not_oracle``."""
        oracle_text = get_oracle_text(card) or ""
        if self.not_oracle is not None and self.not_oracle.search(oracle_text):
            return False
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
        if self.self_recur:
            out["self_recur"] = True
        if self.names:
            out["names"] = sorted(self.names)
        if self.not_oracle is not None:
            out["not_oracle"] = self.not_oracle.pattern
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
            or self.self_recur
            or self.names
            or self.not_oracle is not None
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


def _compile(pat):
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
        self_recur=bool(data.get("self_recur")),
        names=frozenset(n.lower() for n in (data.get("names") or ())),
        not_oracle=_compile(data.get("not_oracle")),
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
    label,
    avenue,
    search,
    serve,
    extras=(),
    *,
    serve_types=(),
    serve_keywords=(),
    serve_cmc_min=None,
    serve_min_devotion=None,
    serve_produces_mana=False,
    serve_power_min=None,
    serve_self_recur=False,
    serve_not=None,
):
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
)
_SLINGER_TYPES = ("instant", "sorcery")
_SLINGER_KEYWORDS = ("prowess",)
_SLINGER_SEARCH_ORACLE = (
    r"\bmagecraft\b|\bprowess\b"
    r"|whenever you cast (?:an instant|a sorcery|a noncreature|your)"
    r"|instant and sorcery spells you cast"
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
# Flicker enablers (CR 603.6e) for a repeated-ETB commander — re-use your own ETBs.
# Pronoun/"you control"-return anchor keeps reanimation (graveyard return) out.
_FLICKER_ORACLE = (
    r"exile[^.]*(?:creature|permanent)s?(?: you control)?[^.]*return "
    r"(?:it|them|that card|those cards|that permanent)[^.]*battlefield"
)
_FLICKER_EXTRA = SubAvenue(
    "Blink / flicker",
    "exile-and-return your own ETB creatures to re-use their enter triggers "
    "(Ephemerate / Cloudshift / Conjurer's Closet)",
    {"preset_names": ("blink",)},
    serve=Serve(oracle=re.compile(_FLICKER_ORACLE, _IC)),
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
# Deathtouch-granting gear (CR 702.2b): with a repeatable pinger, deathtouch + 1 damage
# kills anything. "(equipped|enchanted) creature … deathtouch" is Equipment/Aura-only.
_DEATHTOUCH_GEAR_ORACLE = r"(?:equipped|enchanted) creature[^.]*\bdeathtouch\b"
_DEATHTOUCH_GEAR_EXTRA = SubAvenue(
    "Deathtouch enablers",
    "Equipment/Auras that grant deathtouch so each ping kills (Basilisk Collar)",
    {"oracle": _DEATHTOUCH_GEAR_ORACLE},
    serve=Serve(oracle=re.compile(_DEATHTOUCH_GEAR_ORACLE, _IC)),
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
        extras=(_ETB_PAYOFF_EXTRA, _FLICKER_EXTRA),
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
        r"create .*creature token|creatures you control get",
        extras=(_ETB_PAYOFF_EXTRA,),
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
        r"",
        serve_power_min=4,
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
        r"(?:each opponent|target opponent|an opponent|that player|target player) mills"
        r"|opponent[^.]*\bmill|mill[^.]*opponent"
        r"|exile (?:target player'?s?|each opponent'?s?|a) graveyard"
        r"|(?:cards?|creature cards?)[^.]*in [^.]*opponents'? graveyards?"
        r"|each opponent'?s graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard",
        {"oracle": r"into your graveyard|surveil"},
        r"into your graveyard|from your graveyard|surveil\b|self-mill",
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
        "counter generators and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        r"\+1/\+1 counter|proliferate",
        extras=(_PROLIFERATE_EXTRA,),
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
    ("spellcast_matters", "you"): _spec(
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
    ),
    # `create .*token` was type-blind — it served every Treasure/Clue/Food maker
    # (~428 in WBR), none of which are sacrifice fodder. Require the literal "creature
    # token" (CR 111.10 token types); and exclude "sacrifice a land" (fetchlands) from
    # the outlet branch.
    ("sacrifice_matters", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create [^.]*creature token|sacrifice"},
        r"create [^.]*creature token|sacrifice (?:a|an|another)(?! land\b)",
        extras=(_SELF_RECUR_EXTRA,),
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create [^.]*creature token|whenever .* dies"},
        r"create [^.]*creature token|sacrifice (?:a|an|another)(?! land\b)"
        r"|whenever .* dies",
        extras=(_SELF_RECUR_EXTRA,),
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
        r"|whenever (?:a|an|another|one or more)[^.]*creatures? you control attacks?",
        serve_keywords=("haste",),
    ),
    # The bare `onto the battlefield` branch matched every cheat-into-play and
    # reanimation effect (Sneak Attack, Reanimate). Anchor it to a LAND card, mirroring
    # lands_matter (CR 305 — landfall fires on a land entering, not any permanent).
    ("landfall", "you"): _spec(
        "Landfall",
        "extra land drops and land fetch",
        {
            "oracle": (
                r"search your library for .*\bland\b"
                r"|play (?:an|one|two|\d+) additional lands?"
                r"|put .*\bland card.*onto the battlefield"
            )
        },
        (
            r"search your library for .*\bland\b"
            r"|play (?:an|one|two|\d+) additional lands?"
            r"|put .*\bland card.*onto the battlefield"
        ),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        r"create [^.]*creature token",
        extras=(_TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA),
    ),
    ("treasure_matters", "you"): _spec(
        "Treasure",
        "Treasure makers for ramp, fixing, and artifact synergy",
        {"oracle": r"create [^.]*treasure token|treasures? you control"},
        r"\btreasure\b",
    ),
    ("artifacts_matter", "you"): _spec(
        "Artifacts",
        "artifacts and artifact-count payoffs",
        {"card_type": "Artifact"},
        r"artifacts? you control|for each artifact|\bmetalcraft\b|\baffinity\b",
    ),
    # Serve augmented with "whenever you cast an enchantment" so the 14 plain CREATURES
    # that trigger on enchantment casts (Verduran/Mesa Enchantress, Sythis) — missed by
    # both the {card_type:Enchantment} type-serve and the count regex — are credited.
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b"
        r"|whenever you cast an enchantment",
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
        extras=(_TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA),
    ),
    # The bare `your opponents` alternative matched any card that merely names opponents
    # (Edric's draw trigger, Telepathy's hand reveal). Serve the actual restriction/tax
    # SHAPES instead (CR 601.2f cost increases, prohibitions) — which also recovers the
    # symmetric taxes the old regex missed (Thalia: "Noncreature spells cost {1} more").
    ("stax_taxes", "opponents"): _spec(
        "Stax & taxes",
        "tax and restriction effects aimed at your opponents",
        {
            "oracle": (
                r"opponents? can't"
                r"|spells your opponents cast cost"
                r"|creatures your opponents control"
            )
        },
        r"opponents? can't"
        r"|(?:players?|that player|each player) can't (?:cast|activate|attack|block|"
        r"untap|search|draw|play)"
        r"|spells?[^.]*cost \{?\d+\}? more|noncreature spells?[^.]*cost \{?\d"
        r"|creatures your opponents control"
        r"|(?:your opponents control|nonbasic lands?) enters?"
        r"(?: the battlefield)? tapped",
    ),
    ("blink_flicker", "you"): _spec(
        "Blink / flicker",
        "exile-and-return effects to re-use enter-the-battlefield abilities",
        {"preset_names": ("blink",)},
        r"exile[^.]*?return[^.]*?battlefield",
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
    ),
    ("proliferate_matters", "you"): _spec(
        "Proliferate",
        "proliferate plus any-kind counter sources (poison/loyalty/charge/+1+1)",
        {"preset_names": ("proliferate",)},
        r"\bproliferate\b|(?:poison|loyalty|charge|oil|\+1/\+1) counter",
    ),
    # Same archetype + matcher as spellcast_matters (a magecraft commander triggers off
    # the same instants/sorceries as a prowess one). Was the canonical bug twice over:
    # a "draw a card" search and an "instant or sorcery" serve branch that credited
    # counterspell-shelters and graveyard payoffs.
    ("magecraft_matters", "you"): _spec(
        "Magecraft / spellslinger",
        "cheap instants and sorceries plus magecraft/prowess payoffs to chain casts",
        {"oracle": _SLINGER_SEARCH_ORACLE},
        _SLINGER_SERVE_ORACLE,
        serve_types=_SLINGER_TYPES,
        serve_keywords=_SLINGER_KEYWORDS,
    ),
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
    # Narrow the bare `from exile` to the impulse/engine phrasing, so single-card
    # rebound/foretell self-casts (Consuming Vapors) don't read as an engine.
    ("cast_from_exile", "you"): _spec(
        "Impulse / cast-from-exile",
        "impulse-draw enablers and cast-from-exile payoffs",
        {"oracle": r"from the top of your library|from exile"},
        r"from the top of your library|spells? you cast from exile"
        r"|whenever you cast a spell from exile"
        r"|you may (?:play|cast) (?:it|that card|those cards?|them|the exiled)"
        r"|\bplot\b",
        extras=(
            SubAvenue(
                "Top-of-library engines",
                "cards that let you play off the top of your library",
                {"oracle": r"from the top of your library"},
            ),
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
    ("discard_matters", "you"): _spec(
        "Discard",
        "loot/connive discard outlets and discard payoffs",
        {"oracle": r"discard (?:a|an|two|your hand)[^:.]*?:|draw [^.]*?then discard"},
        r"whenever you discard|discard (?:a|an|two|your hand)[^:.]*?:"
        r"|draw [^.]*then discard",
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
        "ways to pay or lose life on demand to fuel your payoffs",
        {"oracle": r"you lose \d+ life|pay \d+ life|lose \d+ life"},
        r"whenever you (?:gain or )?lose life|you lose (?:\d+|x) life"
        r"|pay (?:\d+|x) life",
        serve_not=r"\bas this land enters\b|enters tapped",
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
        r"the number of lands you control|for each land you control"
        r"|play an additional land",
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
        r"|if a source[^.]*would deal damage[^.]*instead",
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
        r"|cast an? (?:aura|equipment)|cast aura and equipment",
        serve_types=("equipment", "aura"),
        serve_keywords=("reconfigure",),
        serve_not=r"can't attack|can't block|doesn't untap during"
        r"|enchant creature you don't control|defending player controls",
    ),
    ("vehicles_matter", "you"): _spec(
        "Vehicles",
        "Vehicle bodies plus crew payoffs, lords, and cheap creatures to crew them",
        {"preset_names": ("crew",)},
        r"\bvehicles? you control\b|\bcrew\b|create [^.]*vehicle artifact",
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
        r"\bfood token|foods? you control|sacrifice a food",
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
    ("doubling_matters", "you"): _spec(
        "Doubling",
        "token/counter doublers and the payoffs that exploit doubled output",
        {"oracle": r"twice that many|double the (?:number|amount)"},
        r"twice that many|double the (?:number|amount)",
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
        {"oracle": r"add \{|search your library for .*\bland\b"},
        r"\{t\}[^.]*:\s*add|add .* mana|search your library for .*\bland\b",
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
        {"oracle": r"untap (?:target|all|another|each)"},
        r"untap (?:target|all|another|each)",
    ),
    # YOU must be the one gaining control — VETO the donate shapes where an OPPONENT
    # gains control of your stuff (Sky Swallower). Add the exile-and-cast theft form.
    ("gain_control", "you"): _spec(
        "Theft",
        "steal effects and ways to keep or sacrifice what you take",
        {"oracle": r"gain control of"},
        r"you (?:gain|may gain) control of|gain control of (?:target|all|each|another)"
        r"|you control enchanted (?:creature|permanent)"
        r"|you may (?:play|cast)[^.]*from (?:that|target) (?:player|opponent)",
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
    ),
    ("clone_matters", "you"): _spec(
        "Clones / copies",
        "clone effects plus strong creatures worth copying",
        {"oracle": r"becomes a copy|copy of (?:target|another)"},
        r"becomes a copy|copy of (?:target|another)",
    ),
    ("cheat_into_play", "you"): _spec(
        "Cheat into play",
        "ways to put big creatures onto the battlefield from hand or library",
        {"oracle": r"onto the battlefield"},
        r"onto the battlefield from your (?:hand|library)"
        r"|put .*creature card.*onto the battlefield",
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
    ),
    ("regenerate_matters", "you"): _spec(
        "Regenerate / resilience",
        "regeneration and resilience to keep your threats around",
        {"oracle": r"\bregenerate\b"},
        r"\bregenerate\b",
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
        {"oracle": r"whenever an opponent draws|each opponent draws"},
        r"whenever an opponent draws|whenever each opponent draws"
        r"|whenever a player (?:other than you )?draws"
        r"|whenever a player draws a card (?:except|other than)",
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
        extras=(_FLICKER_EXTRA,),
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
        r"\bsuspend\b|\bvanishing\b|\bimpending\b|time counter|time travel",
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
        {"oracle": rf"{esc}s? you control"},
    )


def _subject_spec(signal) -> SignalSpec:
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
            extras=(_payoff_extra(subj, esc), _TOKEN_DOUBLER_EXTRA, _ETB_PAYOFF_EXTRA),
        )
    # tribal (type_matters) / typed spellcast: the cards themselves (type-line match),
    # plus a distinct "{s} payoffs" sub-avenue for the lords/anthems that reward them.
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    # Changelings (CR 702.73a) are every creature type, so they count for EVERY tribe —
    # but they type-line as "Shapeshifter", so the {card_type: subj} search misses every
    # one. Fold them (the keyword bearers + the "is/are every creature type" granters)
    # into the type-tribal serve so a Goblin/Elf/Zombie deck credits its changelings.
    is_type_tribal = signal.key == signal_keys.TYPE_MATTERS
    serve_oracle = rf"\b{esc}s?\b" + (
        r"|(?:is|are) every creature type" if is_type_tribal else ""
    )
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        search={"card_type": subj},
        serve=Serve(
            oracle=re.compile(serve_oracle, _IC),
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


def spec_for(signal) -> SignalSpec | None:
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


def serves(card: dict, signal) -> bool:
    """True if ``card`` feeds ``signal`` (scope-aware), on any structured/oracle
    dimension of the spec's precise ``Serve`` predicate — no longer oracle-only."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.matches(card)


def search_filters(signal, *, color_identity: str, fmt: str) -> dict:
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
