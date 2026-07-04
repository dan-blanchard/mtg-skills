"""Deterministic signal extraction — the discovery-engine keystone.

A ``Signal`` is a precisely-scoped fact pulled from a card's oracle text: what it
cares about / triggers on, *whose* resource it concerns (scope), and — when the
clause names one — the *subject* it cares about (a creature subtype). Scope and
subject are part of the signal's identity, which is how we avoid overgeneralization:
a card that benefits from an opponent's graveyard yields ``graveyard_matters`` scoped
``opponents`` (never a generic one that would justify self-mill), and a Goblin lord
yields ``type_matters`` with ``subject="Goblin"`` (never collapsed into a generic
"creatures matter").

Three tiers, all keyless and precision-gated:

  1. **Baseline detectors** — the original substring/regex bag (creature_etb,
     graveyard_matters, …). Subject-free.
  2. **Parametric subject detectors** — ``type_matters`` / ``token_maker`` /
     ``typed_spellcast`` capture the subtype noun, singularize it, and validate it
     against the harvested creature-subtype vocabulary (``_subtypes``). An
     unresolvable capture emits nothing (silent drop = the safe failure mode), so
     clones / "Plant creature" / card-type words never become junk subjects.
  3. **Structural-anchor floor detectors + theme_presets reuse** — whole archetypes
     the baseline was blind to (treasure / artifacts / enchantments / tokens / stax),
     each requiring a ``X you control`` / ``for each X`` / ``whenever … enters`` /
     ``opponents can't`` anchor; plus a curated subset of ``theme_presets`` (blink /
     mill / goad / proliferate / magecraft / extra-combats / extra-turns).

One narrow structural scope rule (combat-damage-to-a-player + "that player's <zone>"
→ opponents) deterministically fixes the Tinybones bug without the broad
possessive→opponents rule that would misfire on self-blink/self-bounce cards.

``coverage_gate`` reports the extractor's own blind spots (zero-signal / only-generic
/ scope-uncertain) so the session-agent (M3, ADR-0009) can scope the residual tail
with mandatory oracle-clause quotes — blind spots are queued, never silently dropped.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._ir_lookup import crosswalk_enabled
from mtg_utils._deck_forge._migrated_keys import MIGRATED_KEYS
from mtg_utils._deck_forge._signals_ir import (
    _IR_KEPT_DETECTORS,
    _IR_KEYWORD_MAP,
    _KEYWORD_COUNTER_KINDS,
    IR_SLICE_KEYS,
    _ir_effect_is_edict,
    _is_exile_until_leaves,
    extract_signals_ir,
)
from mtg_utils._deck_forge._signals_regex import (
    _DETECTORS,
    _DIRECT_KEYWORD_SIGNALS,
    _DISCARD_OUTLET_SWEEP_RE,
    _GENERIC_KEYS,
    _HAND_FLOOR,
    _LURE_MATTERS_PLAN_MIRROR,
    _PLAY_FROM_TOP_FLOOR_MIRROR,
    _PLAY_FROM_TOP_MIRROR,
    _PRESET_KEYWORD_SIGNALS,
    _PRESET_REGEX_SIGNALS,
    _VOLTRON_EQUIP_RE,
    Signal,
    _clauses,
    _fold_referenced_objects,
    _tinybones_scope,
    _voltron_double_strike_beater,
    _voltron_land_scaler,
    _voltron_self_heroic,
    _voltron_self_pump,
    _voltron_self_recurs,
    _voltron_self_unblockable,
    clauses,
    extract_signals,
)
from mtg_utils._deck_forge._subtypes import (
    CREATURE_SUBTYPES,
)
from mtg_utils._deck_forge._sweep_detectors import (
    SWEEP_DETECTORS,
)
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.card_ir import Card

# Public surface re-exported by this facade after the ADR-0027 split of the
# detection paths into _signals_regex (base) + _signals_ir. Listed here so the
# re-export imports above are not pruned as "unused" — external consumers and
# tests still do `from mtg_utils._deck_forge.signals import <name>`.
__all__ = [
    "IR_SLICE_KEYS",
    "MIGRATED_KEYS",
    "_IR_KEPT_DETECTORS",
    "_IR_KEYWORD_MAP",
    "_KEYWORD_COUNTER_KINDS",
    "_VOLTRON_EQUIP_RE",
    "Signal",
    "_ir_effect_is_edict",
    "_is_exile_until_leaves",
    "_tinybones_scope",
    "_voltron_double_strike_beater",
    "_voltron_land_scaler",
    "_voltron_self_heroic",
    "_voltron_self_pump",
    "_voltron_self_recurs",
    "_voltron_self_unblockable",
    "aggregate_signals",
    "clauses",
    "coverage_gate",
    "extract_signals",
    "extract_signals_hybrid",
    "extract_signals_ir",
    "producible_static_keys",
    "rank_deck_signals",
    "signal_keys",
]


# ── Hybrid dispatch seam (ADR-0027 strangler) ─────────────────────────────────


def _hybrid_merge(
    record: dict,
    ir: Card | None,
    regex_signals: list[Signal],
    *,
    vocab: frozenset[str],
    include_membership: bool,
    resolve_object: Callable[[str], dict | None] | None,
) -> list[Signal] | None:
    """Merge the non-regex signal sources into the stripped regex set.

    Returns the merged ``out`` (before the shared reconciliation tail), or ``None``
    to signal "no non-regex source ran — return the pure regex set". With the
    Stage-3a flag OFF (default) this is byte-identical to the pre-Stage-3a code:
    strip ``MIGRATED_KEYS`` from the regex set and re-supply them from
    ``extract_signals_ir``."""
    if crosswalk_enabled():
        crosswalk_out = _crosswalk_merge(
            record,
            regex_signals,
            vocab=vocab,
            include_membership=include_membership,
            resolve_object=resolve_object,
        )
        if crosswalk_out is not None:
            return crosswalk_out
    if ir is None or not MIGRATED_KEYS:
        return None
    out: list[Signal] = [s for s in regex_signals if s.key not in MIGRATED_KEYS]
    seen = {(s.key, s.scope, s.subject) for s in out}
    # ADR-0027 β: fold referenced objects (ADR-0025 — a ventured dungeon / meld result
    # / the Ring) into the record the IR path reads, so a migrated kept-mirror key whose
    # plan lives on a FOLDED object (e.g. combat_damage_to_opp from the Ring-bearer's
    # "deals combat damage to a player" level) still fires from the IR path. The regex
    # path folds internally above; the IR path takes the pre-folded record. No-op when
    # no resolver / nothing folds.
    ir_record = (
        _fold_referenced_objects(record, resolve_object)
        if resolve_object is not None
        else record
    )
    for sig in extract_signals_ir(
        ir_record, ir, vocab=vocab, include_membership=include_membership
    ):
        if sig.key not in MIGRATED_KEYS:
            continue
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(sig)
    return out


def _crosswalk_merge(
    record: dict,
    regex_signals: list[Signal],
    *,
    vocab: frozenset[str],
    include_membership: bool,
    resolve_object: Callable[[str], dict | None] | None,
) -> list[Signal] | None:
    """The ADR-0035 Stage-3a three-way merge (flag ON). ``None`` when the concept
    tree is unavailable so the caller degrades to the legacy IR path.

    Three-way dispatch (the key-set delta is exact, NOT a clean swap):
    ``PORTED_KEYS`` come from the typed-substrate crosswalk; the residual keys the
    crosswalk does not reproduce (``MIGRATED_KEYS - PORTED_KEYS`` — the two permanent
    KEPT lanes ``damage_redirect`` / ``land_destruction`` plus the unported tail)
    stay on the legacy ``extract_signals_ir`` path; every other key stays regex. The
    shared reconciliation tail runs once in the caller, its ``not in out_keys`` guards
    absorbing the crosswalk's own already-applied reconciliations (single fire)."""
    from mtg_utils._deck_forge._ir_lookup import old_ir_for, tree_for
    from mtg_utils._deck_forge.crosswalk_signals import (
        PORTED_KEYS,
        extract_crosswalk_signals,
    )

    tree = tree_for(record)
    if tree is None:
        return None
    residual = MIGRATED_KEYS - PORTED_KEYS
    served = PORTED_KEYS | residual  # == PORTED_KEYS | MIGRATED_KEYS
    out: list[Signal] = [s for s in regex_signals if s.key not in served]
    seen = {(s.key, s.scope, s.subject) for s in out}

    def _add(sig: Signal) -> None:
        ident = (sig.key, sig.scope, sig.subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(sig)

    keywords = frozenset(
        k for k in (record.get("keywords") or []) if isinstance(k, str)
    )
    # The OLD projected Card — fetched ONCE, up front: the residual keys read it
    # below AND (ADR-0035 Stage-3a floor port) the crosswalk's membership floor reads
    # it for its structural ``big_mana`` / ``kill_engine`` / token-kindred arms. Never
    # the flag-switched ``ir_for`` (under the flag that is the crosswalk Card).
    old = old_ir_for(record)
    for sig in extract_crosswalk_signals(
        tree,
        keys=PORTED_KEYS,
        keywords=keywords,
        include_membership=include_membership,
        record=record,
        ir=old,
        vocab=vocab,
    ):
        if sig.key in PORTED_KEYS:
            _add(sig)
    if old is not None:
        ir_record = (
            _fold_referenced_objects(record, resolve_object)
            if resolve_object is not None
            else record
        )
        for sig in extract_signals_ir(
            ir_record, old, vocab=vocab, include_membership=include_membership
        ):
            if sig.key in residual:
                _add(sig)
    return out


def extract_signals_hybrid(
    record: dict,
    ir: Card | None,
    *,
    vocab: frozenset[str] = CREATURE_SUBTYPES,
    include_membership: bool = True,
    resolve_object: Callable[[str], dict | None] | None = None,
) -> list[Signal]:
    """Dispatch each signal key to the IR or the regex path per ``MIGRATED_KEYS``.

    Keys in ``MIGRATED_KEYS`` come from ``extract_signals_ir`` (the Card IR path);
    every other key comes from ``extract_signals`` (the legacy regex path). The two
    sets are merged and deduped by ``(key, scope, subject)``. With ``MIGRATED_KEYS``
    empty (today) the IR contributes nothing, so the result is byte-identical to a
    pure ``extract_signals`` call regardless of ``ir`` (including ``ir is None``).

    Graceful degradation: when ``ir is None`` (the sidecar is absent / a brand-new
    set), return the pure regex path — the IR sidecar is a new core dependency but
    must never hard-crash production if missing. The ``extract_signals`` keyword args
    (``vocab`` / ``include_membership`` / ``resolve_object``) are forwarded through."""
    regex_signals = extract_signals(
        record,
        vocab=vocab,
        include_membership=include_membership,
        resolve_object=resolve_object,
    )
    # Merge the non-regex signal sources into ``out`` (ADR-0035 Stage-3a routes the
    # ported keys through the crosswalk when the flag is ON; the legacy IR path
    # otherwise). ``None`` means "no non-regex source ran" → return the pure regex
    # set unchanged, EXACTLY as before Stage-3a (the flag-OFF byte-identity invariant).
    out = _hybrid_merge(
        record,
        ir,
        regex_signals,
        vocab=vocab,
        include_membership=include_membership,
        resolve_object=resolve_object,
    )
    if out is None:
        return regex_signals
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


def aggregate_signals(records: list[dict | None]) -> list[Signal]:
    """Union of signals across many cards, deduped by (key, scope, subject)."""
    seen: dict[tuple[str, str, str], Signal] = {}
    for record in records:
        if not record:
            continue
        for sig in extract_signals(record):
            ident = (sig.key, sig.scope, sig.subject)
            seen.setdefault(ident, sig)
    return list(seen.values())


def rank_deck_signals(
    records: Sequence[dict | None],
    commander_names: set[str],
    *,
    resolve_object: Callable[[str], dict | None] | None = None,
    ir_for: Callable[[dict], Card | None] | None = None,
) -> list[Signal]:
    """Deck signals deduped by (key, scope, subject) and ranked by relevance.

    Membership signals (own-subtype tribal, voltron fallback) are taken from the
    COMMANDER only — otherwise every creature's race/stat-line floods the deck. A
    signal's *support* (how many cards feed it) drives the ranking. Kept ForgeState-free
    so both the deck-forge engine (``engine.ranked_deck_signals``) and the deterministic
    tuner share one ranking (ADR-0023).

    ``ir_for`` (ADR-0027): a per-record Card-IR resolver. When supplied, each card
    runs through ``extract_signals_hybrid`` so migrated keys (served only from the IR)
    surface in the deck's ranked signals / avenues — the engine wires its index here.
    When ``None`` (the deterministic tuner's no-sidecar path), falls back to the pure
    regex ``extract_signals`` (a migrated key whose regex producer is deleted simply
    won't surface — graceful degradation, matching the hybrid's ``ir is None`` arm)."""
    support: dict[tuple[str, str, str], int] = {}
    from_commander: set[tuple[str, str, str]] = set()
    first: dict[tuple[str, str, str], Signal] = {}
    for card in records:
        if not card:
            continue
        is_cmd = card.get("name") in commander_names
        # Folded objects (a ventured dungeon — ADR-0025) belong to the COMMANDER's plan,
        # so only fold for the commander, never the 99.
        if ir_for is not None:
            sigs = extract_signals_hybrid(
                card,
                ir_for(card),
                include_membership=is_cmd,
                resolve_object=resolve_object if is_cmd else None,
            )
        else:
            sigs = extract_signals(
                card,
                include_membership=is_cmd,
                resolve_object=resolve_object if is_cmd else None,
            )
        for sig in sigs:
            ident = (sig.key, sig.scope, sig.subject)
            support[ident] = support.get(ident, 0) + 1
            if is_cmd:
                from_commander.add(ident)
            first.setdefault(ident, sig)
    return sorted(
        first.values(),
        key=lambda s: (
            (s.key, s.scope, s.subject) in from_commander,
            support[(s.key, s.scope, s.subject)],
            s.confidence == "high",
        ),
        reverse=True,
    )


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


# Keys emitted by hand-written full-text / function detectors via a direct add(), i.e.
# NOT carried by a producer table — co-listed so the key-agreement gate guards them too.
# (Subject-bearing keys live in signal_keys.SUBJECT_KEYS and are excluded below; they
# resolve dynamically via signal_specs._subject_spec, not a static spec.)
_LITERAL_ADD_KEYS = frozenset(
    {
        "self_blink",
        "combat_buff_engine",
        "discard_matters",
        "card_draw_engine",
        "ability_strip_payoff",
        "land_destruction",
        "cheat_from_top",
        "kill_engine",
        "one_punch",
        "big_mana",
    }
)


def producible_static_keys() -> set[str]:
    """Every scope-bearing, subject-LESS signal key a detector can emit into
    ``Signal.key`` — DERIVED from the producer tables (so it can never lag the
    detectors) and fed to the key-agreement gate in signal_specs.py. Subject-bearing
    keys are excluded: they have no static spec (signal_specs._subject_spec builds one
    from the captured subject) and so must not be probed with an empty subject."""
    keys: set[str] = set()
    keys.update(key for key, _matcher, _scope in _DETECTORS)
    keys.update(key for key, _pattern, _scope in _HAND_FLOOR)
    keys.update(d["key"] for d in SWEEP_DETECTORS)
    for table in (
        _PRESET_KEYWORD_SIGNALS,
        _PRESET_REGEX_SIGNALS,
        _DIRECT_KEYWORD_SIGNALS,
    ):
        keys.update(key for key, _scope in table.values())
    keys.update(_LITERAL_ADD_KEYS)
    # ADR-0027 strangler: a migrated key's regex production is deleted, but it is
    # still produced (from the IR path) and still needs a resolving spec — so it
    # stays guarded by the key-agreement gate (signal_specs ADR-0014). The
    # producer tables above no longer mention it, so union it back in explicitly.
    keys.update(MIGRATED_KEYS)
    # ADR-0035 Stage-3a: when the flag is ON the crosswalk becomes a key source, so
    # union ``PORTED_KEYS`` into the gate's coverage too (lazy import — no crosswalk
    # machinery is pulled in on the default flag-OFF import path). This is a superset
    # no-op today (every PORTED key is already regex- or IR-produced) but keeps the
    # gate honest if a future PORTED key has no other producer.
    if crosswalk_enabled():
        from mtg_utils._deck_forge.crosswalk_signals import PORTED_KEYS

        keys.update(PORTED_KEYS)
    return keys - signal_keys.SUBJECT_KEYS
