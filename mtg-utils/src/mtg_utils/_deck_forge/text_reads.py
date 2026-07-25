"""Sanctioned bounded oracle-text patterns and text-detector helpers
that structural signal lanes and ledgered bridges still call.

Extracted 2026-07-25 from the retired regex/IR signal engines; every symbol
here is production-serving (imported by signals.py, structural lanes,
bridges, or the membership floor)."""

from __future__ import annotations

import re
from functools import lru_cache

from mtg_utils._deck_forge import signal_keys
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge._sweep_detectors import (
    ARTIFACTS_MATTER_REGEX,
    DAMAGE_REDIRECT_REGEX,
    DISCARD_OUTLET_REGEX,
    ENCHANTMENTS_MATTER_REGEX,
    LURE_MATTERS_REGEX,
    TOUGHNESS_VALUE_REGEX,
)
from mtg_utils._deck_forge.signal_base import (
    _clauses,
    _resolve_subject,
    _tinybones_scope,
)
from mtg_utils.card_classify import card_pt_int


@lru_cache(maxsize=4096)
def _rx_name(pattern: str) -> re.Pattern[str]:
    """Compile cache for the name-interpolated detector patterns. Per-card
    patterns overflow ``re``'s small module-level cache, so without this every
    detector call recompiled its pattern from scratch."""
    return re.compile(pattern, re.IGNORECASE)


_EVERGREEN_KW_WORDS = (
    "flying",
    "first strike",
    "double strike",
    "deathtouch",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
    "ward",
    "protection",
)


_EVERGREEN_CK: frozenset[str] = frozenset(
    kw.replace(" ", "") for kw in _EVERGREEN_KW_WORDS
)


_ETB_OPP_RE = re.compile(
    r"creature an opponent controls enters"
    r"|creatures? your opponents? control enter"
    r"|creature[s]?[^.]*enters?[^.]*under (?:an |your )?opponent",
    re.IGNORECASE,
)


_ETB_ANY_RE = re.compile(
    r"\b(?:a|another|one or more|each)\b[^.]*\bcreature[s]?\b[^.]*\benter",
    re.IGNORECASE,
)


_ETB_DOUBLER_RE = re.compile(r"entering[^.]*triggers an additional time", re.IGNORECASE)


_ETB_HAD_RE = re.compile(
    r"you had (?:a|an|another|one or more|\d+)[^.]*creatures? "
    r"enter the battlefield under your control",
    re.IGNORECASE,
)


def _creature_etb_clause(cl: str) -> str | None:
    """Scope ("you"|"opponents") the deleted creature_etb _DETECTORS rows would emit
    for one lowercased, reminder-stripped clause, or ``None``. The "you" row vetoes
    on an opponent-controlled entering creature; the "opponents" row is the punisher.
    """
    has_when = "whenever" in cl or "when " in cl
    opp = _ETB_OPP_RE.search(cl) is not None
    if opp and has_when:
        return "opponents"
    if (
        (_ETB_ANY_RE.search(cl) is not None and has_when)
        or _ETB_DOUBLER_RE.search(cl) is not None
        or _ETB_HAD_RE.search(cl) is not None
    ) and not opp:
        return "you"
    return None


_GY_YOUR_RE = re.compile(r"your graveyard")


_GY_EXILE_MILL_OPP_RE = re.compile(
    r"exile (?:the top|\w+ cards?|cards?)[^.]*"
    r"(?:target player'?s?|an opponent'?s?|each (?:player|opponent)'?s?"
    r"|that player'?s?) librar"
)


def _graveyard_matters_clauses(text: str, name: str) -> set[tuple[str, str]]:
    """All (``"graveyard_matters"``, scope) pairs the THREE deleted producers would emit
    over the reminder-stripped joined oracle, applied PER-CLAUSE with the exact scope
    logic of extract_signals's detector loop (Tinybones rescope wins; else the
    producer's forced scope; else the clause-resolved scope). Byte-identical to the
    deleted regex path so regex_only == 0."""
    out: set[tuple[str, str]] = set()
    for clause in _clauses(text):
        cl = clause.lower()
        rescope = _tinybones_scope(clause)
        clause_scope = _scope(cl)
        resolved_scope, _ = _resolve_scope(clause, cl, clause_scope, name)
        # (1) "your graveyard" — forced 'you' (rescope wins).
        if _GY_YOUR_RE.search(cl):
            out.add(("graveyard_matters", rescope or "you"))
        # (2) a bare "graveyard" mention (not "your graveyard") — clause-resolved scope.
        if "graveyard" in cl and "your graveyard" not in cl:
            out.add(("graveyard_matters", rescope or resolved_scope))
        # (3) exile-mill of an opponent's library — forced 'opponents'.
        if _GY_EXILE_MILL_OPP_RE.search(cl):
            out.add(("graveyard_matters", rescope or "opponents"))
    return out


_COLOR = r"(?:white|blue|black|red|green)"


_COLOR_HOSER_RE = re.compile(
    rf"(?:destroy|exile|return|counter) (?:target |all )?(?:\w+ )?{_COLOR} "
    rf"(?:creature|permanent|spell)"
    rf"|can'?t (?:cast|be cast|block|attack)[^.]{{0,30}}{_COLOR}"
    rf"|non{_COLOR} creatures? [^.]*get -"
    rf"|{_COLOR} creatures? (?:your |that your )?opponents control"
    rf"|choose a color, then (?:return|destroy|exile)",
    re.IGNORECASE,
)


_TYPE_HOSER_RE = re.compile(r"protection from (\w+)")


def _type_hoser_clause(cl: str) -> bool:
    return any(
        w in CREATURE_SUBTYPES or w.rstrip("s") in CREATURE_SUBTYPES
        for w in _TYPE_HOSER_RE.findall(cl)
    )


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


_TYPE_MATTERS_PATTERNS = (
    re.compile(r"\bother ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    # "another Elf you control" (singular) — tribal triggers the "other Xs" form misses.
    re.compile(r"\banother ([A-Za-z]+?) you control\b", re.IGNORECASE),
    # "a Spider you control enters/attacks/dies/deals …" — tribal trigger. A common
    # trigger verb follows (so a bare "a Goblin you control" can't over-capture); the
    # vocab gate drops "creature"/"permanent". Mary Jane Watson / Patron of the Nezumi
    # ("a Rat you control deals") / Sylvia ("a Dragon you control attack").
    re.compile(
        r"\b(?:a|an) ([A-Za-z]+?) you control "
        r"(?:enters|entering|attacks?|dies|deals|blocks?|becomes?|leaves)\b",
        re.IGNORECASE,
    ),
    # "each attacking Samurai" / "attacking Goblins" — tribal combat trigger (Nagao).
    re.compile(r"\b(?:each )?attacking ([A-Za-z]+?)s?\b", re.IGNORECASE),
    # "you control an Army" — reverse word order the "X you control" anchors miss; the
    # subtype-vocab gate keeps it precise (creature/artifact/Mountain drop out). Grond.
    re.compile(r"\byou control (?:a|an) ([A-Za-z]+?)\b", re.IGNORECASE),
    # "becomes a Samurai in addition to its other creature types" — type-granting that
    # adds a kindred subject (the "in addition" anchor keeps it off clone/animate).
    re.compile(r"\bbecomes? an? ([A-Za-z]+?) in addition\b", re.IGNORECASE),
    # "Other Elf creatures have …" (lord with no "you control"); tribal in an
    # activated cost ("untapped Wizard you control:" / "<Sub> you control:").
    re.compile(r"\bother ([A-Za-z]+?) creatures?\b", re.IGNORECASE),
    re.compile(r"\buntapped ([A-Za-z]+?) you control\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?) you control\s*:", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?)s? you control gets? [+\-](?:\d|x)", re.IGNORECASE),
    re.compile(r"\b(?:number of|for each) ([A-Za-z]+?)s? you control\b", re.IGNORECASE),
    # "the number of tapped Assassins you control" — a state adjective sits between the
    # count anchor and the tribe, so the bare anchor above captures the adjective (which
    # the vocab gate drops) and the tribe is lost. The fixed adjective set + subtype
    # vocab gate keep it precise (a "tapped creature" count still drops). Lydia Frye.
    re.compile(
        r"\b(?:number of|for each) "
        r"(?:tapped|untapped|attacking|blocking|nontoken|enchanted) "
        r"([A-Za-z]+?)s? you control\b",
        re.IGNORECASE,
    ),
    # Keyword-grant lord: "have"/"has" (static) and "gain"/"gains" (granted) — "Spirits
    # you control gain flying", "Knights you control gain double strike". The subtype
    # vocab gate keeps the generic "Creatures you control gain …" out.
    re.compile(r"\b([A-Za-z]+?)s? you control (?:ha(?:ve|s)|gains?)\b", re.IGNORECASE),
    # Global lords with no "you control" / "other": "Bird creatures get +1/+1"
    # (Soraya) or the singular "Each Fungus creature gets +1/+1" (Thelon). The
    # subtype-vocab gate drops "all"/"other"/"creature" so only a real tribe sticks.
    re.compile(r"\b([A-Za-z]+?) creatures? gets? [+\-](?:\d|x)", re.IGNORECASE),
    # The canonical tribal lord "Goblin creatures you control get +1/+1" — "you control"
    # sits between the tribe and the verb, so the adjacency patterns above and the "Xs
    # you control get" pattern (which captures "creatures") both miss it. 351 cards.
    re.compile(
        r"\b([A-Za-z]+?) creatures? you control (?:gets?|have|has|gains?)\b",
        re.IGNORECASE,
    ),
    # Multiplayer "your team controls" (Sylvia: "Dragons your team controls have …").
    re.compile(
        r"\b([A-Za-z]+?)s? your team controls? (?:have|has|get|gain)\b", re.IGNORECASE
    ),
    # Offering mechanic (Patron cycle): "Rat offering" / "Dragon offering" sacrifices a
    # tribe member to cast — so the commander is that tribe.
    re.compile(r"\b([A-Za-z]+) offering\b", re.IGNORECASE),
    # "for each Rat on the battlefield" — a tribal count payoff with no "you control"
    # (Patron's discard channel counts Rats). Vocab gate keeps it to real tribes.
    re.compile(
        r"\bfor each ([A-Za-z]+?)s? (?:on the battlefield|you control)\b", re.IGNORECASE
    ),
    # Evasion-grant lord: "Boars you control can't be blocked …" (Rocksteady — a
    # Rhino Mutant buffing Boars, so type-line membership can't supply the tribe).
    # The vocab gate drops the generic "Creatures you control can't be blocked".
    re.compile(r"\b([A-Za-z]+?)s? you control can't be blocked\b", re.IGNORECASE),
    # Tribal SUPPORT that never says "Xs you control": a commander that BUFFS a TARGET
    # of a type (Owen Grady: "put a … counter on target Dinosaur"; Otepec: "target
    # Dinosaur gains haste"), TUTORS the tribe ("search … for a Dragon card" — Sivitri),
    # WRATHS around it ("destroy all non-Dragon creatures" — Sivitri, Liliana Death's
    # Majesty), or COST-REDUCES its spells ("Dragon spells you cast cost {1} less" —
    # Nogi) is that tribe's commander. The subtype-vocab gate (_resolve_subject) keeps
    # each precise; "destroy ALL non-X" excludes the non-X drawback/reward forms (Yukora
    # "sacrifice all non-Ogre", Anim Pakal "attack with non-Gnome").
    re.compile(r"counter on target ([A-Za-z]+?)\b", re.IGNORECASE),
    re.compile(r"\btarget ([A-Za-z]+?) (?:gains?|gets [+\-])", re.IGNORECASE),
    re.compile(
        r"\bsearch (?:your library )?for (?:a|an) ([A-Za-z]+?)"
        r"(?: (?:permanent|creature|nonland|artifact|enchantment))? card",
        re.IGNORECASE,
    ),
    re.compile(r"\bdestroy all non-([A-Za-z]+?) creatures?\b", re.IGNORECASE),
    re.compile(r"\b([A-Za-z]+?) spells you cast cost\b", re.IGNORECASE),
    # Tribal-spell payoff phrased as "<Tribe> creature spell": a commander that casts /
    # cost-reduces / copies "Dragon creature spells" (Rivaz), "Zombie creature spells"
    # (Gisa and Geralf), or "Beast creature spells" (Tawnos) is that tribe. The bare
    # "X spells you cast cost" pattern captures "creature", not the tribe.
    re.compile(r"\b([A-Za-z]+?) creature spells?\b", re.IGNORECASE),
    # Tribal evasion-grant on a single target with no "you control" anchor: "target
    # Ninja can't be blocked" (Splinter, a Ninja-tribal payoff). The vocab gate drops
    # the bare "target creature can't be blocked".
    re.compile(r"\btarget ([A-Za-z]+?) can't be blocked", re.IGNORECASE),
    # "(a|an) <Tribe> [permanent/creature] card/spell": finditer captures EVERY tribe in
    # a multi-tribe reveal/cast/return list the single-capture patterns miss. Kaalia
    # ("an Angel card, a Demon card, and/or a Dragon card"), Disa ("a Lhurgoyf permanent
    # card"), Eivor ("a Saga card"). Vocab-gated: "a creature card" / "a land" drop out.
    re.compile(
        r"\b(?:a|an) ([A-Za-z]+?)(?: (?:permanent|creature|nonland))? (?:card|spell)\b",
        re.IGNORECASE,
    ),
)


_TWO_TRIBE_TRIGGER_RE = re.compile(
    r"\b(?:a|an) ([A-Za-z]+?) or ([A-Za-z]+?) you control "
    r"(?:enters|attacks?|dies|deals|blocks?)\b",
    re.IGNORECASE,
)


_TYPE_GRANT_RE = re.compile(
    r"(?:is|are|becomes?|it's) (?:a |an )?([A-Za-z]+?)s? "
    r"in addition to (?:its|their) other(?: creature)? types",
    re.IGNORECASE,
)


_TRIBE_LIST_RE = re.compile(
    r"\b(?:a|an) ((?:[A-Za-z]+, )+(?:or )?[A-Za-z]+)(?: creature)? (?:card|spell)s?\b",
    re.IGNORECASE,
)


_TWO_TRIBE_SPELL_RE = re.compile(
    r"\b(?:a|an) ([A-Za-z]+) or ([A-Za-z]+) creature spells?\b", re.IGNORECASE
)


_TWO_TRIBE_TUTOR_RE = re.compile(
    r"\bsearch (?:your library )?for (?:a|an) ([A-Za-z]+) or ([A-Za-z]+) card",
    re.IGNORECASE,
)


_TOKEN_MAKER_PATTERN = re.compile(r"create [^.]*?\bcreature tokens?\b", re.IGNORECASE)


_TOKEN_SUBJECT_WORDS = re.compile(r"\b([A-Z][a-z]+)\b")


def _detect_type_matters(clause: str, vocab: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pat in _TYPE_MATTERS_PATTERNS:
        for m in pat.finditer(clause):
            subject = _resolve_subject(m.group(1), vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Two-tribe head ("a Goblin or Orc you control deals …"): emit for BOTH sides.
    for m in _TWO_TRIBE_TRIGGER_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Multi-tribe comma list ("a Kraken, Leviathan, Octopus, or Serpent spell"): emit
    # for EVERY listed type.
    for m in _TRIBE_LIST_RE.finditer(clause):
        for raw in re.findall(r"[A-Za-z]+", m.group(1)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Two-tribe creature spell ("a Beast or Bird creature spell"): emit for BOTH.
    for m in _TWO_TRIBE_SPELL_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Two-tribe tutor ("search for a Lesson or Noble card"): emit for BOTH.
    for m in _TWO_TRIBE_TUTOR_RE.finditer(clause):
        for raw in (m.group(1), m.group(2)):
            subject = _resolve_subject(raw, vocab)
            if subject:
                out.append((signal_keys.TYPE_MATTERS, subject))
    # Type GRANT ("it's a Zombie in addition to its other creature types"): the
    # commander converts its board to that tribe → wants that tribe's lords.
    for m in _TYPE_GRANT_RE.finditer(clause):
        subject = _resolve_subject(m.group(1), vocab)
        if subject:
            out.append((signal_keys.TYPE_MATTERS, subject))
    return out


_MULTI_TRIBE_HEAD_RE = re.compile(
    r"creatures? (?:you control )?that(?:'s| is| are)\b(.{0,80}?)"
    r"\b(?:gets?|have|has|gains?)\b",
    re.IGNORECASE,
)


_MULTI_TRIBE_LIST_RE = re.compile(
    r"\bother ([A-Za-z]+(?:, (?:and |or )?[A-Za-z]+)+) you control "
    r"(?:gets?|have|has|gains?)\b",
    re.IGNORECASE,
)


def _detect_multi_tribe_anthem(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for pattern in (_MULTI_TRIBE_HEAD_RE, _MULTI_TRIBE_LIST_RE):
        for m in pattern.finditer(clause):
            for word in re.findall(r"[A-Za-z]+", m.group(1)):
                subject = _resolve_subject(word, vocab)
                if subject:
                    out.append((signal_keys.TYPE_MATTERS, subject))
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
        out.append((signal_keys.TOKEN_MAKER, chosen))
    return out


_TYPED_GY_RECUR_PATTERN = re.compile(
    r"\breturn (?:target |all |each |up to \w+ target )?([A-Za-z]+) cards?\b"
    r"[^.]*from (?:your|a) graveyard[^.]*(?:to|onto) the battlefield",
    re.IGNORECASE,
)


def _detect_typed_gy_recursion(
    clause: str, vocab: frozenset[str]
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for m in _TYPED_GY_RECUR_PATTERN.finditer(clause):
        raw = m.group(1).lower()
        if raw == "vehicle":
            out.append(("vehicles_matter", "you", ""))
            continue
        subject = _resolve_subject(m.group(1), vocab)
        if subject:
            out.append((signal_keys.TYPE_MATTERS, "you", subject))
    return out


_KEYWORD_IMPLIES_TRIBE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bninjutsu\b"), "Ninja"),
)


def _detect_keyword_implied_tribe(clause: str) -> list[tuple[str, str]]:
    return [
        (signal_keys.TYPE_MATTERS, subj)
        for pat, subj in _KEYWORD_IMPLIES_TRIBE
        if pat.search(clause)
    ]


_ABILITY_KEYWORDS = frozenset(
    {
        "flying",
        "deathtouch",
        "vigilance",
        "trample",
        "lifelink",
        "menace",
        "reach",
        "haste",
        "hexproof",
        "indestructible",
        "defender",
        "flash",
        "ward",
        "shroud",
        "fear",
        "intimidate",
        "horsemanship",
        "prowess",
        "skulk",
        "wither",
        "infect",
        "persist",
        "undying",
        "flanking",
        "banding",
        "shadow",
        "exalted",
    }
)


_KW_TRIBE_RE = re.compile(
    r"\b(?:other )?([A-Za-z]+) creatures you control\b", re.IGNORECASE
)


_KEYWORD_TRIBE_PATTERNS = (
    # "Flying creatures you control …" / "other Flying creatures …"
    (_KW_TRIBE_RE, "you"),
    (re.compile(r"\bother ([A-Za-z]+) creatures\b", re.IGNORECASE), "you"),
    # "creatures you control with deathtouch …" PLUS the SINGULAR forms a fliers-matter
    # (or any keyword-tribe) commander uses: "creature you control with flying" /
    # "creature spell with flying" (Momo). The "you control"/"spell" qualifier is
    # REQUIRED so anti-tribe removal ("destroy all creatures with flying") stays out;
    # the _ABILITY_KEYWORDS gate validates the captured word.
    (
        re.compile(
            r"\bcreatures? (?:you control |spell )with ([A-Za-z]+)\b", re.IGNORECASE
        ),
        "you",
    ),
    # "all creatures with deathtouch …" (symmetric)
    (
        re.compile(
            r"\bcreatures with ([A-Za-z]+)\b[^.]{0,20}?"
            r"(?:gets? [+\-]|have \"|gains?\b)",
            re.IGNORECASE,
        ),
        "any",
    ),
    # "cast spells with flash or flying from the top …" (Errant and Giada) — a
    # play-from-top engine gated on a keyword rewards that keyword's tribe (here
    # fliers). Capture the second keyword; the _ABILITY_KEYWORDS gate validates it.
    (
        re.compile(
            r"cast spells with flash or ([A-Za-z]+) from the top", re.IGNORECASE
        ),
        "you",
    ),
    # Keyword-tribe TUTOR (Isperia: "search your library for a creature card with
    # flying"): fetching a keyworded creature card IS a keyword-tribe payoff — the
    # "card" form the "you control"/"spell" patterns above didn't cover. Anchored on a
    # FETCH verb (search / reveal) so a self-gain card that buffs off any graveyard ("as
    # long as a creature card with flying is in a graveyard" — Cairn Wanderer) stays
    # out. The _ABILITY_KEYWORDS gate still validates the captured word.
    (
        re.compile(
            r"(?:search(?:es)? (?:their|your) library for|reveal)"
            r"[^.]{0,40}creature cards? with ([A-Za-z]+)",
            re.IGNORECASE,
        ),
        "you",
    ),
)


def _detect_keyword_tribe(clause: str) -> list[tuple[str, str, str]]:
    # ADR-0027: keyword_tribe is migrated to the Card IR. extract_signals no longer
    # calls this (the regex path must not emit the migrated key); it is now imported
    # by _signals_ir and run PER-CLAUSE over the reminder-stripped kept_oracle as a
    # byte-identical KEPT MIRROR. The mirror preserves the keyword subject (Flying,
    # Deathtouch, …) the per-subject serve spec interpolates — phase's WithKeyword
    # predicate covers ~70 of the 87 but a structural arm loses ~19 tail cards phase
    # folds keyword-less (tutors, P/T-scaling, granted-fly), so the byte-mirror (not
    # a structural arm) is the clean shape: commander-legal residual both==87,
    # ir_only==0, regex_only==0; flat-over-kept_oracle == per-clause (0 divergences).
    out: list[tuple[str, str, str]] = []
    for pat, scope in _KEYWORD_TRIBE_PATTERNS:
        for m in pat.finditer(clause):
            kw = m.group(1).lower()
            if kw in _ABILITY_KEYWORDS:
                out.append((signal_keys.KEYWORD_TRIBE, scope, kw.capitalize()))
    return out


_LURE_MATTERS_PLAN_MIRROR = re.compile(LURE_MATTERS_REGEX, re.IGNORECASE)


_VOLTRON_EQUIP_RE = re.compile(
    r"equipped creature|enchanted creature|\breconfigure\b|\bequip \{"
    r"|attach[^.]*(?:equipment|aura)|aura[^.]{0,30}equipment|equipment[^.]{0,30}aura"
    r"|cast an? (?:aura|equipment)|(?:equipment|aura)s? you control"
    r"|for each (?:equipment|aura)",
    re.IGNORECASE,
)


def _voltron_self_pump(text: str, name: str) -> bool:
    """True if the commander GROWS ITSELF on combat damage (Mirri: 'whenever Mirri deals
    combat damage …, put a +1/+1 counter on Mirri') — the canonical voltron growth loop.
    Self-scoped (this creature / itself / its name) so a counter placed on 'target' /
    'another' / 'each' creature (a go-wide counters payoff) does NOT qualify."""
    alts = "|".join(["this creature", "itself", *_self_name_alts(name)])
    pat = re.compile(
        rf"deals combat damage[^.]*put a \+1/\+1 counter on (?:{alts})\b", re.IGNORECASE
    )
    return pat.search(text) is not None


def _voltron_self_unblockable(text: str, name: str) -> bool:
    """True if the COMMANDER ITSELF can't be blocked (Tromokratis) — an unblockable fat
    body is a prime voltron threat. Self-scoped so a grant to 'target creature you
    control' / 'creatures you control' (go-wide evasion — Bria) does NOT qualify;
    parenthetical landwalk reminders are already stripped before this runs."""
    alts = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    pat = re.compile(rf"(?:{alts}) can'?t be blocked", re.IGNORECASE)
    return pat.search(text) is not None


def _voltron_self_heroic(text: str, name: str) -> bool:
    """True if the COMMANDER has a SELF-targeting heroic trigger ("whenever you cast a
    spell that targets [itself]", CR 702.86-style: Brigone, Feather, Anax and Cymede).
    Casting an Aura/pump spell on it fires heroic AND suits it up, so it's a single-big-
    threat voltron deck. Self-scoped (this creature / its name) so a trigger targeting
    'another' / 'target creature you control' (a go-wide granter) doesn't qualify."""
    alts = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    pat = re.compile(
        rf"whenever you cast (?:a |an |your )?(?:noncreature )?spell that targets "
        rf"(?:only )?(?:{alts})\b",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _voltron_land_scaler(text: str, name: str) -> bool:
    """True if the COMMANDER's OWN power equals a basic-land-type count (Sima Yi: "Sima
    Yi's power is equal to the number of Swamps you control") — a single mono-color
    scaling threat whose top synergy is the land-scaling equipment that suits it up
    (Nightmare Lash, Lashwrithe). Self-scoped (its name / this creature) so a team
    anthem setting OTHERS' power by a land count isn't read as a suit-up threat."""
    alts = "|".join(["this creature", *_self_name_alts(name)])
    pat = re.compile(
        rf"(?:{alts})'?s power (?:is )?equal to the number of "
        r"(?:plains|islands?|swamps?|mountains?|forests?) you control",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


def _voltron_self_recurs(text: str, name: str) -> bool:
    """True if the COMMANDER returns ITSELF from the graveyard to the battlefield —
    "return Akuta from your graveyard to the battlefield" (Akuta, Calim): a resilient,
    hard-to-keep-dead threat, hence a prime equipment carrier (voltron, like the
    hexproof tell). Self-scoped (its name / this creature) so a reanimation effect
    returning ANOTHER creature doesn't qualify."""
    alts = "|".join(["this creature", "itself", *_self_name_alts(name)])
    pat = re.compile(
        rf"return (?:{alts}) from (?:your|its owner's) graveyard to the battlefield",
        re.IGNORECASE,
    )
    return pat.search(text) is not None


_VOLTRON_TOKEN_MAKE_RE = re.compile(r"create[^.]*token", re.IGNORECASE)


def _voltron_double_strike_beater(card: dict, text: str) -> bool:
    """True if the commander ITSELF has double strike (Scryfall keyword) and a real body
    (power >= 4) and is NOT a token go-wide engine — a single beater that doubles every
    equipment/aura bonus, so a prime voltron threat (Sabin, Leonardo). The power>=4 +
    no-"create token" gate excludes the double-strike go-wide token-makers (Oketra) that
    are the documented over-fire class for an ungated double-strike rule."""
    kws = {k.lower() for k in (card.get("keywords") or [])}
    if "double strike" not in kws:
        return False
    return card_pt_int(card) >= 4 and not _VOLTRON_TOKEN_MAKE_RE.search(text)


_DISCARD_OUTLET_SWEEP_RE = re.compile(DISCARD_OUTLET_REGEX, re.IGNORECASE)


_PLAY_FROM_TOP_MIRROR = re.compile(
    r"(?:may )?play (?:the )?top card of (?:your|their) library"
    r"|you may look at the top card of your library (?:any time|at any time)"
    r"|play with the top card of your library revealed"
    r"|(?:play|cast) (?:lands?|spells?|creature spells?)[^.]*from the top of your "
    r"library",
    re.IGNORECASE,
)


_PLAY_FROM_TOP_FLOOR_MIRROR = re.compile(
    r"(?:play|cast)\b[^.]*?\bfrom the top of your library",
    re.IGNORECASE,
)


_MELD_FULLTEXT_RE = re.compile(r"\bmeld them into\b|\bmelds with\b", re.IGNORECASE)


_SELF_ETB_PAYOFF = (
    # The whole alternation is wrapped in ONE (?:...) group. Without it, the trailing
    # "|choose …" alternative floats to the TOP of the interpolated _self_etb_value
    # pattern and matches a bare "choose one" ANYWHERE — e.g. a DEATH modal ("When ~
    # dies, choose one") — instead of staying anchored under "when ~ enters". (Guarded
    # by test_self_etb_modal_choose_requires_enters_not_dies.)
    r"(?:\b(?:draws?|create|creates|search|searches|look at|reveal|returns?"
    r"|gains? control|put[^.]*counter|mills?|investigate|scry|draft|copy"
    # Damage ETBs are value (Flametongue Kavu — flicker re-fires the burn): numeric
    # "deals N damage" AND the variable forms "deals X damage" / "deals damage equal
    # to …" (Dong Zhou, Ureni, Themberchaud, Jet). Distinct from exile/destroy removal
    # (the O-Ring exclusion), which carries no "deals … damage".
    r"|deals? (?:\d+|x) damage|deals? damage equal to)\b"
    # Modal ETBs ("When ~ enters, choose one —") are value triggers; the value verbs
    # sit in the bullet modes (separate clauses), so credit the modal template itself
    # (CR 700.2). "choose one/two/three/up to" is the modal marker — narrower than bare
    # "choose". Catches Donnie & April, Charming Prince, Aether Channeler.
    r"|choose (?:one|two|three|up to)"
    r")"
)


def _detect_self_damage_prevention(text: str, name: str) -> bool:
    """True if the commander prevents/redirects ALL damage dealt to ITSELF (Cho-Manno,
    Anti-Venom) — the unkillable Pariah redirect target. Name-aware so a generic fog
    ('prevent all combat damage this turn') doesn't qualify."""
    alts = "|".join(["this creature", "~", *_self_name_alts(name)])
    pat = _rx_name(
        r"(?:prevent all damage that would be dealt to"
        r"|if damage would be dealt to) "
        rf"(?:{alts})\b"
    )
    return pat.search(text) is not None


@lru_cache(maxsize=4096)
def _self_name_alts(name: str) -> tuple[str, ...]:
    """Regex-escaped ways a card's oracle refers to itself BY NAME: the short name
    (everything before the first comma — 'Spider-Byte', 'Donnie & April', 'Black Cat')
    and the first meaningful token (legacy nickname forms). Oracle self-references use
    the short name, which may be hyphenated / two-named / multi-word, so keying on the
    first token alone misses them ('Spider' is followed by '-Byte', not ' enters')."""
    alts: list[str] = []
    short = name.split(",", maxsplit=1)[0].strip()
    if short:
        alts.append(re.escape(short))
    for w in re.split(r"\W+", name):
        if len(w) > 2 and w.lower() not in _ARTICLES:
            tok = re.escape(w)
            if tok not in alts:
                alts.append(tok)
            break
    return tuple(alts)


def self_power_scale_match(text: str, name: str) -> bool:
    """True for the self-power-scaling cross-open tell ADR-0027 β re-homed from the
    deleted self_counter_grow _DETECTORS add: an effect whose value scales with the
    SOURCE's OWN power ("X is ~'s power", "equal to this creature's power" — Mona Lisa,
    Esper Sentinel, Velomachus Lorehold). Such a commander wants +1/+1 counter sources
    to pump its own power, so it opens self_counter_grow as a low-confidence cross-open.
    Name-aware (the card's own name + "this creature", NOT "its") so a fling's "target
    creature's power" stays out. Reused by the narrowed _SELF_COUNTER_GROW_MIRROR in
    _signals_ir so the migration keeps this cross-open out of extract_signals. CR
    122.1."""
    _self = "|".join(["this creature", "this permanent", *_self_name_alts(name)])
    return bool(
        _rx_name(
            rf"(?:equal to|x is|x equals?|where x is) [^.]*?(?:{_self})[^.]*?\bpower\b"
        ).search(text)
    )


def _self_etb_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self enters-the-battlefield VALUE trigger."""
    alts = "|".join(["this creature", "this permanent", "~", *_self_name_alts(name)])
    # when(?:ever)? + enters? — catch "WHENEVER ~ enters" (Roxanne) and the plural
    # "enter" of two-name commanders ("When Donnie & April enter").
    pat = _rx_name(rf"\bwhen(?:ever)? (?:{alts}) enters?\b[^.]*?{_SELF_ETB_PAYOFF}")
    for clause in _clauses(text):
        if pat.search(clause):
            return clause.strip()
    return None


_SELF_DIES_PAYOFF = (
    r"\b(?:gains? control|loses? \d+ life|lose life|each opponent|each player"
    r"|draws?|returns?|create|creates|destroys?|exiles?"
    # Numeric AND variable damage (Orca: "deals damage equal to its power").
    r"|deals? (?:\d+|x) damage|deals? damage equal to"
    r"|put[^.]*counter|skips?)\b"
)


def _self_dies_value(text: str, name: str) -> str | None:
    """Grounding clause if the card has a self DIES VALUE trigger — a clone/token copy
    re-fires it when the copy dies (Keiga, Kokusho). Name-aware (short name like
    Scryfall prints) so 'When Keiga dies' matches."""
    alts = "|".join(["this creature", "this permanent", "~", *_self_name_alts(name)])
    pat = _rx_name(rf"\bwhen (?:{alts}) dies\b[^.]*?{_SELF_DIES_PAYOFF}")
    for clause in _clauses(text):
        if pat.search(clause):
            return clause.strip()
    return None


_GRANTED_ABILITY = re.compile(r'(?:have|gains?) "', re.IGNORECASE)


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


_BASE_PT_RAW_HOOK = re.compile(r"base power|base toughness", re.IGNORECASE)


_BASE_PT_ANIMATE_HOOK = re.compile(
    r"\b\d+/\d+\b[^.]*\bin addition to its other types", re.IGNORECASE
)


_SELF_PROTECTION_GRANT_KW: frozenset[str] = frozenset(
    {"hexproof", "indestructible", "protection", "shroud", "ward"}
)


_COUNTER_KIND_KEYS: dict[str, tuple[str, str]] = {
    "m1m1": ("minus_counters_matter", "you"),
    "oil": ("oil_counter_matters", "you"),
    "shield": ("shield_counter_makers", "you"),
    "rad": ("rad_counter_makers", "opponents"),
    "ki": ("ki_counter_matters", "you"),
    # NB: lore counters do NOT map here — saga_matters fires from a `saga` marker
    # (project._dropped_static_markers, the "lore counter" / "Saga you control" face
    # reference), NOT every lore placement (a vanilla Saga's intrinsic chapter
    # advancement is not a build-around tell — the reminder is stripped, matching the
    # regex).
}


_NAMED_COUNTER_KINDS: frozenset[str] = frozenset(
    {
        "egg",
        "divinity",
        "prey",
        "bounty",
        "bribery",
        "page",
        "study",
        "knowledge",
        "silver",
        "gold",
        "fate",
        "incubation",
    }
)


_KEYWORD_COUNTER_KINDS: frozenset[str] = frozenset(
    {
        "flying",
        "menace",
        "trample",
        "reach",
        "haste",
        "deathtouch",
        "hexproof",
        "indestructible",
        "lifelink",
        "vigilance",
        "firststrike",
        "doublestrike",
    }
)


_OPP_COUNTER_BENEFICIAL: frozenset[str] = (
    frozenset({"p1p1", "shield"}) | _KEYWORD_COUNTER_KINDS
)


_LAND_SUBTYPES: frozenset[str] = frozenset(
    {
        "plains",
        "island",
        "swamp",
        "mountain",
        "forest",
        "wastes",
        "desert",
        "gate",
        "lair",
        "locus",
        "urza's",
        "mine",
        "power-plant",
        "tower",
        "cave",
        "sphere",
    }
)


_CONVOKE_RAW = re.compile(r"\bconvoke\b", re.IGNORECASE)


_POWER_SCALING_RAW = re.compile(
    r"(?:equal to|where x is|x is)[^.]*\bpower\b|greatest power", re.IGNORECASE
)


_PROLIFERATE_REMOVE_COST_RE = re.compile(
    r"remove (?:a|an|one|two|three|x|\d+) (?:\w+ )?counters? from "
    r"[^:.\n]{0,40}:",
    re.IGNORECASE,
)


_FIGHT_RAW = re.compile(
    r"\bfights? (?:up to (?:one|two|\d+) )?(?:other |another )?target\b"
    r"|\bfights? (?:up to (?:one|two) )?(?:other )?creature"
    r"|\bfight each other\b|\bfights? it\b|\bfights? (?:another|each)\b",
    re.IGNORECASE,
)


_GOAD_STYLE_FORCE = re.compile(
    r"target creature[^.]*attacks?[^.]*\bif able\b", re.IGNORECASE
)


_DAMAGE_REDIRECT_MIRROR = re.compile(DAMAGE_REDIRECT_REGEX, re.IGNORECASE)


_TOUGHNESS_VALUE_MIRROR = re.compile(TOUGHNESS_VALUE_REGEX, re.IGNORECASE)


_ARTIFACTS_MATTER_MIRROR = re.compile(
    r"(?:"
    + ARTIFACTS_MATTER_REGEX
    + r")|(?:if you control an artifact"
    + r"|if you control (?:a|an|one or more) artifacts?)",
    re.IGNORECASE,
)


_ENCHANTMENTS_MATTER_MIRROR = re.compile(
    ENCHANTMENTS_MATTER_REGEX,
    re.IGNORECASE,
)


_STAX_TAXES_RESIDUE_RE = re.compile(
    # pillowfort attack-lock (protects a player) + opponent cast/activate lock.
    # ADR-0027 C6 final: `\bwith\b` (not bare `with`, which matched INSIDE "without"
    # — "Enchant creature WITHOUT flying") and `[^.\n]*` (not `[^.]*`, which BRIDGED
    # the newline to the next line's "can't attack") so a single-target pacify Aura
    # whose two lines are one un-split clause (Trapped in the Tower) no longer fires.
    # `(?<!target )` keeps a single-target "target creature an opponent controls can't
    # attack" pacify (Spara's Adjudicators ETB) out — genuine board pillowfort never
    # says "target" (it's a class-wide static the structural scope='opp' arm carries).
    r"(?<!target )creatures? "
    r"(?:\bwith\b|you don't control|an opponent controls)[^.\n]*can't attack"
    r"|can't attack you\b"
    # ADR-0027 #24 (SIDECAR v52): the "your opponents can't cast" cast-lock is now
    # recovered structurally (supplement `_recover_opponent_cast_lock` → a
    # restriction Effect scope='opp' the structural stax arm reads), so the
    # opponent-can't branch DEFERS to it via `(?! cast)` — it still covers the
    # non-cast opponent locks phase drops ("opponents can't gain life / win the
    # game / search / block …", Archfiend of Despair, Platinum Angel, Stranglehold)
    # but no longer the structurally-load-bearing cast sub-case (Dromoka, Marisi,
    # Myrel, Tidal Barracuda, Conqueror's Flail, Narset Transcendent's emblem).
    # The one residue kept is the genuinely-UNSTRUCTURABLE tail: a named cast-lock on
    # a split/aftermath face phase emits NO record for (Failure // Comply — "your
    # opponents can't cast spells with the chosen name"), where the build-time
    # joined-oracle supplement can't see the dropped face.
    r"|\bopponents? can't\b(?! cast)|opponents? can't cast spells with\b"
    r"|spells your opponents cast cost"
    # OVER-FIRE branch `creatures your opponents control` DROPPED here.
    r"|(?:target player|that player|each player|a player|that opponent"
    # one-sided controller tax — "enchanted creature's controller can't cast"
    # (Brand of Ill Omen) restricts a PLAYER, CR 109.5; the pacify guard keeps it.
    r"|(?:enchanted |equipped )?creature['\u2019]s controller)"
    r"[^.]{0,90}?can't (?:cast|activate|attack|block|search|untap|draw)"
    r"|must pay \{?\d?\}?[^.]*additional"
    r"|spells?[^.]*cost \{?\d+\}? more to (?:cast|activate)"
    r"|noncreature spells?[^.]*cost(?:s)? \{?\d"
    r"|noncreature spells?[^.]*can't be cast"
    r"|spells? with mana value \d[^.]*can't be cast"
    r"|players? can't cast|that player can't cast spells|spells can't be cast"
    r"|can cast spells only|your opponents control enter(?:s)? tapped"
    r"|nonbasic lands enter(?:s)? tapped|costs? players \{?\d+\}? more"
    r"|doing the chosen action costs"
    r"|players? can't pay life or sacrifice nonland permanents",
    re.IGNORECASE,
)


_SYMMETRIC_STAX_RESIDUE_RE = re.compile(
    # symmetric "players can't <verb>" lock + symmetric enters-tapped. OVER-FIRE branch
    # `(?:doesn't|don't|does not) untap during` (single-target removal) DROPPED here.
    r"players? can't (?:cast|untap|attack|gain|search their|draw|play|activate)"
    r"|other permanents enter (?:the battlefield )?tapped",
    re.IGNORECASE,
)


_TYPED_ANTHEM_MULTI_RAW = re.compile(
    r"that's (?:an? )?[A-Z][a-z]+(?:,? (?:an? )?[A-Z][a-z]+)*,? or (?:an? )?[A-Z][a-z]+"
)


_ACTIVATED_ABILITY_DROP_EFFECTS: frozenset[str] = frozenset({"ramp", "attach"})


_SAME_TRUE_KW_RE = re.compile(r"the same is true for", re.IGNORECASE)


_PLAYER_BOARD_RESTR_RE = re.compile(
    r"\benchanted player\b|\byour opponents?\b|\beach (?:other )?player\b"
    r"|\bplayers? can't\b|\ball players\b|\bthat opponent\b"
    # genitive player tell — "enchanted creature's controller can't cast" restricts a
    # PLAYER (the controller), not the creature (Brand of Ill Omen); CR 109.5.
    r"|\b(?:creature|permanent)['\u2019]?s controller\b"
    r"|\beach creature\b|\ball creatures\b|\bnonland permanents\b"
    r"|\bcreatures (?:you|they|your opponents|an opponent|each player)\b"
    # board pillowfort — a class of creatures (by keyword / controller) can't attack:
    # "creatures with power N or less can't attack you", "creatures you don't control".
    r"|\bcreatures? (?:with\b|you don't control|an opponent controls)",
    re.IGNORECASE,
)


_SINGLE_CREATURE_RESTR_RE = re.compile(
    r"\benchanted creature\b|\bequipped creature\b|\benchanted permanent\b"
    r"|\bequipped permanent\b|\bthat creature\b|\btarget creature\b",
    re.IGNORECASE,
)


def _restriction_pacifies_single_creature(raw: str) -> bool:
    """True when a restriction's AFFECTED ENTITY is a single creature/permanent — a
    single-target pacify/removal (CR 303.4 / 301.5 / 608.2), so it must open NEITHER
    stax lane regardless of how its subject/scope projected.

    A PLAYER/BOARD tax tell ("enchanted player", "your opponents", "each player",
    "players can't", "creatures you/they control") OVERRIDES — a clause that restricts a
    player or the whole board is a genuine tax even when it also names a creature (an
    "Enchant player" Curse, a board pillowfort), so it KEEPS firing. ADR-0027 C6 final —
    the AFFECTED-ENTITY discriminator that replaces the over-broad card-type gate
    (an Aura/Equipment can carry a player/board tax — CR 303.4)."""
    r = raw or ""
    if _PLAYER_BOARD_RESTR_RE.search(r):
        return False
    return bool(_SINGLE_CREATURE_RESTR_RE.search(r))
