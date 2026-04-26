"""Smoke test: playtest-custom-format CLI is registered."""

from click.testing import CliRunner

from mtg_utils.playtest import custom_format_main


def test_custom_format_help():
    runner = CliRunner()
    result = runner.invoke(custom_format_main, ["--help"])
    assert result.exit_code == 0
    assert "format" in result.output.lower()
