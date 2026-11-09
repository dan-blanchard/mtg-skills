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
  ``no-phase-parse``, ``unsure-pairing``, ``reflexive`` (a "When you do" or delayed
  trigger, which phase keeps inside its parent);
* triggers: ``match`` / ``mismatch`` (the events of what set it off aren't the event
  phase's trigger watches), ``not-logged`` (Arena logs no event for it, e.g. a
  library search), ``unchecked`` (phase's event has no Arena counterpart),
  ``reflexive`` (a "When you do" or delayed trigger, set off by its parent's action),
  or why it wasn't scored.

A rebalanced (Alchemy "A-") card is compared against the paper card's parse with a
``rebalanced`` warning; a digital-only card is compared only if phase parses it.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict
from importlib import resources
from pathlib import Path

from mtg_utils._arena_crosscheck.align import Pairing, PhaseAbility, abilities_of, pair
from mtg_utils._arena_crosscheck.effects import (
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
    replacement_event_tag,
)
from mtg_utils.arena_card_db import TRIGGERED, CardText

__all__ = ["Checker", "crosscheck", "load_ignores"]

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


#: A rules object Arena resolves (no printed card): ability text → the kinds it shows.
RULES_OBJECTS: dict[str, dict[str, frozenset[str]]] = {
    # the monarch's two rules triggers
    "The Monarch": {
        "draw a card": frozenset({"draw"}),
        "becomes the monarch": frozenset({"designation"}),
    },
}


def load_ignores() -> list[dict]:
    """The Arena mistakes not to flag again (``data/arena_crosscheck_ignore.toml``):
    ``{"card", "ability", "reason"}`` rows, ``ability`` a prefix of Arena's ability
    text (``""`` for any)."""
    text = resources.files("mtg_utils.data").joinpath("arena_crosscheck_ignore.toml")
    return tomllib.loads(text.read_text(encoding="utf-8")).get("ignore", [])


def _unsure(row: dict, pairing: Pairing) -> dict:
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
    ) -> None:
        self.text = card_text
        self._card_of = card_of
        self._trees_of = trees_of
        self._ignores = list(ignores)
        self._abilities: dict[str, tuple[PhaseAbility, ...] | None] = {}

    def _lookup(self, grp: int | None, row: dict) -> tuple[PhaseAbility, ...] | dict:
        """The card's phase abilities, or ``row`` with why there are none. Fills
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
        if name not in self._abilities:
            record = self._card_of(name)
            trees = self._trees_of(record) if record else ()
            self._abilities[name] = tuple(abilities_of(trees)) if trees else None
        abilities = self._abilities[name]
        return abilities or {**row, "status": "no-phase-parse"}

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
        permanent = set(res.card_types) & PERMANENT_CARD_TYPES
        found = self._lookup(res.source_grpid if is_ability else res.grpid, row)
        if not is_ability and permanent and not observed:
            return {**row, "status": "permanent-spell"}
        if row["card"] in RULES_OBJECTS:
            return self._rules_object(row, observed)
        if isinstance(found, dict):
            return found
        if ability is not None and ability.parent is not None:
            # a "When you do" or delayed trigger: phase keeps it inside its parent
            return {**row, "status": "reflexive"}
        if ability is not None:
            pairing = pair(ability.text, found, keyword=ability.keyword)
            if pairing.ability is None:
                return _unsure(row, pairing)
            chosen = [pairing.ability]
            row["pairing"] = pairing.method
        else:
            chosen = [a for a in found if a.origin == "ability" and a.kind == "Spell"]
        kinds = compare_kinds(observed, chosen)
        checks = strict_checks(
            chosen, mine, res.controller, counter_name=self.text.counter
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

    @staticmethod
    def _rules_object(row: dict, observed: set[str]) -> dict:
        shows = RULES_OBJECTS[row["card"]]
        text = row["arena_text"] or ""
        want = next((k for t, k in shows.items() if t in text), frozenset())
        extra = sorted(observed - want - {"replaced", "trigger"})
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
        if row["card"] in RULES_OBJECTS:
            return {**row, "status": "rules-object"}
        if isinstance(found, dict):
            return found
        if ability.parent is not None:
            # set off by its parent's action ("When you do"), or a delayed trigger
            return {**row, "status": "reflexive"}
        pairing = pair(
            ability.text,
            found,
            keyword=ability.keyword,
            keep=lambda a: a.trigger_event is not None,
        )
        if pairing.ability is None:
            return _unsure(row, pairing)
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
