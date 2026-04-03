"""Tests for web page fetcher."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from commander_utils.web_fetch import _strip_html, fetch_page, main


class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_removes_scripts(self):
        html = "<p>Before</p><script>var x = 1;</script><p>After</p>"
        result = _strip_html(html)
        assert "var x" not in result
        assert "Before" in result
        assert "After" in result

    def test_removes_styles(self):
        html = "<style>.foo { color: red; }</style><p>Content</p>"
        result = _strip_html(html)
        assert "color" not in result
        assert "Content" in result

    def test_converts_block_elements_to_newlines(self):
        html = "<h1>Title</h1><p>Para 1</p><p>Para 2</p>"
        result = _strip_html(html)
        assert "Title" in result
        assert "Para 1" in result
        assert "Para 2" in result

    def test_decodes_entities(self):
        assert "Tom & Jerry" in _strip_html("Tom &amp; Jerry")
        assert '"hello"' in _strip_html("&quot;hello&quot;")

    def test_collapses_whitespace(self):
        html = "<p>  lots   of   spaces  </p>"
        result = _strip_html(html)
        assert "  " not in result


class TestFetchPage:
    def test_fetches_and_strips(self):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><p>Card strategy here</p></body></html>"
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.web_fetch.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = fetch_page("https://example.com/deck-tech")

        assert "Card strategy here" in result

    def test_uses_browser_headers(self):
        mock_resp = MagicMock()
        mock_resp.text = "<p>Content</p>"
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.web_fetch.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            fetch_page("https://example.com")

        # Verify browser-like headers were set
        update_call = mock_session.headers.update.call_args[0][0]
        assert "Mozilla" in update_call["User-Agent"]
        assert "Accept" in update_call
        assert "Accept-Language" in update_call


class TestCurlFallback:
    def test_falls_back_to_curl_on_403(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with (
            patch("commander_utils.web_fetch.requests") as mock_requests,
            patch("commander_utils.web_fetch.subprocess") as mock_subprocess,
        ):
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "<p>Content via curl</p>"
            mock_subprocess.run.return_value = mock_result

            result = fetch_page("https://example.com")

        assert "Content via curl" in result
        mock_subprocess.run.assert_called_once()

    def test_does_not_use_curl_on_200(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<p>Content via requests</p>"
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("commander_utils.web_fetch.requests") as mock_requests,
            patch("commander_utils.web_fetch.subprocess") as mock_subprocess,
        ):
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = fetch_page("https://example.com")

        assert "Content via requests" in result
        mock_subprocess.run.assert_not_called()


class TestCLI:
    def test_outputs_text(self):
        mock_resp = MagicMock()
        mock_resp.text = "<p>Strategy guide content</p>"
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.web_fetch.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, ["https://example.com"])

        assert result.exit_code == 0
        assert "Strategy guide content" in result.output

    def test_truncates_with_max_length(self):
        mock_resp = MagicMock()
        mock_resp.text = "<p>" + "A" * 1000 + "</p>"
        mock_resp.raise_for_status = MagicMock()

        with patch("commander_utils.web_fetch.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, ["https://example.com", "--max-length", "100"])

        assert result.exit_code == 0
        assert "[Truncated]" in result.output
