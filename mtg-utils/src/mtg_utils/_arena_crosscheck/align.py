"""Pair an Arena ability with the phase ability it is.

Arena names an ability by its own id and rules text (``CARDNAME`` for the card);
phase writes each ability's text as its ``description`` (``~`` for the card). A
pairing is **confident** only when the texts are near-identical (:data:`CONFIDENT`)
or the same but for a cost one writes in front (a loyalty ability), by a keyword
rule (an
Arena keyword instance, "Fading 5", pairs with the ability phase writes for that
keyword; a Saga's chapter pairs by its number with phase's "Chapter N"), by a
grant ("~ gains "…"" is the granting ability), or as one Arena ability
phase writes as two triggers ("When ~ enters or dies", "When ~ enters and at the
beginning of your upkeep"). An ability word in front of either text is dropped
(CR 207.2c: it has no rules meaning). Anything weaker is reported as unsure and
never scored, since a wrong pairing turns into a false finding or, worse, a false
pass. An
instance of a keyword phase lists on the card with no ability to compare it to
(prowess, ward, warp's delayed exile, ninjutsu's untexted activation) is
``keyword-only`` rather than unsure, and only once nothing else pairs and the
card has no keyword ability phase wrote out ("CR 702.…: …") that it could be.

Only abilities that can resolve are candidates: a static ability never goes on the
stack (CR 405.6b), though an ability it grants can.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    ConceptTree,
    iter_nested_granted_bodies,
    tag_of,
    trigger_def_unit,
    walk_effect_chain,
)
from mtg_utils.arena_card_db import strip_markup

__all__ = [
    "CONFIDENT",
    "SAGA_CHAPTER",
    "Pairing",
    "PhaseAbility",
    "abilities_of",
    "norm",
    "pair",
]

#: The text similarity a pairing needs to be scored.
CONFIDENT = 0.9


@dataclass(frozen=True)
class PhaseAbility:
    """One phase ability a resolution can be: its text, effects, origin
    (``ability`` / ``trigger`` / ``keyword`` / ``granted``), the node its effects
    hang off, and, for a trigger, its event (``crosswalk.trigger_def_event``)."""

    desc: str
    effects: tuple[ConceptNode, ...]
    origin: str
    kind: str | None
    root: object
    trigger_event: str | None = None
    #: The ability that grants this one (a granted body only).
    granted_by: PhaseAbility | None = field(default=None, compare=False)
    #: ``desc`` as :func:`norm` reads it.
    normed: str = field(default="", compare=False)
    #: The ability unit it is, for the reads that take one (``None`` for a granted
    #: ability that isn't a trigger).
    unit: AbilityUnit | None = field(default=None, compare=False)
    #: The name of the face it is on (its tree's).
    face: str = field(default="", compare=False)


def _ability(
    desc: object,
    *,
    effects: Sequence[ConceptNode],
    origin: str,
    kind: str | None,
    root: object,
    trigger_event: str | None,
    granted_by: PhaseAbility | None = None,
    unit: AbilityUnit | None = None,
    face: str = "",
) -> PhaseAbility:
    text = str(desc or "")
    return PhaseAbility(
        desc=text,
        effects=tuple(effects),
        origin=origin,
        kind=kind,
        root=root,
        trigger_event=trigger_event,
        granted_by=granted_by,
        normed=norm(text),
        unit=unit,
        face=face,
    )


def abilities_of(trees: Sequence[ConceptTree]) -> list[PhaseAbility]:
    """Every ability of ``trees`` that can resolve, with each ability it grants."""
    out: list[PhaseAbility] = []
    for tree in trees:
        for unit in tree.iter_units():
            own = _ability(
                getattr(unit.node, "description", ""),
                effects=unit.effects,
                origin=unit.origin,
                kind=unit.kind,
                root=unit.node,
                trigger_event=unit.trigger_event,
                unit=unit,
                face=tree.name,
            )
            if unit.origin not in ("static", "replacement"):
                out.append(own)
            for kind, body in iter_nested_granted_bodies(unit.node):
                granted = trigger_def_unit(body) if kind == "trigger" else None
                out.append(
                    _ability(
                        getattr(body, "description", ""),
                        effects=granted.effects
                        if granted
                        else tuple(walk_effect_chain(body)),
                        origin="granted",
                        kind=None,
                        root=body,
                        trigger_event=granted.trigger_event if granted else None,
                        granted_by=own,
                        unit=granted,
                        face=tree.name,
                    )
                )
    return out


_SPACE = re.compile(r"\s+")
#: Curly single quotes, as Arena and phase may write an apostrophe.
_QUOTES = {0x2019: "'", 0x2018: "'"}
#: Arena's mana symbols: ``{o2oUoB}`` is ``{2}{U}{B}``.
_ARENA_MANA = re.compile(r"\{o([^}]*)\}")
#: A self-reference either text may spell out ("this permanent") instead of ``~``.
_SELF = re.compile(
    r"\bthis (?:permanent|creature|artifact|enchantment|land|card|spell|equipment)\b"
)
#: The ability words (CR 207.2c), which "have no special rules meaning": Arena
#: writes one in front of its ability ("Landfall — Whenever …") and phase may not.
ABILITY_WORDS = (
    "adamant",
    "addendum",
    "alliance",
    "battalion",
    "bloodrush",
    "celebration",
    "channel",
    "chroma",
    "cohort",
    "constellation",
    "converge",
    "council's dilemma",
    "coven",
    "delirium",
    "descend 4",
    "descend 8",
    "disappear",
    "domain",
    "eerie",
    "eminence",
    "enrage",
    "fateful hour",
    "fathomless descent",
    "ferocious",
    "flurry",
    "formidable",
    "grandeur",
    "hellbent",
    "heroic",
    "imprint",
    "infusion",
    "inspired",
    "join forces",
    "kinship",
    "landfall",
    "lieutenant",
    "magecraft",
    "metalcraft",
    "morbid",
    "opus",
    "pack tactics",
    "paradox",
    "parley",
    "radiance",
    "raid",
    "rally",
    "renew",
    "repartee",
    "revolt",
    "secret council",
    "spell mastery",
    "strive",
    "survival",
    "sweep",
    "tempting offer",
    "threshold",
    "undergrowth",
    "valiant",
    "vivid",
    "void",
    "will of the council",
)
_ABILITY_WORD = re.compile(rf"^(?:{'|'.join(ABILITY_WORDS)}) ?— ?")


def _mana(match: re.Match) -> str:
    return "".join(f"{{{s}}}" for s in match.group(1).split("o") if s)


def norm(text: str | None) -> str:
    """Arena's or phase's ability text in one spelling: markup dropped, mana
    symbols as ``{1}{R}``, the card as ``~``, lower case, and no ability word in
    front (:data:`ABILITY_WORDS`)."""
    text = _ARENA_MANA.sub(_mana, strip_markup(text or ""))
    text = text.replace("CARDNAME", "~").translate(_QUOTES)
    text = _SPACE.sub(" ", text).strip().lower()
    return _SELF.sub("~", _ABILITY_WORD.sub("", text))


#: An Arena keyword (``Abilities.BaseId``'s text) → the word phase's own ability
#: for it carries.
KEYWORD_ABILITIES: dict[str, str] = {
    "fading": "fade counter",
    "vanishing": "time counter",
    "impending": "impending",
    "evoke": "evoke",
    # CR 702.79a, as phase writes persist's own trigger
    "persist": "if it had no -1/-1 counters on it",
    "for mirrodin!": "for mirrodin!",
    # CR 702.181a's attack trigger: "Mobilize — create Warrior tokens tapped and
    # attacking"
    "mobilize": "mobilize",
    # CR 702.175a's enters trigger: "When this permanent enters, if its offspring
    # cost was paid, create a token that's a copy of it, except it's 1/1"
    "offspring": "offspring cost was paid",
    # CR 702.165a's enters trigger: "When this creature enters, put N +1/+1
    # counters on target creature", which phase writes as "Backup N — …"
    "backup": "backup",
    # CR 702.134a's attack trigger, which phase writes as "Mentor — …"; Arena's
    # database can file it bare, with no BaseId
    "mentor": "mentor",
}
#: Arena's ``BaseId`` text for a Saga's chapter ability; its numeral is the chapter.
SAGA_CHAPTER = "sagachapter"
#: Arena text of a keyword's ability that has no ``BaseId`` (warp's delayed exile)
#: → the word phase's own ability for it carries.
KEYWORD_TEXTS: dict[str, str] = {
    "exile this at the beginning of the next end step": "warp",
}
#: A Case's "To solve — [condition]" (CR 719.3a): the trigger phase writes with a
#: ``SolveCase`` effect.
_TO_SOLVE = "to solve —"


@dataclass(frozen=True)
class Pairing:
    ability: PhaseAbility | None
    #: ``text`` / ``cost-prefix`` / ``keyword`` / ``chapter`` / ``grant`` /
    #: ``split`` / ``modal``, or with no ability ``keyword-only`` / ``unsure`` /
    #: ``none`` (no candidate) / ``no-text`` (Arena's database has no text for
    #: the ability).
    method: str
    score: float
    #: The best phase text, for an unsure pairing.
    phase_text: str = ""
    #: For a ``split`` pairing, the other phase abilities Arena's one ability is.
    also: tuple[PhaseAbility, ...] = ()

    @property
    def abilities(self) -> tuple[PhaseAbility, ...]:
        return () if self.ability is None else (self.ability, *self.also)


def _similarity(a: str, b: str) -> float:
    """1.0 when the texts are the same but for a cost one writes in front ("[-2]:
    …", "{T}: …"); else their similarity. A text held inside another (a reflexive
    "When you do" ability inside its parent trigger) is not the same ability."""
    if a and b:
        short, long = sorted((a, b), key=len)
        if long.endswith(short) and long[: len(long) - len(short)].rstrip().endswith(
            ":"
        ):
            return 1.0
    # no autojunk: it drops every character seen in more than 1% of a text over
    # 200 characters, which scores two identical long texts near 0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _best(
    text: str, candidates: Sequence[PhaseAbility]
) -> tuple[float, PhaseAbility] | None:
    scored = [(_similarity(text, a.normed), a) for a in candidates]
    return max(scored, key=lambda s: s[0], default=None)


#: One Arena ability phase writes as two triggers with the same effect: "When ~
#: enters and whenever it deals combat damage to a player, <effect>", "When ~
#: enters and at the beginning of your upkeep, <effect>" (two trigger
#: conditions), and "Whenever ~ enters or attacks, <effect>" (two events of one
#: object; the second may be more than a word: "enters or transforms into ~",
#: Brigid, Clachan's Heart). Each gives its two halves; a split pairs only when
#: each half pairs confidently with a different phase trigger.
_COMBINED: tuple[tuple[re.Pattern, Callable[[re.Match], tuple[str, str]]], ...] = (
    (
        re.compile(r"^(when(?:ever)? .+?) and ((?:whenever|at) .+?), (.+)$"),
        lambda m: (f"{m[1]}, {m[3]}", f"{m[2]}, {m[3]}"),
    ),
    (
        re.compile(r"^(when(?:ever)? .+?) (\w+) or ([^,]+?), (.+)$"),
        lambda m: (f"{m[1]} {m[2]}, {m[4]}", f"{m[1]} {m[3]}, {m[4]}"),
    ),
)
_GRANT = re.compile(r'gains? "(.+?)"?$')
#: A modal ability's condition before its modes ("When ~ enters, choose one —
#: …"): phase writes a modal trigger's description as that condition alone.
_MODAL = re.compile(r"^(.+?), choose (?:one|two|three|one or more|any number)\b")


def _split(text: str, candidates: Sequence[PhaseAbility]) -> Pairing | None:
    """The two phase triggers one combined Arena ability is (:data:`_COMBINED`),
    both on one face: an ability is on one face of a double-faced card (CR
    712.8), so Brinebound Gift's "Whenever this Aura enters or enchanted
    creature becomes the target …" is never half Brine Comber's."""
    best: Pairing | None = None
    for face in dict.fromkeys(a.face for a in candidates):
        on_face = [a for a in candidates if a.face == face]
        for pattern, halves in _COMBINED:
            if (match := pattern.match(text)) is None:
                continue
            one, two = (_best(half, on_face) for half in halves(match))
            if (
                one
                and two
                and one[1] is not two[1]
                and (score := min(one[0], two[0])) >= CONFIDENT
                and (best is None or score > best.score)
            ):
                best = Pairing(one[1], "split", score, also=(two[1],))
    return best


def _keep_all(_ability: PhaseAbility) -> bool:
    return True


def pair(
    arena_text: str | None,
    abilities: Sequence[PhaseAbility],
    *,
    keyword: str | None = None,
    numeral: int | None = None,
    card_keywords: frozenset[str] = frozenset(),
    keep: Callable[[PhaseAbility], bool] = _keep_all,
) -> Pairing:
    """The phase ability ``arena_text`` is, among ``abilities`` that ``keep``;
    ``keyword`` is the Arena keyword it is an instance of, if any, ``numeral``
    that instance's number, and ``card_keywords`` the keywords phase lists on
    the card (lower case)."""
    text = norm(arena_text)
    candidates = [a for a in abilities if keep(a)]
    if not text:
        return Pairing(None, "no-text", 0.0)
    named = norm(keyword)
    if named == SAGA_CHAPTER and numeral:
        chapter = [a for a in candidates if a.normed == f"chapter {numeral}"]
        if chapter:
            return Pairing(chapter[0], "chapter", 1.0)
    # an instance of a keyword (its BaseId), or the keyword written bare
    bare = next((w for k, w in KEYWORD_TEXTS.items() if text.startswith(k)), None)
    word = KEYWORD_ABILITIES.get(named or text) or bare
    if word is not None:
        own = sorted(
            (a for a in candidates if word in a.normed),
            key=lambda a: not a.desc.startswith("CR "),  # the keyword's own ability
        )
        if own:
            return Pairing(own[0], "keyword", 1.0)
    # a keyword phase lists on the card: nothing to compare when nothing pairs
    # and no ability phase wrote out for a keyword could be this one
    listed = (named or bare or text) in card_keywords and not any(
        a.desc.startswith("CR ") for a in abilities
    )
    if not candidates:
        return Pairing(None, "keyword-only" if listed else "none", 0.0)
    if (granted := _GRANT.search(text)) is not None:
        # the quoted ability is the granted body's own text
        best = _best(
            granted.group(1), [a for a in abilities if a.granted_by is not None]
        )
        granter = best[1].granted_by if best else None
        if best and granter and best[0] >= CONFIDENT and keep(granter):
            return Pairing(granter, "grant", best[0])
    if text.startswith(_TO_SOLVE):
        solves = [
            a
            for a in candidates
            if any(tag_of(c.node) == "SolveCase" for c in a.effects)
        ]
        if solves:
            return Pairing(solves[0], "keyword", 1.0)
    if (split := _split(text, candidates)) is not None:
        return split
    if (modal := _MODAL.match(text)) is not None:
        heads = [a for a in candidates if a.normed == modal[1]]
        if len(heads) == 1:
            return Pairing(heads[0], "modal", 1.0)
    best = _best(text, candidates)
    if best is None or best[0] < CONFIDENT:
        if listed:
            return Pairing(None, "keyword-only", 0.0)
        score, nearest = best or (0.0, None)
        return Pairing(None, "unsure", score, nearest.desc if nearest else "")
    score, ability = best
    method = "cost-prefix" if score == 1.0 and ability.normed != text else "text"
    return Pairing(ability, method, score)
