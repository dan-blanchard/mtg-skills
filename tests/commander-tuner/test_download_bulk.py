"""Tests for Scryfall bulk data downloader."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from commander_utils.download_bulk import download_bulk, main


class TestDownloadBulk:
    def test_downloads_to_specified_path(self, tmp_path):
        mock_bulk_meta = {
            "data": [
                {
                    "type": "default_cards",
                    "download_uri": "https://data.scryfall.io/default-cards/default-cards-123.json",
                }
            ]
        }
        mock_cards = [{"id": "abc", "name": "Lightning Bolt"}]

        with patch("commander_utils.download_bulk.requests") as mock_requests:
            mock_meta_resp = MagicMock()
            mock_meta_resp.json.return_value = mock_bulk_meta
            mock_meta_resp.raise_for_status = MagicMock()

            mock_cards_resp = MagicMock()
            mock_cards_resp.iter_content.return_value = [
                json.dumps(mock_cards).encode()
            ]
            mock_cards_resp.raise_for_status = MagicMock()
            mock_cards_resp.__enter__ = lambda s: s
            mock_cards_resp.__exit__ = MagicMock(return_value=False)

            mock_session = MagicMock()
            mock_session.get.side_effect = [mock_meta_resp, mock_cards_resp]
            mock_requests.Session.return_value = mock_session

            result_path = download_bulk(output_dir=tmp_path)

        assert result_path.exists()
        assert result_path.parent == tmp_path

    def test_skips_if_fresh(self, tmp_path):
        existing = tmp_path / "default-cards.json"
        existing.write_text("[]")

        with patch("commander_utils.download_bulk.requests") as mock_requests:
            result_path = download_bulk(output_dir=tmp_path)

        mock_requests.Session.assert_not_called()
        assert result_path == existing

    def test_uses_existing_bulk_path(self, tmp_path):
        existing = tmp_path / "my-bulk.json"
        existing.write_text('[{"id": "abc"}]')

        result_path = download_bulk(existing_path=existing)
        assert result_path == existing

    def test_existing_path_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            download_bulk(existing_path=tmp_path / "nonexistent.json")


class TestCLI:
    def test_prints_path(self, tmp_path):
        existing = tmp_path / "default-cards.json"
        existing.write_text("[]")

        runner = CliRunner()
        result = runner.invoke(main, ["--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert str(tmp_path) in result.output
