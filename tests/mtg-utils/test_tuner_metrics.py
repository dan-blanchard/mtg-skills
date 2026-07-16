"""Tuner Tier-2 metrics: win-condition heuristic detection (grill F6)."""

from mtg_utils._tuner.metrics import _ir_wincon, _is_wincon_card, top_issues
from mtg_utils.card_ir import Ability, Card, Effect, Face


def _ir(*effects):
    return Card(
        oracle_id="x",
        name="T",
        faces=(Face(name="T", abilities=(Ability(kind="spell", effects=effects),)),),
    )


def test_ir_wincon_reads_win_lose_game_structurally():
    # The IR encodes alt-wins natively: cat=win_game (Felidar Sovereign) and a
    # cat=lose_game forcing a non-self player to lose (Door to Nothingness). A
    # cat=lose_game scope="you" is the Pact-of-Negation self-loss drawback — NOT a closer.
    assert _ir_wincon(_ir(Effect(category="win_game", scope="you"))) is True
    assert _ir_wincon(_ir(Effect(category="lose_game", scope="any"))) is True
    assert _ir_wincon(_ir(Effect(category="lose_game", scope="you"))) is False
    assert _ir_wincon(_ir(Effect(category="counter_spell", scope="any"))) is False


def _card(name, oracle, type_line="Instant", power=None):
    rec = {"name": name, "oracle_text": oracle, "type_line": type_line}
    if power is not None:
        rec["power"] = power
    return rec


def test_self_loss_drawback_is_not_a_wincon():
    # A self-loss drawback ("you lose the game") is the opposite of a finisher (CR 104.3e
    # — a player losing is a drawback to its controller). Pact of Negation is a free
    # counter, not a closer; the subjectless r"loses? the game" wrongly counted it.
    pact = _card(
        "Pact of Negation",
        "Counter target spell. At the beginning of your next upkeep, pay {3}{U}{U}. "
        "If you don't, you lose the game.",
    )
    assert _is_wincon_card(pact) is False


def test_platinum_angel_self_protection_is_not_a_wincon():
    angel = _card(
        "Platinum Angel",
        "You can't lose the game and your opponents can't win the game.",
        type_line="Artifact Creature — Angel",
        power="4",
    )
    assert _is_wincon_card(angel) is False


def test_opponent_loses_the_game_is_a_wincon():
    # A genuine alt-win makes an OPPONENT lose (CR 104.3e). Still detected.
    lab = _card(
        "Mortal Combat",
        "At the beginning of your upkeep, if there are twenty or more creature cards "
        "in your graveyard, target opponent loses the game.",
        type_line="Enchantment",
    )
    assert _is_wincon_card(lab) is True


def test_scaling_group_drain_is_a_wincon():
    # Yuriko's printed base drain is the deck's archetypal finisher and was uncounted —
    # the pattern list had the burn analog ("damage to each opponent equal") but no
    # life-loss sibling. Not trigger-multiplication (no commander doubler involved).
    yuriko = _card(
        "Yuriko, the Tiger's Shadow",
        "Whenever a Ninja you control deals combat damage to a player, reveal the top "
        "card of your library and put that card into your hand. Each opponent loses "
        "life equal to that card's mana value.",
        type_line="Legendary Creature — Human Ninja",
        power="1",
    )
    assert _is_wincon_card(yuriko) is True


def test_small_fixed_pinger_is_not_a_group_drain_wincon():
    # A 1-life incidental drip is not a finisher — keep the drain pattern scaling-scoped.
    blood_artist = _card(
        "Blood Artist",
        "Whenever Blood Artist or another creature dies, target player loses 1 life "
        "and you gain 1 life.",
        type_line="Creature — Vampire",
        power="0",
    )
    assert _is_wincon_card(blood_artist) is False


def test_closer_grant_counts_as_one_wincon():
    # ADR-0040 §5 (task #100): a Granter granting a closer-grade ability
    # (team double strike) is ONE closer regardless of recipient count — the
    # benchmark read "2 closers" while holding Bonescythe-class team double
    # strike twice. ADR-0024 advisory semantics unchanged; only the count
    # gets honest.
    from mtg_utils._tuner.classify import CardClass
    from mtg_utils._tuner.metrics import win_conditions

    def cc(name, closer):
        return CardClass(
            name=name,
            bucket="engine",
            roles=(),
            served=("Slivers",),
            dual_purpose=False,
            cmc=4.0,
            record={"name": name, "oracle_text": "", "type_line": "Creature"},
            grant_closer=closer,
        )

    classes = [
        cc("Team Double Strike", closer=True),
        cc("Team Vigilance", closer=False),
    ]
    wins = win_conditions(classes, shape="midrange", combo_count=0)
    assert "Team Double Strike" in wins["cards"]
    assert "Team Vigilance" not in wins["cards"]


def _band(current, lo, hi, **extra):
    dev = current - hi if current > hi else (current - lo if current < lo else 0)
    return {
        "current": current,
        "min": lo,
        "max": hi,
        "target": hi,
        "remaining": max(0, lo - current),
        "deviation": dev,
        **extra,
    }


_ISSUES_BASE = {
    "efficiency_r": {"verdict": "ok"},
    "focus_r": {
        "filler": 0,
        "viable_avenues": [],
        "emerging": [],
        "verdict": "FOCUSED",
        "stranded_avenues": [],
    },
    "wincons_r": {"status": "ok"},
    "protection_r": {"status": "ok"},
    "commander_r": {"misfit": False},
}


def test_grant_covered_role_short_is_advisory_but_still_shows_the_literal_number():
    # ADR-0040 §1: a grant-covered role's shortfall stays in the scorecard with its
    # real numbers (never suppressed) but is flagged advisory — the swap engine must
    # not source fills for it (verified separately in test_tuner_swaps.py).
    template_r = {
        "short": {
            "card_draw": _band(
                0, 10, 12, grant_covered=True, grant_covered_by="Sliver Weftwinder"
            ),
            "ramp": _band(2, 10, 12),  # short too, but NOT grant-covered
        },
        "over": {},
    }
    issues = top_issues(template_r=template_r, **_ISSUES_BASE)
    by_role = {i["role"]: i for i in issues if i["kind"] == "role_short"}
    draw_issue = by_role["card_draw"]
    assert draw_issue["advisory"] is True
    assert draw_issue["grant_covered"] is True
    assert "Sliver Weftwinder" in draw_issue["message"]
    # The literal deficit is untouched — short by 10 (0/10-12), not suppressed to 0.
    assert draw_issue["severity"] == 10
    # A short role with no grant coverage stays a normal actionable issue.
    ramp_issue = by_role["ramp"]
    assert ramp_issue.get("advisory", False) is False
    assert ramp_issue.get("grant_covered", False) is False
