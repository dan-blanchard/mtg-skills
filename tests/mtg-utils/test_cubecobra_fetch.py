"""Tests for cubecobra-fetch CLI."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mtg_utils._http import BROWSER_HEADERS, USER_AGENT
from mtg_utils.cubecobra_fetch import extract_cube_id, main


class TestExtractCubeId:
    def test_bare_id(self):
        assert extract_cube_id("regular") == "regular"

    def test_overview_url(self):
        url = "https://cubecobra.com/cube/overview/regular"
        assert extract_cube_id(url) == "regular"

    def test_list_url(self):
        url = "https://cubecobra.com/cube/list/regular"
        assert extract_cube_id(url) == "regular"

    def test_url_with_query(self):
        url = "https://cubecobra.com/cube/overview/regular?tab=cards"
        assert extract_cube_id(url) == "regular"

    def test_trailing_slash(self):
        url = "https://cubecobra.com/cube/overview/my-cube-name/"
        assert extract_cube_id(url) == "my-cube-name"


class TestCLIInterface:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_json_success_path(self, tmp_path: Path):
        """Happy path: primary cubeJSON endpoint returns 200."""
        runner = CliRunner()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(
            {
                "shortID": "regular",
                "name": "Regular Cube",
                "description": "My unpowered cube",
                "mainboard": [{"cardID": "abc", "details": {"name": "Lightning Bolt"}}],
                "maybeboard": [],
            }
        )
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out_file = tmp_path / "regular.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["shortID"] == "regular"

    def test_falls_back_to_csv_when_json_fails(self, tmp_path: Path):
        """cubeJSON raises → fetch falls back to CSV endpoint."""
        runner = CliRunner()

        call_count = {"n": 0}

        def side_effect(url, **_kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            if "cubeJSON" in url:
                resp.status_code = 500
                resp.raise_for_status.side_effect = Exception("500 server error")
            else:
                resp.status_code = 200
                resp.text = "name,CMC\nLightning Bolt,1\n"
                resp.raise_for_status = MagicMock()
            return resp

        mock_session = MagicMock()
        mock_session.get.side_effect = side_effect

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out_file = tmp_path / "regular.csv"
        assert out_file.exists()

    def test_403_falls_back_to_curl(self, tmp_path: Path):
        """Every client identity refused (403): the curl fallback is tried."""
        runner = CliRunner()
        mock_session = MagicMock()
        resp_403 = MagicMock(status_code=403)
        mock_session.get.return_value = resp_403

        curl_payload = json.dumps(
            {
                "shortID": "regular",
                "name": "Regular",
                "mainboard": [],
                "maybeboard": [],
            }
        )

        with (
            patch(
                "mtg_utils.cubecobra_fetch.requests.Session",
                return_value=mock_session,
            ),
            patch(
                "mtg_utils.cubecobra_fetch._fetch_with_curl",
                return_value=curl_payload,
            ),
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out_file = tmp_path / "regular.json"
        assert out_file.exists()

    def test_asks_as_its_own_client_first(self, tmp_path: Path):
        """The first request carries the tool's own User-Agent; a refusal
        (403) moves on to browser headers before curl is tried."""
        runner = CliRunner()
        mock_session = MagicMock()
        ok = MagicMock(status_code=200, text=json.dumps({"name": "Regular"}))
        ok.raise_for_status = MagicMock()
        mock_session.get.side_effect = [MagicMock(status_code=403), ok]

        with (
            patch(
                "mtg_utils.cubecobra_fetch.requests.Session",
                return_value=mock_session,
            ),
            patch("mtg_utils.cubecobra_fetch._fetch_with_curl") as curl,
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        agents = [
            call.kwargs["headers"]["User-Agent"]
            for call in mock_session.get.call_args_list
        ]
        assert agents == [USER_AGENT, BROWSER_HEADERS["User-Agent"]]
        curl.assert_not_called()

    def test_a_refusal_is_not_called_a_missing_cube(self, tmp_path: Path):
        """Every identity refused, and curl handed the 403 page: the error
        says CubeCobra refused, since the cube may well exist."""
        runner = CliRunner()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(status_code=403)

        with (
            patch(
                "mtg_utils.cubecobra_fetch.requests.Session",
                return_value=mock_session,
            ),
            patch(
                "mtg_utils.cubecobra_fetch._fetch_with_curl",
                return_value="<!DOCTYPE html><html><body>Forbidden</body></html>",
            ),
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        errors = (result.stderr_bytes or b"").decode(errors="ignore") + result.output
        assert "refused the request (HTTP 403)" in errors
        assert "not found" not in errors

    def test_a_404_is_a_missing_cube(self, tmp_path: Path):
        runner = CliRunner()
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(
            status_code=404, text="Cube not found."
        )

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["bogus", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        errors = (result.stderr_bytes or b"").decode(errors="ignore") + result.output
        assert "no such cube (HTTP 404)" in errors

    def test_summary_counts_v2_shape(self, tmp_path: Path):
        """CubeCobra v2 nests mainboard under `cards`; the summary line must
        read from `cards.mainboard` not `mainboard` or report 0."""
        runner = CliRunner()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(
            {
                "shortId": "regular",
                "name": "Regular Cube",
                "description": "My unpowered cube",
                "cardCount": 3,
                "cards": {
                    "mainboard": [
                        {"cardID": "a", "name": "Lightning Bolt"},
                        {"cardID": "b", "name": "Counterspell"},
                        {"cardID": "c", "name": "Dark Ritual"},
                    ],
                    "maybeboard": [],
                },
            }
        )
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "3 mainboard cards" in result.output

    def test_rejects_html_404_with_200_status(self, tmp_path: Path):
        """CubeCobra returns HTML 404 pages with HTTP 200 for missing IDs.

        Without explicit detection, the fallback would write the error shell
        as the 'result'. The _fetch_text helper rejects anything starting
        with <!doctype / <html; we assert end-to-end that this propagates.
        """
        runner = CliRunner()
        mock_session = MagicMock()
        resp = MagicMock(
            status_code=200,
            text="<!DOCTYPE html><html><body>404 not found</body></html>",
        )
        resp.raise_for_status = MagicMock()
        mock_session.get.return_value = resp

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["bogus", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert not (tmp_path / "bogus.json").exists()
        assert not (tmp_path / "bogus.csv").exists()

    def test_all_endpoints_fail(self, tmp_path: Path):
        runner = CliRunner()
        mock_session = MagicMock()
        resp_500 = MagicMock(status_code=500)
        resp_500.raise_for_status.side_effect = Exception("500 error")
        mock_session.get.return_value = resp_500

        with patch(
            "mtg_utils.cubecobra_fetch.requests.Session", return_value=mock_session
        ):
            result = runner.invoke(main, ["regular", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert (
            "could not fetch" in result.output.lower()
            or "could not fetch"
            in (result.stderr_bytes or b"").decode(errors="ignore").lower()
        )
