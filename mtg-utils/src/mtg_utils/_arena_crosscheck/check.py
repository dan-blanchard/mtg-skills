"""Check each Arena resolution and fired trigger against phase's parse, and each
trigger phase's parse expects on an object's own event against what Arena fired
(ADR-0064).

Arena's log is evidence, not the referee: a disagreement is a lead, checked against
the Comprehensive Rules (``/rules-lawyer``) before it is called a phase misparse; an
Arena mistake goes to the ignore list (``data/arena_crosscheck_ignore.toml``) with
its reason.

Rows, one per resolution, fired trigger or expected trigger, each with a
``status``:

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
  ``rules-object``, or why it wasn't scored;
* expected (the reverse check, :meth:`Checker.expected`: a trigger of the card that
  watches an event of the object itself, ``log.ObjectEvent``): ``fired`` /
  ``unfired`` (Arena created no instance of it by the turn's end, though it lists
  the ability on the object), or why a missing instance is no evidence
  (:data:`EXPECTED_STATUSES`): ``face-down``, ``copy``, ``game-over``,
  ``unfired-unsure``, ``no-abilities``, ``unfired-unpaired``,
  ``unfired-conditional``, ``unfired-targeted``, ``ignored``.

An ability on an emblem is its source card's (``log``), compared against the
emblem's ability in phase's parse of that card, with an ``emblem`` warning; Arena's
database files it under the ability that made the emblem, which isn't "reflexive".

A rebalanced (Alchemy "A-") card is compared against the paper card's parse with a
``rebalanced`` warning; a digital-only card is compared only if phase parses it.
"""

from __future__ import annotations

import collections
import re
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
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
from mtg_utils._arena_crosscheck.log import (
    Instance,
    ObjectEvent,
    Resolution,
    TriggerFired,
    read_logs,
)
from mtg_utils._arena_crosscheck.report import build_report
from mtg_utils._card_ir.crosswalk import (
    PERMANENT_CARD_TYPES,
    AbilityUnit,
    ConceptTree,
    TriggerSuppression,
    effect_targets,
    own_keyword_bodies,
    replacement_event_tag,
    trigger_gates,
    trigger_suppressions,
    trigger_zone_changes,
    watches_itself,
)
from mtg_utils.arena_card_db import ACTIVATED, TRIGGERED, ArenaAbility, CardText

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


#: Phase's trigger events the reverse check expects on an object's own event
#: (``log.ObjectEvent``): the ones the log shows every time they happen. Not
#: ``taps`` (an attack taps only a creature without vigilance), damage, counters
#: or a target choice.
_OWN_EVENTS = frozenset(
    {
        "enters",
        "dies",
        "leaves",
        "changes_zone",
        "entersorattacks",
        "attacks",
        "blocks",
        "becomes_blocked",
        "cast_spell",
        "sacrificed",
    }
)
#: The zone-change watchers, whose zones are checked against the move's.
_MOVES = frozenset({"enters", "dies", "leaves", "changes_zone"})


def watches_own_event(ability: PhaseAbility, event: ObjectEvent) -> bool:
    """Whether a phase trigger of the object's own card watches ``event`` of
    the object itself: a trigger on the card (not one it grants another
    object) whose subject is the card alone (``SelfRef``), of an event in
    :data:`_OWN_EVENTS` that ``event`` is, and, for a zone change, a move from
    and to the zones it names."""
    if ability.origin != "trigger" or ability.unit is None:
        return False
    trig = ability.unit.node
    shown = shown_by(ability.trigger_event)
    if (
        ability.trigger_event not in _OWN_EVENTS
        or shown is None
        or not shown & event.events
        or not watches_itself(trig)
    ):
        return False
    if ability.trigger_event not in _MOVES:
        return True
    return any(
        (origin is None or origin == event.origin)
        and (dest is None or dest == event.destination)
        for origin, dest in trigger_zone_changes(trig)
    )


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
        self._suppression: dict[str, tuple[TriggerSuppression, ...]] = {}

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
        observed = arena_kinds(mine, self.text.counter)
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
            pairing = self._pair(ability, found)
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
        pairing = self._pair(ability, found, _is_trigger)
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

    def expected(self, events: Sequence[ObjectEvent]) -> list[dict]:
        """One row per trigger phase's parse gives an object's card that
        watches one of ``events`` of the object itself
        (:func:`watches_own_event`): whether Arena created an instance of it
        (``fired``), and when it didn't, whether that is a finding
        (``unfired``) or why it isn't one (:data:`EXPECTED_STATUSES`). No rows
        for an object with no card or no parse to expect anything of.

        Arena names the object an instance came from, never its event, so the
        events of one object in a turn are offered the same instances. Each
        instance answers at most one row: of the events offered it with a row
        whose trigger it pairs with, the last (the latest before it), and
        none when that row is answered already. That row is ``fired``. A row
        left unanswered though an instance offered it pairs with its trigger
        (one that answered another event, or none) is ``unfired-unsure``:
        the log can't tell which event the instance was for.

        So with two events of one object and the instances logged after both:
        one instance pairing with both rows (an enter and a leave, one Arena
        ability; a haste attack after an enter) makes the later row ``fired``
        and the earlier ``unfired-unsure``; two instances (a second Bilbo,
        Retired Burglar put into the graveyard by the legend rule before its
        enter trigger is on the stack; a doubled attack trigger under Isshin,
        Two Heavens as One) make the same, never an earlier ``fired`` nor an
        ``unfired`` either way. The later row's ``fired`` assumes the instance
        is its event's: one logged after both events goes with the later. An
        instance that pairs with only one of the rows answers that one: an
        enter trigger logged after the creature died at once, its persist
        beside it (Woodfall Primus), is the enter's."""
        pending = [p for event in events for p in self._expecting(event)]
        # the last event offered each instance that has a row it pairs with:
        # the one it answers, its row credited or not
        answers: dict[tuple, int] = {}
        for p in pending:
            for instance, _ability, pairing in p.instances:
                if p.trig in pairing.abilities:
                    key = (p.event.game, instance.id)
                    answers[key] = max(answers.get(key, -1), p.event.ordinal)
        for p in pending:
            for instance, _ability, pairing in p.instances:
                if (
                    not p.credited
                    and p.trig in pairing.abilities
                    and answers[(p.event.game, instance.id)] == p.event.ordinal
                ):
                    p.credited = True
        out = []
        for p in pending:
            row = {
                **p.row,
                "phase_text": p.trig.desc,
                "phase_event": p.trig.trigger_event,
            }
            row.update(self._own_status(p))
            if row["status"] != "fired":
                # what Arena did put on the stack from the object, for triage
                row["fired"] = [a.text for _, a, _ in p.instances]
            out.append(row)
        return out

    def _expecting(self, event: ObjectEvent) -> list[_Expect]:
        """The triggers phase expects on ``event``, with the instances offered
        to it, each paired with phase's triggers of the card."""
        row: dict = {
            "game": list(event.game),
            "turn": event.turn,
            "event": event.event,
            "event_index": event.ordinal,
            "warnings": [],
        }
        if event.origin or event.destination:
            row["zones"] = [event.origin, event.destination]
        found = self._lookup(event.grpid, row)
        if isinstance(found, dict):
            return []
        card = self.text.card(event.grpid)
        face = card.paper_name if card else None
        # a double-faced card's other face is not on the battlefield (CR 712.8)
        on_face = [a for a in found.abilities if a.face == face] or found.abilities
        expected = [a for a in on_face if watches_own_event(a, event)]
        if not expected:
            return []
        instances = [
            (instance, ability, self._pair(ability, found, _is_trigger))
            for instance in event.fired
            if (ability := self.text.ability(instance.grpid)).category == TRIGGERED
            and ability.parent is None
        ]
        return [_Expect(event, trig, row, found, instances) for trig in expected]

    @staticmethod
    def _pair(
        ability: ArenaAbility,
        found: _Parsed,
        keep: Callable[[PhaseAbility], bool] | None = None,
    ) -> Pairing:
        """The phase ability (among those that ``keep``) an Arena ability is."""
        return pair(
            ability.text,
            found.abilities,
            keyword=ability.keyword,
            numeral=ability.numeral,
            card_keywords=found.keywords,
            keep=keep or _any_ability,
        )

    def _own_status(self, p: _Expect) -> dict:
        """The status of a trigger phase expects on an event
        (:data:`EXPECTED_STATUSES`, in their order), and what it rests on."""
        event, trig, found = p.event, p.trig, p.found
        if event.face_down:
            return {"status": "face-down"}
        if event.copy or event.kind != "Card":
            return {"status": "copy"}
        if event.rolled_back:
            return {"status": "rolled-back"}
        if p.credited:
            return {"status": "fired"}
        if not event.turn_ended:
            return {"status": "game-over"}
        if (by := self._suppressed_by(event, trig)) is not None:
            return {"status": "suppressed", "suppressed_by": by}
        if "rebalanced" in p.row["warnings"]:
            return {"status": "rebalanced"}
        if any(pairing.method == "unsure" for _, _, pairing in p.instances):
            # an instance phase's text can't name could be this trigger
            return {"status": "unfired-unsure"}
        if any(trig in pairing.abilities for _, _, pairing in p.instances):
            # an instance of this trigger that answered another event (or
            # none): which event it was for, the log can't tell
            return {"status": "unfired-unsure", "unsure": "another event's"}
        if not event.abilities:
            return {"status": "no-abilities"}
        paired = (
            (ability, self._pair(ability, found))
            for ability in map(self.text.ability, event.abilities)
        )
        listed = [(a, pairing) for a, pairing in paired if trig in pairing.abilities]
        if not listed:
            return {"status": "unfired-unpaired"}
        arena, pairing = listed[0]
        out: dict = {
            "arena_text": arena.text,
            "arena_category": _CATEGORY.get(arena.category, str(arena.category)),
        }
        if arena.category != TRIGGERED:
            return {**out, "status": "arena-not-triggered"}
        unit = trig.unit
        if gates := trigger_gates(unit.node if unit else None):
            return {**out, "status": "unfired-conditional", "gates": list(gates)}
        if _targets(arena, pairing, unit):
            # with no legal target Arena puts no instance on the stack at all
            # (CR 603.3d: "the ability is simply removed from the stack")
            return {**out, "status": "unfired-targeted"}
        if (reason := self._ignored(p.row["card"], arena.text)) is not None:
            return {**out, "status": "ignored", "ignored": reason}
        return {**out, "status": "unfired"}

    def _suppressed_by(self, event: ObjectEvent, trig: PhaseAbility) -> str | None:
        """The card on the battlefield whose static stops ``event`` from
        triggering ``trig`` (``crosswalk.trigger_suppressions``: Hushbringer's
        "Creatures entering the battlefield or dying don't cause abilities to
        trigger"), if any: :func:`_silences`. An event name phase gives that
        this reader doesn't know is taken to silence every trigger."""
        for grp, controller in event.battlefield:
            card = self.text.card(grp)
            name = card.paper_name if card else None
            for s in self._suppressions(name):
                if s.trigger_side == "opponents" and controller == event.controller:
                    continue
                if s.trigger_side == "you" and controller != event.controller:
                    continue
                if s.source_types and not (
                    "Permanent" in s.source_types
                    or set(s.source_types) & set(event.card_types)
                ):
                    continue
                if any(_silences(e, event, trig) for e in s.events or ("*",)):
                    return name
        return None

    def _suppressions(self, name: str | None) -> tuple[TriggerSuppression, ...]:
        if name is None:
            return ()
        if name not in self._suppression:
            record = self._card_of(name)
            self._suppression[name] = tuple(
                s
                for tree in (self._trees_of(record) if record else ())
                for s in trigger_suppressions(tree)
            )
        return self._suppression[name]


@dataclass
class _Expect:
    """A trigger phase expects on an object event, before its status: the
    event's row so far, the card's parse, the instances offered to the event
    with their pairings, and whether one of them answers it."""

    event: ObjectEvent
    trig: PhaseAbility
    row: dict
    found: _Parsed
    instances: list[tuple[Instance, ArenaAbility, Pairing]]
    credited: bool = False


def _silences(name: str, event: ObjectEvent, trig: PhaseAbility) -> bool:
    """Whether phase's ``SuppressTriggers`` event ``name`` stops ``event``
    from triggering ``trig``. ``EntersBattlefield``: an enter (every own
    trigger expected on one watches the entering). ``Dies``: a dies or leaves
    trigger on a leave to a graveyard (Hushbringer's rulings: a "leaves the
    battlefield" ability won't trigger on dying), or a zone change whose every
    move starts on the battlefield; never a "whenever you sacrifice" trigger
    nor a dying card's own "put into a graveyard from anywhere", which its
    rulings say still trigger. An unknown name silences every trigger."""
    if name == "EntersBattlefield":
        return event.event == "enters"
    if name == "Dies":
        moves = trigger_zone_changes(trig.unit.node) if trig.unit else ()
        return "dies" in event.events and (
            trig.trigger_event in ("dies", "leaves")
            or (
                trig.trigger_event == "changes_zone"
                and bool(moves)
                and all(origin == "Battlefield" for origin, _ in moves)
            )
        )
    return True


#: The reverse check's statuses (:meth:`Checker.expected`), one per trigger
#: phase's parse expects on an object's own event. ``fired``: Arena created an
#: instance of it from the object. ``unfired``, the finding: it didn't, though
#: it lists the ability on the object, and nothing below explains why. The
#: rest say why a missing instance is no evidence, in the order they are
#: decided:
EXPECTED_STATUSES: dict[str, str] = {
    "face-down": "Arena marks the object face down: it has no abilities "
    "(CR 708.2) and its enters abilities don't trigger (CR 708.3)",
    "copy": "a copy (Arena's isCopy, or a token of a card's printing): a copy "
    "effect may make exceptions (CR 707.9), and a copy of a spell isn't cast "
    "(CR 707.10)",
    "rolled-back": "Arena undid the event (a cancelled cast): a later message "
    "reused the id of the annotation it came from for another one",
    "fired": "an instance Arena created from the object answers it (each "
    "instance answers one row: Checker.expected)",
    "game-over": "the game or the log ended before the turn did",
    "suppressed": "a card on the battlefield stops the event from triggering "
    "abilities (crosswalk.trigger_suppressions: Hushbringer)",
    "rebalanced": "a rebalanced (A-) card, scored against the paper card's parse",
    "unfired-unsure": "Arena created an instance from the object that pairs "
    "with no phase trigger confidently, or one of this trigger that answered "
    "another of the object's events: it could be this one",
    "no-abilities": "Arena lists no abilities on the object (it lost them)",
    "unfired-unpaired": "none of the abilities Arena lists on the object pairs "
    "with it confidently (lost, or a text phase writes otherwise)",
    "arena-not-triggered": "the ability Arena lists for it is no triggered "
    "ability in Arena's database (a static, a replacement)",
    "unfired-conditional": "an intervening if, a limit, a filter or a parked "
    "clause on the trigger (crosswalk.trigger_gates)",
    "unfired-targeted": "it targets (Arena's text says target, or it is a "
    "keyword, whose rule may): with no legal target Arena puts no instance on "
    "the stack at all (CR 603.3d)",
    "ignored": "an Arena mistake on the ignore list",
    "unfired": "the finding",
}


#: The word that makes an object or player a target (CR 115.10a).
_TARGET = re.compile(r"\btargets?\b", re.IGNORECASE)


def _targets(arena: ArenaAbility, pairing: Pairing, unit: AbilityUnit | None) -> bool:
    """Whether Arena's ability targets, the question being whether Arena would
    put it on the stack: its rules text says "target" (CR 115.10a), or it is
    an instance of a keyword whose rule may (Backup's "target creature", CR
    702.165a; Mentor's "target attacking creature", CR 702.134a: an Arena
    ``BaseId``, or a pairing by the keyword, as a bare "Mentor" with none) and
    phase's ability for it holds a target
    (``crosswalk.effect_targets``, which also counts a player the effect
    names, such as scry's controller: too broad to read alone)."""
    if _TARGET.search(arena.text or ""):
        return True
    return (
        (bool(arena.keyword) or pairing.method == "keyword")
        and unit is not None
        and any(effect_targets(unit.node, c.node, unit) for c in unit.effects)
    )


def _is_trigger(ability: PhaseAbility) -> bool:
    return ability.trigger_event is not None


def _any_ability(_ability: PhaseAbility) -> bool:
    return True


#: Arena's ability categories by number (``arena_card_db``).
_CATEGORY = {ACTIVATED: "activated", TRIGGERED: "triggered", 3: "static"}


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
    logs = read_logs(paths)
    return build_report(
        [checker.resolution(r) for r in logs.resolutions],
        [row for t in logs.triggers if (row := checker.trigger(t)) is not None],
        logs.games,
        phase_tag,
        expected=checker.expected(logs.events),
    )
