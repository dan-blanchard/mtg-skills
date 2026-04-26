"""Smoke test: playtest-goldfish CLI is registered and prints --help."""

from click.testing import CliRunner

from mtg_utils.playtest import _keep_hand, goldfish_main


def test_goldfish_help():
    runner = CliRunner()
    result = runner.invoke(goldfish_main, ["--help"])
    assert result.exit_code == 0
    assert "simulator" in result.output.lower()


def _h(land=0, one=0, two=0, three=0, four=0, five_plus=0):
    """Build a synthetic hand: list of dicts with cmc and is_land flag."""
    hand = []
    for _ in range(land):
        hand.append({"cmc": 0, "is_land": True})
    for cmc, n in [(1, one), (2, two), (3, three), (4, four), (5, five_plus)]:
        for _ in range(n):
            hand.append({"cmc": cmc, "is_land": False})
    return hand


class TestKeepHand:
    def test_keeps_2_lands_with_early_plays(self):
        hand = _h(land=2, one=2, two=2, three=1)
        assert _keep_hand(hand) is True

    def test_mulligans_zero_lands(self):
        hand = _h(land=0, one=3, two=3, three=1)
        assert _keep_hand(hand) is False

    def test_mulligans_six_lands(self):
        hand = _h(land=6, one=1)
        assert _keep_hand(hand) is False

    def test_mulligans_no_early_plays(self):
        hand = _h(land=3, four=2, five_plus=2)
        assert _keep_hand(hand) is False

    def test_keeps_three_lands_with_curve(self):
        hand = _h(land=3, one=1, two=1, three=1, four=1)
        assert _keep_hand(hand) is True
