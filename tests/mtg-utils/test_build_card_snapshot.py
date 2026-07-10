"""Tests for the snapshot builder's usage-derived name scan (AST-based)."""

from mtg_utils.build_card_snapshot import _scan_module

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
