"""Smoke test: playtest-goldfish CLI is registered and prints --help."""

from click.testing import CliRunner

from mtg_utils.playtest import goldfish_main


def test_goldfish_help():
    runner = CliRunner()
    result = runner.invoke(goldfish_main, ["--help"])
    assert result.exit_code == 0
    assert "simulator" in result.output.lower()
