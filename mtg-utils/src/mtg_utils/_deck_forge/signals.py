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
    _GENERIC_KEYS,
    _HAND_FLOOR,
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
    if ir is None or not MIGRATED_KEYS:
        return regex_signals
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
    # ADR-0027 spell-copy cross-open reconciliation: the regex path cross-opens
    # spellcast_matters from a spell_copy_matters commander (a spell-copier is a
    # spellslinger wanting a dense I/S base), gated on the regex set carrying
    # spell_copy_matters. Now that spell_copy_matters migrated, the regex set lacks it,
    # so the cross-open stops firing — re-supply it here when the IR provides spell_copy
    # and the regex set didn't already cross-open spellcast (matching pre-migration
    # behavior; low confidence, you-scope).
    out_keys = {s.key for s in out}
    if (
        "spell_copy_matters" in out_keys
        and "spell_copy_matters" not in {s.key for s in regex_signals}
        and "spellcast_matters" not in out_keys
    ):
        out.append(
            Signal("spellcast_matters", "you", "", "", record.get("name", ""), "low")
        )
    # ADR-0027 β gain_control cross-open reconciliation. The regex include_membership
    # cross-open ties two LOW-confidence theft-archetype tells to gain_control: (1) it
    # opens the theft_matters sibling when a body has gain_control OR rewards permanents
    # "you control but DON'T OWN"; (2) it opens a LOW gain_control on a theft-PAYOFF
    # commander that only says "don't own" with no structural form (Gonti Canny, Tasha,
    # Vaan, Don Andres, Arvinox, Nita, Laughing Jasper Flint, Nathan Drake, Thieving
    # Amalgam / Varmint, Tinybones Bauble Burglar, Sentinel of Lost Lore, Staff of Eden
    # — 13 commanders). gain_control now migrates, so the hybrid DROPS every regex
    # gain_control (the LOW cross-open included) and the regex cross-open's
    # `gain_control in keys_now` test sees the deleted producer's absence — re-run both
    # tells against
    # the MERGED key set, gated on include_membership (the regex cross-open's gate).
    # theft_matters is NOT migrated, so a regex firing already survives; re-open it only
    # when the IR supplies gain_control and the merged set lacks it (a structural-theft
    # commander — Memnarch, Dragonlord Silumgar, Nihiloor, Empress Galina — whose
    # theft_matters depended on the deleted regex gain_control). Re-add the LOW
    # gain_control for the 13 "don't own" payoff commanders the hybrid dropped (no
    # structural form). Matches the spell_copy reconciliation pattern above. CR 800.4a.
    if include_membership:
        regex_keys = {s.key for s in regex_signals}
        gc_now = "gain_control" in out_keys
        dont_own = re.search(
            r"you (?:cast|control|own)?[^.]{0,25}?(?:do not|don't) own",
            get_oracle_text(record) or "",
            re.IGNORECASE,
        )
        if (
            gc_now
            and "gain_control" not in regex_keys
            and "theft_matters" not in out_keys
        ):
            out.append(
                Signal(
                    "theft_matters", "opponents", "", "", record.get("name", ""), "low"
                )
            )
        if dont_own and not gc_now:
            out.append(
                Signal("gain_control", "you", "", "", record.get("name", ""), "low")
            )
    # ADR-0027 voltron reconciliation: the regex path computes the commander-damage
    # voltron MEMBERSHIP fallback against its OWN signal set (gated on
    # ``not has_other_plan``), which no longer carries a migrated PLAN key — when a key
    # migrates, its regex producer is deleted, so the regex set stops silencing the
    # membership tell on a card whose plan now lives only in the IR (a reanimator /
    # tap-untap / hand-disruption / aristocrats engine is NOT a vanilla beater). The
    # sacrifice/lifeloss *_PLAN_MIRROR re-silences those two on the oracle, but it goes
    # blind on a DFC's empty top-level oracle_text and doesn't cover the SWEEP-batch
    # plan keys. So drop the spurious low-confidence commander-damage membership tell
    # when the IR supplies one of the plan keys whose regex producer this batch deleted
    # and the regex set now LACKS — exactly the keys that used to count toward
    # `has_other_plan` (matching pre-migration behavior; a non-plan migrated key like a
    # color/type predicate is excluded, so voltron firings the OLD path kept survive).
    if include_membership:
        regex_keys = {s.key for s in regex_signals}
        ir_plan = any(
            s.key in _VOLTRON_SILENCING_PLAN_KEYS and s.key not in regex_keys
            for s in out
        )
        if ir_plan:
            out = [
                s
                for s in out
                if not (
                    s.key == "voltron_matters"
                    and s.confidence == "low"
                    and s.text == "commander damage (CR 903.10a)"
                )
            ]
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

# ADR-0027 voltron reconciliation set: migrated plan keys whose (now-deleted) regex
# producer used to count toward `has_other_plan` and so silenced the commander-damage
# voltron membership tell. When the IR re-supplies one of these the regex set lacks,
# the hybrid re-silences voltron — preserving pre-migration behavior. Only the keys
# that actually fire as a high-confidence non-generic non-voltron-compat plan in the
# regex path belong here (sacrifice/lifeloss were the first two; the SWEEP batch adds
# the engine plans whose deletion would otherwise leak a vanilla-beater voltron tell).
_VOLTRON_SILENCING_PLAN_KEYS = frozenset(
    {
        "sacrifice_matters",
        "lifeloss_matters",
        "reanimator",
        "tap_untap_matters",
        "minus_counters_matter",
        "donate_matters",
        "hand_disruption",
        "team_evasion_grant",
        "commander_matters",
        "opponent_exile_matters",
        "domain_matters",
        "speed_matters",
        # ADR-0027 SWEEP batch: each fired high-confidence (forced scope) in the regex
        # path and so counted toward `has_other_plan`, silencing the spurious commander-
        # damage voltron tell. Their regex producers are now deleted, so the hybrid must
        # re-silence from the IR re-supply to preserve pre-migration behavior (without
        # this, an infect/suspend vanilla beater — Skithiryx, Errant Ephemeron — leaks a
        # spurious voltron membership tell). NO-FLOOD requires these four here.
        "legends_matter",
        "lands_matter",
        "poison_matters",
        "suspend_matters",
        # ADR-0027 counters_matter pass 2: the +1/+1-counter regex producers (detector
        # / floor / keyword block / self-counter adds) fired high-confidence non-
        # generic, counting toward has_other_plan. Now migrated, so the hybrid must re-
        # silence the spurious voltron tell from the IR re-supply (a +1/+1-counter
        # engine — Hardened Scales, Forgotten Ancient — is not a vanilla beater).
        "counters_matter",
        # ADR-0027 tranche2-B: mass_bounce / permanent_etb / power_double each fired
        # high-confidence in the regex path and counted toward has_other_plan, silencing
        # the spurious commander-damage voltron tell on a non-vanilla-beater (a
        # bounce/tempo engine — Scourge of Fleets; a permanent-ETB value engine —
        # Amareth; a power-doubler — Okaun). Their regex producers are deleted, so the
        # hybrid re-silences from the IR re-supply. None of the affected cards is a DFC,
        # so the structural IR-signal gate suffices (no oracle mirror needed). team_buff
        # is NOT here — it carries a regex over-fire tail the narrower IR drops AND DFC
        # grant faces (Topaz Dragon), so it uses the byte-identical
        # _TEAM_BUFF_PLAN_MIRROR gate instead.
        "mass_bounce",
        "permanent_etb",
        "power_double",
        # ADR-0027 tranche2-batch-3-A: land_denial fired high-confidence in the regex
        # path (the _HAND_FLOOR producer, now deleted) and counted toward
        # has_other_plan, silencing the spurious commander-damage voltron tell on
        # Taniwha (a Trample Serpent that is a land-phasing stax commander, not a
        # vanilla beater). The IR re-supplies land_denial on the SAME single card
        # (IR==regex==1: phasing+Land+you isolates Taniwha exactly), so this is
        # byte-identical re-silencing — not a broadening, so no over-silence. The other
        # three migrated keys (keyword_soup / land_creatures_matter / land_protection)
        # leaked NO voltron on the file-swap (their cards already carry another plan),
        # so they are NOT added here.
        "land_denial",
        # ADR-0027 tranche2-A: the migrated anthem_static / aoe_ping / mass_removal keys
        # silenced the spurious commander-damage voltron membership tell when their
        # (now-deleted) regex producers fired. The silencing is done on the regex side
        # via the has_other_plan oracle mirrors (_ANTHEM_GO_WIDE_MIRROR /
        # _AOE_PING_PLAN_MIRROR / _MASS_REMOVAL_PLAN_MIRROR), each matching ONLY the old
        # regex's matches — NOT the broader IR re-supply, which would over-silence the
        # IR-only sweep/anthem bodies the old regex never caught (Sunblast Angel, Reiver
        # Demon). The mirrors now run against the joined-face ``text`` (see _oracle), so
        # they catch DFC back-face bodies (Archangel Avacyn, Fang Dragon) byte-
        # identically — no silencing-set entry needed. activated_draw is a draw engine
        # that never rode the per-card voltron membership gate at all.
        # NB (ADR-0027 tranche2-C): the five tranche2-C keys (self_pump / tapper_engine
        # / count_anthem / exert_matters / recast_etb) are NOT added here. They also
        # silenced voltron pre-migration (high-conf plans), but their IR recall is
        # BROADER than the deleted regex (self_pump 567->725, tapper 474->784 on the
        # commander-legal IR corpus), so the IR-supply reconciliation here would
        # OVER-silence (-117 on Aetherling / Angel's Trumpet / vigilance-granter
        # bodies the narrow regex missed). Instead they re-silence via the regex-path
        # _TRANCHE2C_PLAN_MIRROR fed into `has_other_plan`, which reproduces the exact
        # pre-migration silence set (the deleted regex patterns) for ALL cards — so
        # voltron_matters is byte-identical to pre-migration. NO-FLOOD.
        # ADR-0027 tranche2-batch-4 (t2b4-C): the 5 kept_detector keys each fired
        # high-confidence (forced/default scope) in the regex path and so counted
        # toward has_other_plan, silencing the spurious commander-damage voltron tell.
        # Their regex producers are deleted, so the hybrid re-silences from the IR
        # re-supply. Unlike tranche2-C, these are kept WORD MIRRORS — the IR re-supply
        # reads the SAME joined oracle as the deleted regex, so it is BYTE-IDENTICAL (no
        # broadening, no over-silence). File-swap: 0 voltron leaked, A-B==0.
        "damage_to_you_punish",
        "excess_damage",
        "self_blink",
        "tap_down_blockers",
        "type_change",
        # ADR-0027 tranche2-batch-5 (t2b5-A): the 5 kept_detector keys each fired
        # high-confidence (forced/default scope) in the regex path and so counted toward
        # has_other_plan, silencing the spurious commander-damage voltron tell. Their
        # regex producers are deleted, so the hybrid re-silences from the IR re-supply.
        # These are kept WORD MIRRORS — the IR re-supply reads the SAME joined oracle as
        # the deleted regex, so it is BYTE-IDENTICAL (no broadening, no over-silence).
        # File-swap: 0 voltron leaked, A-B==0.
        "draft_spellbook",
        "each_mode_player",
        "flip_self",
        "free_plot",
        "miracle_grant",
        # ADR-0027 tranche2-batch-5 (t2b5-C): the four kept_detector keys each fired
        # high-confidence (forced/default scope) in the regex path and so counted toward
        # has_other_plan, silencing the spurious commander-damage voltron tell on a
        # becomes-target / sticky-theft / villainous-choice / named-counter body that is
        # NOT a vanilla beater (Reality Smasher, Horobi, The Valeyard, Tetzimoc — 34
        # cards verified to leak the tell post-deletion). Their regex producers are
        # deleted, so the hybrid re-silences from the IR re-supply. These are kept WORD
        # MIRRORS — the IR re-supply reads the SAME joined oracle as the deleted regex,
        # so it is BYTE-IDENTICAL (no broadening, no over-silence). File-swap: 34
        # voltron leaked without this, 0 with it; A-B==0. (powerup_matters is a keyword-
        # array field lookup with 0 commander-legal cards, so it leaks nothing here.)
        "targeting_matters",
        "theft_protection",
        "villainous_choice",
        "named_counter_misc",
        # ADR-0027 β: tribe_damage_trigger fired high-confidence (forced scope 'you') in
        # the regex path and so counted toward has_other_plan, silencing the spurious
        # commander-damage voltron tell on a connect-for-damage engine that is NOT a
        # vanilla beater (Francisco, Fowl Marauder — a Flying/can't-block Partner Pirate
        # whose plan is "Pirates connect → explore", verified to leak the tell post-
        # deletion). Its regex producer is deleted, so the hybrid re-silences from the
        # IR re-supply. This is a kept WORD MIRROR — the IR re-supply reads the SAME
        # joined oracle as the deleted regex, so it is BYTE-IDENTICAL (no broadening, no
        # over-silence). File-swap: 1 voltron leaked without this, 0 with it; A-B==0.
        "tribe_damage_trigger",
        # ADR-0027: tokens_matter fired high-confidence (forced scope 'you') in the
        # regex path — via TWO _HAND_FLOOR producers AND the amass / mobilize keyword
        # map — and so counted toward has_other_plan, silencing the spurious
        # commander-damage voltron tell on a go-wide token engine that is NOT a vanilla
        # beater. All three regex producers are deleted, so the hybrid re-silences from
        # the IR re-supply. The IR firing is BYTE-IDENTICAL to the deleted regex
        # (commander-legal: regex == hybrid == 230, 0 broadening), so this set entry
        # re-silences ALL 230 — the oracle-payoff bodies (covered by
        # _TOKENS_MATTER_MIRROR) AND the 3 vanilla mobilize-KEYWORD bodies whose
        # token-making lives in stripped reminder text (Dragonback Lancer, Dalkovan
        # Packbeasts, Nightblade Brigade), which a regex-path oracle PLAN mirror cannot
        # see (a byte-identical mirror would leak those 3 — verified). File-swap: 3
        # voltron leaked without this, 0 with it; A-B == 0. Matches the keyword-bearing
        # counters_matter / suspend_matters / poison_matters precedent. CR 903.10a /
        # 111.1.
        "tokens_matter",
        # ADR-0027: second_spell_matters fired high-confidence (forced scope 'you')
        # in the regex path — via the _HAND_FLOOR floor producer (it was an
        # _IR_FLOOR_LANE) — and so counted toward has_other_plan, silencing the
        # spurious commander-damage voltron tell on a second-spell Storm-lite engine
        # that is NOT a vanilla beater. The floor producer is deleted, so the hybrid
        # re-silences from the IR re-supply. The IR firing is BYTE-IDENTICAL to the
        # deleted floor regex (commander-legal: regex == hybrid == 92, 0 broadening,
        # 0 ir_only), so this set entry re-silences exactly without over-silence —
        # matching the byte-identical kept-mirror precedent (counters_matter /
        # tokens_matter). CR 601 / 903.10a.
        "second_spell_matters",
        # ADR-0027: land_sacrifice_matters fired high-confidence (scope 'you') in the
        # regex path via the _HAND_FLOOR producer and so counted toward has_other_plan
        # (it is NOT in _GENERIC_KEYS / _VOLTRON_COMPAT_KEYS), silencing the spurious
        # commander-damage voltron tell on a land-sac creature commander that is NOT a
        # vanilla beater (Slogurk, Titania, Uurg, The Gitrog Monster). Its regex
        # producer is deleted, so the hybrid re-silences from the IR re-supply — a kept
        # WORD MIRROR reading the SAME reminder-stripped joined oracle as the deleted
        # regex, so it is BYTE-IDENTICAL (IR==regex==66, no broadening, no
        # over-silence), matching the lands_matter / draw_matters kept-mirror
        # precedent. A NO-FLOOD voltron entry.
        "land_sacrifice_matters",
        # NB (ADR-0027 β): legend_rule_off + timing_control are NOT added here. Both
        # fired high-confidence pre-migration (scope 'you' / 'any') and so counted
        # toward has_other_plan, but the FILE-SWAP showed 0 voltron leaked without an
        # entry (their creature bodies — Cadric, Brothers Yamazaki, Sakashima, The
        # Master, Sliver Gravemother, Teferi Mage of Zhalfir, Dosan — already carry
        # another plan signal, e.g. legends_matter / self-copy). Adding them would be
        # dead over-silencing, so they stay out (matching the keyword_soup /
        # land_creatures_matter precedent above).
    }
)

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


def coverage_gate(card: dict, signals: list[Signal]) -> tuple[bool, str]:
    """Report a blind spot: (needs_agent, reason). reason ∈ {zero_signal,
    only_generic, low_confidence, scope_uncertain, ""}. Surfaces gaps for agent
    scoping instead of dropping them silently."""
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
    return keys - signal_keys.SUBJECT_KEYS
