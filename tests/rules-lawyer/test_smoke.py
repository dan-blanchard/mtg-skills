"""Smoke tests: rules-lawyer package installs and key CLIs resolve."""

from click.testing import CliRunner


class TestEntryPointsImport:
    def test_rules_lookup_main(self):
        from mtg_utils.rules_lookup import main

        assert callable(main)

    def test_rulings_lookup_main(self):
        from mtg_utils.rulings_lookup import main

        assert callable(main)

    def test_download_rules_main(self):
        from mtg_utils.download_rules import main

        assert callable(main)


class TestCLIHelpSmoke:
    def _run_help(self, main_fn) -> str:
        runner = CliRunner()
        result = runner.invoke(main_fn, ["--help"])
        assert result.exit_code == 0, result.output
        return result.output

    def test_rules_lookup_help_mentions_modes(self):
        from mtg_utils.rules_lookup import main

        out = self._run_help(main)
        assert "--rule" in out
        assert "--term" in out
        assert "--grep" in out

    def test_rulings_lookup_help_mentions_card(self):
        from mtg_utils.rulings_lookup import main

        out = self._run_help(main)
        assert "--card" in out
        assert "--batch" in out

    def test_download_rules_help_mentions_output_dir(self):
        from mtg_utils.download_rules import main

        out = self._run_help(main)
        assert "--output-dir" in out
        assert "--existing" in out
