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

from mtg_utils.card_classify import get_oracle_text

_IC = re.IGNORECASE


@dataclass(frozen=True)
class SubAvenue:
    """An additional, separately-searchable angle on the same signal. A theme like
    land-creatures has genuinely distinct buckets — be the land-creatures (manlands),
    reward them (payoffs), turn lands into creatures (animators) — each needing its
    own precise search, so one signal fans out into several explorable avenues."""

    label: str
    avenue: str
    search: dict


@dataclass(frozen=True)
class SignalSpec:
    label: str
    avenue: str
    search: dict  # card_search kwargs fragment (oracle / preset_names / card_type)
    serve: re.Pattern[str]  # matcher on a candidate card's oracle text
    extras: tuple[SubAvenue, ...] = ()  # additional precise sub-avenues (optional)


def _spec(label, avenue, search, serve, extras=()):
    return SignalSpec(
        label=label,
        avenue=avenue,
        search=search,
        serve=re.compile(serve, _IC),
        extras=tuple(extras),
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
    ),
    ("creature_etb", "opponents"): _spec(
        "Creatures entering — opponents'",
        "punish creatures your opponents play",
        {"oracle": r"whenever a creature an opponent controls enters"},
        r"opponent.*creature.*enters",
    ),
    ("creatures_matter", "you"): _spec(
        "Go wide",
        "token swarms and anthems that scale with creature count",
        {"oracle": r"create .*creature token"},
        r"create .*creature token|creatures you control get",
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
    ("graveyard_matters", "opponents"): _spec(
        "Opponents' graveyards",
        "mill opponents and punish their graveyards (NOT self-mill)",
        {"oracle": r"each opponent mills|target opponent mills|opponent.*mills"},
        r"opponent[^.]*\bmill|mill[^.]*opponent|each opponent[^.]*graveyard",
    ),
    ("graveyard_matters", "you"): _spec(
        "Your graveyard",
        "self-mill and recursion fuel for your own graveyard",
        {"oracle": r"into your graveyard|surveil"},
        r"into your graveyard|from your graveyard|surveil\b|self-mill",
    ),
    ("lifegain_matters", "you"): _spec(
        "Lifegain",
        "incidental and repeatable lifegain",
        {"oracle": r"gain .* life"},
        r"gain \d+ life|gain x life|gains? [^.]*life|lifelink",
    ),
    ("counters_matter", "any"): _spec(
        "+1/+1 counters",
        "counter generators and proliferate",
        {"oracle": r"\+1/\+1 counter"},
        r"\+1/\+1 counter|proliferate",
    ),
    ("spellcast_matters", "you"): _spec(
        "Spellslinger",
        "cheap instants/sorceries and cantrips to chain casts",
        {"oracle": r"draw a card"},
        r"draw a card|prowess|magecraft",
    ),
    ("sacrifice_matters", "you"): _spec(
        "Sacrifice — fodder & outlets",
        "token fodder and free sacrifice outlets",
        {"oracle": r"create .*token|sacrifice"},
        r"create .*token|sacrifice (?:a|an|another)",
    ),
    ("death_matters", "any"): _spec(
        "Aristocrats",
        "creatures dying as a resource — fodder plus drain payoffs",
        {"oracle": r"create .*token|whenever .* dies"},
        r"create .*token|sacrifice (?:a|an|another)|whenever .* dies",
    ),
    ("attack_matters", "you"): _spec(
        "Combat",
        "haste enablers and evasive/aggressive bodies",
        {"oracle": r"haste|create .*creature token"},
        r"haste|create .*creature token",
    ),
    ("landfall", "you"): _spec(
        "Landfall",
        "extra land drops and land fetch",
        {
            "oracle": (
                r"search your library for .*land"
                r"|play an additional land|onto the battlefield"
            )
        },
        (
            r"search your library for .*land"
            r"|play an additional land|onto the battlefield"
        ),
    ),
    # ── Archetype floor specs (whole themes the baseline was blind to) ──────────
    ("token_maker", "you"): _spec(
        "Token generators",
        "more cards that flood the board with creature tokens",
        {"oracle": r"create [^.]*creature token"},
        r"create [^.]*creature token",
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
    ("enchantments_matter", "you"): _spec(
        "Enchantments",
        "enchantments and enchantment-count payoffs",
        {"card_type": "Enchantment"},
        r"enchantments? you control|for each enchantment|\bconstellation\b",
    ),
    ("tokens_matter", "you"): _spec(
        "Tokens matter",
        "token makers and payoffs that scale with tokens you control",
        {"oracle": r"create [^.]*token"},
        r"\btokens? you control\b|whenever .*token.*enters|\bpopulate\b",
    ),
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
        r"opponents? can't|spells your opponents cast cost|your opponents",
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
        "proliferate and counter generators",
        {"preset_names": ("proliferate",)},
        r"\bproliferate\b|\+1/\+1 counter",
    ),
    ("magecraft_matters", "you"): _spec(
        "Magecraft / spellslinger",
        "cheap instants and sorceries and cantrips to trigger magecraft",
        {"oracle": r"draw a card"},
        r"\bmagecraft\b|\bprowess\b|instant or sorcery",
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
}

# Subject-bearing signal keys: their spec is built dynamically from the captured
# subtype (a Goblin lord and a Sliver lord must not share one static spec).
_SUBJECT_KEYS = frozenset({"type_matters", "token_maker", "typed_spellcast"})
_SUBJECT_TEMPLATES = {
    "type_matters": ("{s} tribal", "{s}s and the anthems/lords that reward them"),
    "token_maker": ("{s} tokens", "more {s} token makers and {s} payoffs"),
    "typed_spellcast": ("{s} spells", "{s}s and {s}-spell payoffs"),
}


def _subject_spec(signal) -> SignalSpec:
    """Build a spec for a subject-bearing signal by interpolating the subtype."""
    subj = signal.subject
    label_t, avenue_t = _SUBJECT_TEMPLATES.get(signal.key, ("{s}", "{s} synergies"))
    return SignalSpec(
        label=label_t.format(s=subj),
        avenue=avenue_t.format(s=subj),
        # card_type matches the type-line substring → finds the tribe itself.
        search={"card_type": subj},
        serve=re.compile(rf"\b{re.escape(subj)}s?\b", _IC),
        extras=(
            SubAvenue(
                f"{subj} payoffs",
                f"anthems and abilities that reward your {subj}s",
                {"oracle": rf"{re.escape(subj)}s? you control"},
            ),
        ),
    )


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
    """True if ``card``'s oracle text feeds ``signal`` (scope-aware)."""
    spec = spec_for(signal)
    if spec is None:
        return False
    return spec.serve.search(get_oracle_text(card) or "") is not None


def search_filters(signal, *, color_identity: str, fmt: str) -> dict:
    """Build ``card_search`` kwargs to find cards that feed ``signal`` in-identity."""
    spec = spec_for(signal)
    base = dict(spec.search) if spec else {}
    base["color_identity"] = color_identity
    base["format"] = fmt
    return base
