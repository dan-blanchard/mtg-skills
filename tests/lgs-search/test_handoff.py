from __future__ import annotations

from unittest.mock import MagicMock

from mtg_utils.lgs_search import handoff_to_browsers


def test_handoff_calls_open_handoff_per_target():
    a = MagicMock()
    b = MagicMock()
    handoff_to_browsers(
        [
            ("tgp", a, "/tmp/profile-tgp"),
            ("manapool", b, "/tmp/profile-mp"),
        ]
    )
    a.open_handoff.assert_called_once_with("/tmp/profile-tgp")
    b.open_handoff.assert_called_once_with("/tmp/profile-mp")


def test_handoff_skips_when_targets_empty():
    handoff_to_browsers([])  # Should not raise
