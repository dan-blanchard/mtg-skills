"""Smoke tests: the twohg-guide package installs and every CLI it declares resolves.

twohg-guide owns five CLIs (the modules live in mtg_utils like every skill's) and
re-declares the rules / card-data CLIs its audit phase uses. Each entry point in
``twohg-guide/pyproject.toml`` must import and answer ``--help``.
"""

import importlib
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

_PYPROJECT = Path(__file__).resolve().parents[2] / "twohg-guide" / "pyproject.toml"
_SCRIPTS = tomllib.loads(_PYPROJECT.read_text())["project"]["scripts"]


@pytest.mark.parametrize(("name", "target"), sorted(_SCRIPTS.items()))
def test_entry_point_answers_help(name, target):
    module, _, attr = target.partition(":")
    command = getattr(importlib.import_module(module), attr)
    result = CliRunner().invoke(command, ["--help"])
    assert result.exit_code == 0, f"{name}: {result.output}"


def test_declares_its_own_clis():
    assert {
        "twohg-scan",
        "limited-stats",
        "thread-extract",
        "guide-card-hovers",
        "twohg-template",
    } <= set(_SCRIPTS)
