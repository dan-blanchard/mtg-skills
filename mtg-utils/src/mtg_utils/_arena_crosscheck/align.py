"""Pair an Arena ability with the phase ability it is.

Arena names an ability by its own id and rules text (``CARDNAME`` for the card);
phase writes each ability's text as its ``description`` (``~`` for the card). A
pairing is **confident** only when the texts are near-identical (:data:`CONFIDENT`)
or the same but for a cost one writes in front (a loyalty ability), by a keyword
rule (an
Arena keyword instance, "Fading 5", pairs with the ability phase writes for that
keyword), by a grant ("~ gains "…"" is the granting ability), or as one Arena ability
phase writes as two triggers. Anything weaker is reported as unsure and never scored,
since a wrong pairing turns into a false finding or, worse, a false pass.

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
    trigger_def_unit,
    walk_effect_chain,
)
from mtg_utils.arena_card_db import strip_markup

__all__ = ["CONFIDENT", "Pairing", "PhaseAbility", "abilities_of", "norm", "pair"]

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


def _mana(match: re.Match) -> str:
    return "".join(f"{{{s}}}" for s in match.group(1).split("o") if s)


def norm(text: str | None) -> str:
    """Arena's or phase's ability text in one spelling: markup dropped, mana
    symbols as ``{1}{R}``, the card as ``~``, lower case."""
    text = _ARENA_MANA.sub(_mana, strip_markup(text or ""))
    text = text.replace("CARDNAME", "~").translate(_QUOTES)
    return _SELF.sub("~", _SPACE.sub(" ", text).strip().lower())


#: An Arena keyword (``Abilities.BaseId``'s text) → the word phase's own ability
#: for it carries.
KEYWORD_ABILITIES: dict[str, str] = {
    "fading": "fade counter",
    "vanishing": "time counter",
    "impending": "impending",
    "evoke": "evoke",
    "persist": "persist",
    "for mirrodin!": "for mirrodin!",
}
#: Arena text of a keyword's ability that has no ``BaseId`` (warp's delayed exile).
KEYWORD_TEXTS: dict[str, str] = {
    "exile this at the beginning of the next end step": "warp",
}


@dataclass(frozen=True)
class Pairing:
    ability: PhaseAbility | None
    #: ``text`` / ``cost-prefix`` / ``keyword`` / ``grant`` / ``split`` / ``unsure`` /
    #: ``none``.
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
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best(
    text: str, candidates: Sequence[PhaseAbility]
) -> tuple[float, PhaseAbility] | None:
    scored = [(_similarity(text, a.normed), a) for a in candidates]
    return max(scored, key=lambda s: s[0], default=None)


#: "When ~ enters and whenever it deals combat damage to a player, <effect>": one
#: Arena ability phase writes as two triggers with the same effect.
_COMBINED = re.compile(r"^(when(?:ever)? .+?) and (whenever .+?), (.+)$")
_GRANT = re.compile(r'gains? "(.+?)"?$')


def _keep_all(_ability: PhaseAbility) -> bool:
    return True


def pair(
    arena_text: str | None,
    abilities: Sequence[PhaseAbility],
    *,
    keyword: str | None = None,
    keep: Callable[[PhaseAbility], bool] = _keep_all,
) -> Pairing:
    """The phase ability ``arena_text`` is, among ``abilities`` that ``keep``;
    ``keyword`` is the Arena keyword it is an instance of, if any."""
    text = norm(arena_text)
    candidates = [a for a in abilities if keep(a)]
    if not text or not candidates:
        return Pairing(None, "none", 0.0)
    # an instance of a keyword (its BaseId), or the keyword written bare
    word = KEYWORD_ABILITIES.get(norm(keyword) or text) or next(
        (w for k, w in KEYWORD_TEXTS.items() if text.startswith(k)), None
    )
    if word is not None:
        own = sorted(
            (a for a in candidates if word in a.normed),
            key=lambda a: not a.desc.startswith("CR "),  # the keyword's own ability
        )
        if own:
            return Pairing(own[0], "keyword", 1.0)
    if (granted := _GRANT.search(text)) is not None:
        # the quoted ability is the granted body's own text
        best = _best(
            granted.group(1), [a for a in abilities if a.granted_by is not None]
        )
        granter = best[1].granted_by if best else None
        if best and granter and best[0] >= CONFIDENT and keep(granter):
            return Pairing(granter, "grant", best[0])
    if (combined := _COMBINED.match(text)) is not None:
        when, whenever, effect = combined.groups()
        one = _best(f"{when}, {effect}", candidates)
        two = _best(f"{whenever}, {effect}", candidates)
        if one and two and one[1] is not two[1] and min(one[0], two[0]) >= CONFIDENT:
            return Pairing(one[1], "split", min(one[0], two[0]), also=(two[1],))
    best = _best(text, candidates)
    if best is None or best[0] < CONFIDENT:
        score, nearest = best or (0.0, None)
        return Pairing(None, "unsure", score, nearest.desc if nearest else "")
    score, ability = best
    method = "cost-prefix" if score == 1.0 and ability.normed != text else "text"
    return Pairing(ability, method, score)
