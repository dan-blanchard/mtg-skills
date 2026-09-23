"""Tests for arena_card_db — the local MTG Arena card database as the wildcard-cost
source of record (the lowest rarity among a card's PRIMARY, i.e. craftable, printings).

The fixture databases carry only the columns the module reads, and use fictional card
names: these tests exercise the reading machinery, not any real card (ADR-0056).
"""

from __future__ import annotations

import os

import pytest
from conftest import make_arena_card_db as make_card_db

from mtg_utils import arena_card_db
from mtg_utils.arena_card_db import ENV_VAR, find_card_db, primary_rarities


@pytest.fixture(autouse=True)
def _fresh_memo():
    arena_card_db.clear_memo()
    yield
    arena_card_db.clear_memo()


class TestPrimaryRarities:
    def test_lowest_rarity_among_primary_printings(self, tmp_path):
        db = make_card_db(
            tmp_path / "Raw_CardDatabase_x.mtga",
            [
                ("Test Bolt", 2, 0),  # a common reprint Arena does not sell
                ("Test Bolt", 3, 1),
                ("Test Bolt", 4, 1),
                ("Test Heat", 2, 1),  # a common primary printing
                ("Test Heat", 5, 1),  # and a later mythic one
            ],
        )
        rarities = primary_rarities(db)
        assert rarities["test bolt"] == "uncommon"
        assert rarities["test heat"] == "common"

    def test_skips_tokens_rebalanced_and_unrated_rows(self, tmp_path):
        db = make_card_db(
            tmp_path / "Raw_CardDatabase_x.mtga",
            [
                ("Test Token", 2, 1, 1, 0),
                ("A-Test Card", 2, 1, 0, 1),
                ("Test Basic", 1, 1),  # rarity 1 is Arena's basic-land rarity
                ("Test Card", 4, 1),
            ],
        )
        assert primary_rarities(db) == {"test card": "rare"}

    def test_reads_the_plain_title_over_the_formatted_one(self, tmp_path):
        """Arena's formatted title hides a rebalanced card's "A-" behind a sprite
        tag and wraps hyphenated words in ``<nobr>``; the plain row is the name."""
        db = make_card_db(
            tmp_path / "Raw_CardDatabase_x.mtga",
            [
                ("Half-Test Monk", 3, 1, 0, 0, "<nobr>Half-Test</nobr> Monk"),
            ],
        )
        assert primary_rarities(db) == {"half-test monk": "uncommon"}

    def test_strips_markup_when_only_a_formatted_title_exists(self, tmp_path):
        db = make_card_db(
            tmp_path / "Raw_CardDatabase_x.mtga",
            [
                (None, 3, 1, 0, 0, "Test Dusk /// Test Dawn"),
                (None, 2, 1, 0, 0, "<nobr>Half-Test</nobr> Cleric"),
            ],
        )
        assert primary_rarities(db) == {
            "test dusk // test dawn": "uncommon",
            "half-test cleric": "common",
        }


class TestFindCardDb:
    def test_env_var_names_the_database(self, tmp_path, monkeypatch):
        db = make_card_db(tmp_path / "anywhere.mtga", [("Test Card", 2, 1)])
        monkeypatch.setenv(ENV_VAR, str(db))
        assert find_card_db() == db

    def test_env_var_none_disables_discovery(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "none")
        assert find_card_db() is None

    def test_reads_the_downloads_folder_from_player_log(self, tmp_path, monkeypatch):
        raw = tmp_path / "MTGA" / "MTGA_Data" / "Downloads" / "Raw"
        raw.mkdir(parents=True)
        make_card_db(raw / "Raw_CardDatabase_old.mtga", [("Test Card", 2, 1)])
        newest = make_card_db(raw / "Raw_CardDatabase_new.mtga", [("Test Card", 3, 1)])
        os.utime(raw / "Raw_CardDatabase_old.mtga", (1, 1))
        log = tmp_path / "Player.log"
        log.write_text(
            "Initialize engine version\n"
            f"[Manifest]Bundle download destination: {raw.parent}\n"
        )
        monkeypatch.delenv(ENV_VAR, raising=False)
        monkeypatch.setattr(arena_card_db, "player_log_path", lambda: log)
        monkeypatch.setattr(arena_card_db, "_INSTALL_DOWNLOADS", ())
        assert find_card_db() == newest

    def test_none_when_nothing_is_installed(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        monkeypatch.setattr(
            arena_card_db, "player_log_path", lambda: tmp_path / "missing.log"
        )
        monkeypatch.setattr(arena_card_db, "_INSTALL_DOWNLOADS", ())
        assert find_card_db() is None
