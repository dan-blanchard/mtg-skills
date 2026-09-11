"""Tests for the USD->AUD conversion helper."""

from mtg_utils.fx import DEFAULT_AUD_PER_USD, aud_per_usd, usd_to_aud


class TestAudPerUsd:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("MTG_SKILLS_AUD_PER_USD", raising=False)
        assert aud_per_usd() == DEFAULT_AUD_PER_USD

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MTG_SKILLS_AUD_PER_USD", "2.0")
        assert aud_per_usd() == 2.0

    def test_invalid_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("MTG_SKILLS_AUD_PER_USD", "not-a-number")
        assert aud_per_usd() == DEFAULT_AUD_PER_USD

    def test_nonpositive_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("MTG_SKILLS_AUD_PER_USD", "-1")
        assert aud_per_usd() == DEFAULT_AUD_PER_USD


class TestUsdToAud:
    def test_none_passthrough(self):
        assert usd_to_aud(None) is None

    def test_converts_with_explicit_rate(self):
        assert usd_to_aud(10.0, rate=1.5) == 15.0

    def test_rounds_to_cents(self):
        assert usd_to_aud(1.23, rate=1.523) == 1.87

    def test_uses_env_rate_when_no_explicit(self, monkeypatch):
        monkeypatch.setenv("MTG_SKILLS_AUD_PER_USD", "2.0")
        assert usd_to_aud(5.0) == 10.0
