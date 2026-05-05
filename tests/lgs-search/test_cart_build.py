from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mtg_utils.lgs_search import (
    CartPollutionError,
    check_carts_empty,
    confirm_proceed,
)


def test_confirm_y_proceeds(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert confirm_proceed("dummy", yes=False) is True


def test_confirm_n_aborts(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    assert confirm_proceed("dummy", yes=False) is False


def test_confirm_default_n_on_blank(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert confirm_proceed("dummy", yes=False) is False


def test_yes_flag_skips_prompt(monkeypatch):
    called = []
    monkeypatch.setattr("builtins.input", lambda _: called.append(True) or "n")
    assert confirm_proceed("dummy", yes=True) is True
    assert called == []


def test_check_carts_empty_passes_when_all_empty():
    a = MagicMock()
    a.get_existing_cart.return_value = []
    b = MagicMock()
    b.get_existing_cart.return_value = []
    check_carts_empty([("tgp", a, "page-a"), ("ae", b, "page-b")])


def test_check_carts_empty_raises_on_pollution():
    a = MagicMock()
    a.get_existing_cart.return_value = []
    b = MagicMock()
    b.get_existing_cart.return_value = [{"card_name": "X"}]
    with pytest.raises(CartPollutionError) as exc:
        check_carts_empty([("tgp", a, None), ("ae", b, None)])
    assert "ae" in str(exc.value)
