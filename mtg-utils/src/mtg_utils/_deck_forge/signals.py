"""Deterministic signal extraction — the discovery-engine keystone.

A ``Signal`` is a precisely-scoped fact pulled from a card's oracle text: what it
cares about / triggers on, *whose* resource it concerns (scope), and — when the
clause names one — the *subject* it cares about (a creature subtype). Scope and
subject are part of the signal's identity, which is how we avoid overgeneralization:
a card that benefits from an opponent's graveyard yields ``graveyard_matters`` scoped
``opponents`` (never a generic one that would justify self-mill), and a Goblin lord
yields ``type_matters`` with ``subject="Goblin"`` (never collapsed into a generic
"creatures matter").

Production extraction is structural (ADR-0035): ``extract_signals`` resolves
the card's per-face concept trees (``_ir_lookup.trees_for``), runs
``crosswalk_signals.extract_crosswalk_signals`` over each, unions by
``(key, scope, subject)``, and applies ONE merge-level
membership floor across all faces. The shared value type and text primitives live
in ``signal_base`` / ``text_reads`` / ``membership_floor``.

``coverage_gate`` reports the extractor's own blind spots (zero-signal / only-generic
/ scope-uncertain / partial-parse) — the "queue it, don't silently drop it" check
(ADR-0009) tests run over extractor output to find cards needing agent scoping.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import (
    CREATURE_SUBTYPES,
)
from mtg_utils._deck_forge.signal_base import (
    _GENERIC_KEYS,
    Signal,
    _clauses,
    _tinybones_scope,
    clauses,
)
from mtg_utils._deck_forge.text_reads import (
    _DISCARD_OUTLET_SWEEP_RE,
    _LURE_MATTERS_PLAN_MIRROR,
    _PLAY_FROM_TOP_FLOOR_MIRROR,
    _PLAY_FROM_TOP_MIRROR,
    _VOLTRON_EQUIP_RE,
    _voltron_double_strike_beater,
    _voltron_land_scaler,
    _voltron_self_heroic,
    _voltron_self_pump,
    _voltron_self_recurs,
    _voltron_self_unblockable,
)
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.card_ir import Card

# Public surface re-exported by this facade. Listed here so the re-export
# imports above are not pruned as "unused" — external consumers and tests still
# do `from mtg_utils._deck_forge.signals import <name>`.
__all__ = [
    "_VOLTRON_EQUIP_RE",
    "Signal",
    "_tinybones_scope",
    "_voltron_double_strike_beater",
    "_voltron_land_scaler",
    "_voltron_self_heroic",
    "_voltron_self_pump",
    "_voltron_self_recurs",
    "_voltron_self_unblockable",
    "clauses",
    "coverage_gate",
    "extract_signals",
    "producible_static_keys",
    "rank_deck_signals",
    "signal_keys",
    "tribal_payoff_subjects",
]


# ── The structural serving seam (ADR-0035) ────────────────────────────────────


def extract_signals(
    record: dict,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
) -> list[Signal]:
    """The production signal-extraction path: ``trees_for(record, bulk=record)``
    resolves the card's per-face concept trees, ``extract_crosswalk_signals``
    runs the structural lanes over EACH one (unioned by ``(key, scope,
    subject)``, never a merged multi-face tree — that would corrupt card-level
    reads like ``is_type`` / cmc that only make sense per-face), and the
    card-type / cares-about MEMBERSHIP floor (``apply_membership_floor``) runs
    ONCE more, over every face together, when ``include_membership`` (see that
    function's docstring for the per-face-isolation gap it closes).

    A card with no ``oracle_id`` / no phase record / no committed mirror schema
    (``trees_for`` returns ``()``) degrades to an empty signal list, not a
    crash — and never to text-guessing. Note: ADR-0025 folded-object references
    (a ventured dungeon / meld result / the Ring) do not currently extend a
    commander's signals — the fold only ever ran through the retired engines
    (a documented regression, tracked for adjudication)."""
    from mtg_utils._deck_forge._ir_lookup import trees_for
    from mtg_utils._deck_forge.crosswalk_signals import (
        apply_membership_floor,
        extract_crosswalk_signals,
    )

    # ADR-0038 W2c: `record` is already the bulk record — thread it as `bulk`
    # so `trees_for` can synthesize text-only trees for phase-missing faces
    # (aftermath second halves, one split gap) off the bulk face text.
    trees = trees_for(record, bulk=record)
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(sig: Signal) -> None:
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(sig)

    keywords = frozenset(
        k for k in (record.get("keywords") or []) if isinstance(k, str)
    )
    for tree in trees:
        for sig in extract_crosswalk_signals(
            tree,
            keywords=keywords,
            vocab=vocab,
            all_trees=trees,
        ):
            _add(sig)
    if include_membership:
        apply_membership_floor(trees, record, out, _add, vocab=vocab)
    # ADR-0027 spell-copy → spellcast cross-open reconciliation: the regex
    # `extract_signals` path UNCONDITIONALLY cross-opens spellcast_matters (low) from
    # any spell_copy_makers card (a spell-copier is a spellslinger wanting a dense I/S
    # base — the inline producer at _signals_regex). Now that BOTH spell_copy_makers
    # AND spellcast_matters are migrated, that inline producer's output is stripped from
    # the regex set (line 150), so the hybrid re-supplies it from the final merged set:
    # fire whenever spell_copy_makers ends up in `out` (the regex `spell-copy` keyword
    # OR the IR provides it) and spellcast not already present. The `spellcast not in
    # out` guard is the dedup; an earlier `spell_copy not in regex_signals` gate broke
    # once spellcast migrated (storm/replicate carry the keyword in the regex set, so it
    # wrongly blocked the re-supply for them). Low confidence, you-scope.
    out_keys = {s.key for s in out}
    if "spell_copy_makers" in out_keys and "spellcast_matters" not in out_keys:
        out.append(
            Signal("spellcast_matters", "you", "", "", record.get("name", ""), "low")
        )
    # ADR-0027 β gain_control cross-open reconciliation. The regex include_membership
    # cross-open ties two LOW-confidence theft-archetype tells to gain_control: (1) it
    # opens the wants_theft sibling when a body has gain_control OR rewards permanents
    # "you control but DON'T OWN"; (2) it opens a LOW gain_control on a theft-PAYOFF
    # commander that only says "don't own" with no structural form (Gonti Canny, Tasha,
    # Vaan, Don Andres, Arvinox, Nita, Laughing Jasper Flint, Nathan Drake, Thieving
    # Amalgam / Varmint, Tinybones Bauble Burglar, Sentinel of Lost Lore, Staff of Eden
    # — 13 commanders). gain_control now migrates, so the hybrid DROPS every regex
    # gain_control (the LOW cross-open included) and the regex cross-open's
    # `gain_control in keys_now` test sees the deleted producer's absence — re-run both
    # tells against
    # the MERGED key set, gated on include_membership (the regex cross-open's gate).
    # wants_theft IS migrated (ADR-0034 split), so the hybrid drops the regex firing;
    # re-open it against the merged set — incl. a structural-theft commander (Memnarch,
    # Dragonlord Silumgar, Nihiloor, Empress Galina) whose gain_control comes only from
    # the IR, not the deleted regex. Re-add the LOW
    # gain_control for the 13 "don't own" payoff commanders the hybrid dropped (no
    # structural form). Matches the spell_copy reconciliation pattern above. CR 800.4a.
    if include_membership:
        gc_now = "gain_control" in out_keys
        dont_own = re.search(
            r"you (?:cast|control|own)?[^.]{0,25}?(?:do not|don't) own",
            get_oracle_text(record) or "",
            re.IGNORECASE,
        )
        # _matters sweep (ADR-0034): the theft split. The HIGH steal-and-cast DOERS
        # ride the IR kept mirror as theft_makers; the LOW gain_control / don't-own
        # cross-open — a steal commander that WANTS the theft package run — is
        # wants_theft. Both theft_makers and wants_theft migrate, so the hybrid drops
        # EVERY regex wants_theft. Re-run that cross-open condition against the MERGED
        # key set (gain_control in out_keys — from the IR arm or this reconciliation OR
        # dont_own) to restore the LOW wants_theft on the battlefield-steal + don't-own
        # commanders. Mirrors the regex producer at _signals_regex.py (`if gain_control
        # in keys_now or dont_own: add wants_theft LOW`).
        if (gc_now or dont_own) and "wants_theft" not in out_keys:
            out.append(
                Signal(
                    "wants_theft", "opponents", "", "", record.get("name", ""), "low"
                )
            )
        if dont_own and not gc_now:
            out.append(
                Signal("gain_control", "you", "", "", record.get("name", ""), "low")
            )
        # ADR-0027 topdeck_stack / topdeck_selection cross-open reconciliation. The
        # regex include_membership path cross-opens the sibling top-of-library lanes
        # from a play-from-top body (Gwenom, Glarb, Reality Chip curate their top to set
        # up what they play), gated on the byte-identical _PLAY_FROM_TOP_MIRROR /
        # _FLOOR_MIRROR — it adds a LOW topdeck_selection AND a LOW topdeck_stack. BOTH
        # now migrate (v28), so the hybrid DROPS both regex LOW cross-opens. Re-run the
        # EXACT gate against the reminder-stripped oracle and re-add each LOW key the
        # merged set lacks — mirroring the regex producer at _signals_regex.py (`if
        # play_from_top mirror: add topdeck_selection LOW; add topdeck_stack LOW`). Both
        # cross-opens were LOW so neither fed has_other_plan. CR 116.
        out_now = {s.key for s in out}
        if "topdeck_stack" not in out_now or "topdeck_selection" not in out_now:
            _pft_text = re.sub(r"\([^)]*\)", " ", get_oracle_text(record) or "")
            if any(
                _PLAY_FROM_TOP_MIRROR.search(cl)
                or _PLAY_FROM_TOP_FLOOR_MIRROR.search(cl)
                for cl in _clauses(_pft_text)
            ):
                if "topdeck_stack" not in out_now:
                    out.append(
                        Signal(
                            "topdeck_stack",
                            "you",
                            "",
                            "",
                            record.get("name", ""),
                            "low",
                        )
                    )
                if "topdeck_selection" not in out_now:
                    out.append(
                        Signal(
                            "topdeck_selection",
                            "you",
                            "",
                            "",
                            record.get("name", ""),
                            "low",
                        )
                    )
        # ADR-0027 graveyard scope/origin/zone (SIDECAR v29) — discard_outlet →
        # graveyard_matters cross-open reconciliation. The regex include_membership path
        # cross-opens graveyard_matters from a discard-OUTLET body (a loot / rummage /
        # discard-to-pay engine fills the graveyard, so the discarded cards become GY
        # fuel — Niambi reanimates, Mishra recurs artifacts), gated on the
        # byte-identical _DISCARD_OUTLET_SWEEP_RE (the EXACT deleted SWEEP producer,
        # per-clause). BOTH discard_outlet (v26) AND graveyard_matters (v29) now
        # migrate, so the hybrid DROPS every regex graveyard_matters — incl. this LOW
        # cross-open. The IR path re-supplies the genuine per-card graveyard hooks, but
        # a discard-outlet body that fills the GY without a structured recursion (a bare
        # loot, no "graveyard" word) carries no IR graveyard_matters, so re-run the
        # EXACT gate against the merged set and re-add the LOW key when the merged lacks
        # it — mirroring the regex producer at _signals_regex.py. The cross-open was LOW
        # so it never fed has_other_plan. CR 701.8a.
        out_now = {s.key for s in out}
        if "graveyard_matters" not in out_now:
            _gy_text = re.sub(r"\([^)]*\)", " ", get_oracle_text(record) or "")
            if any(_DISCARD_OUTLET_SWEEP_RE.search(cl) for cl in _clauses(_gy_text)):
                out.append(
                    Signal(
                        "graveyard_matters",
                        "you",
                        "",
                        "",
                        record.get("name", ""),
                        "low",
                    )
                )
        # ADR-0027 Cluster D blocked_matters cross-open reconciliation. The regex
        # include_membership path cross-opens blocked_matters from a LURE body (a
        # lure / must-be-blocked commander wants the punish-when-blocked payoffs —
        # Engulfing Slagwurm, Tolarian Entrancer), gated on lure_makers OR the
        # byte-identical _LURE_MATTERS_PLAN_MIRROR. BOTH lure_makers AND
        # blocked_matters now migrate (v36), so the hybrid DROPS the regex LOW
        # cross-open. lure_makers rides the IR (so it's in `out`), but the
        # cross-open's blocked_matters is filtered out as a migrated key — and a lure
        # commander that doesn't ITSELF carry a becomes-blocked trigger has no IR
        # blocked_matters. Re-run the EXACT gate (lure present in the merged set OR the
        # lure mirror) against the merged set and re-add the LOW key when the merged
        # lacks it — mirroring the regex producer at
        # _signals_regex.py. The cross-open was LOW so it never fed has_other_plan.
        # CR 509.1c.
        if "blocked_matters" not in out_now and (
            "lure_makers" in out_now
            or _LURE_MATTERS_PLAN_MIRROR.search(
                re.sub(r"\([^)]*\)", " ", get_oracle_text(record) or "")
            )
        ):
            out.append(
                Signal(
                    "blocked_matters",
                    "you",
                    "",
                    "",
                    record.get("name", ""),
                    "low",
                )
            )
    # ADR-0027 voltron migration (the LAST key): voltron_matters now comes from the IR
    # path (``extract_signals_ir``), which derives its own ``has_other_plan`` from the
    # IR signal lanes directly — so the regex-side reconciliation that re-silenced the
    # regex-path commander-damage tell (the old ``_VOLTRON_SILENCING_PLAN_KEYS`` cross-
    # check) is retired. The IR voltron set is self-consistent; no post-merge fix-up.
    return out


def _deck_signal_stats(
    records: Sequence[dict | None],
    commander_names: set[str],
) -> tuple[
    dict[tuple[str, str, str], int],
    set[tuple[str, str, str]],
    dict[tuple[str, str, str], Signal],
    dict[tuple[str, str, str], int],
]:
    """The shared per-card extraction loop backing ``rank_deck_signals`` and
    ``tribal_payoff_subjects``: for every distinct ``(key, scope, subject)``
    ident, its *support* (how many cards feed it), whether the COMMANDER is
    among those cards, the first ``Signal`` seen for it, and its
    HIGH-confidence non-commander support (the payoff-grade count — the
    membership floor's own-subtype signals are deliberately LOW and must
    never read as payoffs)."""
    support: dict[tuple[str, str, str], int] = {}
    from_commander: set[tuple[str, str, str]] = set()
    first: dict[tuple[str, str, str], Signal] = {}
    nc_high: dict[tuple[str, str, str], int] = {}
    for card in records:
        if not card:
            continue
        is_cmd = card.get("name") in commander_names
        # Membership signals come from the COMMANDER only (see rank_deck_signals);
        # a deployment with no card data degrades to empty signals, never to
        # text-guessing.
        sigs = extract_signals(card, include_membership=is_cmd)
        for sig in sigs:
            ident = (sig.key, sig.scope, sig.subject)
            support[ident] = support.get(ident, 0) + 1
            if is_cmd:
                from_commander.add(ident)
            elif sig.confidence == "high":
                nc_high[ident] = nc_high.get(ident, 0) + 1
            first.setdefault(ident, sig)
    return support, from_commander, first, nc_high


def rank_deck_signals(
    records: Sequence[dict | None],
    commander_names: set[str],
) -> list[Signal]:
    """Deck signals deduped by (key, scope, subject) and ranked by relevance.

    Membership signals (own-subtype tribal, voltron fallback) are taken from the
    COMMANDER only — otherwise every creature's race/stat-line floods the deck. A
    signal's *support* (how many cards feed it) drives the ranking. Kept ForgeState-free
    so both the deck-forge engine (``engine.ranked_deck_signals``) and the deterministic
    tuner share one ranking (ADR-0023).
"""
    support, from_commander, first, _nc_high = _deck_signal_stats(
        records, commander_names
    )
    return _ranked_from_stats(support, from_commander, first)


def _ranked_from_stats(
    support: dict[tuple[str, str, str], int],
    from_commander: set[tuple[str, str, str]],
    first: dict[tuple[str, str, str], Signal],
) -> list[Signal]:
    return sorted(
        first.values(),
        key=lambda s: (
            (s.key, s.scope, s.subject) in from_commander,
            support[(s.key, s.scope, s.subject)],
            s.confidence == "high",
        ),
        reverse=True,
    )


def _payoffs_from_stats(
    first: dict[tuple[str, str, str], Signal],
    nc_high: dict[tuple[str, str, str], int],
) -> frozenset[str]:
    subjects: set[str] = set()
    for ident in first:
        key, _scope, subject = ident
        if key != signal_keys.TYPE_MATTERS or not subject:
            continue
        # HIGH-confidence non-commander emissions only: the go-wide
        # membership floor emits own-subtype type_matters at LOW confidence
        # (Birds of Paradise → Bird) — membership, never a payoff.
        if nc_high.get(ident, 0) >= 1:
            subjects.add(subject)
    return frozenset(subjects)


def ranked_signals_and_payoffs(
    records: Sequence[dict | None],
    commander_names: set[str],
) -> tuple[list[Signal], frozenset[str]]:
    """``rank_deck_signals`` + ``tribal_payoff_subjects`` from ONE extraction
    pass. A tune needs both, and calling the two helpers separately ran the
    full per-card lane pass twice per deck (the tree build is memoized; the
    lane pass is not)."""
    support, from_commander, first, nc_high = _deck_signal_stats(
        records, commander_names
    )
    return (
        _ranked_from_stats(support, from_commander, first),
        _payoffs_from_stats(first, nc_high),
    )


def tribal_payoff_subjects(
    records: Sequence[dict | None],
    commander_names: set[str],
) -> frozenset[str]:
    """The tribal (``type_matters``) subjects with >=1 NON-COMMANDER card
    emitting the ident — a genuine payoff (ADR-0040 companion, task #101).

    ``_deck_signal_stats`` runs the 99 with ``include_membership=False``, so
    any tribal ident a non-commander card contributes is a real cares-about
    signal, never mere membership; a subject whose ONLY source is the
    commander's own emission (``support - (ident in from_commander)`` == 0)
    is membership only, not a payoff. Feeds ``metrics.focus``'s emerging-
    tribal gate: an *emerging* tribal avenue with no payoff subject is a
    changeling-inflated phantom (every changeling SERVES every tribe's
    avenue once ANY card opens it — see ``signal_specs._subject_spec``'s
    changeling fold — so depth alone over-credits a tribe nobody actually
    built toward), not a real budding theme."""
    _support, _from_commander, first, nc_high = _deck_signal_stats(
        records, commander_names
    )
    return _payoffs_from_stats(first, nc_high)


def grant_payloads_for(card: dict) -> tuple:
    """CARD's mass static-grant payloads (ADR-0040 §2, task #97) — the
    card-record facade over ``crosswalk_signals.extract_grant_payloads``,
    unioned across the card's per-face concept trees (the same per-face
    resolution ``extract_signals`` uses). Empty for a synthetic
    no-``oracle_id`` record or a card phase can't parse — the standard
    no-IR degradation."""
    from mtg_utils._deck_forge._ir_lookup import trees_for
    from mtg_utils._deck_forge.crosswalk_signals import extract_grant_payloads

    out: list = []
    for tree in trees_for(card) or ():
        out.extend(extract_grant_payloads(tree))
    return tuple(out)


# ── Coverage gate — the agent-augmentation (M3) hook ──────────────────────────
# Generic = {creatures_matter}: it fires on "creatures you control" (nearly every


_SELF_MARKER = re.compile(r"\byou\b|\byour\b", re.IGNORECASE)
_THIRD_PARTY_POSSESSIVE = re.compile(
    r"that player's|each opponent's|target opponent's|their (?:hand|graveyard|library)",
    re.IGNORECASE,
)


def _scope_uncertain(text: str) -> bool:
    """True if any clause mixes a self-marker AND a third-party possessive that the
    narrow Tinybones rule did NOT already resolve — the agent's territory."""
    for clause in _clauses(text):
        if (
            _SELF_MARKER.search(clause)
            and _THIRD_PARTY_POSSESSIVE.search(clause)
            and _tinybones_scope(clause) is None
        ):
            return True
    return False


def coverage_gate(
    card: dict, signals: list[Signal], ir: Card | None = None
) -> tuple[bool, str]:
    """Report a blind spot: (needs_agent, reason). reason ∈ {zero_signal,
    only_generic, low_confidence, scope_uncertain, partial_parse, ""}. Surfaces
    gaps for agent scoping instead of dropping them silently.

    ADR-0027 A4: when the card's Card IR is a PARTIAL parse (``ir.parse_confidence
    != "full"`` — some clause fell to ``category="other"`` / an unresolved
    trigger), the structural signals may under-report, so the card is flagged
    ``partial_parse`` for the agent to hand-scope. ``ir=None`` (no sidecar /
    synthetic fixture) preserves the pre-A4 behavior exactly — the new reason is
    purely additive and never changes an existing verdict."""
    if not signals:
        return (True, "zero_signal")
    keys = {s.key for s in signals}
    if keys <= _GENERIC_KEYS and not any(s.subject for s in signals):
        return (True, "only_generic")
    # Every signal is a scope guess (Phase B) → the agent should confirm the scoping.
    if all(s.confidence == "low" for s in signals):
        return (True, "low_confidence")
    if _scope_uncertain(get_oracle_text(card) or ""):
        return (True, "scope_uncertain")
    # The IR itself reports an incomplete parse → some clause wasn't structured,
    # so the structural signals may miss a lane. Flag it last (additive; the
    # signal-quality reasons above keep precedence; ir=None → inert).
    if ir is not None and ir.parse_confidence != "full":
        return (True, "partial_parse")
    return (False, "")


def producible_static_keys() -> set[str]:
    """Every scope-bearing, subject-LESS signal key the extractor can emit into
    ``Signal.key`` — the served-key manifest, fed to the key-agreement gate in
    signal_specs.py (ADR-0014). Subject-bearing keys are excluded: they have no
    static spec (signal_specs._subject_spec builds one from the captured subject)
    and so must not be probed with an empty subject.

    The manifest is the single key source: the retired regex producer tables were
    measured to contribute zero keys outside it before deletion (every regex /
    sweep / literal-add key was already manifest-served — 360 == 360, 2026-07-25).
    Lazy import so no lane machinery loads on a bare ``import signals``."""
    from mtg_utils._deck_forge.crosswalk_signals import SERVED_SIGNAL_KEYS

    return set(SERVED_SIGNAL_KEYS) - signal_keys.SUBJECT_KEYS
