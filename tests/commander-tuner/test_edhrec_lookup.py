"""Tests for EDHREC lookup."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mtg_utils.edhrec_lookup import edhrec_lookup, main, slugify


class TestSlugify:
    def test_simple_name(self):
        assert slugify("Korvold, Fae-Cursed King") == "korvold-fae-cursed-king"

    def test_apostrophe(self):
        assert slugify("Ashnod's Altar") == "ashnods-altar"

    def test_multiple_spaces(self):
        assert slugify("Sakura  Tribe  Elder") == "sakura-tribe-elder"

    def test_partner_combined(self):
        result = slugify("Thrasios, Triton Hero", "Tymna the Weaver")
        assert result == "thrasios-triton-hero-tymna-the-weaver"


class TestEdhrecLookup:
    def test_fetches_commander_data(self, sample_edhrec_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_edhrec_response
        mock_resp.raise_for_status = MagicMock()

        with patch("mtg_utils.edhrec_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = edhrec_lookup(["Korvold, Fae-Cursed King"])

        assert "high_synergy" in result
        assert len(result["high_synergy"]) == 2
        assert result["high_synergy"][0]["name"] == "Pitiless Plunderer"
        assert result["high_synergy"][0]["synergy"] == 0.55

    def test_fetches_partner_data(self, sample_edhrec_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_edhrec_response
        mock_resp.raise_for_status = MagicMock()

        with patch("mtg_utils.edhrec_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            edhrec_lookup(["Thrasios, Triton Hero", "Tymna the Weaver"])

        call_url = mock_session.get.call_args[0][0]
        assert "thrasios-triton-hero-tymna-the-weaver" in call_url

    def test_returns_empty_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("mtg_utils.edhrec_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            result = edhrec_lookup(["Unknown Commander"])

        assert result["high_synergy"] == []
        assert result["top_cards"] == []


class TestCLI:
    def test_outputs_json(self, sample_edhrec_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_edhrec_response
        mock_resp.raise_for_status = MagicMock()

        with patch("mtg_utils.edhrec_lookup.requests") as mock_requests:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            mock_requests.Session.return_value = mock_session

            runner = CliRunner()
            result = runner.invoke(main, ["Korvold, Fae-Cursed King"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "high_synergy" in data
