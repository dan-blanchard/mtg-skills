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


def test_not_yet_wired_flags_warn(tmp_path):
    """Flags advertised in --help but stubbed in v1 should print a warning,
    not silently no-op, so users don't think they're getting behavior they
    aren't.
    """
    import json

    deck_path = tmp_path / "deck.json"
    deck_path.write_text(
        json.dumps(
            {
                "commanders": [],
                "cards": [],
                "sideboard": [],
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input",
            str(deck_path),
            "--output-dir",
            str(tmp_path),
            "--dry-run",
            "--retry-relaxed",
            "--max-retries",
            "5",
        ],
    )
    # Click's default CliRunner combines stdout + stderr in result.output.
    assert "not yet wired" in result.output.lower()
    assert "--retry-relaxed" in result.output
    assert "--max-retries" in result.output
