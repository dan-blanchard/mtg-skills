"""Tests for the snapshot builder's usage-derived name scan (AST-based)."""

import json
from unittest.mock import patch

from mtg_utils.build_card_snapshot import _existing_names, _scan_module, main

# NB: the module under scan is a STRING — the test_card(...) calls inside it are
# data for the scanner, not calls this test file makes, so they must not feed
# the real snapshot. The scanner reads files, never strings in other files.


def test_scans_direct_literal_calls():
    src = 'def test_x():\n    assert test_card("Sol Ring")\n'
    assert _scan_module(src) == {"Sol Ring"}


def test_scans_wrapper_family_and_apostrophes():
    src = 'def test_x():\n    _ks_real("Atraxa, Praetors\' Voice")\n'
    assert _scan_module(src) == {"Atraxa, Praetors' Voice"}


def test_ignores_comments_and_docstrings():
    # The old regex scan false-positived on both of these ('…' and a card name
    # mentioned in prose); the AST never sees comments, and a docstring is not
    # a call argument.
    src = (
        '# a comment mentioning test_card("…") stays out\n'
        "def test_x():\n"
        '    """Mentions test_card("Harsh Mentor") in prose only."""\n'
        "    assert True\n"
    )
    assert _scan_module(src) == set()


def test_scans_parametrize_column_feeding_a_helper():
    # Only the column that actually flows into test_card(...) is harvested —
    # the `wanted` labels ("rat") are not card names and stay out.
    src = (
        "@pytest.mark.parametrize(\n"
        '    ("name", "wanted"),\n'
        "    [\n"
        '        ("Daring Saboteur", "rat"),\n'
        '        ("Divination", "orc"),\n'
        "    ],\n"
        ")\n"
        "def test_x(name, wanted):\n"
        "    assert not matches(test_card(name), wanted)\n"
    )
    assert _scan_module(src) == {"Daring Saboteur", "Divination"}


def test_scans_parametrize_comma_string_argnames_and_scalar_rows():
    src = (
        '@pytest.mark.parametrize("name", ["Duress", "Addle"])\n'
        "def test_x(name):\n"
        "    assert test_card_ir(name)\n"
    )
    assert _scan_module(src) == {"Duress", "Addle"}


def test_scans_pytest_param_rows():
    src = (
        '@pytest.mark.parametrize("name", [pytest.param("Peek"), "Telepathy"])\n'
        "def test_x(name):\n"
        "    assert test_signals(name)\n"
    )
    assert _scan_module(src) == {"Peek", "Telepathy"}


def test_ignores_parametrize_columns_not_feeding_a_helper():
    # `label` never reaches a helper call, so its values (which could collide
    # with real card names, e.g. "Mountain") are not harvested.
    src = (
        '@pytest.mark.parametrize("label", ["Mountain", "Island"])\n'
        "def test_x(label):\n"
        "    assert label\n"
    )
    assert _scan_module(src) == set()


def test_scans_real_cases_table_values():
    src = (
        "_REAL_CASES: dict[str, str] = {\n"
        '    "hand_disruption": "Duress",\n'
        '    "tap_down": "Yosei, the Morning Star",\n'
        "}\n"
    )
    assert _scan_module(src) == {"Duress", "Yosei, the Morning Star"}


def test_syntax_error_returns_empty():
    assert _scan_module("def broken(:\n") == set()


# ─── existing-snapshot-names union (task #86) ──────────────────────────────
#
# The AST scan is necessarily incomplete: a parametrize table built from a
# dynamic comprehension over imported registry data (e.g.
# ``[card for name in PRESETS for card in PRESETS[name].should_match]``, the
# real shape of ``TestStructuralPresetsAgainstSnapshot`` in
# test_theme_presets.py) has no string literal anywhere in the test file for
# the scanner to find. A bare regen must never silently drop such a name —
# it must be unioned in from the snapshot already on disk.


def test_existing_names_missing_file_returns_empty(tmp_path):
    assert _existing_names(tmp_path / "nope.json") == set()


def test_existing_names_reads_committed_card_keys(tmp_path):
    path = tmp_path / "snap.json"
    path.write_text(json.dumps({"cards": {"Sol Ring": {}, "Duress": {}}}))
    assert _existing_names(path) == {"Sol Ring", "Duress"}


def test_existing_names_malformed_json_returns_empty(tmp_path):
    path = tmp_path / "snap.json"
    path.write_text("not json")
    assert _existing_names(path) == set()


def test_main_carries_forward_a_name_only_the_snapshot_knows(tmp_path):
    """A name present only in the existing committed snapshot (never a scan
    hit, never --names/--names-file) survives a bare regen — the exact trap
    the AST scan can't see around a dynamic-comprehension parametrize table.
    """
    out_path = tmp_path / "card_snapshot.json"
    out_path.write_text(json.dumps({"cards": {"Only-In-Snapshot Card": {}}}))

    captured: dict = {}

    def fake_build_snapshot(names, out):
        captured["names"] = set(names)
        out.write_text(json.dumps({"cards": {n: {} for n in names}}))
        return out, {
            "cards": len(names),
            "requested": len(names),
            "unresolved": [],
            "no_phase_records": [],
            "bytes": out.stat().st_size,
        }

    with (
        patch(
            "mtg_utils.build_card_snapshot._scan_names",
            return_value={"Newly Scanned Card"},
        ),
        patch(
            "mtg_utils.build_card_snapshot.build_snapshot",
            side_effect=fake_build_snapshot,
        ),
    ):
        rc = main(["--out", str(out_path)])

    assert rc == 0
    assert "Only-In-Snapshot Card" in captured["names"]
    assert "Newly Scanned Card" in captured["names"]


def test_main_prune_drops_names_the_scan_no_longer_supplies(tmp_path):
    out_path = tmp_path / "card_snapshot.json"
    out_path.write_text(json.dumps({"cards": {"Stale Card": {}}}))

    captured: dict = {}

    def fake_build_snapshot(names, out):
        captured["names"] = set(names)
        out.write_text(json.dumps({"cards": {n: {} for n in names}}))
        return out, {
            "cards": len(names),
            "requested": len(names),
            "unresolved": [],
            "no_phase_records": [],
            "bytes": out.stat().st_size,
        }

    with (
        patch(
            "mtg_utils.build_card_snapshot._scan_names",
            return_value={"Fresh Card"},
        ),
        patch(
            "mtg_utils.build_card_snapshot.build_snapshot",
            side_effect=fake_build_snapshot,
        ),
    ):
        rc = main(["--out", str(out_path), "--prune"])

    assert rc == 0
    assert captured["names"] == {"Fresh Card"}
