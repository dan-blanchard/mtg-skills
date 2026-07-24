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
token makers, an aristocrats deck rewards death payoffs. Two anti-gaming reads
on top (2026-07-16 discovery study): same-role cluster stacks decay
geometrically (a four-payoff text wall isn't 4x one payoff) and every cluster
earns a prominence-weighted breadth credit (one clause the deck wants for seven
reasons beats seven clauses it wants for one each). Premium fixing / bombs
score low on synergy BY DESIGN and are surfaced on the separate
``structural_floor`` axis (so the tuner can protect them on the cut side without
faking synergy).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence

from mtg_utils._deck_forge._ir_lookup import ir_for
from mtg_utils._deck_forge.budgets import role_of
from mtg_utils._deck_forge.pair_reads import PairContext, pair_score
from mtg_utils._deck_forge.rate import RateIndex, rate_for
from mtg_utils._deck_forge.signal_specs import serve_from_dict, spec_for
from mtg_utils._deck_forge.signals import clauses
from mtg_utils.card_classify import (
    classifying_type_line,
    extract_price,
    get_oracle_text,
    is_ramp,
    type_line_has,
)
from mtg_utils.card_ir import Ability, Card, Effect, Filter

# Cluster role weights: a reactive payoff clause is worth more than a bare
# generative/fodder action, which beats mere type/keyword membership.
_ROLE_WEIGHT = {"payoff": 3.0, "enabler": 1.0, "structural": 0.5}
_ROLE_RANK = {"payoff": 2, "enabler": 1, "structural": 0}

# Same-role stacking decay: the i-th cluster of a role (sorted by weight desc)
# contributes x0.35^i. A card fills ONE deck slot, so its best property defines
# its job — the linear sum let text walls win discovery (every clause of a
# four-ability value engine read role=payoff and the stack outranked the
# deck's on-plan staples; 2026-07-16 EDHREC study, recall@100 4.3%→6.2% with
# this + the breadth credit below).
_STACK_DECAY = 0.35
# Lane-breadth credit: one physical property the deck wants for K distinct
# reasons beats a property wanted for one. Each lane beyond the cluster's best
# adds 0.25 x that lane's own prominence (deck-relative: grazing K stranded
# lanes earns a fraction of hitting K viable ones).
_BREADTH_CREDIT = 0.25

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


def _clause_role_regex(clause: str) -> str:
    """The legacy oracle-clause role classifier — the ``ir is None`` fallback."""
    if _TRIGGER_RE.search(clause) and _REWARD_RE.search(clause):
        return "payoff"
    if _ACTIVATED_RE.search(clause) and _STRONG_REWARD_RE.search(clause):
        return "payoff"
    if _STATIC_PAYOFF_RE.search(clause):
        return "payoff"
    return "enabler"


# ── Card IR role classification (ADR-0027) ────────────────────────────────────
# The same three payoff conditions the regex tiers above encode, read off the
# candidate's structured abilities instead of its oracle text. The reward
# CATEGORY sets mirror the regex reward sets verbatim (rules-anchored: destroy =
# CR 701.8a board removal, draw = card advantage, a creature token is a
# GENERATIVE enabler not a reward per CR 111.1 — so make_token is excluded except
# the artifact-token "create a Treasure/Clue/…" form the regex also rewards).

# Broad reward set off a TRIGGER (the trigger already proves reactive value), the
# structured mirror of ``_REWARD_RE``.
_TRIGGER_REWARD_CATS = frozenset(
    {
        "draw",
        "damage",
        "gain_life",
        "lose_life",
        "destroy",
        "exile",
        "reanimate",
        "bounce",
        "place_counter",
    }
)
# Narrow board-impacting set off an ACTIVATED ability (a self-pump activation is
# NOT a payoff), the structured mirror of ``_STRONG_REWARD_RE`` — bare counters
# excluded by leaving ``place_counter`` out.
_ACTIVATED_REWARD_CATS = frozenset({"damage", "lose_life", "draw", "destroy", "exile"})
# Artifact-token kinds the regex rewards ("create a Treasure/Blood/Clue/Food/Gold")
# — a make_token whose subject is one of these is value, not creature fodder.
_REWARD_TOKEN_SUBTYPES = frozenset({"Treasure", "Blood", "Clue", "Food", "Gold"})
# Static anthem/grant effect categories (the buff a "creatures you control get …"
# line projects to), the structured mirror of ``_STATIC_PAYOFF_RE``.
_STATIC_ANTHEM_CATS = frozenset({"pump", "grant_keyword", "base_pt_set"})


def _is_reward_token(e: Effect) -> bool:
    """A make_token of a value artifact token (Treasure/Clue/…), the structured
    mirror of the regex's "create … treasure/blood/clue/food/gold" reward."""
    sub = e.subject
    return (
        e.category == "make_token"
        and isinstance(sub, Filter)
        and bool(set(sub.subtypes) & _REWARD_TOKEN_SUBTYPES)
    )


def _your_creature_buff(e: Effect) -> bool:
    """A static buff/grant over YOUR creatures (controller 'you', Creature in the
    filter) OR a count/multiply over your own board — the structured "creatures
    you control get …" / "for each … you control" anthem (CR 604.3 board count)."""
    sub = e.subject
    if (
        e.category in _STATIC_ANTHEM_CATS
        and isinstance(sub, Filter)
        and sub.controller == "you"
        and "Creature" in sub.card_types
    ):
        return True
    if e.category == "board_count":
        return True
    amt = e.amount
    return (
        amt is not None
        and amt.op in ("count", "multiply")
        and isinstance(amt.subject, Filter)
        and amt.subject.controller == "you"
    )


def _ability_is_payoff(ab: Ability) -> bool:
    """Does this IR ability reward the deck — the structured mirror of the three
    ``_clause_role_regex`` payoff tiers (triggered reward / activated strong reward
    / static anthem).

    The static-anthem tier (``_your_creature_buff``) is checked for EVERY ability
    kind, because the regex it mirrors (``_STATIC_PAYOFF_RE``) is clause-based and
    fires regardless of the surrounding ability: a planeswalker ``+1: creatures
    you control get +1/+0`` (Sorin) and a one-shot ``Creatures you control get
    +2/+2`` (Overrun) are both anthem payoffs, not just static enchantments."""
    if any(_your_creature_buff(e) for e in ab.effects):
        return True
    if ab.kind == "triggered":
        return any(
            e.category in _TRIGGER_REWARD_CATS or _is_reward_token(e)
            for e in ab.effects
        )
    if ab.kind == "activated":
        return any(e.category in _ACTIVATED_REWARD_CATS for e in ab.effects)
    return False


def _norm_raw(text: str) -> str:
    """Normalize a clause / IR ``raw`` for cross-matching: lowercase, fold the
    self-reference (``~`` and a leading card name both collapse), drop reminder
    text + punctuation, collapse whitespace. The IR raw replaces the card name
    with ``~`` while ``clauses(oracle)`` keeps it, so both sides fold to ``~``."""
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    text = text.replace("~", " ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def _clause_overlaps(clause_norm: str, raw_norm: str) -> bool:
    """Whether a normalized oracle clause and an IR ``raw`` describe the same span:
    one contains the other, or they share a strong content-word overlap (the IR
    sometimes merges two oracle sentences into one ability ``raw``, and drops the
    leading self-name, so an exact equality test is too strict)."""
    if not clause_norm or not raw_norm:
        return False
    if clause_norm in raw_norm or raw_norm in clause_norm:
        return True
    cw = set(clause_norm.split())
    rw = set(raw_norm.split())
    if not cw or not rw:
        return False
    overlap = len(cw & rw)
    return overlap >= 3 and overlap >= min(len(cw), len(rw)) * 0.6


def _ir_payoff_raws(ir: Card) -> list[str]:
    """Normalized effect-``raw`` strings of every PAYOFF ability of the card — the
    spans a matched oracle clause is credited as a payoff for."""
    out: list[str] = []
    for ab in ir.all_abilities():
        if not _ability_is_payoff(ab):
            continue
        for e in ab.effects:
            if e.raw:
                out.append(_norm_raw(e.raw))
    return out


def _ir_gate_subtypes(ir: Card) -> list[tuple[str, frozenset[str]]]:
    """(normalized trigger/effect raw, gating creature subtypes) for every TRIGGERED
    payoff whose trigger narrows to a creature subtype — the structured mirror of
    ``_TRIBAL_GATE_RE``. A "whenever you attack with one or more Lizards" payoff
    carries ``trigger.subject.subtypes == ('Lizard',)``, so the gate is a field
    read, not a regex over the clause."""
    out: list[tuple[str, frozenset[str]]] = []
    for ab in ir.all_abilities():
        if ab.kind != "triggered" or ab.trigger is None:
            continue
        sub = ab.trigger.subject
        if not (isinstance(sub, Filter) and sub.subtypes):
            continue
        tribes = frozenset(s.lower() for s in sub.subtypes)
        for e in ab.effects:
            if e.raw:
                out.append((_norm_raw(e.raw), tribes))
    return out


def _clause_role(clause: str, ir: Card | None, payoff_raws: list[str]) -> str:
    """The cluster role for one oracle clause. With the candidate's IR present, a
    clause is a payoff iff it aligns to one of the card's payoff-ability raws
    (``payoff_raws``); else enabler. Without IR, the legacy regex tiers."""
    if ir is None:
        return _clause_role_regex(clause)
    clause_norm = _norm_raw(clause)
    if any(_clause_overlaps(clause_norm, raw) for raw in payoff_raws):
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


def _gate_penalty_regex(clause: str, deck_tribes: frozenset[str]) -> float:
    """The legacy clause-regex gate detector — the ``ir is None`` fallback."""
    from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES

    for m in _TRIBAL_GATE_RE.finditer(clause):
        word = m.group(1).lower()
        singular = word.removesuffix("s")
        for cand in (word, singular):
            if cand in CREATURE_SUBTYPES:
                return 1.0 if cand in deck_tribes else _GATE_PENALTY
    return 1.0


def _gate_penalty(
    clause: str,
    deck_tribes: frozenset[str] | None,
    ir: Card | None,
    gate_subtypes: list[tuple[str, frozenset[str]]],
) -> float:
    """1.0 unless the clause gates on a creature subtype the deck lacks (then
    ``_GATE_PENALTY``). No penalty without deck context (``deck_tribes`` falsy).

    With the candidate's IR present, the gate's tribe rides in the trigger's
    ``subject.subtypes`` (``gate_subtypes``) — a structured field read, not a
    clause regex; without IR, the legacy ``_TRIBAL_GATE_RE``."""
    if not deck_tribes:
        return 1.0
    if ir is None:
        return _gate_penalty_regex(clause, deck_tribes)
    clause_norm = _norm_raw(clause)
    for raw_norm, tribes in gate_subtypes:
        if _clause_overlaps(clause_norm, raw_norm):
            return 1.0 if tribes & deck_tribes else _GATE_PENALTY
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
      - bare ``search`` fragment (legacy): oracle regex AND card_type token,
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
    regex and its card_type token (mirrors how the card_search FIND ANDs
    them)."""

    def predicate(card: dict) -> bool:
        oracle_ok = (
            regex is None or regex.search(get_oracle_text(card) or "") is not None
        )
        # Transform-aware: match card_type against the FRONT face (what you play),
        # so a transform DFC's back-face type can't credit it. Word-boundary
        # token, never a substring ('rat' must not credit a Pirate).
        type_line = classifying_type_line(card).lower()
        type_ok = not card_type or type_line_has(type_line, card_type)
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
    ir: Card | None,
) -> tuple[float, list[dict]]:
    """Depth-over-breadth synergy: cluster served lanes by the oracle clause they
    matched (one property = one credit), weight payoff > enabler > structural,
    scale by deck prominence, and discount a payoff gated on a tribe the deck
    lacks. Same-role cluster stacks decay geometrically (``_STACK_DECAY``) so a
    text wall of payoff clauses can't sum linearly past the deck's on-plan
    staples, and each cluster earns a prominence-weighted lane-breadth credit
    (``_BREADTH_CREDIT``) so one property the deck wants for many reasons
    outearns a property wanted for one. Returns (score, per-cluster readout);
    readout rows carry each cluster's actual contribution and sum to the score.

    Cluster ROLE and the tribal-gate discount read the candidate's Card IR
    (``ir``) when present — a clause is a payoff iff it aligns to a payoff
    ability, the gate iff a trigger narrows to a creature subtype — and degrade to
    the legacy oracle-clause regexes when ``ir is None`` (ADR-0027)."""
    payoff_raws = _ir_payoff_raws(ir) if ir is not None else []
    gate_subtypes = _ir_gate_subtypes(ir) if ir is not None else []
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
        role = _clause_role(clause_list[i], ir, payoff_raws)
        prev = merged.get(key)
        merged[key] = (
            (_stronger(prev[0], role), prev[1] | labels, [*prev[2], i])
            if prev
            else (role, labels, [i])
        )

    # Per-cluster (role, base weight, breadth credit, labels). Base = role
    # weight x the cluster's BEST lane prominence; breadth = _BREADTH_CREDIT
    # x Σ prominence of every extra lane. The tribal-gate discount scales the
    # WHOLE cluster contribution (base AND breadth) — the extra lanes matched
    # the same gated clause, so they are equally dead (verified-review F2).
    entries: list[tuple[str, float, float, list[str]]] = []
    for role, labels, idxs in merged.values():
        proms = sorted(
            (_prominence(label, focus_sets) for label in labels), reverse=True
        )
        weight = _ROLE_WEIGHT[role] * (proms[0] if proms else _PROM_DEFAULT)
        breadth = _BREADTH_CREDIT * sum(proms[1:])
        if role == "payoff":
            # A dead tribal gate (Lizard payoff, no Lizards) discounts the cluster.
            gate = min(
                _gate_penalty(clause_list[i], deck_tribes, ir, gate_subtypes)
                for i in idxs
            )
            weight *= gate
            breadth *= gate
        entries.append((role, weight, breadth, sorted(labels)))
    if struct_labels:
        # ALL structural serves are one physical property (the type line /
        # keyword array), so they form ONE cluster earning breadth — never a
        # decayed stack of per-label rows (verified-review F3: a changeling
        # serving three viable tribal lanes is one body, not three cards).
        proms = sorted(
            (_prominence(label, focus_sets) for label in struct_labels),
            reverse=True,
        )
        entries.append(
            (
                "structural",
                _ROLE_WEIGHT["structural"] * proms[0],
                _BREADTH_CREDIT * sum(proms[1:]),
                sorted(struct_labels),
            )
        )

    # Same-role stacks decay geometrically (sorted desc); the breadth credit
    # rides undecayed on its own cluster. Each readout row's ``weight`` is the
    # cluster's ACTUAL contribution (decayed + breadth), so rows sum to the
    # score — the readout stays a truthful transparency surface.
    by_role: dict[str, list[tuple[str, float, float, list[str]]]] = {}
    for entry in entries:
        by_role.setdefault(entry[0], []).append(entry)
    score = 0.0
    readout: list[dict] = []
    for group in by_role.values():
        group.sort(key=lambda e: -e[1])
        for i, (role, base, breadth, labels) in enumerate(group):
            weight = round(base * (_STACK_DECAY**i) + breadth, 3)
            score += weight
            readout.append({"role": role, "weight": weight, "lanes": labels})
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
    _ir_resolved: tuple[Card | None] | None = None,
    rate_index: RateIndex | None = None,
    pair_ctx: PairContext | None = None,
) -> dict:
    """Return the multi-axis readout for one candidate.

    ``focus_sets`` is the deck's avenue prominence — ``{"viable", "emerging",
    "stranded"}`` sets of labels — which makes ``synergy_score`` deck-relative.
    When omitted, every lane gets the neutral default weight, so synergy_score
    still corrects the breadth bias (payoff > enabler) without deck context.

    ``widening_base`` (the deck's color identity) is set ONLY on the partner
    avenue: it adds the ``color_widening`` axis (ADR-0019), 0 everywhere else.

    ``_avenue_preds`` / ``_signal_specs`` are an internal fast path built once per
    ranking; when omitted they are derived here, so behavior is unchanged.
    ``_ir_resolved`` is the candidate's Card IR (boxed in a 1-tuple so a resolved
    ``None`` is distinct from "not yet looked up"); when omitted it is resolved
    here by ``oracle_id`` (ADR-0027), degrading to the legacy regex when absent."""
    oracle = get_oracle_text(card) or ""
    clause_list = clauses(oracle)
    ir = _ir_resolved[0] if _ir_resolved is not None else ir_for(card)

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
    synergy_score, clusters = _synergy_score(
        hits, clause_list, focus_sets, deck_tribes, ir
    )
    _pair = pair_score(card, pair_ctx)

    return {
        "synergy_fit": len(served),
        "synergy_score": synergy_score,
        # Rate (ADR-0042): the card's cost-effectiveness percentile within
        # its peer class — 0.5 (neutral) without an index or a measurable
        # effect, so degraded/no-bulk deployments rank exactly as before.
        "rate": rate_for(card, rate_index),
        # Pair reads (ADR-0042): summed weights of the matched ledger rows
        # (candidate ident-pattern x commander/density anchor) — 0.0 inert
        # without a context. Additive, never Rate-multiplied.
        "pair_score": _pair[0],
        "pairs": _pair[1],
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
    rate_index: RateIndex | None = None,
    pair_ctx: PairContext | None = None,
    row_class_permutation: bool = False,
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
                _ir_resolved=(ir_for(c),),
                rate_index=rate_index,
                pair_ctx=pair_ctx,
            ),
        }
        for c in cards
    ]

    # Rate is a READOUT ONLY — the v1 multiplier is structurally disarmed
    # (Dan, 2026-07-24). ADR-0042's four-way eval falsified the percentile
    # multiplier in every variant, and the "ships NEUTRAL" outcome left it
    # armed behind a non-None rate_index; the Rate-v2 gate-(b) review
    # (cycle 4) verified that landmine and CI now asserts the sort is
    # invariant to any rate_index. The FOCUSED fit path stays a raw count —
    # the user hand-picked those lanes.
    def _depth(r: dict) -> float:
        if synergy_key == "synergy_fit":
            return r["score"]["synergy_fit"]
        # Depth: synergy + pair_score — the pair term is additive (the row
        # priced the interaction); Rate never touches the sort.
        return r["score"]["synergy_score"] + r["score"]["pair_score"]

    scored.sort(
        key=lambda r: (
            -r["score"]["color_widening"],
            -_depth(r),
            r["score"]["price"] if r["score"]["price"] is not None else math.inf,
            r["score"]["cmc"],
            # Deterministic final key (2026-07-24): without it, ties fell
            # through to stable-sort INPUT order — the staples avenue's
            # dict-merge order leaked into the ranking (gate-b cycle-5
            # finding). Tie regions are large on the fit path (integer
            # depth) and among no-listing candidates (price=inf).
            r["card"].get("name") or "",
        )
    )
    if row_class_permutation:
        # Rate v2 S1 (design note 2.6, approved): default-off until the
        # slice measurement accepts; flipped by its own protocol event.
        scored = apply_row_class_permutation(scored)
    return scored


def _default_rider_fn(r: dict) -> bool:
    """Cantrip rider on the OWNER class's attributed tree (2.6 D2 key a):
    the card carries a draw-shaped ident attributed to a unit on the same
    tree as an attributed row-matching ident. Unattributed -> no rider
    (the conservative epistemic default, same rule as the discounts)."""
    from mtg_utils._deck_forge.ident_provenance import unit_idents_for

    pairs = r["score"].get("pairs") or []
    if not pairs:
        return False
    try:
        attr = unit_idents_for(r["card"])
    except (KeyError, ValueError, TypeError):  # no IR — no evidence, no rider
        return False
    rider_keys = ("cantrip|", "card_draw_engine|")
    match_trees = {
        ti
        for (ti, _ui), ids in attr.items()
        for i in ids
        if "|" in i  # any attributed ident on a matched card's tree
    }
    if not match_trees:
        return False
    return any(
        i.startswith(rider_keys)
        for (ti, _ui), ids in attr.items()
        if ti in match_trees
        for i in ids
    )


def apply_row_class_permutation(
    scored: list[dict],
    *,
    rider_fn: Callable[[dict], bool] | None = None,
) -> list[dict]:
    """The S1 slot permutation (2.6 D2): within each (color_widening,
    0.25-depth-bucket) stratum, each row class reorders the slots of the
    cards it OWNS — one parallel pass against the pre-pass snapshot.

    Ownership: a card's owner class is the lexicographically FIRST
    pair_id among its matched rows; other classes treat it as fixed
    (the cycle-6 anti-chaining fix — a shared-member card can no longer
    ferry order changes between disjoint classes). Keys inside a class:
    cantrip rider first, then cmc ascending, then name. Zero-class
    candidates never move (position-fixity invariant); candidates with
    no shared class never reorder (anti-chaining invariant) — both are
    CI-asserted properties of this construction, not policies.
    """
    import math as _math

    rider = rider_fn or _default_rider_fn
    out = list(scored)

    def stratum(r: dict) -> tuple:
        depth = r["score"]["synergy_score"] + r["score"]["pair_score"]
        return (r["score"]["color_widening"], _math.floor(depth / 0.25))

    def owner(r: dict) -> str | None:
        pids = sorted(p["pair"] for p in (r["score"].get("pairs") or []))
        return pids[0] if pids else None

    groups: dict[tuple, dict[str, list[int]]] = {}
    for idx, r in enumerate(out):
        o = owner(r)
        if o is None:
            continue
        groups.setdefault(stratum(r), {}).setdefault(o, []).append(idx)

    for classes in groups.values():
        for slots in classes.values():
            if len(slots) < 2:
                continue
            members = [out[i] for i in slots]
            members.sort(
                key=lambda r: (
                    not rider(r),
                    r["score"]["cmc"],
                    r["card"].get("name") or "",
                )
            )
            for slot, member in zip(slots, members, strict=True):
                out[slot] = member
    return out
