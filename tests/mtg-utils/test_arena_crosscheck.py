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
from mtg_utils._arena_crosscheck.check import Checker, crosscheck
from mtg_utils._arena_crosscheck.effects import compare_kinds
from mtg_utils._arena_crosscheck.log import read_logs
from mtg_utils._arena_crosscheck.report import diff_reports
from mtg_utils._card_ir.crosswalk import (
    chosen_x_sign,
    effect_is_delayed,
    effect_targets_optional,
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
    resolutions, _, games = read_logs([first, second])
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
