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
class SignalSpec:
    label: str
    avenue: str
    search: dict  # card_search kwargs fragment (oracle / preset_names / card_type)
    serve: re.Pattern[str]  # matcher on a candidate card's oracle text


def _spec(label, avenue, search, serve):
    return SignalSpec(
        label=label, avenue=avenue, search=search, serve=re.compile(serve, _IC)
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
}


def spec_for(signal) -> SignalSpec | None:
    """Resolve a spec: exact (key, scope) → (key, any) → first entry by key."""
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
