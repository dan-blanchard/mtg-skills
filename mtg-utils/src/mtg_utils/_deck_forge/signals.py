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
from dataclasses import dataclass

from mtg_utils._deck_forge._subtypes import (
    CARD_TYPE_SUBJECTS,
    CREATURE_SUBTYPES,
    IRREGULAR_SINGULAR,
    NON_SUBJECT_WORDS,
)
from mtg_utils.card_classify import get_oracle_text
from mtg_utils.theme_presets import get_preset


@dataclass(frozen=True)
class Signal:
    """A scoped fact extracted from one card's oracle text."""

    key: str  # canonical signal id, e.g. "creature_etb"
    scope: str  # "you" | "opponents" | "each" | "any"
    subject: str  # subtype qualifier (e.g. "Goblin"); "" if none
    text: str  # the matched oracle clause (the quote, for grounding/scoping)
    source: str  # the card name the signal came from


# ── Tier 1: baseline detectors ────────────────────────────────────────────────
# Each detector: (key, clause-matcher, forced_scope|None). When forced_scope is
# None the clause's own scope is used (critical for creature_etb / graveyard_matters).
def _has(*needles: str):
    return lambda c: all(n in c for n in needles)


def _re(pattern: str):
    rx = re.compile(pattern)
    return lambda c: rx.search(c) is not None


_DETECTORS: tuple[tuple[str, object, str | None], ...] = (
    (
        "creature_etb",
        lambda c: (
            _re(r"\b(?:a|another|one or more|each)\b[^.]*\bcreature[s]?\b[^.]*\benter")(
                c
            )
            and ("whenever" in c or "when " in c)
        ),
        None,
    ),
    ("creatures_matter", _has("creatures you control"), "you"),
    # Type-matters: "land creature(s)" as a phrase. \b before "land" so "nonland
    # creature" / "Plant creature" / "island creature" do NOT register — only a
    # genuine land-creature reference (the Jyoti / Sylvan Advocate theme).
    ("land_creatures_matter", _re(r"\bland creatures?\b"), None),
    (
        "lifegain_matters",
        lambda c: "whenever" in c and "gain" in c and "life" in c,
        "you",
    ),
    ("graveyard_matters", _has("graveyard"), None),
    ("spellcast_matters", _has("whenever you cast", "spell"), "you"),
    ("death_matters", lambda c: "whenever" in c and "dies" in c, None),
    ("sacrifice_matters", _re(r"sacrifice (?:a|an|another|two|three|x|\d)"), "you"),
    ("attack_matters", lambda c: "whenever" in c and "attack" in c, None),
    ("draw_matters", _has("whenever you draw"), "you"),
    (
        "landfall",
        lambda c: "landfall" in c or ("whenever a land" in c and "enter" in c),
        "you",
    ),
    (
        "counters_matter",
        lambda c: "+1/+1 counter" in c and ("for each" in c or "number of" in c),
        None,
    ),
)


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"(?<=[.;\n])\s+", text) if c.strip()]


def _scope(clause_lower: str) -> str:
    if "opponent" in clause_lower:
        return "opponents"
    if "each player" in clause_lower:
        return "each"
    if (
        "you control" in clause_lower
        or "your " in clause_lower
        or re.search(r"\byou\b", clause_lower)
    ):
        return "you"
    return "any"


# ── Tier 2: parametric subject detectors ──────────────────────────────────────


def _singularize(raw: str) -> str:
    """Lowercase + best-effort singularize a captured noun. The (\\w+?)s? capture
    can emit a partial plural ("Elve", "Dwarve"), so we map those explicitly."""
    w = raw.lower().strip(",.")
    if w in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    if w.endswith("ve") and len(w) > 3 and w not in ("cave", "wave", "brave"):
        return w[:-2] + "f"
    if w.endswith("s") and len(w) > 1 and not w.endswith("ss"):
        return w[:-1]
    return w


def _resolve_subject(raw: str, vocab: frozenset[str]) -> str:
    """Resolve a raw capture to a canonical kindred subject, or "" (silent drop).

    Card-type words ("creature"/"permanent") and card-type subjects
    ("artifact"/"land", handled by the floor detectors) never become a kindred
    subject — they fall through to the generic / floor keys. This is the precision
    gate: an unparseable or non-kindred noun produces zero false positives.
    """
    w = _singularize(raw)
    if w in NON_SUBJECT_WORDS or w in CARD_TYPE_SUBJECTS:
        return ""
    if w in vocab:
        return w.capitalize()
    return ""


# type_matters: the subject NOUN is captured. Every pattern requires a structural
# "you control" / "for each" anchor — never a bare noun. IGNORECASE is load-bearing
# (sentence-initial "Other Dwarves" else drops Magda).
_TYPE_MATTERS_PATTERNS = (
    re.compile(r"\bother ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?)s? you control get [+\-](?:\d|x)", re.IGNORECASE),
    re.compile(r"\b(?:number of|for each) ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?)s? you control have\b", re.IGNORECASE),
)
# typed_spellcast: subject-bearing extension of spellcast_matters — catches tribal
# spell payoffs ("Sliver spells you cast") the literal spellcast_matters misses.
_TYPED_SPELLCAST_PATTERN = re.compile(
    r"\b([A-Za-z]+?)s? spells? you cast\b", re.IGNORECASE
)
# token_maker: capture the LAST creature subtype before "creature token(s)",
# preferring a real subtype over the card-type word "artifact"
# ("Thopter artifact creature token" → Thopter).
_TOKEN_MAKER_PATTERN = re.compile(r"create [^.]*?\bcreature tokens?\b", re.IGNORECASE)
_TOKEN_SUBJECT_WORDS = re.compile(r"\b([A-Z][a-z]+)\b")


def _detect_type_matters(clause: str, vocab: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pat in _TYPE_MATTERS_PATTERNS:
        for m in pat.finditer(clause):
            subject = _resolve_subject(m.group(1), vocab)
            if subject:
                out.append(("type_matters", subject))
    return out


def _detect_typed_spellcast(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _TYPED_SPELLCAST_PATTERN.finditer(clause):
        subject = _resolve_subject(m.group(1), vocab)
        if subject:
            out.append(("typed_spellcast", subject))
    return out


def _detect_token_maker(clause: str, vocab: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _TOKEN_MAKER_PATTERN.finditer(clause):
        head = re.split(r"creature tokens?", m.group(0), flags=re.IGNORECASE)[0]
        chosen = ""
        for w in reversed(_TOKEN_SUBJECT_WORDS.findall(head)):
            if w.lower() in vocab:
                chosen = w.capitalize()
                break
        out.append(("token_maker", chosen))
    return out


# ── Tier 3: structural-anchor floor detectors + theme_presets reuse ────────────

# Each floor detector requires a structural anchor, never a bare substring, so
# incidental one-shot makers (Beledros, Faramir) and self-restrictions (Kefnet)
# don't misfire.
_REGEX_FLOOR_DETECTORS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "treasure_matters",
        re.compile(
            r"create (?:a|an|one|two|three|four|five|\d+|x)[^.]*?\btreasure token"
            r"|\btreasures? you control\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "artifacts_matter",
        re.compile(
            r"\bartifacts? you control\b"
            r"|for each artifact you control"
            r"|whenever an? artifact (?:you control )?enters",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "enchantments_matter",
        re.compile(
            r"\benchantments? you control\b"
            r"|for each enchantment you control"
            r"|whenever an? enchantment (?:you control )?enters",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "tokens_matter",
        re.compile(
            r"\btokens? you control\b"
            r"|whenever (?:a|one or more|another)[^.]*?\btokens?\b[^.]*?\benters?\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "stax_taxes",
        re.compile(
            r"\bopponents? can't\b"
            r"|spells your opponents cast cost"
            r"|creatures your opponents control",
            re.IGNORECASE,
        ),
        "opponents",
    ),
)

# (preset_name → (signal_key, scope)). KEYWORD-ARRAY presets only — these read
# Scryfall's authoritative `keywords` array, the low-false-positive path. mill is
# scoped "any" (it can target self or opponents; Phase-B nested-scope refines it).
_PRESET_KEYWORD_SIGNALS = {
    "mill": ("mill_matters", "any"),
    "goad": ("goad_matters", "opponents"),
    "proliferate": ("proliferate_matters", "you"),
    "magecraft": ("magecraft_matters", "you"),
}
# REGEX presets reused clause-scoped via the preset's own compiled patterns — these
# close documented pure-reuse gaps (blink/Brago, extra-combats/Aurelia) where the
# tested theme exists but the extractor never called it.
_PRESET_REGEX_SIGNALS = {
    "blink": ("blink_flicker", "you"),
    "extra-combats": ("extra_combats", "you"),
    "extra-turns": ("extra_turns", "you"),
}


def _detect_keyword_presets(card: dict) -> list[tuple[str, str]]:
    card_kws = {k.lower() for k in (card.get("keywords") or [])}
    out: list[tuple[str, str]] = []
    for preset_name, (key, scope) in _PRESET_KEYWORD_SIGNALS.items():
        preset_kws = {k.lower() for k in get_preset(preset_name).keywords}
        if card_kws & preset_kws:
            out.append((key, scope))
    return out


def _detect_regex_presets(clause: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for preset_name, (key, scope) in _PRESET_REGEX_SIGNALS.items():
        if any(p.search(clause) for p in get_preset(preset_name).patterns):
            out.append((key, scope))
    return out


# ── Narrow Tinybones structural scope rule ────────────────────────────────────
_COMBAT_DAMAGE_TO_PLAYER = re.compile(r"deals combat damage to a player", re.IGNORECASE)
_THAT_PLAYERS_ZONE = re.compile(
    r"that player's (?:graveyard|hand|library)", re.IGNORECASE
)


def _tinybones_scope(clause: str) -> str | None:
    """combat-damage-to-a-player + that-player's-zone → opponents. Kept narrow: a
    broad "its owner's hand → opponents" rule misfires on self-blink/self-bounce."""
    if _COMBAT_DAMAGE_TO_PLAYER.search(clause) and _THAT_PLAYERS_ZONE.search(clause):
        return "opponents"
    return None


# ── The extractor ─────────────────────────────────────────────────────────────


def extract_signals(
    card: dict, *, vocab: frozenset[str] = CREATURE_SUBTYPES
) -> list[Signal]:
    """Extract scoped, subject-bearing signals from a card (deterministic baseline)."""
    # Strip parenthetical reminder text first: it restates a keyword and is rules-
    # redundant, so it must never generate a signal (e.g. an Earthbend reminder's
    # "is exiled, return it to the battlefield" is not a blink engine).
    text = re.sub(r"\([^)]*\)", " ", get_oracle_text(card) or "")
    name = card.get("name", "")
    out: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    def add(key: str, scope: str, subject: str, clause: str) -> None:
        ident = (key, scope, subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(
            Signal(key=key, scope=scope, subject=subject, text=clause, source=name)
        )

    for clause in _clauses(text):
        stripped = clause.strip()
        cl = clause.lower()
        clause_scope = _scope(cl)
        rescope = _tinybones_scope(clause)
        # Tier 1 — baseline (subject-free)
        for key, matches, forced_scope in _DETECTORS:
            if not matches(cl):
                continue
            scope = rescope or forced_scope or clause_scope
            add(key, scope, "", stripped)
        # Tier 2 — parametric subject detectors (forced scope=you: "you control")
        for key, subject in _detect_type_matters(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_typed_spellcast(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_token_maker(clause, vocab):
            add(key, "you", subject, stripped)
        # Tier 3 — structural floor detectors + regex-preset reuse
        for key, rx, forced_scope in _REGEX_FLOOR_DETECTORS:
            if rx.search(clause):
                add(key, forced_scope, "", stripped)
        for key, scope in _detect_regex_presets(clause):
            add(key, scope, "", stripped)

    # Tier 3 — keyword-array presets (card-level, authoritative)
    for key, scope in _detect_keyword_presets(card):
        add(key, scope, "", text[:120])

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


# ── Coverage gate — the agent-augmentation (M3) hook ──────────────────────────
# Generic = {creatures_matter}: it fires on "creatures you control" (nearly every
# creature commander) and discriminates no archetype. The other keys each pin a
# real sub-archetype, so they are NOT generic.
_GENERIC_KEYS = frozenset({"creatures_matter"})

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
    only_generic, scope_uncertain, ""}. Surfaces gaps for agent scoping instead of
    dropping them silently."""
    if not signals:
        return (True, "zero_signal")
    keys = {s.key for s in signals}
    if keys <= _GENERIC_KEYS and not any(s.subject for s in signals):
        return (True, "only_generic")
    if _scope_uncertain(get_oracle_text(card) or ""):
        return (True, "scope_uncertain")
    return (False, "")
