"""Transparent multi-axis candidate ranking (D6).

Every candidate exposes separate readouts — synergy (which signals/avenues it
serves and how *deeply*), mana efficiency (cmc), and price — rather than one
opaque score. EDHREC popularity is deliberately absent.

Synergy has two readouts. ``synergy_fit`` is the raw COUNT of distinct lanes
served (kept for display + back-compat). ``synergy_score`` is the SORT key: a
depth-over-breadth measure that fixes the count's fatal flaw — because many
lanes share a trigger clause (``create … creature token`` lives in ~14 serve
specs), one generic property used to score one point *per lane*, so a card that
makes a single 1/1 outscored the deck's actual payoff. ``synergy_score`` instead
clusters served lanes by the ORACLE CLAUSE that matched them (one physical
property = one credit), weights each cluster ``payoff > enabler > structural``
(a reactive reward-trigger clause beats a bare token-creation clause beats a
type/keyword membership), and scales by the deck's own avenue prominence
(``focus_sets``) so the fix is deck-relative — a genuine token deck still rewards
token makers, an aristocrats deck rewards death payoffs. Premium fixing / bombs
score low on synergy BY DESIGN and are surfaced on the separate
``structural_floor`` axis (so the tuner can protect them on the cut side without
faking synergy).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence

from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
from mtg_utils._deck_forge.signals import clauses
from mtg_utils.card_classify import (
    classifying_type_line,
    extract_price,
    get_oracle_text,
    is_ramp,
)

# Cluster role weights: a reactive payoff clause is worth more than a bare
# generative/fodder action, which beats mere type/keyword membership.
_ROLE_WEIGHT = {"payoff": 3.0, "enabler": 1.0, "structural": 0.5}
_ROLE_RANK = {"payoff": 2, "enabler": 1, "structural": 0}

# Deck-relative avenue prominence (focus tiers); an unmapped lane is mid-low.
_PROM = {"viable": 1.0, "emerging": 0.6, "stranded": 0.25}
_PROM_DEFAULT = 0.4

# A clause is a PAYOFF if it REWARDS the deck off a reactive TRIGGER (whenever a
# creature dies → drain) OR an ACTIVATED ability whose effect impacts the board
# (Walking Ballista's "remove a counter: deal 1 damage" — a real payoff with no
# trigger word) OR a static team anthem. Everything else with oracle text is an
# ENABLER (fodder/generative); a match with no oracle clause is STRUCTURAL.
_TRIGGER_RE = re.compile(
    r"\b(whenever|when|at the beginning of|each time)\b", re.IGNORECASE
)
# Broad reward set, accepted off a triggered ability (a trigger already proves the
# clause is reactive value, so weaker rewards like a counter/token still count).
_REWARD_RE = re.compile(
    r"loses? \d|loses? [^.]*\blife\b|gains? [^.]*\blife\b|\bdraw\b|"
    r"deals? \d|deals? [^.]*\bdamage\b|\bdestroy\b|\bexile\b|"
    r"return[s]? [^.]*to (?:the battlefield|your hand)|each opponent|"
    r"\+1/\+1 counter|create [^.]*\b(?:treasure|blood|clue|food|gold)\b|"
    r"put[s]? [^.]*counter",
    re.IGNORECASE,
)
# An activated ability: a cost (mana/tap symbol, "Sacrifice …:", "Remove a …
# counter:") followed by a colon. Its effect must be a STRONG (board-impacting)
# reward to count as a payoff — a self-pump activation ("{1}{R}: put a counter on
# this creature") is NOT a payoff, so the narrower set excludes bare counters.
_ACTIVATED_RE = re.compile(
    r"(?:\{[^}]*\}|sacrifice[^:.]*|remove (?:a|one|two|x|\d+)[^:.]*counter[^:.]*)\s*:",
    re.IGNORECASE,
)
_STRONG_REWARD_RE = re.compile(
    r"deals? \d|deals? [^.]*\bdamage\b|loses? \d|loses? [^.]*\blife\b|"
    r"\bdraw\b|\bdestroy\b|\bexile\b|each opponent",
    re.IGNORECASE,
)
_STATIC_PAYOFF_RE = re.compile(
    r"creatures? you control get |other creatures? you control (?:get|have|gain)|"
    r"for each [^.]*you control",
    re.IGNORECASE,
)


def _clause_role(clause: str) -> str:
    if _TRIGGER_RE.search(clause) and _REWARD_RE.search(clause):
        return "payoff"
    if _ACTIVATED_RE.search(clause) and _STRONG_REWARD_RE.search(clause):
        return "payoff"
    if _STATIC_PAYOFF_RE.search(clause):
        return "payoff"
    return "enabler"


# A payoff gated on a creature SUBTYPE the deck doesn't field is a dead payoff
# ("whenever you attack with one or more Lizards …" in a deck with no Lizards).
# Detect the gate's subtype and, only when given the deck's tribes, discount the
# cluster — deck-relative, so the same card is full-credit in a Lizard deck.
_GATE_PENALTY = 0.4
_TRIBAL_GATE_RE = re.compile(
    r"\b(?:attacks? with|control)\s+"
    r"(?:one or more|a|an|another|each|\d+|x|that many)?\s*"
    r"([A-Za-z][A-Za-z'\-]+)\b",
    re.IGNORECASE,
)


def _gate_penalty(clause: str, deck_tribes: frozenset[str] | None) -> float:
    """1.0 unless the clause gates on a creature subtype the deck lacks (then
    ``_GATE_PENALTY``). No penalty without deck context (``deck_tribes`` falsy)."""
    if not deck_tribes:
        return 1.0
    from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

    for m in _TRIBAL_GATE_RE.finditer(clause):
        word = m.group(1).lower()
        singular = word.removesuffix("s")
        for cand in (word, singular):
            if cand in CREATURE_SUBTYPES:
                return 1.0 if cand in deck_tribes else _GATE_PENALTY
    return 1.0


def _stronger(a: str, b: str) -> str:
    return a if _ROLE_RANK[a] >= _ROLE_RANK[b] else b


def _avenue_predicates(
    avenues: Sequence[dict],
) -> list[tuple[str, Callable[[dict], bool], re.Pattern[str] | None]]:
    """(label, card->bool, oracle_regex|None) per avenue.

    The predicate decides membership (the same precise serve / oracle-AND-type
    test as before). The trailing oracle regex is the clause-attribution handle
    ``synergy_score`` uses to find which clause an avenue matched (``None`` when
    the avenue is purely structured / type-gated).

    Two classification regimes, matching how each was authored:
      - explicit structured ``serve``: the SAME precise OR-predicate the spec
        serves on (a cantrip by TYPE, a prowess creature by KEYWORD).
      - bare ``search`` fragment (legacy): oracle regex AND card_type substring,
        so an avenue scoped to ``card_type='Land'`` won't credit a non-land clone
        that merely matches the oracle regex."""
    out: list[tuple[str, Callable[[dict], bool], re.Pattern[str] | None]] = []
    for avenue in avenues:
        serve_data = avenue.get("serve")
        if serve_data is not None:
            label = avenue.get("label", "avenue")
            serve = serve_from_dict(serve_data)
            out.append((label, serve.matches, serve.oracle))
            continue
        search = avenue.get("search") or {}
        oracle = search.get("oracle")
        card_type = (search.get("card_type") or "").lower()
        if not oracle and not card_type:
            continue
        regex: re.Pattern[str] | None = None
        if oracle:
            try:
                regex = re.compile(oracle, re.IGNORECASE)
            except re.error:
                continue  # an uncompilable avenue regex credits nothing
        out.append(
            (avenue.get("label", "avenue"), _search_and(regex, card_type), regex)
        )
    return out


def _search_and(
    regex: re.Pattern[str] | None, card_type: str
) -> Callable[[dict], bool]:
    """A card serves the avenue only if it satisfies BOTH the avenue's oracle
    regex and its card_type substring (mirrors how the card_search FIND ANDs
    them)."""

    def predicate(card: dict) -> bool:
        oracle_ok = (
            regex is None or regex.search(get_oracle_text(card) or "") is not None
        )
        # Transform-aware: match card_type against the FRONT face (what you play),
        # so a transform DFC's back-face type can't credit it.
        type_line = classifying_type_line(card).lower()
        type_ok = not card_type or card_type in type_line
        return oracle_ok and type_ok

    return predicate


def _color_widening(card: dict, widening_base: str | None) -> int:
    """Count of NEW colors a candidate second commander adds to the deck's
    current identity (ADR-0019). ``0`` when ``widening_base`` is None."""
    if widening_base is None:
        return 0
    return len(set(card.get("color_identity") or []) - set(widening_base))


def _prominence(label: str, focus_sets: Mapping[str, set] | None) -> float:
    if not focus_sets:
        return _PROM_DEFAULT
    for tier in ("viable", "emerging", "stranded"):
        if label in focus_sets.get(tier, ()):
            return _PROM[tier]
    return _PROM_DEFAULT


def _structural_floor(card: dict) -> dict:
    """The out-of-synergy quality axis: a card can be load-bearing (fixing, ramp,
    tutor, finisher) while serving few THEME lanes. The cut side reads this so a
    premium dork like Birds of Paradise isn't trimmed as "low synergy"."""
    produced = card.get("produced_mana") or []
    colors = {c for c in produced if c in "WUBRG"}
    oracle = (get_oracle_text(card) or "").lower()
    return {
        "is_fixing": len(colors) >= 2,
        "is_ramp": is_ramp(card),
        "is_tutor": "search your library" in oracle,
        "cmc_bomb": (card.get("cmc") or 0) >= 6.0,
    }


def _synergy_score(
    hits: Sequence[tuple[str, re.Pattern[str] | None]],
    clause_list: Sequence[str],
    focus_sets: Mapping[str, set] | None,
    deck_tribes: frozenset[str] | None,
) -> tuple[float, list[dict]]:
    """Depth-over-breadth synergy: cluster served lanes by the oracle clause they
    matched (one property = one credit), weight payoff > enabler > structural,
    scale by deck prominence, and discount a payoff gated on a tribe the deck
    lacks. Returns (score, per-cluster readout)."""
    # Attribute each hit to the clause(s) its oracle matched; lanes that matched
    # only structurally (type/keyword/cmc) go to a structural bucket.
    clause_labels: dict[int, set[str]] = {}
    struct_labels: set[str] = set()
    for label, pat in hits:
        matched = (
            [i for i, cl in enumerate(clause_list) if pat.search(cl)]
            if pat is not None
            else []
        )
        if matched:
            for i in matched:
                clause_labels.setdefault(i, set()).add(label)
        else:
            struct_labels.add(label)

    # Merge oracle clusters that serve the IDENTICAL label-set (the same mechanic
    # split across two lines, e.g. "Equipped creature gets…" + "Equip {3}"); keep
    # the constituent clause indices so the tribal-gate discount can read the text.
    merged: dict[frozenset[str], tuple[str, set[str], list[int]]] = {}
    for i, labels in clause_labels.items():
        key = frozenset(labels)
        role = _clause_role(clause_list[i])
        prev = merged.get(key)
        merged[key] = (
            (_stronger(prev[0], role), prev[1] | labels, [*prev[2], i])
            if prev
            else (role, labels, [i])
        )

    score = 0.0
    readout: list[dict] = []
    for role, labels, idxs in merged.values():
        prom = max(
            (_prominence(label, focus_sets) for label in labels),
            default=_PROM_DEFAULT,
        )
        weight = _ROLE_WEIGHT[role] * prom
        if role == "payoff":
            # A dead tribal gate (Lizard payoff, no Lizards) discounts the cluster.
            weight *= min(_gate_penalty(clause_list[i], deck_tribes) for i in idxs)
        weight = round(weight, 3)
        score += weight
        readout.append({"role": role, "weight": weight, "lanes": sorted(labels)})
    for label in struct_labels:
        weight = round(_ROLE_WEIGHT["structural"] * _prominence(label, focus_sets), 3)
        score += weight
        readout.append({"role": "structural", "weight": weight, "lanes": [label]})
    return round(score, 3), readout


def score_candidate(
    card: dict,
    *,
    active_signals: list,
    avenues: Sequence[dict] = (),
    widening_base: str | None = None,
    focus_sets: Mapping[str, set] | None = None,
    deck_tribes: frozenset[str] | None = None,
    _avenue_preds: list[tuple[str, Callable[[dict], bool], re.Pattern[str] | None]]
    | None = None,
    _signal_specs: list | None = None,
) -> dict:
    """Return the multi-axis readout for one candidate.

    ``focus_sets`` is the deck's avenue prominence — ``{"viable", "emerging",
    "stranded"}`` sets of labels — which makes ``synergy_score`` deck-relative.
    When omitted, every lane gets the neutral default weight, so synergy_score
    still corrects the breadth bias (payoff > enabler) without deck context.

    ``widening_base`` (the deck's color identity) is set ONLY on the partner
    avenue: it adds the ``color_widening`` axis (ADR-0019), 0 everywhere else.

    ``_avenue_preds`` / ``_signal_specs`` are an internal fast path built once per
    ranking; when omitted they are derived here, so behavior is unchanged."""
    oracle = get_oracle_text(card) or ""
    clause_list = clauses(oracle)

    specs = (
        _signal_specs
        if _signal_specs is not None
        else [spec_for(s) for s in active_signals]
    )
    hits: list[tuple[str, re.Pattern[str] | None]] = []
    for spec in specs:
        if spec is not None and spec.serve.matches(card):
            hits.append((spec.label, spec.serve.oracle))
    preds = _avenue_preds if _avenue_preds is not None else _avenue_predicates(avenues)
    for label, predicate, oracle_re in preds:
        if predicate(card):
            hits.append((label, oracle_re))

    seen: set[str] = set()
    served = [label for label, _ in hits if not (label in seen or seen.add(label))]
    synergy_score, clusters = _synergy_score(hits, clause_list, focus_sets, deck_tribes)

    return {
        "synergy_fit": len(served),
        "synergy_score": synergy_score,
        "served": served,
        "clusters": clusters,
        "structural_floor": _structural_floor(card),
        "cmc": card.get("cmc") or 0.0,
        "price": extract_price(card),
        "roles": sorted(role_of(card)),
        "color_widening": _color_widening(card, widening_base),
    }


def rank_candidates(
    cards: list[dict],
    *,
    active_signals: list,
    avenues: Sequence[dict] = (),
    widening_base: str | None = None,
    focus_sets: Mapping[str, set] | None = None,
    deck_tribes: frozenset[str] | None = None,
    rank_by: str = "score",
) -> list[dict]:
    """Score and sort candidates: synergy desc, then price asc (no-listing last),
    then cmc asc.

    ``rank_by="score"`` (default) sorts on ``synergy_score`` — the depth measure
    that fixes the breadth bias so a box-ticker grazing many lanes no longer
    outranks the deck's real payoffs. ``rank_by="fit"`` sorts on the raw
    ``synergy_fit`` count — the FOCUSED-avenue path's deliberate "serves N of your
    M focused lanes" semantics, where the user has hand-picked the lanes and a
    card serving more of them should win (clustering would wrongly collapse two
    effects the user chose as distinct). On the partner avenue (``widening_base``
    set) color widening leads the sort (ADR-0019)."""
    synergy_key = "synergy_fit" if rank_by == "fit" else "synergy_score"
    avenue_preds = _avenue_predicates(avenues)
    signal_specs = [spec_for(signal) for signal in active_signals]
    scored = [
        {
            "card": c,
            "score": score_candidate(
                c,
                active_signals=active_signals,
                avenues=avenues,
                widening_base=widening_base,
                focus_sets=focus_sets,
                deck_tribes=deck_tribes,
                _avenue_preds=avenue_preds,
                _signal_specs=signal_specs,
            ),
        }
        for c in cards
    ]
    scored.sort(
        key=lambda r: (
            -r["score"]["color_widening"],
            -r["score"][synergy_key],
            r["score"]["price"] if r["score"]["price"] is not None else math.inf,
            r["score"]["cmc"],
        )
    )
    return scored
