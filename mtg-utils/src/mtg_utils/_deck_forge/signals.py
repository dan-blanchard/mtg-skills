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
from mtg_utils._deck_forge._sweep_detectors import SWEEP_DETECTORS
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
    confidence: str = (
        "high"  # "high" | "low" — low = a scope guess the agent should confirm
    )


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
    (
        "land_creatures_matter",
        _re(
            r"\bland creatures?\b|lands? you control (?:are|become)\b"
            r"|all lands[^.]*become[^.]*creature"
            r"|target land[^.]*becomes? a[^.]*creature"
        ),
        None,
    ),
    (
        # Lifegain payoff ("whenever you gain life") OR the act of gaining life.
        "lifegain_matters",
        _re(r"whenever[^.]*gain[^.]*life|you gain \d+ life|gain \d+ life"),
        "you",
    ),
    ("graveyard_matters", _has("graveyard"), None),
    ("spellcast_matters", _has("whenever you cast", "spell"), "you"),
    ("death_matters", lambda c: "whenever" in c and "dies" in c, None),
    ("sacrifice_matters", _re(r"sacrifice (?:a|an|another|two|three|x|\d)"), "you"),
    (
        "attack_matters",
        lambda c: ("whenever" in c and "attack" in c) or "attacking causes" in c,
        None,
    ),
    ("draw_matters", _has("whenever you draw"), "you"),
    (
        "landfall",
        lambda c: (
            "landfall" in c
            or ("whenever a land" in c and "enter" in c)
            or _re(r"play (?:an|one|two|three|\d+) additional lands?")(c)
        ),
        "you",
    ),
    (
        # Counter payoffs: "for each"/"number of" count-matters PLUS distributor
        # anchors (Mikaeus, Shalai and Hallar) that spread/reward counters without
        # the count phrasing — but NOT bare "put a +1/+1 counter on it" self-growth.
        "counters_matter",
        lambda c: (
            "+1/+1 counter" in c
            and (
                "for each" in c
                or "number of" in c
                or "on each creature you control" in c
                or "creatures you control with +1/+1 counter" in c
            )
        ),
        None,
    ),
    # Combat-damage triggers (distinct from attack_matters, which keys on "attack").
    # Forced opponents — the damaged party is a player/opponent. The single biggest
    # zero-signal recovery (Edric, Dragonlord Ojutai, Wrexial, …).
    (
        "combat_damage_matters",
        _re(
            r"\bwhen(?:ever)?\b[^.]*?\bdeals combat damage to "
            r"(?:a player|an opponent|one of your opponents|each opponent"
            r"|a player or planeswalker|a player or battle)\b"
        ),
        "opponents",
    ),
    # "whenever you discard" payoff OR a loot outlet ("draw a card, then discard").
    (
        "discard_matters",
        _re(r"whenever you discard|draw (?:a|two|three|x|\d+) cards?, then discard"),
        "you",
    ),
    # Life-loss / drain. Scope varies (opponents drain vs your own life-loss), so
    # forced_scope is None — the clause scope resolves it.
    (
        "lifeloss_matters",
        _re(
            r"\b(?:each opponent|each player|target opponent|target player|that player"
            r"|an opponent|each of your opponents|opponents?) loses? (?:\d+|x) life\b"
            r"|\bwhenever you (?:gain or )?lose life\b"
            r"|\bwhenever (?:an opponent|a player|one or more (?:players|opponents))"
            r" loses? life\b"
        ),
        None,
    ),
    # Pay-life / self life-loss as a resource (forced you — it's your life).
    ("lifeloss_matters", _re(r"pay \d+ life|you lose \d+ life"), "you"),
)


# card_draw_engine: a recurring/bulk card-advantage engine, NOT a cantrip. The bare
# "draw a card" must never fire — the single-card branch is gated behind a recurring
# "at the beginning of" anchor, and a one-shot ETB draw is skipped.
_CARD_DRAW_RE = re.compile(
    r"at the beginning of [^.]*\bdraws? "
    r"(?:a|an|two|three|four|five|six|seven|eight|nine|ten|x|\d+)\b[^.]*\bcard"
    r"|\bdraws? (?:two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?\b"
    r"|\bdraw cards equal to\b"
    r"|\bdraws? an additional card\b"
    r"|if you would draw a card, (?:instead )?draw "
    r"(?:two|three|four|five|six|seven|eight|nine|ten|x|\d+)",
    re.IGNORECASE,
)


def _detect_card_draw(clause: str) -> tuple[str, str] | None:
    if not _CARD_DRAW_RE.search(clause):
        return None
    cl = clause.lower()
    # Skip a one-shot ETB draw (not an engine) unless it's a recurring trigger too.
    if "when" in cl and "enters" in cl and "at the beginning of" not in cl:
        return None
    return ("card_draw_engine", "each" if "each player" in cl else "you")


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
    # "another Elf you control" (singular) — tribal triggers the "other Xs" form misses.
    re.compile(r"\banother ([A-Za-z]+?) you control\b", re.IGNORECASE),
    # "a Spider you control enters" — tribal ETB trigger (anchored on "enters" so a
    # bare "a Goblin you control" elsewhere can't over-capture). Mary Jane Watson.
    re.compile(r"\b(?:a|an) ([A-Za-z]+?) you control enters\b", re.IGNORECASE),
    # "Other Elf creatures have …" (lord with no "you control"); tribal in an
    # activated cost ("untapped Wizard you control:" / "<Sub> you control:").
    re.compile(r"\bother ([A-Za-z]+?) creatures?\b", re.IGNORECASE),
    re.compile(r"\buntapped ([A-Za-z]+?) you control\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?) you control\s*:", re.IGNORECASE),
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


@dataclass(frozen=True)
class Detector:
    """A compiled floor/sweep detector: a regex over a clause → a scoped signal key.
    The single record type the extractor's Tier-3 loop consumes, whether the source
    is a curated hand-written rule or a row of the exhaustively-mined sweep table."""

    key: str
    scope: str  # forced scope ("you" | "opponents" | "each" | "any")
    pattern: re.Pattern[str]


# Each floor detector requires a structural anchor, never a bare substring, so
# incidental one-shot makers (Beledros, Faramir) and self-restrictions (Kefnet)
# don't misfire. Hand-written source stays as (key, compiled-pattern, scope) tuples;
# the assembly below adapts both these and the mined sweep into Detector records.
_HAND_FLOOR: tuple[tuple[str, re.Pattern[str], str], ...] = (
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
    (
        "cost_reduction",
        re.compile(
            r"\b(?:spells?|each spell) you cast\b[^.]{0,80}?"
            r"\bcosts?\b[^.]{0,40}?\bless\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    # Impulse-draw / cast-from-exile. Self-anchored branches only (each requires
    # "from the top of your library" / "from exile" / "plot") — the bare-pronoun
    # branch is dropped to stay precise without paragraph-level parsing.
    (
        "cast_from_exile",
        re.compile(
            r"(?:play|cast|plot)\b[^.]*?\bfrom the top of your library"
            r"|top card of your library has plot"
            r"|(?:whenever|each time) you (?:cast a spell|play a (?:card|land)"
            r"|play a land or cast a spell)[^.]*?from exile"
            r"|spells? you cast from exile"
            r"|you may (?:play|cast) (?:it|that card|this card|those cards?|them)"
            r"[^.]*?(?:for as long as it remains exiled|from exile)"
            r"|you may play (?:a |that )?card[^.]*?from exile",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "lands_matter",
        re.compile(
            r"(?:the number of|for each) (?:basic )?lands? you control", re.IGNORECASE
        ),
        "you",
    ),
    (
        "direct_damage",
        re.compile(
            r"deals? (?:\d+|x) damage to any target"
            r"|\{t\}[^.]*?:[^.]*?deals? (?:\d+|x) damage"
            r"|would deal damage[^.]*?(?:it deals double|it deals twice"
            r"|deals that much damage plus)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "mana_amplifier",
        re.compile(
            r"tap(?:ped)? (?:a |an |another |each |any )?[^.]*?for mana[^.]*?"
            r"(?:add (?:an additional|one mana of any|that much|twice)"
            r"|produces? (?:twice|an additional))",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Sweep survivors ─────────────────────────────────────────────────────────
    (
        "voltron_matters",
        re.compile(
            r"\bfor each (?:equipment|aura|role)\b[^.]*?\b(?:attached|you control)\b"
            r"|\battach (?:target |all |any number of |up to one target |an |a )?"
            r"(?:equipment|aura)"
            r"|attach (?:any number of |all )?"
            r"(?:auras? and equipment|equipment and auras?)"
            r"|search your library for an? (?:equipment|aura)"
            r"(?: or (?:equipment|aura|vehicle))? card"
            r"|(?:equipment|auras?) you control have equip"
            r"|equip (?:abilities|costs?)[^.]{0,40}?(?:cost|costs?)[^.]{0,20}?less"
            r"|spend this mana only to cast (?:an? )?(?:aura|equipment)"
            r"|whenever you attach (?:a |an )?(?:equipment|aura|role)"
            r"|whenever an? (?:equipment|aura) (?:you control )?enters"
            r"|as long as \w+ is equipped|\bequipment you control\b"
            r"|pay [^.]*equip cost",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "vehicles_matter",
        re.compile(
            r"\bvehicles you control\b|\bmounts? and vehicles?\b"
            r"|\bvehicle you control enters\b|\bcrews a vehicle\b"
            r"|\bwhenever[^.]*\bcrews?\b"
            r"|\b(?:mount|equipment) or vehicle (?:card|spell)\b"
            r"|\bvehicle or artifact (?:creature )?(?:card|spell)\b"
            r"|create [^.]*\bvehicle artifact (?:creature )?token\b",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "scry_surveil_matters",
        re.compile(
            r"whenever you scry or surveil\b|whenever you (?:scry|surveil)\b"
            r"|if you would scry (?:a number of cards|\d)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Named-mechanic long tail (precise named anchors → novel build-arounds) ───
    ("monarch_matters", re.compile(r"\bthe monarch\b", re.IGNORECASE), "you"),
    ("initiative_matters", re.compile(r"\bthe initiative\b", re.IGNORECASE), "you"),
    (
        "ring_matters",
        re.compile(r"ring tempts you|your ring-bearer|the ring-bearer", re.IGNORECASE),
        "you",
    ),
    (
        "venture_matters",
        re.compile(
            r"venture into the dungeon|complete a dungeon|\bdungeon\b", re.IGNORECASE
        ),
        "you",
    ),
    ("energy_matters", re.compile(r"\{e\}|energy counters?", re.IGNORECASE), "you"),
    ("devotion_matters", re.compile(r"devotion to \w", re.IGNORECASE), "you"),
    (
        "superfriends_matters",
        re.compile(
            r"planeswalkers? you control|loyalty counters?"
            r"|activate (?:a |one )?loyalty|one or more loyalty",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("historic_matters", re.compile(r"\bhistoric\b", re.IGNORECASE), "you"),
    (
        "legends_matter",
        re.compile(
            r"legendary creatures? you control"
            r"|whenever (?:a|another) legendary (?:creature|permanent)[^.]*you control"
            r"|whenever you cast a legendary|for each legendary (?:creature|permanent)"
            r"|cast legendary|legendary (?:creature|permanent|spell)s? you cast"
            r"|legendary spells?",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "big_hand_matters",
        re.compile(
            r"no maximum hand size|maximum hand size"
            r"|(?:five|six|seven|eight) or more cards in your hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "party_matters",
        re.compile(
            r"\byour party\b|members? of your party|full party"
            r"|assemble[^.]*party|creatures? in your party",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "exile_matters",
        re.compile(
            r"cards? (?:you own )?(?:that are )?in exile"
            r"|for each card (?:you own )?(?:in )?exile",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("experience_matters", re.compile(r"experience counters?", re.IGNORECASE), "you"),
    (
        "poison_matters",
        re.compile(
            r"poison counters?|\bpoisonous\b|\btoxic\b|\binfect\b", re.IGNORECASE
        ),
        "opponents",
    ),
    ("modified_matters", re.compile(r"\bmodified\b", re.IGNORECASE), "you"),
    ("mutate_matters", re.compile(r"\bmutate\b", re.IGNORECASE), "you"),
    (
        # Anchor on the Food-token mechanic (CR 111.10), like its sibling token axes,
        # not the bare word.
        "food_matters",
        re.compile(
            r"\bfood token|create (?:a|an|one|two|three|x|\d+)[^.]*?\bfood\b"
            r"|sacrifice a food|foods? you control",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("clue_matters", re.compile(r"\bclue\b|\binvestigate\b", re.IGNORECASE), "you"),
    ("blood_matters", re.compile(r"blood tokens?", re.IGNORECASE), "you"),
    (
        "daynight_matters",
        re.compile(
            r"\bdaybound\b|\bnightbound\b|it becomes night"
            r"|day becomes night|night becomes day|as long as it's (?:day|night)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "voting_matters",
        re.compile(
            r"will of the council|council's dilemma|each player votes?|\bvote\b",
            re.IGNORECASE,
        ),
        "each",
    ),
    ("coven_matters", re.compile(r"\bcoven\b", re.IGNORECASE), "you"),
    (
        "doubling_matters",
        re.compile(
            r"double the (?:number|amount)|create twice that many"
            r"|would (?:create|put|draw|gain|deal)[^.]*\binstead\b"
            r"[^.]*(?:twice|double|that many plus)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "second_spell_matters",
        re.compile(
            r"second spell you cast (?:each|this) turn|cast your second spell"
            r"|(?:second|third|fourth|fifth) spell (?:you cast|of (?:a|each|that) turn)"
            r"|cast two or more spells",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "opponent_cast_matters",
        re.compile(
            r"whenever an opponent casts|whenever (?:a|another) player casts a spell"
            r"|whenever an opponent cast",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    (
        "opponent_draw_matters",
        re.compile(
            r"whenever an opponent draws|whenever each opponent draws"
            r"|whenever a player draws a card (?:except|other than)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # Punish opponents' library manipulation (River Song's Spoilers; Aven
    # Mindcensor / Opposition Agent / Leovold space) — distinct from your own
    # scry_surveil payoff, which is scoped "you".
    (
        "opponent_search_matters",
        re.compile(
            r"whenever (?:an opponent|a player|each opponent)[^.]*"
            r"(?:scries|surveils|searches (?:their|a) library"
            r"|shuffles (?:their|a) library)",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # ── Mechanics recovered from the "rejected" families (still-zero commanders) ──
    (
        "token_copy_matters",
        re.compile(
            r"tokens? that(?:'s| are) (?:a )?cop(?:y|ies) of"
            r"|create a token that's a copy",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("specialize_matters", re.compile(r"\bspecialize\b", re.IGNORECASE), "you"),
    (
        "dice_matters",
        re.compile(
            r"roll (?:a|one or more|two|\d+) (?:d\d+|dice|die)"
            r"|result of (?:the|a|your) (?:roll|die)|whenever you roll",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "crimes_matter",
        re.compile(r"commit(?:s|ted)? a crime|whenever you commit", re.IGNORECASE),
        "you",
    ),
    ("connive_matters", re.compile(r"\bconnives?\b", re.IGNORECASE), "you"),
    (
        "spell_copy_matters",
        re.compile(
            r"copy target (?:instant or sorcery spell|spell)|\bcopy that spell\b"
            r"|you may copy (?:it|that spell)|whenever you copy (?:a|an|target|that)",
            re.IGNORECASE,
        ),
        "you",
    ),
    # ── Effect-axis detectors: every ability is a direction to build around ──────
    (
        "ramp_matters",
        re.compile(
            r"\{t\}[^.]*:\s*add \{|add (?:one|two|three|four|five|x|\d+) mana"
            r"|add \{[wubrgc]\}",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Destroy/damage removal — the slice that indestructible & regeneration blank
        # (CR 701.8/702.12/702.19). Exile is a separate axis (bypasses those).
        "removal_matters",
        re.compile(
            r"destroy target "
            r"(?:creature|permanent|artifact|enchantment|planeswalker|nonland)"
            r"|deals? (?:\d+|x) damage to target (?:creature|permanent)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Exile removal — bypasses indestructible/regeneration and stops death/LTB
        # recursion (CR 406, 701.10). Distinct build axis from destroy/damage.
        "exile_removal",
        re.compile(
            r"exile target (?:creature|permanent|artifact|enchantment|nonland)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "counter_control",
        re.compile(
            r"counter target (?:spell|ability|activated|triggered)", re.IGNORECASE
        ),
        "you",
    ),
    (
        "team_buff",
        re.compile(
            r"(?:creatures?|permanents?) you control (?:gain|gains|have|has) "
            r"(?:flying|trample|menace|hexproof|indestructible|protection|deathtouch"
            r"|lifelink|double strike|first strike|vigilance|haste|ward|reach)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "tutor_matters",
        re.compile(
            r"search your library for (?:a|an|up to|one|two|three|x|that)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "untap_engine",
        re.compile(
            r"untap (?:target|another target|all|each|two|up to)", re.IGNORECASE
        ),
        "you",
    ),
    ("gain_control", re.compile(r"gain control of", re.IGNORECASE), "you"),
    (
        "opponent_discard",
        re.compile(
            r"(?:each opponent|target opponent|an opponent|that opponent"
            r"|target player|that player|each player) discards",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # "deals damage to an opponent" — ANY damage (not the literal "combat damage" the
    # combat_* keys require, per the rules-lawyer audit). The connect-trigger axis for
    # self-source pingers/evasion (Lu Xun, Zhang Liao) the tribe/combat keys miss.
    (
        "damage_to_opp_matters",
        re.compile(
            r"\bwhen(?:ever)?\b[^.]*?\bdeals (?:noncombat )?damage to "
            r"(?:a player|an opponent|one of your opponents|each opponent"
            r"|target opponent|that player|a player or planeswalker)\b",
            re.IGNORECASE,
        ),
        "opponents",
    ),
    # "another permanent you control enters" — the generic permanent-ETB value engine
    # (distinct from creature_etb, which needs the word "creature"). Amareth.
    (
        "permanent_etb",
        re.compile(
            r"\bwhen(?:ever)?\b[^.]*?\b(?:a|an|another|one or more|each) "
            r"(?:nonland |nontoken )?permanents? you control enters",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        # Evasion = a blocking RESTRICTION (CR 509.1b). "attacks if able" is a
        # forced-attack REQUIREMENT (CR 508.1d) — that belongs to forced_attack/goad.
        "evasion_self",
        re.compile(r"can't be blocked|\bunblockable\b", re.IGNORECASE),
        "you",
    ),
    (
        # Clone = a permanent that itself becomes/enters as a copy (CR 707). Drop the
        # bare "copy of target creature" branch — it bleeds into the token-copy phrase
        # "create a token that's a copy of target creature" (that's token_copy_matters).
        "clone_matters",
        re.compile(
            r"becomes a copy of|enters [^.]*as a copy of",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "cheat_into_play",
        re.compile(
            r"put [^.]*creature card[^.]*onto the battlefield"
            r"|put (?:a|that|those) [^.]*onto the battlefield from your "
            r"(?:hand|library)",
            re.IGNORECASE,
        ),
        "you",
    ),
    (
        "bounce_tempo",
        re.compile(
            r"return target (?:creature|permanent|nonland)[^.]*"
            r"to (?:its|their) owner's hand",
            re.IGNORECASE,
        ),
        "you",
    ),
    ("cascade_matters", re.compile(r"\bcascade\b", re.IGNORECASE), "you"),
    ("regenerate_matters", re.compile(r"\bregenerate\b", re.IGNORECASE), "you"),
)

# One registration path: the curated hand-written detectors plus the exhaustively-
# mined sweep (one ability-axis each, grounded in real oracle text), unified into a
# single Detector record type. Same-key sweep widens carry the complete merged regex,
# so the extractor's (key, scope, subject) dedup unions them with the hand originals.
_FLOOR_DETECTORS: tuple[Detector, ...] = tuple(
    Detector(key, scope, pattern) for key, pattern, scope in _HAND_FLOOR
) + tuple(
    Detector(d["key"], d["scope"], re.compile(d["regex"], re.IGNORECASE))
    for d in SWEEP_DETECTORS
)

# (preset_name → (signal_key, scope)). KEYWORD-ARRAY presets only — these read
# Scryfall's authoritative `keywords` array, the low-false-positive path. mill is
# scoped "any" (it can target self or opponents; Phase-B nested-scope refines it).
_PRESET_KEYWORD_SIGNALS = {
    "mill": ("mill_matters", "any"),
    "goad": ("goad_matters", "opponents"),
    "proliferate": ("proliferate_matters", "you"),
    "magecraft": ("magecraft_matters", "you"),
    # Prowess is a spellslinger payoff (cast noncreature spells) → same avenue.
    "prowess": ("spellcast_matters", "you"),
    # Storm/Casualty/Replicate/etc. are spell-copy keywords.
    "spell-copy": ("spell_copy_matters", "you"),
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


# Cross-sentence flicker: the blink preset's single-clause "exile…return…battlefield"
# regex can't span the period in "Exile target creature. Return that card to the
# battlefield" (Roon). Detect the exile + pronoun-return pair on the full text; the
# pronoun ("it"/"that card"/"them") gates out reanimation, which returns a *graveyard*
# card ("return target creature card … to the battlefield"), not the exiled object.
_BLINK_EXILE_RE = re.compile(
    r"\bexile (?:up to \w+ |any number of )?(?:another |one )?"
    r"target (?:creature|permanent|nonland permanent|artifact)",
    re.IGNORECASE,
)
# Pronoun-return only: "return the exiled card to the battlefield" is the O-ring
# signature (Journey to Nowhere / Fiend Hunter) — removal with a leaves-the-
# battlefield-delayed return, NOT a flicker engine. Real flicker pronominally
# references the exiled object (it / that card / those cards).
_BLINK_RETURN_RE = re.compile(
    r"\breturn (?:it|them|that card|those cards|that permanent) to the battlefield",
    re.IGNORECASE,
)


def _detect_blink_fulltext(text: str) -> str | None:
    """Grounding clause if the card is a cross-sentence flicker engine, else None."""
    if not (_BLINK_EXILE_RE.search(text) and _BLINK_RETURN_RE.search(text)):
        return None
    for clause in _clauses(text):
        if _BLINK_RETURN_RE.search(clause):
            return clause.strip()
    return text[:160]


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


# ── Phase B: nested-scope / self-reference resolvers behind a confidence flag ──
# A granted ability ("creatures you control have \"…\"") has an OUTER scope (who has
# it) and an INNER scope (who it affects); the flat parser can't resolve the inner
# confidently, so signals pulled from it are marked low confidence.
_GRANTED_ABILITY = re.compile(r'(?:have|gains?) "', re.IGNORECASE)
# Third-party possessive zones — the broad scope rule (deliberately excludes "its
# owner's" so it never flips the ~123 self-blink/self-bounce cards).
_BROAD_THIRD_PARTY = re.compile(
    r"that player's (?:graveyard|hand|library)"
    r"|each opponent's (?:graveyard|hand|library)"
    r"|target opponent's (?:graveyard|hand|library)"
    r"|their (?:graveyard|hand|library)\b",
    re.IGNORECASE,
)
_SELF_REF_MARKER = re.compile(r"\bthis (?:creature|permanent|land|card)\b|~")
_ARTICLES = frozenset({"the", "a", "an", "and", "of"})


def _self_reference(clause_lower: str, name: str) -> bool:
    """True if the clause refers to the card itself (own name or "this <type>")."""
    words = [
        w for w in re.split(r"\W+", name) if len(w) > 2 and w.lower() not in _ARTICLES
    ]
    if words and words[0].lower() in clause_lower:
        return True
    return _SELF_REF_MARKER.search(clause_lower) is not None


def _resolve_scope(
    clause: str, clause_lower: str, base_scope: str, name: str
) -> tuple[str, str]:
    """Resolve a clause's (scope, confidence) for unforced baseline detectors.

    The narrow Tinybones rule (high confidence) is applied separately and takes
    precedence. Otherwise: a granted ability is low-confidence (nested scope); a
    third-party possessive zone is an opponents guess (low confidence — the broad
    rule, on behind the flag); a self-reference resolves an otherwise-unscoped clause
    to "you" (high confidence)."""
    if _GRANTED_ABILITY.search(clause):
        return base_scope, "low"
    if _BROAD_THIRD_PARTY.search(clause_lower):
        return "opponents", "low"
    if base_scope == "any" and _self_reference(clause_lower, name):
        return "you", "high"
    return base_scope, "high"


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

    def add(
        key: str, scope: str, subject: str, clause: str, confidence: str = "high"
    ) -> None:
        ident = (key, scope, subject)
        if ident in seen:
            return
        seen.add(ident)
        out.append(
            Signal(
                key=key,
                scope=scope,
                subject=subject,
                text=clause,
                source=name,
                confidence=confidence,
            )
        )

    for clause in _clauses(text):
        stripped = clause.strip()
        cl = clause.lower()
        clause_scope = _scope(cl)
        rescope = _tinybones_scope(clause)
        # Phase B: (scope, confidence) for unforced baseline detectors.
        resolved_scope, resolved_conf = _resolve_scope(clause, cl, clause_scope, name)
        # Tier 1 — baseline (subject-free)
        for key, matches, forced_scope in _DETECTORS:
            if not matches(cl):
                continue
            if rescope:  # narrow Tinybones rule — confident
                scope, conf = rescope, "high"
            elif forced_scope:
                scope, conf = forced_scope, "high"
            else:
                scope, conf = resolved_scope, resolved_conf
            add(key, scope, "", stripped, conf)
        # Tier 2 — parametric subject detectors (forced scope=you: "you control")
        for key, subject in _detect_type_matters(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_typed_spellcast(clause, vocab):
            add(key, "you", subject, stripped)
        for key, subject in _detect_token_maker(clause, vocab):
            add(key, "you", subject, stripped)
        draw = _detect_card_draw(clause)
        if draw is not None:
            add(draw[0], draw[1], "", stripped)
        # Tier 3 — structural floor detectors + regex-preset reuse
        for det in _FLOOR_DETECTORS:
            if det.pattern.search(clause):
                add(det.key, det.scope, "", stripped)
        for key, scope in _detect_regex_presets(clause):
            add(key, scope, "", stripped)

    # Tier 3 — keyword-array presets (card-level, authoritative)
    for key, scope in _detect_keyword_presets(card):
        add(key, scope, "", text[:120])

    # Cross-sentence flicker (full text, not per-clause) — Roon and kin.
    blink_clause = _detect_blink_fulltext(text)
    if blink_clause is not None:
        add("blink_flicker", "you", "", blink_clause)

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
