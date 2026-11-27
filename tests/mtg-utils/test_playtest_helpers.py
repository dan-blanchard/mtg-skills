"""The playtest commands' shared helpers (ADR-0069): the output tail, the cube and
stated-archetype reads, and the phase-run path match and gauntlet share."""

from __future__ import annotations

import json

import click
import pytest
from click.testing import CliRunner

from mtg_utils import _phase
from mtg_utils._playtest_common import emit
from mtg_utils.playtest import (
    _first_five,
    _gauntlet_phase_format,
    _load_cube,
    _refuse_if_blocked,
    _run_duel,
    _stated_archetypes,
    _stated_overrides,
    gauntlet_main,
    match_main,
)
from mtg_utils.testkit import test_card


def _cov(status: str, missing: list[str] | None = None) -> dict:
    missing = missing or []
    return {
        "status": status,
        "supported_pct": {"full": 1.0, "warn": 0.95, "blocked": 0.5}[status],
        "missing": missing,
        "requested": 40,
        "supported": 40 - len(missing),
    }


def _duel_result(games: int) -> dict:
    return {
        "status": "ok",
        "wins_p0": games,
        "wins_p1": 0,
        "draws": 0,
        "games": games,
        "games_completed": games,
        "games_requested": games,
        "timed_out": False,
        "avg_turns": 7.0,
        "avg_duration_ms": 10,
    }


class TestEmit:
    def test_writes_the_envelope_and_prints_the_report(self, tmp_path, capsys):
        out = tmp_path / "out.json"
        emit({"mode": "x", "n": 1}, str(out), lambda env: f"report {env['n']}")
        assert json.loads(out.read_text()) == {"mode": "x", "n": 1}
        assert out.read_text() == json.dumps({"mode": "x", "n": 1}, indent=2)
        assert capsys.readouterr().out == "report 1\n"

    def test_no_output_path_only_prints(self, tmp_path, capsys):
        emit({"n": 2}, None, lambda _env: "only stdout")
        assert capsys.readouterr().out == "only stdout\n"
        assert list(tmp_path.iterdir()) == []


class TestCubeReads:
    def test_load_cube_keeps_the_cards_the_records_resolve(self, tmp_path):
        cube_path = tmp_path / "cube.json"
        hydrated_path = tmp_path / "hydrated.json"
        cube_path.write_text(
            json.dumps(
                {
                    "cards": [
                        {"name": "Grizzly Bears", "quantity": 1},
                        {"name": "Not In The Records", "quantity": 1},
                        {"name": "Forest", "quantity": 1},
                    ]
                }
            )
        )
        hydrated_path.write_text(
            json.dumps([test_card("Forest"), test_card("Grizzly Bears")])
        )
        cube, lookup, cards = _load_cube(str(cube_path), str(hydrated_path))
        assert cube["cards"][1]["name"] == "Not In The Records"
        assert [c["name"] for c in cards] == ["Grizzly Bears", "Forest"]
        assert lookup.get("Forest")["name"] == "Forest"

    def test_stated_archetypes_names_and_overrides(self):
        cube = {
            "designer_intent": {
                "stated_archetypes": [
                    {"name": "custom-burn", "regex": "deals \\d+ damage"},
                    {"name": "tokens", "gauntlet": {"shape": "aggro"}},
                    {"name": "graveyard", "members": ["reanimate", "self-mill"]},
                ]
            }
        }
        resolved, names = _stated_archetypes(cube)
        overrides = _stated_overrides(cube)
        # Presets (a group's members flattened in), then groups, then custom regexes.
        assert names == ["tokens", "reanimate", "self-mill", "graveyard", "custom-burn"]
        assert [g.name for g in resolved.groups] == ["graveyard"]
        assert overrides == {
            "custom-burn": None,
            "tokens": {"shape": "aggro"},
            "graveyard": None,
        }

    def test_no_stated_archetypes(self):
        _resolved, names = _stated_archetypes({"cards": []})
        overrides = _stated_overrides({"cards": []})
        assert names == []
        assert overrides == {}


class TestPhasePath:
    def test_first_five(self):
        assert _first_five(["a", "b"]) == "a, b"
        assert _first_five(list("abcde")) == "a, b, c, d, e"
        assert _first_five(list("abcdef")) == "a, b, c, d, e…"

    def test_refuse_if_blocked_exits_2_with_the_message(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _refuse_if_blocked(_cov("blocked"), "nope")
        assert exc.value.code == 2
        assert capsys.readouterr().err == "nope\n"

    @pytest.mark.parametrize("status", ["full", "warn"])
    def test_refuse_if_blocked_lets_the_rest_run(self, status, capsys):
        _refuse_if_blocked(_cov(status), "nope")
        assert capsys.readouterr().err == ""

    def test_run_duel_reads_phase_at_call_time(self, tmp_path, monkeypatch):
        seen = {}

        def fake(a, b, **kw):
            seen.update(kw, a=a, b=b)
            return _duel_result(kw["games"])

        monkeypatch.setattr("mtg_utils._phase.run_duel", fake)
        got = _run_duel(
            tmp_path / "a.json",
            tmp_path / "b.json",
            games=3,
            seed=4,
            format_="modern",
            difficulty="Hard",
            timeout_s=9,
        )
        assert got["wins_p0"] == 3
        assert seen == {
            "a": tmp_path / "a.json",
            "b": tmp_path / "b.json",
            "games": 3,
            "seed": 4,
            "format_": "modern",
            "difficulty": "Hard",
            "timeout_s": 9,
        }

    def test_run_duel_engine_failure_is_a_click_error(self, tmp_path, monkeypatch):
        def boom(*_a, **_kw):
            raise _phase.PhaseRuntimeError("ai-duel exited with code 3", "panic!")

        monkeypatch.setattr("mtg_utils._phase.run_duel", boom)
        with pytest.raises(click.ClickException) as exc:
            _run_duel(
                tmp_path / "a.json",
                tmp_path / "b.json",
                games=1,
                seed=0,
                format_="modern",
                difficulty="Medium",
                timeout_s=1,
            )
        assert exc.value.message == (
            "ai-duel exited with code 3\nEngine stderr:\npanic!"
        )

    def test_gauntlet_phase_format(self):
        assert _gauntlet_phase_format({"format": "pauper_cube"}) == "pauper"
        assert _gauntlet_phase_format({}) == "modern"
        # An empty format passes through as is (no "modern" default).
        assert _gauntlet_phase_format({"format": ""}) == ""
        assert _gauntlet_phase_format({"format": "_cube"}) == ""

    def test_is_phase_native(self):
        assert _phase.is_phase_native({"main": []})
        assert not _phase.is_phase_native({"main": [], "cards": []})
        assert not _phase.is_phase_native({"cards": []})


def _gauntlet_cube(tmp_path):
    cube = {"format": "pauper_cube", "cards": []}
    hydrated = []
    for color, cmc in [("R", 1), ("R", 2), ("B", 2), ("B", 3)]:
        for i in range(30):
            name = f"Fixture {color}{cmc} {i}"
            cube["cards"].append({"name": name, "quantity": 1})
            hydrated.append(
                {
                    "name": name,
                    "type_line": "Creature — Fixture",
                    "oracle_text": "",
                    "mana_cost": f"{{{color}}}",
                    "cmc": cmc,
                    "power": "2",
                    "toughness": "2",
                    "color_identity": [color],
                    "produced_mana": [],
                }
            )
    manifest = {
        "format": "pauper_cube",
        "deck_size": 40,
        "lands": 17,
        "archetypes": [
            {"name": "Red", "colors": ["R"], "shape": "aggro", "curve_target": {}},
            {"name": "Black", "colors": ["B"], "shape": "aggro", "curve_target": {}},
        ],
    }
    paths = []
    for name, data in (
        ("cube.json", cube),
        ("hydrated.json", hydrated),
        ("manifest.json", manifest),
    ):
        (tmp_path / name).write_text(json.dumps(data))
        paths.append(str(tmp_path / name))
    return paths


class TestMatchAndGauntletShareThePhasePath:
    def test_gauntlet_refuses_a_blocked_gate_and_has_no_force(
        self, tmp_path, monkeypatch
    ):
        cube, hydrated, manifest = _gauntlet_cube(tmp_path)
        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report", lambda _names: _cov("blocked")
        )
        args = [cube, "--hydrated", hydrated, "--gauntlet", manifest]
        result = CliRunner().invoke(gauntlet_main, args)
        assert result.exit_code == 2
        assert result.stderr == (
            "Refusing: phase coverage 50.0% is below threshold for built archetype "
            "decks.\n"
        )
        forced = CliRunner().invoke(gauntlet_main, [*args, "--force"])
        assert forced.exit_code == 2
        assert "No such option: --force" in forced.stderr

    def test_gauntlet_writes_phase_decks_and_reports_engine_errors(
        self, tmp_path, monkeypatch
    ):
        cube, hydrated, manifest = _gauntlet_cube(tmp_path)
        written = []

        def fake(a, b, **_kw):
            written.extend(json.loads(p.read_text()) for p in (a, b))
            raise _phase.PhaseRuntimeError("ai-duel exited with code 1", "bad deck")

        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report", lambda _names: _cov("full")
        )
        monkeypatch.setattr("mtg_utils._phase.run_duel", fake)
        result = CliRunner().invoke(
            gauntlet_main, [cube, "--hydrated", hydrated, "--gauntlet", manifest]
        )
        assert result.exit_code == 1
        assert "Engine stderr:\nbad deck" in result.stderr
        assert [(d["name"], d["format"], list(d)) for d in written] == [
            ("Red", "pauper", ["name", "format", "main"]),
            ("Black", "pauper", ["name", "format", "main"]),
        ]

    def test_match_coverage_warning_lists_five_missing(self, tmp_path, monkeypatch):
        deck = {
            "format": "modern",
            "cards": [{"name": "Forest", "quantity": 40}],
            "commanders": [],
        }
        a = tmp_path / "a.json"
        a.write_text(json.dumps(deck))
        missing = [f"Missing {i}" for i in range(7)]
        monkeypatch.setattr(
            "mtg_utils._phase.coverage_report", lambda _names: _cov("warn", missing)
        )
        monkeypatch.setattr(
            "mtg_utils._phase.run_duel", lambda *_a, **kw: _duel_result(kw["games"])
        )
        out = tmp_path / "out.json"
        result = CliRunner().invoke(
            match_main, [str(a), str(a), "--games", "2", "--output", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(out.read_text())["warnings"] == [
            (
                "Phase coverage 95.0% — 7 cards substituted: "
                "Missing 0, Missing 1, Missing 2, Missing 3, Missing 4…"
            )
        ]
