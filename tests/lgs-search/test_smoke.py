"""Smoke: lgs-search package installs and key CLIs resolve."""

from __future__ import annotations

from click.testing import CliRunner


def test_lgs_search_main_importable():
    from mtg_utils.lgs_search import main

    assert callable(main)


def test_parse_deck_main_importable():
    from mtg_utils.parse_deck import main

    assert callable(main)


def test_help_succeeds():
    from mtg_utils.lgs_search import main

    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0


def test_login_subcommand_present():
    from mtg_utils.lgs_search import main

    result = CliRunner().invoke(main, ["login", "--help"])
    assert result.exit_code == 0
    assert "--store" in result.output
