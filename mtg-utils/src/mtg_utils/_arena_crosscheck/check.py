"""Check each Arena resolution and fired trigger against phase's parse (ADR-0064).

Arena's log is evidence, not the referee: a disagreement is a lead, checked against
the Comprehensive Rules (``/rules-lawyer``) before it is called a phase misparse; an
Arena mistake goes to the ignore list (``data/arena_crosscheck_ignore.toml``) with
its reason.

Rows, one per resolution or trigger, each with a ``status``:

* resolutions: ``agree`` / ``conditional`` (an effect that may not happen didn't) /
  ``phase-extra`` / ``arena-extra`` (see ``effects``), or why it wasn't scored:
  ``permanent-spell`` (a permanent spell only resolves onto the battlefield),
  ``no-card``, ``token`` (a token's ability has no card to look up),
  ``no-phase-parse``, ``unsure-pairing``, ``keyword-only`` (an instance of a
  keyword phase lists on the card, or the card's own ability grants it, with no
  ability to compare it to: prowess, ward, warp's delayed exile, ninjutsu's
  untexted activation), ``granted-keyword`` (an instance of a keyword the card
  neither prints nor grants itself: another object gave it, as a decayed counter
  or an Alchemy "perpetually gains"), ``no-arena-text`` (Arena's database has no
  text for the ability), ``reflexive`` (a "When you do" or delayed trigger, which
  phase keeps inside its parent), ``rules-object`` (a game rule's own ability,
  with no card behind it, that :data:`RULES_OBJECTS` / :data:`HOLDER_ABILITIES`
  can't score);
* triggers: ``match`` / ``mismatch`` (the events of what set it off aren't the event
  phase's trigger watches), ``not-logged`` (Arena logs no event for it, e.g. a
  library search), ``unchecked`` (phase's event has no Arena counterpart),
  ``reflexive`` (a "When you do" or delayed trigger, set off by its parent's action),
  ``rules-object``, or why it wasn't scored.

An ability on an emblem is its source card's (``log``), compared against the
emblem's ability in phase's parse of that card, with an ``emblem`` warning; Arena's
database files it under the ability that made the emblem, which isn't "reflexive".

A rebalanced (Alchemy "A-") card is compared against the paper card's parse with a
``rebalanced`` warning; a digital-only card is compared only if phase parses it.
"""

from __future__ import annotations

import collections
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from mtg_utils._arena_crosscheck.align import (
    ABILITY_WORDS,
    SAGA_CHAPTER,
    Pairing,
    PhaseAbility,
    abilities_of,
    norm,
    pair,
)
from mtg_utils._arena_crosscheck.effects import (
    Board,
    arena_kinds,
    compare_kinds,
    explain_excess,
    own_effects,
    strict_checks,
)
from mtg_utils._arena_crosscheck.log import Resolution, TriggerFired, read_logs
from mtg_utils._arena_crosscheck.report import build_report
from mtg_utils._card_ir.crosswalk import (
    PERMANENT_CARD_TYPES,
    ConceptTree,
    own_keyword_bodies,
    replacement_event_tag,
)
from mtg_utils.arena_card_db import TRIGGERED, ArenaAbility, CardText

if TYPE_CHECKING:
    from mtg_utils.card_pool import CardPool

__all__ = ["Checker", "checker_for", "crosscheck", "load_ignores"]

#: Logged events (``log.events_of``) spelled as phase's trigger events are.
_LOGGED = frozenset(
    {
        "enters",
        "dies",
        "attacks",
        "blocks",
        "becomes_blocked",
        "cast_spell",
        "drawn",
        "discarded",
        "sacrificed",
        "deals_damage",
        "counter_added",
        "life_gained",
        "life_lost",
        "phase",
        "becomes_target",
    }
)
#: Phase's trigger events whose logged events are spelled otherwise.
_SHOWN_BY: dict[str, frozenset[str]] = {
    "leaves": frozenset({"leaves", "dies"}),
    "changes_zone": frozenset({"zone_change"}),
    "entersorattacks": frozenset({"enters", "attacks"}),
    "damage_received": frozenset({"deals_damage"}),
    "taps": frozenset({"taps", "attacks"}),
}


def shown_by(event: str | None) -> frozenset[str] | None:
    """The logged events that show phase's trigger ``event``; ``None`` for one
    Arena logs no counterpart of."""
    if event in _SHOWN_BY:
        return _SHOWN_BY[event]
    return frozenset({event}) if event in _LOGGED else None


#: A rules object Arena resolves (no printed card), by the name Arena gives it:
#: ability text → the kinds it shows (none: one Arena logs nothing for).
RULES_OBJECTS: dict[str, dict[str, frozenset[str]]] = {
    # the monarch's two rules triggers
    "The Monarch": {
        "draw a card": frozenset({"draw"}),
        "becomes the monarch": frozenset({"designation"}),
    },
    # speed's inherent trigger, which "has no source" (CR 702.179d)
    "Start Your Engines!": {"increase your speed": frozenset()},
}
#: A game rule's own ability on a trigger holder Arena names no card for: ability
#: text → the kinds it shows.
HOLDER_ABILITIES: dict[str, frozenset[str]] = {
    # earthbend's delayed trigger: "When that land dies or is put into exile,
    # return it to the battlefield tapped under your control" (CR 701.66a)
    "Return that land to the battlefield tapped": frozenset(
        {"move:Graveyard->Battlefield", "move:Exile->Battlefield"}
    ),
}


def load_ignores() -> list[dict]:
    """The Arena mistakes not to flag again (``data/arena_crosscheck_ignore.toml``):
    ``{"card", "ability", "reason"}`` rows, ``ability`` a prefix of Arena's ability
    text (``""`` for any)."""
    text = resources.files("mtg_utils.data").joinpath("arena_crosscheck_ignore.toml")
    return tomllib.loads(text.read_text(encoding="utf-8")).get("ignore", [])


class _Parsed(NamedTuple):
    """Phase's parse of one card: its abilities, the keywords it lists on the
    card or its own abilities grant it (Bloodbraid Marauder's "This spell has
    cascade as long as …"), and the keywords its record prints (lower case)."""

    abilities: tuple[PhaseAbility, ...]
    keywords: frozenset[str]
    printed: frozenset[str] = frozenset()


#: Arena keywords that are no keyword a card is granted: a Saga's chapter, and
#: the ability words (CR 207.2c).
_NOT_GRANTED = frozenset({SAGA_CHAPTER, *ABILITY_WORDS})


def _granted(keyword: str | None, parsed: _Parsed) -> bool:
    """Whether an instance of ``keyword`` came from another object: a keyword the
    card neither lists, grants itself, nor prints."""
    return (
        keyword is not None
        and keyword not in _NOT_GRANTED
        and keyword not in parsed.keywords | parsed.printed
    )


def _unpaired(
    row: dict, pairing: Pairing, parsed: _Parsed, keyword: str | None
) -> dict:
    """The row for an Arena ability with no phase ability to compare;
    ``keyword`` is the keyword it is an instance of, if any."""
    if pairing.method == "keyword-only":
        return {**row, "status": "keyword-only"}
    if pairing.method == "no-text":
        return {**row, "status": "no-arena-text"}
    if _granted(keyword, parsed):
        return {**row, "status": "granted-keyword", "keyword": keyword}
    return {
        **row,
        "status": "unsure-pairing",
        "pairing_score": round(pairing.score, 2),
        "phase_text": pairing.phase_text,
    }


class Checker:
    """Checks resolutions and triggers against phase. ``card_of(name)`` gives a
    card record (``None`` when the pool has none) and ``trees_of(card)`` its
    concept trees, so production reads the card pool and tests the snapshot."""

    def __init__(
        self,
        card_text: CardText,
        card_of: Callable[[str], dict | None],
        trees_of: Callable[[dict], Sequence[ConceptTree]],
        ignores: Sequence[dict] = (),
        keywords: frozenset[str] = frozenset(),
    ) -> None:
        self.text = card_text
        self._card_of = card_of
        self._trees_of = trees_of
        self._ignores = list(ignores)
        #: Every keyword a card can print (lower case): what an Arena ability
        #: written as a bare word with no keyword of its own ("Decayed") is.
        self._keywords = keywords
        #: Per card name, phase's parse; ``None`` for a card phase has no tree for.
        self._parsed: dict[str, _Parsed | None] = {}

    def _keyword(self, ability: ArenaAbility) -> str | None:
        """The keyword an Arena ability is an instance of: its ``BaseId``'s
        ("Ward {o2}" is Ward), or its text when that is a keyword ("Decayed")."""
        if ability.keyword:
            return norm(ability.keyword)
        text = norm(ability.text)
        return text if text in self._keywords else None

    def _lookup(self, grp: int | None, row: dict) -> _Parsed | dict:
        """Phase's parse of the card, or ``row`` with why there is none. Fills
        the row's ``card`` and ``warnings``."""
        card = self.text.card(grp)
        name = card.paper_name if card else None
        if card and card.rebalanced:
            row["warnings"].append("rebalanced")
        row["card"] = name
        if name is None:
            return {**row, "status": "no-card"}
        if card and card.token:
            return {**row, "status": "token"}
        if name not in self._parsed:
            record = self._card_of(name)
            trees = self._trees_of(record) if record else ()
            self._parsed[name] = (
                _Parsed(
                    tuple(abilities_of(trees)),
                    frozenset(kw.lower() for t in trees for kw in t.card_keywords)
                    | frozenset().union(*(own_keyword_bodies(t) for t in trees)),
                    frozenset(
                        kw.lower() for kw in (record or {}).get("keywords") or ()
                    ),
                )
                if trees
                else None
            )
        return self._parsed[name] or {**row, "status": "no-phase-parse"}

    def _replacements(
        self, battlefield: Sequence[tuple[int, int | None]], seat: int | None
    ) -> Callable[[], list[tuple[str, str]]]:
        def read() -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for grp, controller in battlefield:
                card = self.text.card(grp)
                name = card.paper_name if card else None
                if controller != seat or name is None:
                    continue
                record = self._card_of(name)
                for tree in self._trees_of(record) if record else ():
                    out += [
                        (name, replacement_event_tag(u.node) or "")
                        for u in tree.iter_units("replacement")
                    ]
            return out

        return read

    def _ignored(self, card: str | None, text: str | None) -> str | None:
        for row in self._ignores:
            prefix = row.get("ability", "")
            if row.get("card") == card and (text or "").startswith(prefix):
                return row.get("reason", "ignored")
        return None

    def resolution(self, res: Resolution) -> dict:
        is_ability = res.kind == "ability"
        ability = self.text.ability(res.grpid) if is_ability else None
        mine, rest = own_effects(res)
        observed = arena_kinds(mine)
        row: dict = {
            "game": list(res.game),
            "turn": res.turn,
            "kind": res.kind,
            "arena_text": ability.text if ability else None,
            "arena": sorted(observed),
            "other_source": sorted({t for e in rest for t in e.types}),
            "warnings": [],
        }
        if res.x.own is not None:
            row["x"] = res.x.own  # the X it was cast or activated with
        if res.x.spell is not None:
            row["spell_x"] = res.x.spell  # the X its permanent's spell was cast with
        permanent = set(res.card_types) & PERMANENT_CARD_TYPES
        found = self._lookup(res.source_grpid if is_ability else res.grpid, row)
        if not is_ability and permanent and not observed:
            return {**row, "status": "permanent-spell"}
        if row["card"] in RULES_OBJECTS:
            return self._rules_object(row, observed, RULES_OBJECTS[row["card"]])
        if row["card"] is None and res.holder is not None:
            return self._rules_object(row, observed, HOLDER_ABILITIES)
        if isinstance(found, dict):
            return found
        emblem = res.holder == "Emblem"
        if emblem:
            row["warnings"].append("emblem")
        if ability is not None and ability.parent is not None and not emblem:
            # a "When you do" or delayed trigger: phase keeps it inside its parent
            return {**row, "status": "reflexive"}
        if ability is not None:
            pairing = pair(
                ability.text,
                found.abilities,
                keyword=ability.keyword,
                numeral=ability.numeral,
                card_keywords=found.keywords,
            )
            if pairing.ability is None:
                return _unpaired(row, pairing, found, self._keyword(ability))
            chosen = [pairing.ability]
            row["pairing"] = pairing.method
        elif not found.abilities:
            return {**row, "status": "no-phase-parse"}
        else:
            chosen = [
                a
                for a in found.abilities
                if a.origin == "ability" and a.kind == "Spell"
            ]
        kinds = compare_kinds(observed, chosen, res.x, self._board(res, row["card"]))
        checks = strict_checks(
            chosen,
            mine,
            res.controller,
            counter_name=self.text.counter,
            x=res.x,
            instance=res.instance,
        )
        explain_excess(checks, self._replacements(res.battlefield, res.controller))
        row.update(
            phase_text=" / ".join(a.desc for a in chosen),
            status=kinds.status,
            phase=list(kinds.phase),
            unexplained=list(kinds.unexplained),
            unseen=list(kinds.unseen),
            checks=[asdict(c) for c in checks],
        )
        flagged = kinds.status in ("arena-extra", "phase-extra") or not all(
            c.ok for c in checks
        )
        if flagged and (reason := self._ignored(row["card"], row["arena_text"])):
            row.update(status="ignored", ignored=reason)
        return row

    def _board(self, res: Resolution, source: str | None) -> Board:
        """The permanents on the battlefield as ``res`` began, by name and side."""
        names: collections.Counter[tuple[str, str]] = collections.Counter()
        for grp, controller in (*res.battlefield, *res.battlefield_tokens):
            card = self.text.card(grp)
            if card and card.paper_name:
                side = "you" if controller == res.controller else "opponent"
                names[(card.paper_name, side)] += 1
        return Board(names, source, res.parent_on_battlefield)

    @staticmethod
    def _rules_object(
        row: dict, observed: set[str], shows: dict[str, frozenset[str]]
    ) -> dict:
        """A rules object's ability scored by the kinds ``shows`` gives its text;
        ``rules-object`` when it gives none to look for."""
        text = row["arena_text"] or ""
        want = next((k for t, k in shows.items() if t in text), None)
        extra = sorted(observed - (want or frozenset()) - {"replaced", "trigger"})
        if want is None or (not want and not extra):
            return {**row, "status": "rules-object", "phase": ["(rules object)"]}
        status = (
            "arena-extra" if extra else ("agree" if observed & want else "conditional")
        )
        return {
            **row,
            "status": status,
            "unexplained": extra,
            "phase": ["(rules object)"],
        }

    def trigger(self, fired: TriggerFired) -> dict | None:
        """The row for a fired trigger, ``None`` for an ability that isn't one."""
        ability = self.text.ability(fired.ability_grpid)
        if ability.category != TRIGGERED:
            return None
        row: dict = {
            "game": list(fired.game),
            "turn": fired.turn,
            "arena_text": ability.text,
            "events": sorted(fired.events),
            "warnings": [],
        }
        found = self._lookup(fired.source_grpid, row)
        if row["card"] in RULES_OBJECTS or (
            row["card"] is None and fired.holder is not None
        ):
            return {**row, "status": "rules-object"}
        if isinstance(found, dict):
            return found
        emblem = fired.holder == "Emblem"
        if emblem:
            row["warnings"].append("emblem")
        if ability.parent is not None and not emblem:
            # set off by its parent's action ("When you do"), or a delayed trigger
            return {**row, "status": "reflexive"}
        pairing = pair(
            ability.text,
            found.abilities,
            keyword=ability.keyword,
            numeral=ability.numeral,
            card_keywords=found.keywords,
            keep=lambda a: a.trigger_event is not None,
        )
        if pairing.ability is None:
            return _unpaired(row, pairing, found, self._keyword(ability))
        events = [a.trigger_event for a in pairing.abilities]
        row.update(
            phase_text=" / ".join(a.desc for a in pairing.abilities),
            phase_event="|".join(e or "" for e in events),
        )
        shown = [shown_by(e) for e in events]
        if any(s is None for s in shown):
            status = "unchecked"
        elif not fired.events:
            status = "not-logged"
        else:
            hits = (
                frozenset().union(*(s for s in shown if s is not None)) & fired.events
            )
            status = "match" if hits else "mismatch"
        row["status"] = status
        if (
            status == "mismatch"
            and (reason := self._ignored(row["card"], ability.text)) is not None
        ):
            row.update(status="ignored", ignored=reason)
        return row


def checker_for(card_text: CardText, pool: CardPool) -> Checker:
    """The production checker: cards from ``pool``, their phase trees, the
    ignore list, and every keyword the pool's records print."""
    from mtg_utils._card_ir.trees import trees_for

    keywords = frozenset(
        kw.lower() for r in pool.by_name.values() for kw in r.get("keywords") or ()
    )
    return Checker(card_text, pool.by_name.get, trees_for, load_ignores(), keywords)


def crosscheck(paths: Iterable[Path], checker: Checker, phase_tag: str) -> dict:
    """Read the logs at ``paths`` and score every resolution and trigger: the
    report (``report.build_report``)."""
    resolutions, triggers, games = read_logs(paths)
    return build_report(
        [checker.resolution(r) for r in resolutions],
        [row for t in triggers if (row := checker.trigger(t)) is not None],
        games,
        phase_tag,
    )
