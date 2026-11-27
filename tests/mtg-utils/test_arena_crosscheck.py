"""``arena-crosscheck`` (ADR-0064): Arena's game log against phase's parse.

Each test writes a small Arena card database and a ``Player.log`` holding the
game-state messages Arena's rules engine sends, for real cards whose text comes from
``testkit`` (ADR-0056), and checks what the crosscheck reports.
"""

from __future__ import annotations

import gzip
import json
import re
import sqlite3
from pathlib import Path

import pytest

from mtg_utils._arena_crosscheck.align import abilities_of, norm, pair
from mtg_utils._arena_crosscheck.check import Checker, crosscheck, watches_own_event
from mtg_utils._arena_crosscheck.effects import compare_kinds
from mtg_utils._arena_crosscheck.log import ObjectEvent, read_logs
from mtg_utils._arena_crosscheck.report import (
    build_report,
    diff_reports,
    render_markdown,
)
from mtg_utils._card_ir.crosswalk import (
    TriggerSuppression,
    chosen_x_sign,
    effect_is_delayed,
    effect_targets_optional,
    trigger_gates,
    trigger_suppressions,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.arena_card_db import ACTIVATED, TRIGGERED, CardText
from mtg_utils.testkit import test_card, test_card_ir

BOLT, VISIONARY, A_BOLT = 1001, 1002, 1004
GROWTH, BLAZE, HEEL, RECLAMATION, ABBOT = 1005, 1006, 1007, 1008, 1009
CHAMPIONS, SWIFTSPEAR, CLOUDSHIFT = 1010, 1011, 1012
VISIONARY_ETB, ABBOT_PROWESS, CHAMPIONS_ETB, SWIFTSPEAR_PROWESS = 2001, 2002, 2003, 2004
STACK, BATTLEFIELD, HAND, LIBRARY, GRAVEYARD = 27, 28, 31, 32, 33
EXILE, THEIR_HAND = 29, 35


def _card_of(name: str) -> dict | None:
    try:
        test_card_ir(name)  # seeds the card's phase trees from the snapshot
        return test_card(name)
    except KeyError:
        return None


def _arena_text(name: str) -> str:
    """The card's oracle text as Arena writes it: the card (or its short name) as
    ``CARDNAME``, reminder text dropped."""
    text = test_card(name)["oracle_text"]
    for ref in (name, name.split(",", maxsplit=1)[0]):
        text = text.replace(ref, "CARDNAME")
    return re.sub(r" ?\([^)]*\)", "", text)


@pytest.fixture
def card_db(tmp_path: Path) -> Path:
    path = tmp_path / "Raw_CardDatabase_test.mtga"
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE Cards (GrpId INT, TitleId INT, IsRebalanced INT,"
        " IsDigitalOnly INT, IsToken INT);"
        "CREATE TABLE Abilities (Id INT, Category INT, TextId INT, BaseId INT,"
        " HiddenByAbilityIds TEXT, BaseIdNumeral INT);"
        "CREATE TABLE Localizations_enUS (LocId INT, Formatted INT, Loc TEXT);"
        "CREATE TABLE Enums (Type TEXT, Value INT, LocId INT);"
    )
    names = {
        BOLT: "Lightning Bolt",
        VISIONARY: "Elvish Visionary",
        A_BOLT: "A-Lightning Bolt",
        GROWTH: test_card("Giant Growth")["name"],
        BLAZE: test_card("Blaze")["name"],
        HEEL: test_card("Call to Heel")["name"],
        RECLAMATION: test_card("Heritage Reclamation")["name"],
        ABBOT: test_card("Abbot of Keral Keep")["name"],
        CHAMPIONS: test_card("Champions from Beyond")["name"],
        SWIFTSPEAR: test_card("Monastery Swiftspear")["name"],
        CLOUDSHIFT: test_card("Cloudshift")["name"],
    }
    for grp, name in names.items():
        con.execute("INSERT INTO Localizations_enUS VALUES (?, 0, ?)", (grp, name))
        con.execute(
            "INSERT INTO Cards VALUES (?, ?, ?, 0, 0)",
            (grp, grp, int(name.startswith("A-"))),
        )
    etb = _arena_text("Elvish Visionary")
    con.execute("INSERT INTO Localizations_enUS VALUES (9001, 1, ?)", (etb,))
    con.execute(
        "INSERT INTO Abilities VALUES (?, ?, 9001, 0, NULL, 0)",
        (VISIONARY_ETB, TRIGGERED),
    )
    con.execute("INSERT INTO Localizations_enUS VALUES (9003, 1, 'Prowess')")
    for prowess in (ABBOT_PROWESS, SWIFTSPEAR_PROWESS):
        con.execute(
            "INSERT INTO Abilities VALUES (?, ?, 9003, 0, NULL, 0)",
            (prowess, TRIGGERED),
        )
    makes_heroes = _arena_text("Champions from Beyond").splitlines()[0]
    con.execute("INSERT INTO Localizations_enUS VALUES (9004, 1, ?)", (makes_heroes,))
    con.execute(
        "INSERT INTO Abilities VALUES (?, ?, 9004, 0, NULL, 0)",
        (CHAMPIONS_ETB, TRIGGERED),
    )
    con.execute("INSERT INTO Localizations_enUS VALUES (9002, 1, '<nobr>+1/+1</nobr>')")
    con.execute("INSERT INTO Enums VALUES ('CounterType', 1, 9002)")
    con.commit()
    con.close()
    return path


# -- a tiny log writer ----------------------------------------------------
def _kv(key: str, value: object) -> dict:
    if isinstance(value, str):
        return {"key": key, "valueString": [value]}
    return {"key": key, "valueInt32": [value]}


def _ann(
    aid: int, kind: str, affector: int | None, affected: list[int], **details
) -> dict:
    out = {"id": aid, "type": [f"AnnotationType_{kind}"], "affectedIds": affected}
    if affector is not None:
        out["affectorId"] = affector
    out["details"] = [_kv(k, v) for k, v in details.items()]
    return out


def _obj(
    iid: int, grp: int, kind: str = "Card", types=("Instant",), controller=1, **extra
) -> dict:
    return {
        "instanceId": iid,
        "grpId": grp,
        "type": f"GameObjectType_{kind}",
        "cardTypes": [f"CardType_{t}" for t in types],
        "controllerSeatId": controller,
        "ownerSeatId": controller,
        **extra,
    }


ZONES = [
    {"zoneId": STACK, "type": "ZoneType_Stack"},
    {"zoneId": BATTLEFIELD, "type": "ZoneType_Battlefield"},
    {"zoneId": HAND, "type": "ZoneType_Hand", "ownerSeatId": 1},
    {"zoneId": LIBRARY, "type": "ZoneType_Library", "ownerSeatId": 1},
    {"zoneId": GRAVEYARD, "type": "ZoneType_Graveyard", "ownerSeatId": 1},
    {"zoneId": EXILE, "type": "ZoneType_Exile"},
    {"zoneId": THEIR_HAND, "type": "ZoneType_Hand", "ownerSeatId": 2},
]


def _state(match: str, objects=(), annotations=(), *, first: bool = False) -> dict:
    state = {
        "gameObjects": list(objects),
        "annotations": list(annotations),
        "turnInfo": {"turnNumber": 3},
    }
    state["gameInfo"] = {"matchID": match, "gameNumber": 1}
    if first:
        state["players"] = [{"systemSeatNumber": 1}, {"systemSeatNumber": 2}]
        state["zones"] = ZONES
    return state


def _write(path: Path, states: list[dict]) -> Path:
    lines = [
        "[UnityCrossThreadLogger]"
        + json.dumps(
            {"greToClientEvent": {"greToClientMessages": [{"gameStateMessage": s}]}}
        )
        for s in states
    ]
    text = "\n".join(["Initialize engine", *lines]) + "\n"
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(text.encode()))
    else:
        path.write_text(text)
    return path


def _bolt_game(match: str = "m1", damage: int = 3) -> list[dict]:
    """Lightning Bolt (seat 1) resolving at seat 2."""
    return [
        _state(match, [_obj(100, BOLT)], first=True),
        _state(
            match,
            annotations=[
                _ann(1, "ResolutionStart", 100, [100], grpid=BOLT),
                _ann(2, "DamageDealt", 100, [2], damage=damage, type=2),
                _ann(3, "ModifiedLife", 100, [2], life=-damage),
                _ann(4, "ResolutionComplete", 100, [100], grpid=BOLT),
            ],
        ),
    ]


def _spell_game(grp: int, *effects: dict, objects=(), match: str = "m3") -> list[dict]:
    """A spell (instance 100, seat 1) resolving with ``effects`` logged."""
    return [
        _state(match, [_obj(100, grp), *objects], first=True),
        _state(
            match,
            annotations=[
                _ann(1, "ResolutionStart", 100, [100], grpid=grp),
                *effects,
                _ann(90, "ResolutionComplete", 100, [100], grpid=grp),
            ],
        ),
    ]


def _checks_of(card_db: Path, tmp_path: Path, game: list[dict]) -> tuple[dict, dict]:
    """The one resolution's row and its strict checks by name."""
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    return row, {c["check"]: c for c in row["checks"]}


def _visionary_game(match: str = "m2", *, event: str = "enters") -> list[dict]:
    """Elvish Visionary enters (or, for ``event="phase"``, a step changes) and its
    trigger fires, then resolves drawing a card."""
    trigger_context = (
        _ann(
            10,
            "ZoneTransfer",
            None,
            [200],
            zone_src=STACK,
            zone_dest=BATTLEFIELD,
            category="Resolve",
        )
        if event == "enters"
        else _ann(10, "PhaseOrStepModified", None, [1], phase=1)
    )
    return [
        _state(match, [_obj(200, VISIONARY, types=("Creature",))], first=True),
        _state(
            match,
            [
                _obj(
                    201,
                    VISIONARY_ETB,
                    kind="Ability",
                    objectSourceGrpId=VISIONARY,
                    parentId=200,
                )
            ],
            [
                trigger_context,
                _ann(11, "AbilityInstanceCreated", 200, [201], source_zone=BATTLEFIELD),
            ],
        ),
        _state(
            match,
            [_obj(202, 55555, types=("Land",))],
            [
                _ann(20, "ResolutionStart", 201, [201], grpid=VISIONARY_ETB),
                _ann(21, "ObjectIdChanged", 201, [150], orig_id=150, new_id=202),
                _ann(
                    22,
                    "ZoneTransfer",
                    201,
                    [202],
                    zone_src=LIBRARY,
                    zone_dest=HAND,
                    category="Draw",
                ),
                _ann(23, "ResolutionComplete", 201, [201], grpid=VISIONARY_ETB),
            ],
        ),
    ]


def _run(card_db: Path, *paths: Path, ignores: list[dict] | None = None) -> dict:
    checker = Checker(CardText(card_db), _card_of, trees_for, ignores or [])
    return crosscheck(paths, checker, "vtest")


# -- resolutions -----------------------------------------------------------
def test_bolt_agrees_with_phase(card_db, tmp_path):
    report = _run(card_db, _write(tmp_path / "Player.log", _bolt_game()))
    (row,) = report["resolutions"]
    assert row["card"] == "Lightning Bolt"
    assert row["status"] == "agree"
    checks = {c["check"]: c for c in row["checks"]}
    assert checks["damage amount"]["ok"]
    assert checks["damage amount"]["expected"] == [3]


def test_a_wrong_amount_fails_the_strict_check(card_db, tmp_path):
    """Bolt dealing 2 in the log: phase's fixed 3 doesn't fit."""
    report = _run(card_db, _write(tmp_path / "Player.log", _bolt_game(damage=2)))
    (row,) = report["resolutions"]
    checks = {c["check"]: c for c in row["checks"]}
    assert not checks["damage amount"]["ok"]
    assert report["summary"]["checks"]["damage amount"] == {"pass": 0, "fail": 1}


def test_another_sources_effect_is_set_aside(card_db, tmp_path):
    """A token another permanent made during the resolution isn't Bolt's."""
    game = _bolt_game()
    game[1]["annotations"][-1]["id"] = 6  # ResolutionComplete, after the token
    game[1]["annotations"].insert(3, _ann(5, "TokenCreated", 999, [300]))
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    assert row["status"] == "agree"
    assert "token" not in row["arena"]
    assert row["other_source"] == ["TokenCreated"]


def test_an_ignored_arena_mistake_is_not_flagged(card_db, tmp_path):
    ignores = [{"card": "Lightning Bolt", "ability": "", "reason": "test: Arena's"}]
    log = _write(tmp_path / "Player.log", _bolt_game(damage=2))
    report = _run(card_db, log, ignores=ignores)
    (row,) = report["resolutions"]
    assert row["status"] == "ignored"
    assert row["ignored"] == "test: Arena's"
    assert report["summary"]["checks"] == {}
    agreeing = _run(
        card_db, _write(tmp_path / "ok.log", _bolt_game("m9")), ignores=ignores
    )
    assert agreeing["resolutions"][0]["status"] == "agree"  # nothing to ignore


def test_an_unsure_pairing_is_listed_not_scored(card_db, tmp_path):
    con = sqlite3.connect(card_db)
    con.execute(
        "UPDATE Localizations_enUS SET Loc = 'Whenever you gain life, scry 1.' WHERE LocId = 9001"
    )
    con.commit()
    con.close()
    report = _run(card_db, _write(tmp_path / "Player.log", _visionary_game()))
    (row,) = report["resolutions"]
    assert row["status"] == "unsure-pairing"
    assert "checks" not in row
    assert row["phase_text"]  # the nearest phase text, for a reader


def test_a_rebalanced_card_is_compared_with_a_warning(card_db, tmp_path):
    game = _bolt_game()
    game[0]["gameObjects"] = [_obj(100, A_BOLT)]
    for ann in game[1]["annotations"]:
        ann["details"] = [
            _kv("grpid", A_BOLT) if d["key"] == "grpid" else d for d in ann["details"]
        ]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    assert row["card"] == "Lightning Bolt"
    assert row["warnings"] == ["rebalanced"]
    assert row["status"] == "agree"


def test_a_triggered_ability_resolves_and_its_draw_checks(card_db, tmp_path):
    report = _run(card_db, _write(tmp_path / "Player.log", _visionary_game()))
    (row,) = report["resolutions"]
    assert row["status"] == "agree"
    assert row["pairing"] == "text"
    checks = {c["check"]: c for c in row["checks"]}
    assert checks["draw count"]["ok"]
    assert checks["drawing player"]["observed"] == "you"


def test_a_pump_is_checked_against_the_logged_change(card_db, tmp_path):
    """Giant Growth's +3/+3 against the power / toughness change Arena logged."""
    creature = _obj(300, VISIONARY, types=("Creature",))

    def grown(by: int) -> list[dict]:
        change = _ann(2, "PowerToughnessModCreated", 100, [300], power=by, toughness=by)
        return _spell_game(GROWTH, change, objects=[creature])

    row, checks = _checks_of(card_db, tmp_path, grown(3))
    assert row["status"] == "agree"
    assert checks["pump amount"]["ok"]
    assert checks["pump amount"]["expected"] == [[3, 3]]
    _row, checks = _checks_of(card_db, tmp_path, grown(2))
    assert not checks["pump amount"]["ok"]


def test_an_x_spell_is_checked_against_the_x_arena_logged(card_db, tmp_path):
    """Blaze deals X damage. Arena logs the X chosen as the spell is cast, so the
    damage is checked against it; with no X logged there is nothing to check."""

    def blaze(damage: int, *, x: int | None) -> list[dict]:
        game = _spell_game(
            BLAZE,
            _ann(2, "DamageDealt", 100, [2], damage=damage, type=2),
            _ann(3, "ModifiedLife", 100, [2], life=-damage),
        )
        if x is not None:
            game[0]["persistentAnnotations"] = [
                _ann(50, "CastingTimeOption", None, [100], type=2, value=x)
            ]
        return game

    row, checks = _checks_of(card_db, tmp_path, blaze(4, x=4))
    assert row["x"] == 4
    assert checks["damage amount"]["ok"]
    assert checks["damage amount"]["expected"] == [4]
    _row, checks = _checks_of(card_db, tmp_path, blaze(3, x=4))
    assert not checks["damage amount"]["ok"]
    row, checks = _checks_of(card_db, tmp_path, blaze(3, x=None))
    assert "x" not in row
    assert "damage amount" not in checks


def _champions_game(heroes: int, *, cast_as: int = 400) -> list[dict]:
    """Champions from Beyond's "create X Hero tokens" resolving for the permanent
    with instance 400, the X = 3 logged on the object ``cast_as``."""
    enters = _obj(
        401, CHAMPIONS_ETB, kind="Ability", objectSourceGrpId=CHAMPIONS, parentId=400
    )
    tokens = [
        _obj(500 + n, 0, kind="Token", types=("Creature",), subtypes=["SubType_Hero"])
        for n in range(heroes)
    ]
    first = _state(
        "m5",
        [_obj(400, CHAMPIONS, types=("Enchantment",)), enters, *tokens],
        first=True,
    )
    first["persistentAnnotations"] = [
        _ann(50, "CastingTimeOption", None, [cast_as], type=2, value=3)
    ]
    made = [_ann(2 + n, "TokenCreated", 401, [500 + n]) for n in range(heroes)]
    return [
        first,
        _state(
            "m5",
            annotations=[
                _ann(1, "ResolutionStart", 401, [401], grpid=CHAMPIONS_ETB),
                *made,
                _ann(90, "ResolutionComplete", 401, [401], grpid=CHAMPIONS_ETB),
            ],
        ),
    ]


def test_an_enters_ability_reads_the_x_its_permanents_spell_was_cast_with(
    card_db, tmp_path
):
    """Champions from Beyond's "create X Hero tokens" (CR 107.3m). A permanent
    keeps its spell's id as it resolves, so Arena's X is on the permanent."""
    row, checks = _checks_of(card_db, tmp_path, _champions_game(3))
    assert row["spell_x"] == 3
    assert "x" not in row  # the ability itself chose no X
    assert checks["token count"]["ok"]
    assert checks["token count"]["expected"] == 3
    _row, checks = _checks_of(card_db, tmp_path, _champions_game(2))
    assert not checks["token count"]["ok"]


def test_a_permanent_that_came_back_was_no_x_spell(card_db, tmp_path):
    """A zone change gives the permanent a new id: the X logged for the object
    it was before is not this one's, and its enters ability reads X as 0."""
    row, checks = _checks_of(card_db, tmp_path, _champions_game(0, cast_as=399))
    assert "spell_x" not in row
    assert "token count" not in checks
    assert row["status"] == "conditional"  # an amount that can be nothing


def test_an_object_an_earlier_effect_named_keeps_the_type_check(card_db, tmp_path):
    """Cloudshift exiles a creature, then returns "that card": the second effect
    names no type of its own, and the creature's type is still checked."""
    mine = _obj(300, VISIONARY, types=("Creature",))
    game = _spell_game(
        CLOUDSHIFT,
        _ann(
            2,
            "ZoneTransfer",
            100,
            [300],
            zone_src=BATTLEFIELD,
            zone_dest=EXILE,
            category="Exile",
        ),
        objects=[mine],
    )
    _row, checks = _checks_of(card_db, tmp_path, game)
    assert checks["moved object type"]["ok"]
    assert checks["moved object type"]["expected"] == ["Creature"]


def test_a_player_named_through_another_object_can_be_either_side(card_db, tmp_path):
    """Call to Heel's "its controller draws a card": the creature's controller,
    whoever that is. An opponent drawing is no mistake, and nothing is checked."""
    theirs = _obj(300, VISIONARY, types=("Creature",), controller=2)
    game = _spell_game(
        HEEL,
        _ann(
            2,
            "ZoneTransfer",
            100,
            [300],
            zone_src=BATTLEFIELD,
            zone_dest=THEIR_HAND,
            category="Return",
        ),
        _ann(
            3,
            "ZoneTransfer",
            100,
            [301],
            zone_src=LIBRARY,
            zone_dest=THEIR_HAND,
            category="Draw",
        ),
        objects=[theirs],
    )
    row, checks = _checks_of(card_db, tmp_path, game)
    assert row["status"] == "agree"
    assert checks["draw count"]["ok"]
    assert "drawing player" not in checks
    assert all(c["ok"] for c in checks.values())


def test_an_effect_on_any_card_leaves_the_type_unchecked(card_db, tmp_path):
    """Heritage Reclamation destroys an artifact or an enchantment, or exiles a
    card of any type from a graveyard: an instant leaving the graveyard is no
    wrong type."""
    game = _spell_game(
        RECLAMATION,
        _ann(
            2,
            "ZoneTransfer",
            100,
            [300],
            zone_src=GRAVEYARD,
            zone_dest=EXILE,
            category="Exile",
        ),
        _ann(
            3,
            "ZoneTransfer",
            100,
            [301],
            zone_src=LIBRARY,
            zone_dest=HAND,
            category="Draw",
        ),
        objects=[_obj(300, BOLT)],
    )
    _row, checks = _checks_of(card_db, tmp_path, game)
    assert "moved object type" not in checks
    assert all(c["ok"] for c in checks.values())


def test_a_keyword_phase_writes_no_ability_for_is_keyword_only(card_db, tmp_path):
    """Arena resolves prowess as an ability of its own; phase lists it as a
    keyword on the card. There is nothing to compare, and it isn't unsure."""
    prowess = _obj(
        401, ABBOT_PROWESS, kind="Ability", objectSourceGrpId=ABBOT, parentId=400
    )
    game = [
        _state("m4", [_obj(400, ABBOT, types=("Creature",)), prowess], first=True),
        _state(
            "m4",
            annotations=[
                _ann(1, "ResolutionStart", 401, [401], grpid=ABBOT_PROWESS),
                _ann(2, "PowerToughnessModCreated", 401, [400], power=1, toughness=1),
                _ann(3, "ResolutionComplete", 401, [401], grpid=ABBOT_PROWESS),
            ],
        ),
    ]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    assert row["status"] == "keyword-only"
    assert "pairing_score" not in row
    # Monastery Swiftspear has haste and prowess and nothing phase writes an
    # ability for: its prowess is keyword-only too, not a card with no parse
    for state in game:
        for obj in state["gameObjects"]:
            obj["grpId"] = {ABBOT: SWIFTSPEAR, ABBOT_PROWESS: SWIFTSPEAR_PROWESS}[
                obj["grpId"]
            ]
            if "objectSourceGrpId" in obj:
                obj["objectSourceGrpId"] = SWIFTSPEAR
        for ann in state["annotations"]:
            for detail in ann["details"]:
                if detail["key"] == "grpid":
                    detail["valueInt32"] = [SWIFTSPEAR_PROWESS]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    assert (row["card"], row["status"]) == ("Monastery Swiftspear", "keyword-only")


# -- triggers --------------------------------------------------------------
def test_an_etb_trigger_matches_the_entering(card_db, tmp_path):
    report = _run(card_db, _write(tmp_path / "Player.log", _visionary_game()))
    (row,) = report["triggers"]
    assert row["phase_event"] == "enters"
    assert row["status"] == "match"


def test_an_etb_trigger_after_only_a_step_change_is_a_mismatch(card_db, tmp_path):
    report = _run(
        card_db, _write(tmp_path / "Player.log", _visionary_game(event="phase"))
    )
    (row,) = report["triggers"]
    assert row["status"] == "mismatch"
    assert row["events"] == ["phase"]


def test_only_the_triggering_objects_events_count(card_db, tmp_path):
    """Arena names the object that set the trigger off: another card entering in
    the same message isn't Elvish Visionary's event."""
    game = _visionary_game(event="phase")
    game[1]["annotations"].insert(
        1,
        _ann(9, "ZoneTransfer", None, [777], zone_src=STACK, zone_dest=BATTLEFIELD),
    )
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    assert report["triggers"][0]["status"] == "match"  # no named object: whole message
    game[1]["persistentAnnotations"] = [_ann(30, "TriggeringObject", 201, [200])]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["triggers"]
    assert row["status"] == "mismatch"
    assert row["events"] == ["phase"]


def test_a_reflexive_trigger_is_not_scored(card_db, tmp_path):
    con = sqlite3.connect(card_db)
    con.execute(
        "UPDATE Abilities SET HiddenByAbilityIds = '1234' WHERE Id = ?",
        (VISIONARY_ETB,),
    )
    con.commit()
    con.close()
    report = _run(card_db, _write(tmp_path / "Player.log", _visionary_game()))
    assert report["triggers"][0]["status"] == "reflexive"


def test_an_activated_ability_is_no_trigger(card_db, tmp_path):
    con = sqlite3.connect(card_db)
    con.execute(
        "UPDATE Abilities SET Category = ? WHERE Id = ?", (ACTIVATED, VISIONARY_ETB)
    )
    con.commit()
    con.close()
    report = _run(card_db, _write(tmp_path / "Player.log", _visionary_game()))
    assert report["triggers"] == []


# -- reading logs ----------------------------------------------------------
def test_a_game_in_two_logs_is_read_once(tmp_path):
    first = _write(tmp_path / "a.log.gz", _bolt_game("same"))
    second = _write(tmp_path / "Player.log", _bolt_game("same"))
    resolutions, _, games, _ = read_logs([first, second])
    assert games == [("same", 1)]
    assert len(resolutions) == 1


# -- pairing ---------------------------------------------------------------
def test_arena_mana_symbols_read_as_phases():
    assert norm("Equip {o1oR}") == norm("Equip {1}{R}") == "equip {1}{r}"
    assert norm("Whenever this permanent attacks") == "whenever ~ attacks"


def test_one_arena_ability_phase_writes_as_two_triggers():
    """Ivora's "When ~ enters and whenever it deals combat damage to a player, create
    a Blood token" is two phase triggers; the pairing takes both."""
    abilities = abilities_of(trees_for(_card_of("Ivora, Insatiable Heir")))
    pairing = pair(_arena_text("Ivora, Insatiable Heir").splitlines()[1], abilities)
    assert pairing.method == "split"
    assert {a.trigger_event for a in pairing.abilities} == {"enters", "deals_damage"}


def test_a_cost_written_in_front_still_pairs():
    """Phase writes a loyalty ability with its cost ("[+1]: …"); Arena doesn't."""
    abilities = abilities_of(trees_for(_card_of("Elvish Visionary")))
    text = abilities[0].desc
    assert pair(text.replace("~", "CARDNAME"), abilities).method == "text"
    from mtg_utils._arena_crosscheck.align import _similarity

    assert _similarity("draw a card.", "[+1]: draw a card.") == 1.0
    assert (
        _similarity(
            "put a +1/+1 counter on it.", "when you do, put a +1/+1 counter on it."
        )
        < 1.0
    )


def test_a_saga_chapter_pairs_by_its_number():
    """Arena writes a chapter as its effect and files it under ``SagaChapter``
    with the chapter's number; phase calls the trigger "Chapter N" (CR 714.2b)."""
    abilities = abilities_of(trees_for(_card_of("Fall of the Thran")))
    text = "Each player returns two land cards from their graveyard."
    pairing = pair(text, abilities, keyword="SagaChapter", numeral=3)
    assert pairing.method == "chapter"
    assert pairing.ability.desc == "Chapter 3"
    # no number, no pairing: the text alone is nothing like "Chapter 3"
    assert pair(text, abilities, keyword="SagaChapter").ability is None


def test_persist_pairs_with_its_own_trigger():
    """Phase writes persist's trigger out in full (CR 702.79a) without the word."""
    abilities = abilities_of(trees_for(_card_of("Kitchen Finks")))
    pairing = pair("Persist", abilities)
    assert pairing.method == "keyword"
    assert pairing.ability.desc.startswith("CR 702.79a")


def test_a_listed_keyword_with_no_ability_is_keyword_only():
    abilities = abilities_of(trees_for(_card_of("Abbot of Keral Keep")))
    listed = pair("Prowess", abilities, card_keywords=frozenset({"prowess"}))
    assert (listed.ability, listed.method) == (None, "keyword-only")
    # an instance with its own number: "Ward {2}" is the keyword Ward
    ward = pair("Ward {o2}", [], keyword="Ward", card_keywords=frozenset({"ward"}))
    assert ward.method == "keyword-only"
    assert pair("Prowess", abilities).method == "unsure"  # not on the card
    # the rule is the last resort: an ability phase wrote still pairs by its text
    enters = pair(
        _arena_text("Abbot of Keral Keep").splitlines()[1],
        abilities,
        card_keywords=frozenset({"prowess"}),
    )
    assert enters.method == "text"
    # and a card with a keyword ability phase wrote out stays unsure: Kitchen
    # Finks' "CR 702.79a: …" could be the keyword Arena names
    finks = abilities_of(trees_for(_card_of("Kitchen Finks")))
    listed = frozenset({"persist", "prowess"})
    assert pair("Prowess", finks, card_keywords=listed).method == "unsure"


def test_a_delayed_triggers_effect_is_not_this_resolutions():
    """Aetherling's "{U}: Exile this creature. Return it … at the beginning of
    the next end step": only the exile happens as the ability resolves; the
    return is the delayed trigger's, which Arena logs by itself (CR 603.7)."""
    blink = abilities_of(trees_for(_card_of("Aetherling")))[0]
    first, *_rest, last = (c for c in blink.effects if c.concept == "change_zone")
    assert not effect_is_delayed(blink.root, first.node)
    assert effect_is_delayed(blink.root, last.node)
    assert compare_kinds({"move:Battlefield->Exile"}, [blink]).status == "agree"


def test_up_to_n_targets_may_be_none():
    """Age of Ultron's "destroy up to one target nonartifact creature": phase
    writes the choice as a target range starting at zero."""
    chapter = abilities_of(trees_for(_card_of("Age of Ultron")))[0]
    (destroy,) = (c for c in chapter.effects if c.concept == "destroy")
    assert effect_targets_optional(chapter.root, destroy.node)
    growth = abilities_of(trees_for(_card_of("Giant Growth")))[0]
    assert not effect_targets_optional(growth.root, growth.effects[0].node)


def test_an_amount_that_is_the_chosen_x():
    """The X a spell was cast with (CR 107.3a), in the two shapes phase leaves:
    an amount that refers to X, and a power or toughness of "X" / "-X"."""
    blaze = abilities_of(trees_for(_card_of("Blaze")))[0]
    assert chosen_x_sign(blaze.effects[0].node, "amount") == 1
    bridge = abilities_of(trees_for(_card_of("Battle at the Bridge")))[0]
    pump, life = bridge.effects
    assert chosen_x_sign(pump.node, "power") == -1
    assert chosen_x_sign(pump.node, "toughness") == -1
    assert chosen_x_sign(life.node, "amount") == 1
    growth = abilities_of(trees_for(_card_of("Giant Growth")))[0]
    assert chosen_x_sign(growth.effects[0].node, "power") is None


def test_an_unrelated_text_is_unsure():
    abilities = abilities_of(trees_for(_card_of("Elvish Visionary")))
    pairing = pair("Whenever you gain life, scry 1.", abilities)
    assert pairing.ability is None
    assert pairing.method == "unsure"


# -- regression diff -------------------------------------------------------
def test_diff_lists_rows_whose_verdict_changed(card_db, tmp_path):
    log = _write(tmp_path / "Player.log", _bolt_game())
    before = _run(card_db, log)
    after = json.loads(json.dumps(before))
    after["resolutions"][0]["checks"][0]["ok"] = False
    (change,) = diff_reports(before, after)
    assert change["card"] == "Lightning Bolt"
    assert change["before"]["failed"] == []
    assert change["after"]["failed"] == ["damage amount"]
    assert diff_reports(before, before) == []


# -- the CLI ---------------------------------------------------------------
def test_cli_reads_the_logs_and_writes_the_report(
    card_db, tmp_path, monkeypatch, capsys
):
    from mtg_utils import arena_crosscheck, card_pool

    class _Pool:
        by_name = {"Lightning Bolt": _card_of("Lightning Bolt")}

    monkeypatch.setattr(card_pool.CardPool, "load", staticmethod(lambda *_: _Pool()))
    log = _write(tmp_path / "Player.log", _bolt_game())
    out = tmp_path / "report.json"
    archive = tmp_path / "archive"
    archive.mkdir()
    code = arena_crosscheck.main(
        [
            str(log),
            "--card-db",
            str(card_db),
            "--no-live",
            "--archive",
            str(archive),
            "--json",
            str(out),
        ]
    )
    assert code == 0
    assert "# Arena crosscheck" in capsys.readouterr().out
    report = json.loads(out.read_text())
    assert report["summary"]["resolutions"] == {"agree": 1}
    assert (archive / "reports" / f"{report['phase_tag']}.json").is_file()


# -- what a corpus of other players' logs showed (2026-11-26) ----------------
#
# Fictional ids throughout; each card whose parse matters comes from testkit.
def _add_card(card_db: Path, grp: int, name: str, *, token: bool = False) -> None:
    con = sqlite3.connect(card_db)
    con.execute("INSERT INTO Localizations_enUS VALUES (?, 0, ?)", (grp, name))
    con.execute("INSERT INTO Cards VALUES (?, ?, 0, 0, ?)", (grp, grp, int(token)))
    con.commit()
    con.close()


def _add_ability(
    card_db: Path,
    aid: int,
    text: str,
    *,
    category: int = TRIGGERED,
    keyword: str | None = None,
    hidden_by: int | None = None,
) -> None:
    """An Arena ability: its text, the keyword it is an instance of (a
    ``BaseId`` naming an ability with that keyword's text), the ability that
    hides it (``HiddenByAbilityIds``)."""
    con = sqlite3.connect(card_db)
    con.execute("INSERT INTO Localizations_enUS VALUES (?, 1, ?)", (aid + 50000, text))
    base = 0
    if keyword is not None:
        base = aid + 60000
        con.execute(
            "INSERT INTO Localizations_enUS VALUES (?, 1, ?)", (base + 50000, keyword)
        )
        con.execute(
            "INSERT INTO Abilities VALUES (?, 3, ?, 0, NULL, 0)", (base, base + 50000)
        )
    con.execute(
        "INSERT INTO Abilities VALUES (?, ?, ?, ?, ?, 0)",
        (aid, category, aid + 50000, base, str(hidden_by) if hidden_by else None),
    )
    con.commit()
    con.close()


def _zones(*, stack=(), battlefield=()) -> list[dict]:
    """The zones with the objects in the stack and on the battlefield."""
    ids = {STACK: list(stack), BATTLEFIELD: list(battlefield)}
    return [{**z, "objectInstanceIds": ids.get(z["zoneId"], [])} for z in ZONES]


def _ability_obj(iid: int, grp: int, src: int, parent: int | None, **extra) -> dict:
    return _obj(
        iid,
        grp,
        kind="Ability",
        types=(),
        objectSourceGrpId=src,
        parentId=parent,
        **extra,
    )


def _fired(match: str, ability: dict, cause: int | None, *annotations: dict) -> dict:
    """A message in which ``ability`` goes on the stack, set off by ``cause``."""
    state = _state(
        match,
        [ability],
        [
            *annotations,
            _ann(80, "AbilityInstanceCreated", cause, [ability["instanceId"]]),
        ],
    )
    if cause is not None:
        state["persistentAnnotations"] = [
            _ann(81, "TriggeringObject", ability["instanceId"], [cause])
        ]
    return state


def _resolves(match: str, inst: int, grp: int, *effects: dict, objects=()) -> dict:
    return _state(
        match,
        list(objects),
        [
            _ann(1, "ResolutionStart", inst, [inst], grpid=grp),
            *effects,
            _ann(90, "ResolutionComplete", inst, [inst], grpid=grp),
        ],
    )


def test_a_created_token_entered_the_battlefield(tmp_path):
    """Arena logs a token's creation with no zone move. It entered the
    battlefield all the same (CR 111.2), which an enters trigger watches. A
    token put onto the battlefield attacking (mobilize's Warriors) was never
    declared an attacker: it never "attacked" for a trigger (CR 508.4), though
    its attack state says attacking; a creature declared an attacker did."""
    attacking = {"attackState": "AttackState_Attacking"}
    token = _obj(300, 9999, kind="Token", types=("Creature",), **attacking)
    game = [
        _state("t1", first=True),
        _fired(
            "t1",
            _ability_obj(301, 8888, 7777, 200),
            300,
            _ann(10, "TokenCreated", 250, [300]),
        ),
    ]
    game[1]["gameObjects"].append(token)
    _, (fired,), _, _ = read_logs([_write(tmp_path / "a.log", game)])
    assert fired.events == {"enters", "zone_change"}
    # a creature on the battlefield before combat, declared an attacker
    declared = [
        _state("t2", [_obj(310, 9999, types=("Creature",))], first=True),
        _fired("t2", _ability_obj(311, 8888, 7777, 200), 310),
    ]
    declared[1]["gameObjects"].append(_obj(310, 9999, types=("Creature",), **attacking))
    _, (fired,), _, _ = read_logs([_write(tmp_path / "b.log", declared)])
    assert fired.events == {"attacks"}


def test_a_spells_cast_is_remembered_while_it_is_on_the_stack(tmp_path):
    """A cast trigger can go on the stack many messages after the cast (each
    mana tap and target choice is a message): the spell's cast still counts
    while the spell is on the stack, and not once it has left."""
    spell = _obj(100, 9998)
    cast = _state(
        "t2",
        [spell],
        [
            _ann(
                5,
                "ZoneTransfer",
                None,
                [100],
                zone_src=HAND,
                zone_dest=STACK,
                category="CastSpell",
            )
        ],
    )
    cast["zones"] = _zones(stack=[100])
    taps = [
        _state(
            "t2", annotations=[_ann(6 + n, "TappedUntappedPermanent", 40 + n, [40 + n])]
        )
        for n in range(5)
    ]
    game = [
        _state("t2", first=True),
        cast,
        *taps,
        _fired("t2", _ability_obj(301, 8888, 7777, 200), 100),
    ]
    _, (fired,), _, _ = read_logs([_write(tmp_path / "a.log", game)])
    assert "cast_spell" in fired.events
    left = _state("t2", annotations=[])
    left["zones"] = _zones()  # the spell resolved: off the stack
    game = [*game[:-1], left, _fired("t2", _ability_obj(302, 8888, 7777, 200), 100)]
    _, (fired,), _, _ = read_logs([_write(tmp_path / "b.log", game)])
    assert "cast_spell" not in fired.events


def test_a_trigger_logged_before_its_event_reads_its_whole_message(tmp_path):
    """Arena can log a trigger ahead of the event that set it off in the same
    message (a card leaving a graveyard, logged after the trigger); with no
    object named, the whole message is the trigger's. A message without
    ``turnInfo`` is in the turn the last one named."""
    fired = _state(
        "t3",
        [_ability_obj(301, 8888, 7777, 200)],
        [
            _ann(5, "AbilityInstanceCreated", 200, [301]),
            _ann(7, "ZoneTransfer", 12, [400], zone_src=GRAVEYARD, zone_dest=EXILE),
        ],
    )
    del fired["turnInfo"]
    _, (trigger,), _, _ = read_logs(
        [_write(tmp_path / "Player.log", [_state("t3", first=True), fired])]
    )
    assert "zone_change" in trigger.events
    assert trigger.turn == 3


def test_a_long_text_scores_as_itself():
    """difflib's autojunk drops every character common in a text over 200
    characters: two identical long texts scored near 0."""
    from mtg_utils._arena_crosscheck.align import _similarity

    text = norm(_arena_text("Tinybones, Bauble Burglar"))
    assert len(text) > 200
    assert _similarity(text, text) == 1.0


@pytest.mark.parametrize(
    ("name", "line", "events"),
    [
        # "enters or dies" (CR 603.6a, 603.6c: two events of one object)
        ("Stitcher's Supplier", 0, {"enters", "dies"}),
        # two trigger conditions, an ability word in front (CR 207.2c)
        ("Optimistic Scavenger", 0, {"enters", "fullyunlock"}),
        # "When ~ enters and at the beginning of your upkeep"
        ("Gathering Stone", 2, {"enters", "phase"}),
    ],
)
def test_one_arena_ability_is_two_phase_triggers(name, line, events):
    abilities = abilities_of(trees_for(_card_of(name)))
    pairing = pair(_arena_text(name).splitlines()[line], abilities)
    assert pairing.method == "split"
    assert {a.trigger_event for a in pairing.abilities} == events


def test_an_ability_word_is_dropped():
    """An ability word has no rules meaning (CR 207.2c): Arena writes one in
    front of Brave Meadowguard's "Valiant — Whenever …", phase need not."""
    assert norm("Valiant — Whenever CARDNAME attacks") == "whenever ~ attacks"
    assert (
        norm("Mobilize — create Warrior tokens") == "mobilize — create warrior tokens"
    )


def test_a_modal_trigger_pairs_with_phases_condition():
    """Phase writes a modal trigger's description as its condition alone."""
    abilities = abilities_of(trees_for(_card_of("Gaius van Baelsar")))
    text = _arena_text("Gaius van Baelsar").split("•")[0]
    pairing = pair(text, abilities)
    assert (pairing.method, pairing.ability.trigger_event) == ("modal", "enters")


@pytest.mark.parametrize(
    ("name", "text", "keyword", "event"),
    [
        # CR 702.181a: "Whenever this creature attacks, create N … tokens"
        ("Voice of Victory", "Mobilize 2", "Mobilize", "attacks"),
        # CR 702.175a: "When this permanent enters, if its offspring cost was paid"
        ("Pawpatch Recruit", "Offspring {o2}", "Offspring", "enters"),
        # CR 719.3a: "To solve — [condition]" is an end-step trigger
        (
            "Case of the Gateway Express",
            "To solve — Three or more creatures attacked this turn.",
            None,
            "phase",
        ),
    ],
)
def test_a_keyword_pairs_with_phases_ability_for_it(name, text, keyword, event):
    abilities = abilities_of(trees_for(_card_of(name)))
    pairing = pair(text, abilities, keyword=keyword)
    assert (pairing.method, pairing.ability.trigger_event) == ("keyword", event)


def _checker(card_db: Path, keywords: frozenset[str] = frozenset()) -> Checker:
    return Checker(CardText(card_db), _card_of, trees_for, [], keywords)


def test_a_keyword_another_object_granted_is_labelled(card_db, tmp_path):
    """Empyrean Eagle has no decayed of its own: a decayed counter gave it. A
    keyword the card's own ability grants is the card's (Bloodbraid Marauder's
    "This spell has cascade as long as …")."""
    eagle, marauder = 3001, 3002
    _add_card(card_db, eagle, test_card("Empyrean Eagle")["name"])
    _add_card(card_db, marauder, test_card("Bloodbraid Marauder")["name"])
    _add_ability(card_db, 4001, "Decayed")
    _add_ability(card_db, 4002, "Cascade")
    game = [
        _state("k1", first=True),
        _resolves("k1", 301, 4001, objects=[_ability_obj(301, 4001, eagle, 300)]),
        _fired("k1", _ability_obj(311, 4002, marauder, 310), 310),
    ]
    log = _write(tmp_path / "Player.log", game)
    checker = _checker(card_db, frozenset({"decayed", "cascade"}))
    report = crosscheck([log], checker, "vtest")
    (res,) = report["resolutions"]
    assert (res["card"], res["status"], res["keyword"]) == (
        "Empyrean Eagle",
        "granted-keyword",
        "decayed",
    )
    (trig,) = report["triggers"]
    assert (trig["card"], trig["status"]) == ("Bloodbraid Marauder", "keyword-only")
    # no keyword vocabulary, no keyword: an unsure pairing, as before
    report = crosscheck([log], _checker(card_db), "vtest")
    assert report["resolutions"][0]["status"] == "unsure-pairing"


def test_rules_objects_and_emblems(card_db, tmp_path):
    """Speed's trigger "has no source" (CR 702.179d): Arena hangs it on a trigger
    holder it names "Start Your Engines!". Earthbend's return (CR 701.66a) is a
    holder's with no card at all. An emblem's ability is its source card's (CR
    114.1), though Arena's database files it under the ability that made it."""
    engines, vraska = 3011, 3012
    speed, ret, emblem_ab, ultimate = 4011, 4012, 4013, 4014
    _add_card(card_db, engines, "Start Your Engines!", token=True)
    _add_card(card_db, vraska, test_card("Vraska, Golgari Queen")["name"])
    _add_ability(
        card_db,
        speed,
        "Whenever one or more opponents lose life during your turn, if your speed "
        "is less than 4, increase your speed by 1. This ability triggers only once "
        "each turn.",
    )
    _add_ability(
        card_db, ret, "Return that land to the battlefield tapped under your control"
    )
    _add_ability(
        card_db,
        emblem_ab,
        "Whenever a creature you control deals combat damage to a player, that player loses the game.",
        hidden_by=ultimate,
    )
    holder = _obj(400, 5, kind="TriggerHolder", types=(), objectSourceGrpId=engines)
    emblem = _obj(420, 2, kind="Emblem", types=(), objectSourceGrpId=vraska)
    land = _obj(430, 55555, types=("Land",))
    attacker = _obj(440, 55556, types=("Creature",))
    game = [
        _state("r1", [holder, emblem, land, attacker], first=True),
        _fired(
            "r1",
            _ability_obj(401, speed, 5, 400),
            None,
            _ann(10, "ModifiedLife", 7, [2], life=-1),
        ),
        _resolves("r1", 401, speed, objects=[_ability_obj(401, speed, 5, 400)]),
        _resolves(
            "r1",
            411,
            ret,
            _ann(
                2, "ZoneTransfer", 411, [431], zone_src=GRAVEYARD, zone_dest=BATTLEFIELD
            ),
            objects=[_ability_obj(411, ret, 5, 430)],
        ),
        _fired(
            "r1",
            _ability_obj(421, emblem_ab, 2, 420),
            440,
            _ann(10, "DamageDealt", 440, [2], damage=2, type=1),
        ),
    ]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    speed_res, ret_res = report["resolutions"]
    assert (speed_res["card"], speed_res["status"]) == (
        "Start Your Engines!",
        "rules-object",
    )
    assert (ret_res["card"], ret_res["status"]) == (None, "agree")
    speed_trig, emblem_trig = report["triggers"]
    assert speed_trig["status"] == "rules-object"
    assert emblem_trig["card"] == "Vraska, Golgari Queen"
    assert emblem_trig["warnings"] == ["emblem"]
    assert (emblem_trig["phase_event"], emblem_trig["status"]) == (
        "deals_damage",
        "match",
    )


def _etb_game(match: str, card: int, etb: int, *effects: dict, others=()) -> list[dict]:
    """Card instance 500 on the battlefield (with ``others``), its ability 501 resolving."""
    first = _state(match, [_obj(500, card, types=("Creature",)), *others], first=True)
    first["zones"] = _zones(battlefield=[500, *(o["instanceId"] for o in others)])
    return [
        first,
        _resolves(
            match, 501, etb, *effects, objects=[_ability_obj(501, etb, card, 500)]
        ),
    ]


def test_a_player_or_planeswalker_target_may_be_the_player(card_db, tmp_path):
    """Sunscorched Desert's "target player or planeswalker": a damaged player is
    the target's player half, no wrong type."""
    desert, etb = 3021, 4021
    _add_card(card_db, desert, test_card("Sunscorched Desert")["name"])
    _add_ability(card_db, etb, _arena_text("Sunscorched Desert").splitlines()[0])
    game = _etb_game(
        "v1",
        desert,
        etb,
        _ann(2, "DamageDealt", 501, [2], damage=1, type=2),
        _ann(3, "ModifiedLife", 501, [2], life=-1),
    )
    _row, checks = _checks_of(card_db, tmp_path, game)
    assert checks["damage target type"]["ok"]


@pytest.mark.parametrize(
    ("name", "moves"),
    [
        # "… airbend all other creatures. … Exile Avatar's Wrath."
        ("Avatar's Wrath", [(BATTLEFIELD, EXILE, "Exile")]),
        # "Destroy all artifacts and creatures. End the turn." (CR 724.1b)
        ("Ultima", [(BATTLEFIELD, GRAVEYARD, "Destroy")]),
    ],
)
def test_the_spell_moving_itself_is_no_wrong_type(card_db, tmp_path, name, moves):
    """A spell's own "Exile ~", and ending the turn exiling every object on the
    stack the resolving spell among them, move the sorcery itself: its type is
    no creature's or artifact's."""
    spell = 3031
    _add_card(card_db, spell, test_card(name)["name"])
    theirs = _obj(300, VISIONARY, types=("Creature",), controller=2)
    game = _spell_game(
        spell,
        *(
            _ann(2 + n, "ZoneTransfer", 100, [300], zone_src=a, zone_dest=b, category=c)
            for n, (a, b, c) in enumerate(moves)
        ),
        _ann(10, "ObjectIdChanged", 100, [100], orig_id=100, new_id=110),
        _ann(
            11,
            "ZoneTransfer",
            100,
            [110],
            zone_src=STACK,
            zone_dest=EXILE,
            category="Exile",
        ),
        objects=[theirs, _obj(110, spell, types=("Sorcery",))],
    )
    game[0]["gameObjects"][0]["cardTypes"] = ["CardType_Sorcery"]
    row, checks = _checks_of(card_db, tmp_path, game)
    assert checks["moved object type"]["ok"]
    assert all(c["ok"] for c in row["checks"])
    assert "move:Stack->Exile" not in row["unexplained"]


def test_each_other_creature_named_x_may_be_none(card_db, tmp_path):
    """Baloth Packhunter's "two +1/+1 counters on each other creature you control
    named Baloth Packhunter": with no other one on the battlefield nothing gets
    a counter, and that is no missing effect; with another, it is."""
    baloth, etb = 3041, 4041
    _add_card(card_db, baloth, test_card("Baloth Packhunter")["name"])
    # Arena's text keeps the name the filter matches ("named Baloth Packhunter")
    _add_ability(
        card_db,
        etb,
        "When CARDNAME enters, put two +1/+1 counters on each other creature you "
        "control named Baloth Packhunter.",
    )
    report = _run(card_db, _write(tmp_path / "a.log", _etb_game("g1", baloth, etb)))
    assert report["resolutions"][0]["status"] == "conditional"
    other = _obj(502, baloth, types=("Creature",))
    report = _run(
        card_db,
        _write(tmp_path / "b.log", _etb_game("g2", baloth, etb, others=[other])),
    )
    assert report["resolutions"][0]["status"] == "phase-extra"
    counters = _ann(2, "CounterAdded", 501, [502], counter_type=1, transaction_amount=2)
    game = _etb_game("g3", baloth, etb, counters, others=[other])
    row, checks = _checks_of(card_db, tmp_path, game)
    assert row["status"] == "agree"
    assert checks["counter amount"]["ok"]


def test_poison_counters_are_a_players_counters(card_db, tmp_path):
    """Fynn's "that player gets two poison counters" (CR 122.1): a counter on a
    player, its kind and number checked."""
    fynn, trig = 3051, 4051
    _add_card(card_db, fynn, test_card("Fynn, the Fangbearer")["name"])
    _add_ability(card_db, trig, _arena_text("Fynn, the Fangbearer").splitlines()[1])
    con = sqlite3.connect(card_db)
    con.execute("INSERT INTO Localizations_enUS VALUES (9010, 1, 'Poison')")
    con.execute("INSERT INTO Enums VALUES ('CounterType', 4, 9010)")
    con.commit()
    con.close()
    game = _etb_game(
        "p1",
        fynn,
        trig,
        _ann(2, "CounterAdded", 501, [2], counter_type=4, transaction_amount=2),
    )
    row, checks = _checks_of(card_db, tmp_path, game)
    assert row["status"] == "agree"
    assert checks["counter type"]["observed"] == "poison"
    assert checks["counter amount"]["ok"]


def test_a_countered_ability_is_the_counters_effect(card_db, tmp_path):
    """Arena files a countered ability's deletion under the ability's source;
    it is the counter's effect when the ability is its target (CR 701.6a)."""
    stifle = 3061
    _add_card(card_db, stifle, test_card("Stifle")["name"])
    game = _spell_game(stifle, _ann(2, "AbilityInstanceDeleted", 355, [356]))
    game[0]["persistentAnnotations"] = [
        _ann(50, "TargetSpec", 100, [356], promptParameters=100)
    ]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["resolutions"]
    assert (row["arena"], row["status"]) == (["counter_spell"], "agree")
    del game[0]["persistentAnnotations"]  # not its target: another's doing
    report = _run(card_db, _write(tmp_path / "b.log", game))
    assert report["resolutions"][0]["status"] == "phase-extra"


@pytest.mark.parametrize(
    ("name", "index", "observed", "status"),
    [
        ("Tifa Lockhart", 0, {"continuous"}, "agree"),  # double power, CR 701.10a
        ("Mossborn Hydra", 0, {"counter_add", "continuous"}, "agree"),  # CR 701.10e
        ("Harmless Offering", 0, {"gain_control", "continuous"}, "agree"),
        ("Thespian's Stage", 1, {"continuous"}, "agree"),  # a copy, CR 707.2
        ("Innkeeper's Talent", 0, {"continuous"}, "agree"),  # Level 2: a static
        ("Innkeeper's Talent", 1, set(), "agree"),  # Level 3: a replacement
        ("Drix Interlacer", 1, {"designation"}, "agree"),  # intensify
        ("Brave Meadowguard", 0, {"move:Limbo->Hand"}, "agree"),  # conjure
        ("Brave Meadowguard", 0, {"token"}, "arena-extra"),  # a conjured card: no token
        ("Sandcloud Harbinger", 0, {"move:Limbo->Library"}, "agree"),
        ("Ultima", 0, {"destroy", "move:Stack->Exile"}, "agree"),  # CR 724.1b
        (
            "Tinybones, Bauble Burglar",
            1,
            {"move:Graveyard->Exile", "counter_add"},
            "agree",
        ),
        ("Tishana's Tidebinder", 0, {"counter_spell", "continuous"}, "agree"),
    ],
)
def test_effect_vocabulary(name, index, observed, status):
    abilities = [
        a for a in abilities_of(trees_for(_card_of(name))) if a.origin != "granted"
    ]
    assert compare_kinds(observed, [abilities[index]]).status == status


def test_a_split_needs_two_different_triggers():
    """Each half of a combined Arena ability must pair with its own phase
    trigger: both halves near one trigger is no split."""
    enters = [
        a
        for a in abilities_of(trees_for(_card_of("Stitcher's Supplier")))
        if a.trigger_event == "enters"
    ]
    text = _arena_text("Stitcher's Supplier").splitlines()[0]
    assert pair(text, enters).method != "split"


def test_a_player_isnt_a_creature_or_planeswalker_target(card_db, tmp_path):
    """Strangle deals 3 damage to target creature or planeswalker: a damaged
    player is no target it could have had."""
    strangle = 3071
    _add_card(card_db, strangle, test_card("Strangle")["name"])
    game = _spell_game(
        strangle,
        _ann(2, "DamageDealt", 100, [2], damage=3, type=2),
        _ann(3, "ModifiedLife", 100, [2], life=-3),
    )
    game[0]["gameObjects"][0]["cardTypes"] = ["CardType_Sorcery"]
    _row, checks = _checks_of(card_db, tmp_path, game)
    assert not checks["damage target type"]["ok"]


@pytest.mark.parametrize(("seat", "ok"), [(2, True), (1, False)])
def test_poison_goes_to_the_player_fynns_creature_hit(card_db, tmp_path, seat, ok):
    """Fynn's "that player" is the player a creature of yours dealt combat damage
    to: an attacking creature's, the player it attacks (CR 510.1b), an opponent
    (CR 506.2). Poison on its own controller is the wrong player."""
    fynn, trig = 3081, 4081
    _add_card(card_db, fynn, test_card("Fynn, the Fangbearer")["name"])
    _add_ability(card_db, trig, _arena_text("Fynn, the Fangbearer").splitlines()[1])
    counters = _ann(
        2, "CounterAdded", 501, [seat], counter_type=1, transaction_amount=2
    )
    _row, checks = _checks_of(card_db, tmp_path, _etb_game("p2", fynn, trig, counters))
    assert checks["counter player"]["ok"] is ok
    assert checks["counter player"]["expected"] == ["opponent"]


@pytest.mark.parametrize(
    ("name", "now", "ok"),
    [
        # "Target opponent gains control of target permanent you control."
        ("Harmless Offering", 2, True),
        ("Harmless Offering", 1, False),
        # "Gain control of target creature until end of turn."
        ("Act of Treason", 1, True),
        ("Act of Treason", 2, False),
    ],
)
def test_who_ends_up_controlling_it(card_db, tmp_path, name, now, ok):
    """Giving control away and gaining it are two directions: Arena logs the
    object under its new controller."""
    spell = 3091
    _add_card(card_db, spell, test_card(name)["name"])
    before = 1 if name == "Harmless Offering" else 2
    moved = _obj(300, VISIONARY, types=("Creature",), controller=before)
    game = _spell_game(spell, _ann(2, "ControllerChanged", 100, [300]), objects=[moved])
    game[1]["gameObjects"] = [_obj(300, VISIONARY, types=("Creature",), controller=now)]
    row, checks = _checks_of(card_db, tmp_path, game)
    assert checks["new controller"]["ok"] is ok
    assert ("give_control" if before == 1 else "gain_control") in row["phase"]


def test_a_case_solves_by_its_solve_effect(card_db, tmp_path):
    """A Case's "To solve" pairs with phase's trigger that solves it, and the
    solve shows as the designation Arena marks the Case with while the trigger
    resolves (CR 719.3b: solved is a designation)."""
    case, solve = 3101, 4101
    _add_card(card_db, case, test_card("Case of the Gateway Express")["name"])
    _add_ability(
        card_db, solve, "To solve — Three or more creatures attacked this turn."
    )

    def solved(*, marked: bool) -> list[dict]:
        game = _etb_game("c1", case, solve)
        game[0]["gameObjects"][0]["cardTypes"] = ["CardType_Enchantment"]
        if marked:
            game[1]["persistentAnnotations"] = [
                _ann(50, "Designation", 500, [500], DesignationType=15)
            ]
        return game

    report = _run(card_db, _write(tmp_path / "a.log", solved(marked=True)))
    (row,) = report["resolutions"]
    assert (row["pairing"], row["status"]) == ("keyword", "agree")
    assert row["arena"] == ["marked"]
    report = _run(card_db, _write(tmp_path / "b.log", solved(marked=False)))
    assert report["resolutions"][0]["status"] != "agree"


# -- the reverse check: a trigger phase expects that Arena never fired --------
#
# An object's own event (it entered, left, attacked, …) and the abilities Arena
# lists on it (``uniqueAbilities``): each trigger phase's parse gives its card for
# that event is expected as an ability instance from the object before the turn
# ends (``Checker.expected``).
def _turn(state: dict, turn: int) -> dict:
    state["turnInfo"] = {"turnNumber": turn}
    return state


def _listing(obj: dict, *abilities: int) -> dict:
    """``obj`` with the abilities Arena lists on it."""
    obj["uniqueAbilities"] = [
        {"id": 90 + n, "grpId": a} for n, a in enumerate(abilities)
    ]
    return obj


def _enters_game(
    match: str,
    *,
    fired: bool = True,
    turn_ends: bool = True,
    abilities: tuple[int, ...] = (VISIONARY_ETB,),
    instance: int = VISIONARY_ETB,
    **extra,
) -> list[dict]:
    """Elvish Visionary (200) resolving onto the battlefield, its enters ability
    (201) going on the stack when ``fired``, and the next turn starting when
    ``turn_ends``."""
    card = _listing(_obj(200, VISIONARY, types=("Creature",), **extra), *abilities)
    move = _ann(
        10,
        "ZoneTransfer",
        None,
        [200],
        zone_src=STACK,
        zone_dest=BATTLEFIELD,
        category="Resolve",
    )
    enters = _state(match, [card], [move])
    if fired:
        enters["gameObjects"].append(_ability_obj(201, instance, VISIONARY, 200))
        enters["annotations"].append(_ann(11, "AbilityInstanceCreated", 200, [201]))
    game = [_state(match, first=True), enters]
    if turn_ends:
        game.append(_turn(_state(match), 4))
    return game


def test_an_own_trigger_that_went_on_the_stack_fired(card_db, tmp_path):
    report = _run(card_db, _write(tmp_path / "Player.log", _enters_game("u1")))
    (row,) = report["expected"]
    assert (row["card"], row["event"], row["phase_event"]) == (
        "Elvish Visionary",
        "enters",
        "enters",
    )
    assert row["zones"] == ["Stack", "Battlefield"]
    assert row["status"] == "fired"
    assert report["summary"]["expected"] == {"fired": 1}


def test_an_own_trigger_arena_never_fired_is_a_finding(card_db, tmp_path):
    """Nothing gates "When ~ enters, draw a card": Arena lists the ability on
    the permanent but put no instance of it on the stack before the turn
    ended. An instance in the next turn is another event's."""
    game = _enters_game("u2", fired=False)
    late = game[-1]
    late["gameObjects"] = [_ability_obj(201, VISIONARY_ETB, VISIONARY, 200)]
    late["annotations"] = [_ann(11, "AbilityInstanceCreated", 200, [201])]
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    (row,) = report["expected"]
    assert row["status"] == "unfired"
    assert row["arena_category"] == "triggered"
    assert row["arena_text"] == _arena_text("Elvish Visionary")
    assert row["fired"] == []
    assert "never fired" in render_markdown(report)


@pytest.mark.parametrize(
    ("status", "game"),
    [
        # the game (or the log) ended before the turn did
        ("game-over", {"fired": False, "turn_ends": False}),
        # an instance from the object phase's text can't name: it could be this
        ("unfired-unsure", {"instance": ABBOT_PROWESS}),
        # Arena lists no abilities on it: it lost them
        ("no-abilities", {"fired": False, "abilities": ()}),
        # what Arena lists on it pairs with no phase trigger
        ("unfired-unpaired", {"fired": False, "abilities": (ABBOT_PROWESS,)}),
        # face down: no abilities (CR 708.2), no enters triggers (CR 708.3)
        ("face-down", {"fired": False, "isFacedown": True}),
        # a copy effect may make exceptions (CR 707.9)
        ("copy", {"fired": False, "isCopy": True}),
    ],
)
def test_a_missing_instance_that_is_no_evidence(card_db, tmp_path, status, game):
    report = _run(card_db, _write(tmp_path / "Player.log", _enters_game("u3", **game)))
    (row,) = report["expected"]
    assert row["status"] == status


def test_a_token_of_a_cards_printing_is_a_copy(card_db, tmp_path):
    game = _enters_game("u4", fired=False)
    game[1]["gameObjects"][0]["type"] = "GameObjectType_Token"
    report = _run(card_db, _write(tmp_path / "Player.log", game))
    assert report["expected"][0]["status"] == "copy"


def test_an_arena_mistake_on_the_ignore_list(card_db, tmp_path):
    log = _write(tmp_path / "Player.log", _enters_game("u5", fired=False))
    ignores = [{"card": "Elvish Visionary", "ability": "When", "reason": "Arena"}]
    (row,) = _run(card_db, log, ignores=ignores)["expected"]
    assert (row["status"], row["ignored"]) == ("ignored", "Arena")


def _attack_game(match: str, card: int, ability: int, *, locked: bool = True):
    """Card 300 declared an attacker, then (``locked``) attacking or (not)
    unselected, and the next turn starting; nothing goes on the stack."""
    declared = {"attackState": "AttackState_Declared"}
    after = {"attackState": "AttackState_Attacking"} if locked else {}
    return [
        _state(match, [_obj(300, card, types=("Creature",))], first=True),
        _state(
            match, [_listing(_obj(300, card, types=("Creature",), **declared), ability)]
        ),
        _state(
            match, [_listing(_obj(300, card, types=("Creature",), **after), ability)]
        ),
        _turn(_state(match), 4),
    ]


@pytest.mark.parametrize(
    ("name", "line", "status"),
    [
        # "Whenever ~ attacks, put a +1/+1 counter on it."
        ("Alesha, Who Laughs at Fate", 1, "unfired"),
        # an intervening "if" (CR 603.4): "if its power is 6 or greater"
        ("Angelic Sell-Sword", 2, "unfired-conditional"),
        # "exile up to one target card from a graveyard": with no legal target
        # Arena puts no instance on the stack (CR 603.3d)
        ("Afterthought Sentry", 1, "unfired-targeted"),
    ],
)
def test_an_attack_trigger_arena_never_fired(card_db, tmp_path, name, line, status):
    card, ability = 3201, 4201
    _add_card(card_db, card, test_card(name)["name"])
    _add_ability(card_db, ability, _arena_text(name).splitlines()[line])
    game = _attack_game("a1", card, ability)
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["event"], row["phase_event"], row["status"]) == (
        "attacks",
        "attacks",
        status,
    )
    if status == "unfired-conditional":
        assert row["gates"] == ["condition"]
    # unselected before the attack was locked in: it never attacked
    game = _attack_game("a2", card, ability, locked=False)
    assert _run(card_db, _write(tmp_path / "b.log", game))["expected"] == []


def test_a_keyword_trigger_whose_rule_targets(card_db, tmp_path):
    """Backup's rule targets (CR 702.165a: "put N +1/+1 counters on target
    creature") though Arena's text for it is the keyword alone."""
    kavu, backup = 3211, 4211
    _add_card(card_db, kavu, test_card("Chomping Kavu")["name"])
    _add_ability(card_db, backup, "Backup 1", keyword="Backup")
    game = _enters_game("b1", fired=False)
    game[1]["gameObjects"] = [_listing(_obj(200, kavu, types=("Creature",)), backup)]
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert row["status"] == "unfired-targeted"


def test_a_dies_trigger_reads_the_permanent_it_was(card_db, tmp_path):
    """Arena logs a dies trigger's instance from the permanent's battlefield id,
    ahead of the move that gives it a new id in the graveyard; the abilities it
    had are the battlefield object's (CR 603.10a: it looks back in time)."""
    traveler, dies = 3221, 4221
    _add_card(card_db, traveler, test_card("Doomed Traveler")["name"])
    _add_ability(card_db, dies, _arena_text("Doomed Traveler"))

    def game(*, fired: bool) -> list[dict]:
        on = _listing(_obj(300, traveler, types=("Creature",)), dies)
        moved = [
            _ann(20, "ObjectIdChanged", None, [300], orig_id=300, new_id=310),
            _ann(
                21,
                "ZoneTransfer",
                None,
                [310],
                zone_src=BATTLEFIELD,
                zone_dest=GRAVEYARD,
                category="SBA_Damage",
            ),
        ]
        death = _state("d1", [_obj(310, traveler, types=("Creature",))], moved)
        if fired:
            death["gameObjects"].append(_ability_obj(301, dies, traveler, 300))
            death["annotations"].insert(
                0, _ann(19, "AbilityInstanceCreated", 300, [301])
            )
        return [_state("d1", [on], first=True), death, _turn(_state("d1"), 4)]

    (row,) = _run(card_db, _write(tmp_path / "a.log", game(fired=True)))["expected"]
    assert (row["event"], row["phase_event"], row["status"]) == (
        "leaves",
        "dies",
        "fired",
    )
    (row,) = _run(card_db, _write(tmp_path / "b.log", game(fired=False)))["expected"]
    assert (row["status"], row["arena_text"]) == (
        "unfired",
        _arena_text("Doomed Traveler"),
    )


def _event(event: str, origin: str | None = None, dest: str | None = None):
    return ObjectEvent(
        game=("m", 1),
        turn=1,
        event=event,
        origin=origin,
        destination=dest,
        grpid=None,
        controller=1,
        kind="Card",
        abilities=(),
        copy=False,
        face_down=False,
        fired=(),
        turn_ended=True,
    )


@pytest.mark.parametrize(
    ("name", "event", "expected"),
    [
        ("Doomed Traveler", _event("leaves", "Battlefield", "Graveyard"), True),
        # dies is a move to a graveyard (CR 700.4), not to exile
        ("Doomed Traveler", _event("leaves", "Battlefield", "Exile"), False),
        # "When ~ is put into a graveyard from anywhere": the move's destination
        ("Emrakul, the Aeons Torn", _event("leaves", "Battlefield", "Graveyard"), True),
        ("Emrakul, the Aeons Torn", _event("leaves", "Battlefield", "Exile"), False),
        # "When you cast this spell"
        ("Emrakul, the Aeons Torn", _event("cast_spell", "Hand", "Stack"), True),
        # a watcher of other objects ("Whenever a creature you control enters")
        ("Impact Tremors", _event("enters", "Stack", "Battlefield"), False),
        # one shared with other objects ("~ or another creature")
        ("Blood Artist", _event("leaves", "Battlefield", "Graveyard"), False),
    ],
)
def test_which_triggers_watch_the_objects_own_event(name, event, expected):
    triggers = [a for a in abilities_of(trees_for(_card_of(name))) if a.unit]
    assert any(watches_own_event(a, event) for a in triggers) is expected


def test_what_gates_a_trigger():
    """A "may" is decided as the ability resolves: it goes on the stack all the
    same (CR 603.5). An intervening "if" (CR 603.4) and a limit gate it."""

    def gates(name: str, event: str) -> tuple[str, ...]:
        (trig,) = (
            a
            for a in abilities_of(trees_for(_card_of(name)))
            if a.origin == "trigger" and a.trigger_event == event
        )
        return trigger_gates(trig.unit.node)

    assert gates("Port Inspector", "becomes_blocked") == ()
    assert gates("Angelic Sell-Sword", "attacks") == ("condition",)
    assert gates("Aurelia, the Warleader", "attacks") == ("constraint",)


def test_enters_or_transforms_is_two_phase_triggers():
    """Brutal Cathar's "When this creature enters or transforms into ~": the
    second event is more than one word."""
    name = "Brutal Cathar // Moonrage Brute"
    abilities = abilities_of(trees_for(_card_of(name)))
    text = test_card(name)["card_faces"][0]["oracle_text"].splitlines()[0]
    pairing = pair(text.replace("Brutal Cathar", "CARDNAME"), abilities)
    assert pairing.method == "split"
    assert {a.trigger_event for a in pairing.abilities} == {"enters", "transformed"}


def test_diff_lists_an_expected_trigger_whose_verdict_changed(card_db, tmp_path):
    before = _run(card_db, _write(tmp_path / "a.log", _enters_game("r1")))
    after = json.loads(json.dumps(before))
    after["expected"][0]["status"] = "unfired"
    (change,) = diff_reports(before, after)
    assert change["section"] == "expected"
    assert (change["before"]["status"], change["after"]["status"]) == (
        "fired",
        "unfired",
    )
    # a report saved before the reverse check has no such rows to compare
    del before["expected"]
    assert diff_reports(before, after) == []


def test_an_expected_rows_key_survives_a_parse_that_drops_another():
    """A parse that drops one event's trigger moves no other row's key, so the
    diff shows the one verdict that changed, not every later row shifted."""

    def row(index: int, text: str, status: str) -> dict:
        return {
            "game": ["m", 1],
            "event_index": index,
            "phase_text": text,
            "status": status,
        }

    def report(*rows: dict) -> dict:
        return build_report([], [], [("m", 1)], "vtest", expected=rows)

    before = report(row(0, "a", "fired"), row(1, "b", "fired"), row(2, "c", "unfired"))
    # the new parse no longer has trigger a, and c now fires
    after = report(row(1, "b", "fired"), row(2, "c", "fired"))
    (change,) = diff_reports(before, after)
    assert change["phase_text"] == "c"
    assert (change["before"]["status"], change["after"]["status"]) == (
        "unfired",
        "fired",
    )
    # dropping a row alone changes no verdict
    assert (
        diff_reports(before, report(row(1, "b", "fired"), row(2, "c", "unfired"))) == []
    )


def test_a_resync_repeating_an_event_opens_it_once(card_db, tmp_path):
    """A full resync (``GameStateType_Full``) repeats earlier annotations,
    the same ids again: the move is one event, answered by the instance logged
    with it the first time."""
    game = _enters_game("s1")
    repeat = _state("s1", game[1]["gameObjects"][:1], game[1]["annotations"][:1])
    repeat["type"] = "GameStateType_Full"
    game.insert(2, repeat)
    report = _run(card_db, _write(tmp_path / "a.log", game))
    assert [r["status"] for r in report["expected"]] == ["fired"]


EMRAKUL, EMRAKUL_CAST = 3501, 4501


def _cast_game(card_db: Path, match: str, *, fired: bool, undone: bool) -> list[dict]:
    """Emrakul, the Aeons Torn cast from hand (its "When you cast this spell"
    listed); when ``undone``, the next message reuses the cast's annotation id
    for Lightning Bolt's cast: Arena rolled the first back."""
    _add_card(card_db, EMRAKUL, test_card("Emrakul, the Aeons Torn")["name"])
    _add_ability(
        card_db, EMRAKUL_CAST, _arena_text("Emrakul, the Aeons Torn").split("\n")[1]
    )
    spell = _listing(_obj(301, EMRAKUL, types=("Creature",)), EMRAKUL_CAST)
    cast = _ann(
        10,
        "ZoneTransfer",
        None,
        [301],
        zone_src=HAND,
        zone_dest=STACK,
        category="CastSpell",
    )
    casting = _state(match, [spell], [cast])
    if fired:
        casting["gameObjects"].append(_ability_obj(302, EMRAKUL_CAST, EMRAKUL, 301))
        casting["annotations"].append(_ann(11, "AbilityInstanceCreated", 301, [302]))
    game = [
        _state(match, [_obj(300, EMRAKUL, types=("Creature",))], first=True),
        casting,
    ]
    if undone:
        bolt = _ann(
            10,
            "ZoneTransfer",
            None,
            [303],
            zone_src=HAND,
            zone_dest=STACK,
            category="CastSpell",
        )
        game.append(_state(match, [_obj(303, BOLT)], [bolt]))
    return [*game, _turn(_state(match), 4)]


@pytest.mark.parametrize(
    ("fired", "undone", "status"),
    [(True, False, "fired"), (False, False, "unfired"), (False, True, "rolled-back")],
)
def test_a_cast_trigger_and_a_cancelled_cast(card_db, tmp_path, fired, undone, status):
    game = _cast_game(card_db, "c1", fired=fired, undone=undone)
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["card"], row["event"], row["phase_event"]) == (
        "Emrakul, the Aeons Torn",
        "cast_spell",
        "cast_spell",
    )
    assert row["status"] == status


RIFTWATCHER, RIFT_ENTERS_OR_LEAVES = 3511, 4511


def test_one_instance_answers_one_event(card_db, tmp_path):
    """Aven Riftwatcher's "When this creature enters or leaves the
    battlefield" is one Arena ability and two phase triggers. It enters and
    leaves in one turn. An instance logged after the leave answers the leave,
    never the enter as well, and leaves the enter unsure: it could have been
    the enter's (Checker.expected)."""
    _add_card(card_db, RIFTWATCHER, test_card("Aven Riftwatcher")["name"])
    text = "When CARDNAME enters or leaves the battlefield, you gain 2 life."
    _add_ability(card_db, RIFT_ENTERS_OR_LEAVES, text)

    def game(*instances: str) -> list[dict]:
        on = _listing(
            _obj(300, RIFTWATCHER, types=("Creature",)), RIFT_ENTERS_OR_LEAVES
        )
        enters = _state(
            "o1",
            [on],
            [
                _ann(
                    10,
                    "ZoneTransfer",
                    None,
                    [300],
                    zone_src=STACK,
                    zone_dest=BATTLEFIELD,
                    category="Resolve",
                )
            ],
        )
        leaves = _state(
            "o1",
            [_obj(310, RIFTWATCHER, types=("Creature",))],
            [
                _ann(20, "ObjectIdChanged", None, [300], orig_id=300, new_id=310),
                _ann(
                    21,
                    "ZoneTransfer",
                    None,
                    [310],
                    zone_src=BATTLEFIELD,
                    zone_dest=GRAVEYARD,
                    category="SBA_Damage",
                ),
            ],
        )
        logged = {
            "enters": (enters, 301, 11),
            "leaves": (leaves, 302, 22),
            # a second leave instance: the trigger doubled
            "leaves again": (leaves, 303, 23),
        }
        for state, iid, aid in (logged[e] for e in instances):
            state["gameObjects"].append(
                _ability_obj(iid, RIFT_ENTERS_OR_LEAVES, RIFTWATCHER, 300)
            )
            state["annotations"].append(_ann(aid, "AbilityInstanceCreated", 300, [iid]))
        return [_state("o1", first=True), enters, leaves, _turn(_state("o1"), 4)]

    def statuses(log: str, *instances: str) -> dict[str, str]:
        rows = _run(card_db, _write(tmp_path / log, game(*instances)))["expected"]
        return {r["event"]: r["status"] for r in rows}

    # one instance after both: the leave's by order, the enter's a guess
    one = statuses("a.log", "leaves")
    assert one == {"enters": "unfired-unsure", "leaves": "fired"}
    assert statuses("b.log", "enters", "leaves") == {
        "enters": "fired",
        "leaves": "fired",
    }
    # two instances after the leave: a doubled leave trigger, or Arena firing
    # both late (a second Bilbo, Retired Burglar put into the graveyard by
    # the legend rule before its enter trigger is on the stack); neither row
    # reads as a finding, and the enter is never credited a second time
    two = statuses("c.log", "leaves", "leaves again")
    assert two == {"enters": "unfired-unsure", "leaves": "fired"}


KORVOLD, KORVOLD_TRIGGER = 3521, 4521


@pytest.mark.parametrize("instances", [1, 2])
def test_an_attack_instance_is_no_enter_instance(card_db, tmp_path, instances):
    """Korvold's "Whenever ~ enters or attacks": entering then attacking in
    one turn (haste), with only the attack's instance logged, or two of them
    (a doubled attack trigger: Isshin, Two Heavens as One)."""
    _add_card(card_db, KORVOLD, test_card("Korvold, Fae-Cursed King")["name"])
    _add_ability(
        card_db,
        KORVOLD_TRIGGER,
        "Whenever CARDNAME enters or attacks, sacrifice another permanent.",
    )

    def korvold(**extra) -> dict:
        return _listing(
            _obj(300, KORVOLD, types=("Creature",), **extra), KORVOLD_TRIGGER
        )

    move = _ann(
        10,
        "ZoneTransfer",
        None,
        [300],
        zone_src=STACK,
        zone_dest=BATTLEFIELD,
        category="Resolve",
    )
    attacking = _state("k1", [korvold(attackState="AttackState_Attacking")])
    for n in range(instances):
        attacking["gameObjects"].append(
            _ability_obj(301 + n, KORVOLD_TRIGGER, KORVOLD, 300)
        )
        attacking["annotations"].append(
            _ann(30 + n, "AbilityInstanceCreated", 300, [301 + n])
        )
    game = [
        _state("k1", first=True),
        _state("k1", [korvold()], [move]),
        _state("k1", [korvold(attackState="AttackState_Declared")]),
        attacking,
        _turn(_state("k1"), 4),
    ]
    rows = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    # the attack instances could be the enter's: unsure, never fired
    assert {r["event"]: r["status"] for r in rows} == {
        "enters": "unfired-unsure",
        "attacks": "fired",
    }


def test_an_instance_another_object_set_off_answers_nothing(card_db, tmp_path):
    """Arena's ``TriggeringObject`` names what set an instance off: one an
    object of the card's but set off by another is no instance of its own
    event."""
    game = _enters_game("t1")
    game[1]["persistentAnnotations"] = [_ann(50, "TriggeringObject", 201, [999])]
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert row["status"] == "unfired"
    game[1]["persistentAnnotations"] = [_ann(50, "TriggeringObject", 201, [200])]
    (row,) = _run(card_db, _write(tmp_path / "b.log", game))["expected"]
    assert row["status"] == "fired"


def test_a_reflexive_instance_is_not_the_trigger(card_db, tmp_path):
    """An instance of an ability Arena files under another (a "When you do",
    ``HiddenByAbilityIds``) is not the trigger phase expects, whatever its
    text."""
    reflexive = 4531
    _add_ability(
        card_db, reflexive, _arena_text("Elvish Visionary"), hidden_by=VISIONARY_ETB
    )
    game = _enters_game("h1", instance=reflexive)
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert row["status"] == "unfired"


HUSHBRINGER = 3541


@pytest.mark.parametrize("controller", [1, 2])
def test_a_trigger_another_permanent_silences(card_db, tmp_path, controller):
    """Hushbringer: "Creatures entering the battlefield or dying don't cause
    abilities to trigger", whoever controls it."""
    _add_card(card_db, HUSHBRINGER, test_card("Hushbringer")["name"])
    game = _enters_game("q1", fired=False)
    game[1]["gameObjects"].append(
        _obj(500, HUSHBRINGER, types=("Creature",), controller=controller)
    )
    game[1]["zones"] = _zones(battlefield=[200, 500])
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["status"], row["suppressed_by"]) == ("suppressed", "Hushbringer")


def test_what_a_trigger_suppressor_silences():
    def read(name: str) -> tuple:
        return tuple(
            s for t in trees_for(_card_of(name)) for s in trigger_suppressions(t)
        )

    (hush,) = read("Hushbringer")
    assert (hush.events, hush.source_types, hush.trigger_side) == (
        ("EntersBattlefield", "Dies"),
        ("Creature",),
        None,
    )
    (orb,) = read("Torpor Orb")
    assert orb.events == ("EntersBattlefield",)
    assert read("Elvish Visionary") == ()


def test_only_the_faces_own_triggers_are_expected(card_db, tmp_path):
    """Brinebound Gift, Brine Comber's back face, entering: its own enter
    trigger, not the front face's (CR 712.8: each face has its own
    characteristics)."""
    gift = 3551
    _add_card(card_db, gift, "Brinebound Gift")
    whole = "Brine Comber // Brinebound Gift"
    checker = Checker(
        CardText(card_db),
        lambda name: _card_of(whole if name == "Brinebound Gift" else name),
        trees_for,
        [],
    )
    game = _enters_game("f1", fired=False)
    game[1]["gameObjects"][0]["grpId"] = gift
    rows = crosscheck([_write(tmp_path / "a.log", game)], checker, "vtest")["expected"]
    assert [r["phase_text"] for r in rows] == [
        a.desc
        for a in abilities_of(trees_for(_card_of(whole)))
        if a.face == "Brinebound Gift" and a.trigger_event == "enters"
    ]


def test_a_split_pairs_halves_of_one_face():
    """Brinebound Gift's "Whenever this Aura enters or enchanted creature
    becomes the target of an Aura spell" is never half Brine Comber's enter
    trigger."""
    name = "Brine Comber // Brinebound Gift"
    abilities = abilities_of(trees_for(_card_of(name)))
    aura = test_card(name)["card_faces"][1]["oracle_text"].splitlines()[1]
    pairing = pair(aura, abilities)
    assert {a.face for a in pairing.abilities} <= {"Brinebound Gift"}


def test_blocks_and_becomes_blocked_once_per_attacker(card_db, tmp_path):
    """Two creatures blocking Port Inspector: one "becomes blocked" (CR
    509.1h), and Cinder Wall's "When ~ blocks" for its own block."""
    wall, inspector, wall_t, inspector_t = 3561, 3562, 4561, 4562
    _add_card(card_db, wall, test_card("Cinder Wall")["name"])
    _add_card(card_db, inspector, test_card("Port Inspector")["name"])
    _add_ability(card_db, wall_t, _arena_text("Cinder Wall").splitlines()[1])
    _add_ability(card_db, inspector_t, _arena_text("Port Inspector"))

    def board(state: str) -> list[dict]:
        info = {"blockState": state, "blockInfo": {"attackerIds": [300]}}
        return [
            _listing(
                _obj(
                    300,
                    inspector,
                    types=("Creature",),
                    attackState="AttackState_Attacking",
                ),
                inspector_t,
            ),
            _listing(
                _obj(400, wall, types=("Creature",), controller=2, **info), wall_t
            ),
            _obj(401, 55555, types=("Creature",), controller=2, **info),
        ]

    game = [
        _state("b2", first=True),
        _state("b2", board("BlockState_Declared")),
        _state("b2", board("BlockState_Blocking")),
        _turn(_state("b2"), 4),
    ]
    rows = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert sorted((r["card"], r["event"], r["status"]) for r in rows) == [
        ("Cinder Wall", "blocks", "unfired"),
        ("Port Inspector", "becomes_blocked", "unfired"),
    ]


def test_a_rebalanced_card_is_no_finding(card_db, tmp_path):
    """A rebalanced (A-) card is scored against the paper card's parse."""
    con = sqlite3.connect(card_db)
    con.execute("INSERT INTO Localizations_enUS VALUES (3571, 0, 'A-Elvish Visionary')")
    con.execute("INSERT INTO Cards VALUES (3571, 3571, 1, 1, 0)")
    con.commit()
    con.close()
    game = _enters_game("a9", fired=False)
    game[1]["gameObjects"][0]["grpId"] = 3571
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert row["status"] == "rebalanced"


def test_an_ability_arena_files_as_no_trigger_is_no_finding(card_db, tmp_path):
    """Arena filing the ability it lists as a static (evoke's, offspring's) is
    no evidence its trigger was missed."""
    static = 4581
    _add_ability(card_db, static, _arena_text("Elvish Visionary"), category=3)
    game = _enters_game("n1", fired=False, abilities=(static,))
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["status"], row["arena_category"]) == ("arena-not-triggered", "static")


def test_a_bare_keyword_whose_rule_targets(card_db, tmp_path):
    """Mentor with no BaseId in Arena's database, its text the bare keyword:
    its rule targets (CR 702.134a: "target attacking creature")."""
    warboss, mentor = 3591, 4591
    _add_card(card_db, warboss, test_card("Legion Warboss")["name"])
    _add_ability(card_db, mentor, "Mentor")
    (row,) = _run(
        card_db, _write(tmp_path / "a.log", _attack_game("w1", warboss, mentor))
    )["expected"]
    assert (row["phase_event"], row["status"]) == ("attacks", "unfired-targeted")


def test_a_creature_dying_with_hushbringer_is_silenced(card_db, tmp_path):
    """A creature dying at the same time as Hushbringer won't cause abilities
    to trigger (Hushbringer's ruling, 2019-10-04): the leave looks back at the
    battlefield as it was (CR 603.10a)."""
    traveler, dies = 3601, 4601
    _add_card(card_db, HUSHBRINGER, test_card("Hushbringer")["name"])
    _add_card(card_db, traveler, test_card("Doomed Traveler")["name"])
    _add_ability(card_db, dies, _arena_text("Doomed Traveler"))
    on = [
        _listing(_obj(300, traveler, types=("Creature",)), dies),
        _obj(500, HUSHBRINGER, types=("Creature",)),
    ]
    gone = [
        _obj(310, traveler, types=("Creature",)),
        _obj(510, HUSHBRINGER, types=("Creature",)),
    ]
    wipe = _state(
        "w2",
        gone,
        [
            _ann(20, "ObjectIdChanged", None, [300], orig_id=300, new_id=310),
            _ann(21, "ObjectIdChanged", None, [500], orig_id=500, new_id=510),
            _ann(
                22,
                "ZoneTransfer",
                None,
                [310, 510],
                zone_src=BATTLEFIELD,
                zone_dest=GRAVEYARD,
                category="Destroy",
            ),
        ],
    )
    wipe["zones"] = _zones()
    first = _state("w2", on, first=True)
    first["zones"] = _zones(battlefield=[300, 500])
    game = [first, wipe, _turn(_state("w2"), 4)]
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["card"], row["status"]) == ("Doomed Traveler", "suppressed")


def _leaves_under_hushbringer(
    card_db: Path, tmp_path: Path, name: str, line: int, category: str, types
) -> dict:
    """``name`` (300, with ``types``) leaving the battlefield for a graveyard
    (``category``) beside Hushbringer, its ``line`` listed, nothing fired."""
    card, ability = 3611, 4611
    _add_card(card_db, HUSHBRINGER, test_card("Hushbringer")["name"])
    _add_card(card_db, card, test_card(name)["name"])
    _add_ability(card_db, ability, _arena_text(name).splitlines()[line])
    first = _state(
        "l1",
        [
            _listing(_obj(300, card, types=types), ability),
            _obj(500, HUSHBRINGER, types=("Creature",)),
        ],
        first=True,
    )
    first["zones"] = _zones(battlefield=[300, 500])
    leave = _state(
        "l1",
        [_obj(310, card, types=types)],
        [
            _ann(20, "ObjectIdChanged", None, [300], orig_id=300, new_id=310),
            _ann(
                21,
                "ZoneTransfer",
                None,
                [310],
                zone_src=BATTLEFIELD,
                zone_dest=GRAVEYARD,
                category=category,
            ),
        ],
    )
    leave["zones"] = _zones(battlefield=[500])
    game = [first, leave, _turn(_state("l1"), 4)]
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    return row


@pytest.mark.parametrize(
    ("name", "line", "category", "types", "status"),
    [
        # "When this creature dies": silenced
        ("Doomed Traveler", 0, "SBA_Damage", ("Creature",), "suppressed"),
        # Hushbringer's rulings: a dying creature's own "put into a graveyard
        # from anywhere" may still trigger ...
        ("Emrakul, the Aeons Torn", 3, "Destroy", ("Creature",), "unfired"),
        # ... and so does "whenever you sacrifice" (an Aura made a creature)
        ("Ordeal of Nylea", 2, "Sacrifice", ("Enchantment", "Creature"), "unfired"),
    ],
)
def test_what_hushbringer_silences_on_a_death(
    card_db, tmp_path, name, line, category, types, status
):
    row = _leaves_under_hushbringer(card_db, tmp_path, name, line, category, types)
    assert row["status"] == status


def _enters_beside(
    card_db: Path, tmp_path: Path, name: str, controller: int, suppression=None
) -> dict:
    """Elvish Visionary entering (seat 1) beside ``name``, controlled by
    ``controller``; nothing fired. ``suppression`` stands in for the card's
    read when given."""
    grp = 3621
    _add_card(card_db, grp, test_card(name)["name"])
    checker = Checker(CardText(card_db), _card_of, trees_for, [])
    if suppression is not None:
        checker._suppression[name] = (suppression,)
    game = _enters_game("e5", fired=False)
    game[1]["gameObjects"].append(
        _obj(500, grp, types=("Creature",), controller=controller)
    )
    game[1]["zones"] = _zones(battlefield=[200, 500])
    (row,) = crosscheck([_write(tmp_path / "a.log", game)], checker, "vtest")[
        "expected"
    ]
    return row


@pytest.mark.parametrize(("controller", "status"), [(2, "suppressed"), (1, "unfired")])
def test_a_suppressor_of_opponents_triggers(card_db, tmp_path, controller, status):
    """Elesh Norn, Mother of Machines: "Permanents entering don't cause
    abilities of permanents your opponents control to trigger"."""
    row = _enters_beside(
        card_db, tmp_path, "Elesh Norn, Mother of Machines", controller
    )
    assert row["status"] == status


@pytest.mark.parametrize(("controller", "status"), [(1, "suppressed"), (2, "unfired")])
def test_a_suppressor_of_its_controllers_triggers(
    card_db, tmp_path, controller, status
):
    """A static silencing only its controller's permanents' triggers: no
    snapshot card has that shape, so the read is set by hand here."""
    mine = TriggerSuppression(("EntersBattlefield",), ("Creature",), "you")
    row = _enters_beside(card_db, tmp_path, "Torpor Orb", controller, mine)
    assert row["status"] == status


def test_a_noncreature_entering_beside_hushbringer(card_db, tmp_path):
    """Hushbringer silences creatures entering: Ichor Wellspring, an
    artifact, still triggers."""
    wellspring, trigger = 3631, 4631
    _add_card(card_db, HUSHBRINGER, test_card("Hushbringer")["name"])
    _add_card(card_db, wellspring, test_card("Ichor Wellspring")["name"])
    _add_ability(card_db, trigger, _arena_text("Ichor Wellspring"))
    game = _enters_game("e6", fired=False)
    game[1]["gameObjects"] = [
        _listing(_obj(200, wellspring, types=("Artifact",)), trigger),
        _obj(500, HUSHBRINGER, types=("Creature",)),
    ]
    game[1]["zones"] = _zones(battlefield=[200, 500])
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert row["status"] == "unfired"


def test_an_enter_instance_logged_after_the_creature_died(card_db, tmp_path):
    """Entering and dying at once (Woodfall Primus put onto the battlefield and
    destroyed): its enter instance is logged after the leave, which has no
    trigger it pairs with, and still answers the enter."""
    game = _enters_game("p1", fired=False, turn_ends=False)
    death = _state(
        "p1",
        [
            _obj(210, VISIONARY, types=("Creature",)),
            _ability_obj(201, VISIONARY_ETB, VISIONARY, 200),
        ],
        [
            _ann(20, "ObjectIdChanged", None, [200], orig_id=200, new_id=210),
            _ann(
                21,
                "ZoneTransfer",
                None,
                [210],
                zone_src=BATTLEFIELD,
                zone_dest=GRAVEYARD,
                category="SBA_Damage",
            ),
            _ann(22, "AbilityInstanceCreated", 200, [201]),
        ],
    )
    game += [death, _turn(_state("p1"), 4)]
    (row,) = _run(card_db, _write(tmp_path / "a.log", game))["expected"]
    assert (row["event"], row["status"]) == ("enters", "fired")


def test_a_resync_repeating_a_resolution_reads_it_once(card_db, tmp_path):
    game = _bolt_game("s2")
    repeat = {**game[1], "type": "GameStateType_Full"}
    report = _run(card_db, _write(tmp_path / "a.log", [*game, repeat]))
    assert [r["card"] for r in report["resolutions"]] == ["Lightning Bolt"]
