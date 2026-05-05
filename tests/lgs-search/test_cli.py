from __future__ import annotations

from click.testing import CliRunner

from mtg_utils.lgs_search import main


def test_help_lists_main_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    out = result.output
    expected_flags = [
        "--input",
        "--collection",
        "--bulk-data",
        "--condition",
        "--allow-foil",
        "--lgs-online-threshold-pct",
        "--lgs-online-threshold-usd",
        "--no-handoff",
        "--dry-run",
        "--retry-relaxed",
        "--clear-existing-carts",
        "--include-basics",
        "--yes",
        "--search-timeout-seconds",
        "--cart-timeout-seconds",
        "--max-retries",
        "--output-dir",
        "--resume",
    ]
    for flag in expected_flags:
        assert flag in out, f"missing {flag} in --help output"


def test_login_subcommand_help():
    runner = CliRunner()
    result = runner.invoke(main, ["login", "--help"])
    assert result.exit_code == 0
    assert "--store" in result.output


def test_no_input_errors_with_exit_2():
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 2
    assert "input" in result.output.lower() or "input" in (result.stderr or "").lower()
