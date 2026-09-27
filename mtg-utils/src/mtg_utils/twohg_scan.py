"""Two-Headed Giant readout: which of a set's cards play differently at a 2HG table.

A pure, deterministic classifier over card records — no agent, no network — plus
its CLI. In Two-Headed Giant each team has two heads, so a card's value moves in
ways a 1v1 read misses. ``twohg_scan`` sorts a set's cards into five buckets:

* ``doubles`` — the card gets twice the work: "each opponent" / "for each
  opponent" effects, effects on your opponents' permanents, triggers that watch
  an opponent, and taxes on your opponents' spells.
* ``hits_partner`` — the card also hits your teammate: "each player" effects,
  sweepers, symmetric taxes. Each row's ``what`` tells symmetric help (each
  player draws) from symmetric harm.
* ``target_player`` — the card can be aimed at your partner ("target player").
* ``step_triggers`` — a "beginning of each player's / each opponent's [step]"
  trigger. It fires once per head only when it refers to "that player" (CR
  805.4d); otherwise it fires once for the step.
* ``removal_reach`` — for removal and sweepers only: whether it can hit a
  planeswalker, and the mana-value floor that makes it miss the 0-mana Jace
  tokens a set like FRA hands out.

**Path policy (no union).** One path per card, like ``roles.is_ramp``: the Card
IR (phase's concept trees, read through the shared ``crosswalk`` reads and the
shared removal / edict walk) whenever phase has trees for the card, or, for a
card phase doesn't cover yet (a brand-new set), a per-clause oracle-text degrade.
The path is decided by the trees themselves, not by ``has_signal_coverage``, so
a card pays for signal extraction only when removal reach needs ``role_of`` (the
cards whose removal walk reaches the board), not for choosing its path.

The one exception is a narrow text veto on the IR path: phase can't yet tell
"each other player" from "each opponent" (both are ``player_scope: Opponent`` —
Grave Pact, Syphon Mind), and at a 2HG table the difference is your partner. An
opponent-owned effect whose own clause says "each other player" moves to
``hits_partner`` and the row's path becomes ``ir+veto``. A retirement-canary test
fails once phase splits the two.

    twohg-scan --set FRA [--bulk-data PATH] [--json]
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

import click

from mtg_utils._analysis.lanes.removal_tutors import removal_edict_answers
from mtg_utils._analysis.roles import role_of
from mtg_utils._analysis.signal_base import clauses
from mtg_utils._card_ir.crosswalk import (
    AbilityUnit,
    ConceptNode,
    _node_raw,
    damage_filter_scope,
    effect_filter,
    effect_owner_player_scope,
    effect_owner_raw,
    effect_player_reach,
    filter_controller,
    filter_core_types,
    filter_mana_value_floor,
    is_opponent_cast_trigger_def,
    iter_nested_granted_effect_concepts,
    modify_cost_mode,
    player_filter_tag,
    recipient_tag,
    refers_to_scoped_player,
    scoped_player_scope,
    trigger_phase,
    trigger_scope,
    trigger_subject_scope,
    trigger_turn_constraint,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.card_classify import _REMINDER_RE, get_oracle_text
from mtg_utils.card_pool import CardPool
from mtg_utils.deck_cli import bulk_data_option, resolve_bulk_path

BUCKETS = ("doubles", "hits_partner", "target_player", "step_triggers")
_ROW_BUCKETS = (*BUCKETS, "removal_reach")
_OPPONENT = "Opponent"
# Removal answer types that reach a permanent on the board, and the ones that
# can take a planeswalker (``Any`` — "any target" — is read off the recipient).
_BOARD_TYPES = frozenset({"Creature", "Planeswalker", "Permanent"})
_WALKER_TYPES = frozenset({"Planeswalker", "Permanent"})
_WHOSE = {None: "each", "OnlyDuringOpponentsTurn": "each_opponent"}
# A step trigger's "that player" / "that opponent", by whose step it watches —
# the (bucket, how) row both paths write.
_SCOPED_ROW = {
    "opponents": ("doubles", "that opponent"),
    "each": ("hits_partner", "that player"),
}


def _is_emblem(card: dict) -> bool:
    return card.get("layout") == "emblem" or (card.get("type_line") or "").startswith(
        "Emblem"
    )


class _Rows:
    """One card's bucket rows, deduplicated per bucket, in first-seen order."""

    def __init__(self) -> None:
        self.buckets: dict[str, list[dict]] = {b: [] for b in BUCKETS}
        self.veto = False

    def add(self, bucket: str, row: dict) -> None:
        if row not in self.buckets[bucket]:
            self.buckets[bucket].append(row)


# ── IR path ──────────────────────────────────────────────────────────────────


def _units(card: dict) -> Iterator[AbilityUnit]:
    """Every ability unit across the card's concept trees (one tree per face)."""
    for tree in trees_for(card, bulk=card):
        yield from tree.units


def _unit_effects(unit: AbilityUnit) -> Iterator[ConceptNode]:
    """The unit's own effects plus every effect inside an ability or trigger it
    grants (Sanctum Lurker's planeswalkers' "[+2]: … 1 damage to each opponent")."""
    yield from unit.effects
    yield from iter_nested_granted_effect_concepts(unit.node)


def _vetoed(unit: AbilityUnit, c: ConceptNode) -> bool:
    """The "each other player" veto: phase reads it as ``player_scope: Opponent``,
    but at a 2HG table "each other player" includes your partner."""
    if effect_owner_player_scope(unit.node, c.node) != _OPPONENT:
        return False
    clause = effect_owner_raw(unit.node, c.node)
    if not clause:
        # No clause of its own (Grave Pact's trigger ``execute``): the whole
        # ability's text speaks for this effect only when no sibling effect is
        # opponent-owned too, so a sibling's "each other player" can't be
        # pinned on an "each opponent" effect.
        if any(
            e is not c and effect_owner_player_scope(unit.node, e.node) == _OPPONENT
            for e in _unit_effects(unit)
        ):
            return False
        clause = _node_raw(unit.node)
    return "each other player" in clause.lower()


def _reach_how(unit: AbilityUnit, c: ConceptNode, reach: str) -> str:
    """How a reach reads on the sheet: a player-level effect ("each opponent
    discards") or a mass effect on permanents ("your opponents' creatures")."""
    if reach == "per_opponent":
        return "for each opponent"
    if effect_owner_player_scope(unit.node, c.node) or player_filter_tag(c.node):
        return "each player" if reach == "each" else "each opponent"
    types = filter_core_types(effect_filter(c.node))
    plural = " and ".join(f"{t.lower()}s" for t in dict.fromkeys(types))
    return f"all {plural}" if reach == "each" else f"your opponents' {plural}"


def _effect_rows(unit: AbilityUnit, rows: _Rows) -> None:
    for c in _unit_effects(unit):
        reach = effect_player_reach(unit.node, c.node)
        if reach is None:
            continue
        if reach == "scoped":
            # "that player" of an each-player / each-opponent step trigger.
            scoped = _SCOPED_ROW.get(scoped_player_scope(unit) or "")
            if scoped is not None:
                bucket, how = scoped
                rows.add(bucket, {"what": c.concept, "how": how})
            continue
        if reach == "each":
            rows.add(
                "hits_partner", {"what": c.concept, "how": _reach_how(unit, c, reach)}
            )
        elif reach == "target":
            rows.add("target_player", {"what": c.concept, "how": "target player"})
        elif _vetoed(unit, c):
            rows.veto = True
            rows.add("hits_partner", {"what": c.concept, "how": "each other player"})
        else:
            rows.add("doubles", {"what": c.concept, "how": _reach_how(unit, c, reach)})


def _concepts(unit: AbilityUnit) -> str:
    return "+".join(dict.fromkeys(c.concept for c in unit.effects)) or "other"


def _trigger_rows(unit: AbilityUnit, rows: _Rows) -> None:
    trig = unit.node
    if unit.trigger_event == "phase":
        constraint = trigger_turn_constraint(trig)
        if constraint in _WHOSE:  # "your [step]" triggers don't change in 2HG
            rows.add(
                "step_triggers",
                {
                    "what": _concepts(unit),
                    "step": trigger_phase(trig) or "?",
                    "whose": _WHOSE[constraint],
                    # CR 805.4d: once per head only when it refers to "that player".
                    "fires": "per_head" if refers_to_scoped_player(trig) else "once",
                },
            )
        return
    # A batched "one or more opponents" watcher fires once however many heads it sees.
    if getattr(trig, "batched", False) is True:
        return
    if (
        trigger_scope(trig) == "opponents"
        or trigger_subject_scope(trig) == "opponents"
        or is_opponent_cast_trigger_def(trig)
    ):
        rows.add(
            "doubles",
            {
                "what": _concepts(unit),
                "how": f"opponent trigger ({unit.trigger_event})",
            },
        )


def _static_rows(unit: AbilityUnit, rows: _Rows) -> None:
    ctrl = filter_controller(effect_filter(unit.node))
    if modify_cost_mode(unit.node) == "Raise":
        if ctrl == _OPPONENT:
            rows.add("doubles", {"what": "tax", "how": "your opponents' spells"})
        elif ctrl is None:
            rows.add("hits_partner", {"what": "tax", "how": "every player's spells"})
        return
    if ctrl == _OPPONENT:
        what = next((c.concept for c in unit.statics), "static")
        rows.add("doubles", {"what": what, "how": "your opponents' permanents"})


def _replacement_rows(unit: AbilityUnit, rows: _Rows) -> None:
    node = unit.node
    if damage_filter_scope(node, "damage_target_filter") == "opponents":
        rows.add("doubles", {"what": "damage", "how": "replacement on opponents"})
    elif filter_controller(getattr(node, "valid_card", None)) == _OPPONENT:
        rows.add(
            "doubles", {"what": "replacement", "how": "your opponents' permanents"}
        )


def _ir_rows(card: dict) -> _Rows:
    rows = _Rows()
    for unit in _units(card):
        _effect_rows(unit, rows)
        if unit.origin == "trigger":
            _trigger_rows(unit, rows)
        elif unit.origin == "static":
            _static_rows(unit, rows)
        elif unit.origin == "replacement":
            _replacement_rows(unit, rows)
    return rows


def _ir_removal_reach(card: dict) -> tuple[bool, int | None] | None:
    """(can hit a planeswalker, mana-value floor) over the card's removal effects
    (the shared removal walk: destroy / damage / exile / tuck / fight / -X/-X)
    and the sacrifices it forces on another player (the shared edict walk, gated
    on the ``edict_makers`` actor read — Winter, Tormented Loner's "you may
    sacrifice a creature or planeswalker" is yours, not theirs) — or ``None``
    when none of them reaches a permanent. Damage reaches the board only when
    aimed at "any target" (Lightning Bolt), never player-only damage (Screeching
    Soulbreaker's "1 damage to each opponent"), and an effect on the card itself
    reaches nothing (the shared walk counts any -X/-X). The floor is the lowest among
    the reaching effects (Your Fate Ends Here → 3; ``None`` when any has none).
    """
    walkers = False
    floors: list[int] = []
    answers = (
        *removal_edict_answers(card, soft=True),
        *removal_edict_answers(card, "edict", forced_only=True),
    )
    for c, types in answers:
        rt = recipient_tag(c.node)
        if rt == "SelfRef":
            continue  # a shrink on the card itself (Loot, the Anomaly's -2/-0)
        if types & _BOARD_TYPES:
            walkers = walkers or bool(types & _WALKER_TYPES)
            floors.append(filter_mana_value_floor(effect_filter(c.node)) or 0)
        elif "Any" in types and rt == "Any":
            walkers = True
            floors.append(0)
    if not floors:
        return None
    return walkers, min(floors) or None


# ── text path (the no-coverage degrade) ──────────────────────────────────────
# These regexes run ONLY for a card the Card IR can't see (no concept trees: a
# set newer than the phase pin, or a synthetic record) — like
# ``card_classify.ramp_by_text``. Never use them to classify a covered card.

_EACH_OTHER_PLAYER = re.compile(r"\beach other player\b")
_TEXT_DOUBLES = (
    (re.compile(r"\bfor each opponent\b"), "for each opponent"),
    (re.compile(r"\beach opponent\b(?!'s)"), "each opponent"),
    (re.compile(r"\byour opponents control\b"), "your opponents' permanents"),
    (re.compile(r"\byour opponents cast\b"), "your opponents' spells"),
    (re.compile(r"\bwhenever an opponent\b"), "opponent trigger"),
    (
        re.compile(r"\bwhenever (?:a|an|another) [^,.]*?\ban opponent controls\b"),
        "opponent trigger",
    ),
)
_TEXT_PARTNER = (
    (re.compile(r"\beach player\b(?!'s)"), "each player"),
    (
        re.compile(
            r"\b(?:each|all) (?:other )?(?:nonland )?(?:creatures?|permanents?)"
            r"(?: and planeswalkers?)?+\b"
            r"(?! (?:you|your opponents|an opponent|target player|that player) "
            r"controls?| cards?\b)"
        ),
        "all permanents",
    ),
)
_TEXT_TARGET = re.compile(r"\btarget player\b")
_TEXT_STEP = re.compile(
    r"^at the beginning of (each player's|each opponent's|each|the) "
    r"(upkeep|draw step|end step|combat|precombat main phase|postcombat main phase)\b"
)
_TEXT_STEP_NAMES = {
    "upkeep": "Upkeep",
    "draw step": "Draw",
    "end step": "End",
    "combat": "BeginCombat",
    "precombat main phase": "PreCombatMain",
    "postcombat main phase": "PostCombatMain",
}
_THAT_PLAYER = re.compile(r"\bthat (?:player|opponent)\b")
_TEXT_WHAT = (
    (re.compile(r"\bdiscards?\b"), "discard"),
    (re.compile(r"\bsacrifices?\b"), "sacrifice"),
    (re.compile(r"\bloses? [^.]*?\blife\b"), "lose_life"),
    (re.compile(r"\bdeals? [^.]*?\bdamage\b"), "deal_damage"),
    (re.compile(r"\bdestroy\b"), "destroy"),
    (re.compile(r"\bexile\b"), "change_zone"),
    (re.compile(r"\breturn\b"), "bounce"),
    (re.compile(r"\b(?:un)?tap\b"), "tap_untap"),
    (re.compile(r"\bdraws?\b"), "draw"),
    (re.compile(r"\bmills?\b"), "mill"),
    (re.compile(r"\bcreates?\b"), "make_token"),
    (re.compile(r"\bgets? [+-]"), "pump"),
    (re.compile(r"\bcounters?\b"), "place_counter"),
    (re.compile(r"\bcosts? [^.]*?\bmore\b"), "tax"),
    (re.compile(r"\bgains? [^.]*?\blife\b"), "gain_life"),
)
_TEXT_WALKERS = re.compile(
    r"\bany target\b|\bplaneswalkers?\b|\btarget (?:nonland |nontoken )?permanent\b"
)
_TEXT_MV_FLOOR = re.compile(r"\bmana value (\d+) or greater\b")
_TEXT_REMOVAL = re.compile(
    r"\b(?:destroy|exile) (?:up to \w+ )?(?:target|all|each)\b"
    r"|\bdeals? (?:\w+ )?damage to (?:any target|each creature"
    r"|(?:up to \w+ )?target (?!opponent|player))"
    r"|\bgets? -\d+/-\d+"
    r"|\bsacrifices? (?:a|an|\w+) (?:[\w-]+ )*?(?:creature|planeswalker|permanent)"
    r"|\breturn (?:up to \w+ )?target (?:[\w-]+ )*?(?:creature|permanent)\b(?! card)"
)
_TEXT_BOARD = re.compile(
    r"\bany target\b|\btarget (?:[\w-]+ )*?(?:creature|planeswalker|permanent)\b"
    r"|\b(?:each|all) (?:[\w-]+ )*?(?:creatures?|planeswalkers?|permanents?)\b"
)


def _text_what(clause: str) -> str:
    return next((what for rx, what in _TEXT_WHAT if rx.search(clause)), "text")


def _text(card: dict) -> str:
    """The card's oracle text, reminder text stripped, lowercased."""
    return _REMINDER_RE.sub("", get_oracle_text(card)).lower()


def _text_clauses(card: dict) -> list[str]:
    return [c.strip() for line in _text(card).splitlines() for c in clauses(line)]


def _text_step_row(clause: str, rows: _Rows) -> bool:
    m = _TEXT_STEP.match(clause)
    if m is None:
        return False
    whose = "each_opponent" if m.group(1) == "each opponent's" else "each"
    per_head = m.group(1) != "the" and bool(_THAT_PLAYER.search(clause))
    what = _text_what(clause[m.end() :])
    rows.add(
        "step_triggers",
        {
            "what": what,
            "step": _TEXT_STEP_NAMES[m.group(2)],
            "whose": whose,
            "fires": "per_head" if per_head else "once",
        },
    )
    if per_head:
        bucket, how = _SCOPED_ROW["opponents" if whose == "each_opponent" else "each"]
        rows.add(bucket, {"what": what, "how": how})
    return True


def _text_rows(card: dict) -> _Rows:
    rows = _Rows()
    for clause in _text_clauses(card):
        if _text_step_row(clause, rows):
            continue
        what = _text_what(clause)
        if _EACH_OTHER_PLAYER.search(clause):
            rows.add("hits_partner", {"what": what, "how": "each other player"})
        else:
            for rx, how in _TEXT_DOUBLES:
                if rx.search(clause):
                    rows.add("doubles", {"what": what, "how": how})
                    break
            for rx, how in _TEXT_PARTNER:
                if rx.search(clause):
                    rows.add("hits_partner", {"what": what, "how": how})
                    break
        if _TEXT_TARGET.search(clause):
            rows.add("target_player", {"what": what, "how": "target player"})
    return rows


def _text_removal(card: dict) -> tuple[bool, bool, int | None]:
    """(removes a permanent, can hit a planeswalker, mana-value floor) from text."""
    text = _text(card)
    floors = [int(n) for n in _TEXT_MV_FLOOR.findall(text)]
    return (
        bool(_TEXT_REMOVAL.search(text) and _TEXT_BOARD.search(text)),
        bool(_TEXT_WALKERS.search(text)),
        min(floors) if floors else None,
    )


# ── the card and the set ─────────────────────────────────────────────────────


def _removal_reach(card: dict, *, ir: bool) -> dict | None:
    if ir:
        # The cheap structural read first: ``role_of`` runs the signal path,
        # so only a card whose removal reaches the board pays for it.
        reach = _ir_removal_reach(card)
        if reach is None:
            return None
        roles = role_of(card)
        if "interaction" not in roles and "board_wipe" not in roles:
            return None
        walkers, floor = reach
    else:
        reaches, walkers, floor = _text_removal(card)
        if not reaches:
            return None
    # A floor misses the Jace tokens: no mana cost, so mana value 0 (CR 202.3a).
    return {"walkers": walkers, "mv_floor": floor}


def _scan(card: dict) -> tuple[str, dict | None] | None:
    """``None`` for an emblem (not a card in the set); else the card's path and
    its row, the row ``None`` when no bucket holds the card."""
    if _is_emblem(card):
        return None
    ir = bool(trees_for(card, bulk=card))
    rows = _ir_rows(card) if ir else _text_rows(card)
    path = "text" if not ir else ("ir+veto" if rows.veto else "ir")
    row = {
        "name": card.get("name", ""),
        "rarity": card.get("rarity") or "",
        "path": path,
        **rows.buckets,
        "removal_reach": _removal_reach(card, ir=ir),
    }
    return path, (row if any(row[b] for b in _ROW_BUCKETS) else None)


def classify_card(card: dict) -> dict | None:
    """One card's 2HG rows, or ``None`` for an emblem or a card no bucket holds.

    ``path`` is ``ir`` (the Card IR), ``text`` (the oracle-text degrade for a card
    the IR can't see) or ``ir+veto`` (the IR plus the "each other player" veto).
    A double-faced or prepare card unions its faces' rows."""
    scanned = _scan(card)
    return scanned[1] if scanned else None


def twohg_scan(records: Sequence[dict], *, code: str | None = None) -> dict:
    """The 2HG readout over one set's records (one per distinct card)."""
    cards: list[dict] = []
    coverage = {"ir": 0, "text": 0}
    for rec in records:
        scanned = _scan(rec)
        if scanned is None:
            continue
        path, row = scanned
        coverage["text" if path == "text" else "ir"] += 1
        if row is not None:
            cards.append(row)
    cards.sort(key=lambda r: r["name"])
    return {
        "code": (code or "").upper() or None,
        "size": sum(coverage.values()),
        "coverage": coverage,
        "counts": {b: sum(bool(c[b]) for c in cards) for b in _ROW_BUCKETS},
        "cards": cards,
    }


_TITLES = {
    "doubles": "x2 — does double work against two opponents",
    "hits_partner": "Hits your partner too",
    "target_player": "Target player — can be aimed at your partner",
    "step_triggers": "Step triggers — once per step, or once per head (CR 805.4d)",
    "removal_reach": "Removal reach — planeswalkers and mana-value floors",
}


def _row_text(bucket: str, row: dict) -> str:
    if bucket == "step_triggers":
        whose = (
            "each opponent's turn" if row["whose"] == "each_opponent" else "each turn"
        )
        fires = "once per head" if row["fires"] == "per_head" else "once"
        return f"{row['step']}, {whose}: {row['what']}, {fires}"
    return f"{row['what']} ({row['how']})"


def _removal_text(reach: dict) -> str:
    text = "hits planeswalkers" if reach["walkers"] else "creature-only"
    if reach["mv_floor"]:
        text += f"; mana value {reach['mv_floor']}+ (misses Jace tokens)"
    return text


def render_twohg_scan(scan: dict) -> str:
    cov = scan["coverage"]
    lines = [
        (
            f"twohg-scan: {scan.get('code') or '?'} — {scan['size']} cards "
            f"(Card IR {cov['ir']}, text {cov['text']})"
        )
    ]
    for bucket in _ROW_BUCKETS:
        lines.extend(("", f"{_TITLES[bucket]} ({scan['counts'][bucket]}):"))
        for card in (c for c in scan["cards"] if c[bucket]):
            tag = f"[{card['path']}]"
            if bucket == "removal_reach":
                detail = _removal_text(card[bucket])
            else:
                detail = "; ".join(_row_text(bucket, r) for r in card[bucket])
            lines.append(f"  {card['name']} {tag}: {detail}")
    return "\n".join(lines) + "\n"


@click.command("twohg-scan")
@click.option("--set", "set_code", required=True, help="The set code (e.g. FRA).")
@bulk_data_option
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of text.")
def main(set_code: str, bulk_data: Path | None, *, as_json: bool) -> None:
    """Which of set SET's cards play differently in Two-Headed Giant."""
    pool = CardPool.load(resolve_bulk_path(bulk_data))
    records = pool.set_records(set_code)
    if not records:
        raise click.ClickException(f"no cards found for set {set_code!r}")
    scan = twohg_scan(records, code=set_code)
    click.echo(json.dumps(scan, indent=2) if as_json else render_twohg_scan(scan))


if __name__ == "__main__":
    main()
