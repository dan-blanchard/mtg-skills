"""Tests for Comprehensive Rules downloader."""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mtg_utils.download_rules import download_rules, main


def _mock_session(landing_html: str, rules_text: str) -> MagicMock:
    """Build a session mock where the first GET returns the landing page
    HTML and the second GET streams the rules TXT body in chunks."""
    landing_resp = MagicMock()
    landing_resp.text = landing_html
    landing_resp.raise_for_status = MagicMock()

    rules_resp = MagicMock()
    rules_resp.iter_content.return_value = [rules_text.encode()]
    rules_resp.raise_for_status = MagicMock()
    rules_resp.__enter__ = lambda s: s
    rules_resp.__exit__ = MagicMock(return_value=False)

    session = MagicMock()
    session.get.side_effect = [landing_resp, rules_resp]
    session.headers = {}
    return session


_LANDING_WITH_LINK = (
    "<html><body>"
    'Latest: <a href="https://media.wizards.com/2026/downloads/'
    'MagicCompRules%2020260227.txt">TXT</a>'
    "</body></html>"
)


class TestDownloadRules:
    def test_downloads_latest_to_output_dir(self, tmp_path):
        with patch("mtg_utils.download_rules.requests") as mock_requests:
            mock_requests.Session.return_value = _mock_session(
                _LANDING_WITH_LINK, "stub rules body"
            )
            mock_requests.RequestException = Exception

            result = download_rules(output_dir=tmp_path)

        assert result.exists()
        assert result.name == "comprehensive-rules-20260227.txt"
        assert result.read_text() == "stub rules body"

    def test_skips_if_fresh(self, tmp_path):
        existing = tmp_path / "comprehensive-rules-20260227.txt"
        existing.write_text("cached", encoding="utf-8")

        with patch("mtg_utils.download_rules.requests") as mock_requests:
            result = download_rules(output_dir=tmp_path)

        mock_requests.Session.assert_not_called()
        assert result == existing
        assert result.read_text() == "cached"

    def test_refreshes_if_stale(self, tmp_path):
        existing = tmp_path / "comprehensive-rules-20250101.txt"
        existing.write_text("old", encoding="utf-8")
        # Make the existing file older than the 24h freshness threshold.
        old_time = time.time() - 86400 * 2
        os.utime(existing, (old_time, old_time))

        with patch("mtg_utils.download_rules.requests") as mock_requests:
            mock_requests.Session.return_value = _mock_session(
                _LANDING_WITH_LINK, "new body"
            )
            mock_requests.RequestException = Exception

            result = download_rules(output_dir=tmp_path)

        assert result.name == "comprehensive-rules-20260227.txt"
        assert result.read_text() == "new body"

    def test_uses_existing_path(self, tmp_path):
        existing = tmp_path / "my-rules.txt"
        existing.write_text("text", encoding="utf-8")
        result = download_rules(existing_path=existing)
        assert result == existing

    def test_existing_path_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            download_rules(existing_path=tmp_path / "nope.txt")

    def test_falls_back_when_landing_page_fails(self, tmp_path):
        """If scraping fails, the hard-coded fallback URL is used with
        whatever date is in the fallback URL."""
        with patch("mtg_utils.download_rules.requests") as mock_requests:

            class _StubError(Exception):
                pass

            mock_requests.RequestException = _StubError

            # The landing-page call raises; the rules-fetch call succeeds.
            rules_resp = MagicMock()
            rules_resp.iter_content.return_value = [b"fallback body"]
            rules_resp.raise_for_status = MagicMock()
            rules_resp.__enter__ = lambda s: s
            rules_resp.__exit__ = MagicMock(return_value=False)

            def _get(url, **_kw):
                if "2026/downloads" in url:
                    return rules_resp
                msg = "landing page down"
                raise _StubError(msg)

            session = MagicMock()
            session.get.side_effect = _get
            session.headers = {}
            mock_requests.Session.return_value = session

            result = download_rules(output_dir=tmp_path)

        # Fallback URL is the 2026-02-27 one; the filename matches.
        assert result.name == "comprehensive-rules-20260227.txt"
        assert result.read_text() == "fallback body"


class TestCLI:
    def test_cli_prints_path(self, tmp_path):
        existing = tmp_path / "comprehensive-rules-20260227.txt"
        existing.write_text("text", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "comprehensive-rules-20260227.txt" in result.output
