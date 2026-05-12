"""Smoke tests: deck-strat package installs and reused CLIs resolve.

deck-strat ships no CLIs of its own (per ADR-0004). The tests verify
that the entry points it re-declares from mtg_utils are importable.
"""

from click.testing import CliRunner


class TestEntryPointsImport:
    def test_parse_deck_main(self):
        from mtg_utils.parse_deck import main

        assert callable(main)

    def test_set_commander_main(self):
        from mtg_utils.set_commander import main

        assert callable(main)

    def test_scryfall_lookup_main(self):
        from mtg_utils.scryfall_lookup import main

        assert callable(main)

    def test_legality_audit_main(self):
        from mtg_utils.legality_audit import main

        assert callable(main)

    def test_mana_audit_main(self):
        from mtg_utils.mana_audit import main

        assert callable(main)

    def test_combo_search_main(self):
        from mtg_utils.combo_search import main

        assert callable(main)

    def test_archetype_audit_main(self):
        from mtg_utils.archetype_audit import main

        assert callable(main)

    def test_edhrec_lookup_main(self):
        from mtg_utils.edhrec_lookup import main

        assert callable(main)

    def test_rules_lookup_main(self):
        from mtg_utils.rules_lookup import main

        assert callable(main)

    def test_rulings_lookup_main(self):
        from mtg_utils.rulings_lookup import main

        assert callable(main)


class TestCLIHelpSmoke:
    def _run_help(self, main_fn) -> str:
        runner = CliRunner()
        result = runner.invoke(main_fn, ["--help"])
        assert result.exit_code == 0, result.output
        return result.output

    def test_parse_deck_help(self):
        from mtg_utils.parse_deck import main

        out = self._run_help(main)
        assert "parse" in out.lower() or "deck" in out.lower()

    def test_combo_search_help(self):
        from mtg_utils.combo_search import main

        self._run_help(main)

    def test_rules_lookup_help(self):
        from mtg_utils.rules_lookup import main

        self._run_help(main)
