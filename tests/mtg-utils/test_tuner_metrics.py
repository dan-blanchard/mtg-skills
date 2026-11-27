"""Tuner Tier-2 metrics: win-condition heuristic detection (grill F6)."""

from dataclasses import replace

import pytest

from mtg_utils._tuner.calibration import (
    COMMANDER,
    CONSTRUCTED,
    LIMITED,
    LIMITED_CLOSER_FLOOR,
    LIMITED_CLOSER_TOP,
)
from mtg_utils._tuner.issues import Sourcing, top_issues
from mtg_utils._tuner.metrics import (
    closer_read,
    is_limited_closer,
    is_wincon_card,
    limited_closer_reason,
)
from mtg_utils.formats import FORMATS, Game
from mtg_utils.testkit import test_card


def _top_issues_for(*, focus_r, template_r, **metrics):
    """``issues.top_issues`` over the budgets the template rows came from."""
    budgets = {**template_r["short"], **template_r["over"]}
    return top_issues(
        focus_r=focus_r,
        template_r=template_r,
        sourcing=Sourcing(focus_r, [], budgets),
        **metrics,
    )


@pytest.mark.parametrize(
    ("name", "closer"),
    [
        # Game wins off the tree's WinTheGame / LoseTheGame player scope.
        ("Felidar Sovereign", True),  # you win (CR 104.2b)
        ("Phage the Untouchable", True),  # that player loses (CR 104.3e)
        # Extra combat (the extra_combats key).
        ("Aggravated Assault", True),
        # One-shot team pumps (Dan's call: "+N" closers): the team_boost_or_grant grant from a
        # spell or trigger that also adds power.
        ("Overrun", True),
        ("Craterhoof Behemoth", True),
        ("Triumph of the Hordes", True),
        # Static anthems are board presence, and a one-shot grant with no pump is
        # a trick.
        ("Glorious Anthem", False),
        ("Akroma's Memorial", False),
        ("Azorius Charm", False),
        # "Infinite" in a name reads no mechanic.
        ("Tome of the Infinite", False),
    ],
)
def test_closer_reads(name, closer):
    assert is_wincon_card(test_card(name)) is closer


def test_a_body_that_hurts_its_controller_is_not_a_wincon():
    """Inverter of Truth is a 6/6 flier whose enter trigger exiles your library:
    a drawback the read charges to you, so it closes nothing (Eldrazi
    Incursion took it as a closer, 2026-11-02)."""
    assert is_wincon_card(test_card("Inverter of Truth")) is False


def test_self_loss_drawback_is_not_a_wincon():
    # A self-loss drawback ("you lose the game") is the opposite of a finisher (CR 104.3e
    # — a player losing is a drawback to its controller). Pact of Negation is a free
    # counter, not a closer; the subjectless r"loses? the game" wrongly counted it.
    pact = test_card("Pact of Negation")
    assert is_wincon_card(pact) is False


def test_platinum_angel_self_protection_is_not_a_wincon():
    # Real Platinum Angel: a 4-power flier, below the 40-life evasive-body bar.
    angel = test_card("Platinum Angel")
    assert is_wincon_card(angel) is False


def test_opponent_loses_the_game_is_a_wincon():
    # A genuine alt-win makes an OPPONENT lose (CR 104.3e). Still detected. Door to
    # Nothingness: "Target player loses the game." (Mortal Combat wins the game
    # instead, the other pattern.)
    door = test_card("Door to Nothingness")
    assert is_wincon_card(door) is True


def test_scaling_group_drain_is_a_wincon():
    # Yuriko's printed base drain is the deck's archetypal finisher and was uncounted —
    # the pattern list had the burn analog ("damage to each opponent equal") but no
    # life-loss sibling. Not trigger-multiplication (no commander doubler involved).
    yuriko = test_card("Yuriko, the Tiger's Shadow")
    assert is_wincon_card(yuriko) is True


def test_small_fixed_pinger_is_not_a_group_drain_wincon():
    # A 1-life incidental drip is not a finisher — keep the drain pattern scaling-scoped.
    blood_artist = test_card("Blood Artist")
    assert is_wincon_card(blood_artist) is False


def _cc(name, record, **kw):
    from mtg_utils._tuner.classify import CardClass

    return CardClass(
        name=name,
        bucket="engine",
        roles=(),
        served=(),
        dual_purpose=False,
        cmc=float(record.get("cmc", 3.0)),
        record=record,
        **kw,
    )


def test_closer_grant_counts_as_one_wincon():
    # ADR-0040 §5 (task #100): a Granter granting a closer-grade ability
    # (team double strike) is ONE closer regardless of recipient count — the
    # benchmark read "2 closers" while holding Bonescythe-class team double
    # strike twice. ADR-0024 advisory semantics unchanged; only the count
    # gets honest.
    from mtg_utils._tuner.metrics import win_conditions

    def rec(name):
        return {"name": name, "oracle_text": "", "type_line": "Creature"}

    classes = [
        _cc("Team Double Strike", rec("Team Double Strike"), grant_closer=True),
        _cc("Team Vigilance", rec("Team Vigilance"), grant_closer=False),
    ]
    wins = win_conditions(classes, shape="midrange", combo_count=0)
    assert "Team Double Strike" in wins["cards"]
    assert "Team Vigilance" not in wins["cards"]


DUEL_25 = Game(medium="digital", life=25, multiplayer=False, commander_damage=False)
POD_30 = Game(medium="paper", life=30, multiplayer=True, commander_damage=True)


class TestClosersReadTheGame:
    """The closer read is relative to the Game (``Format.game``): an evasive body
    that closes at 25 life one-on-one is not a closer at a 40-life pod, fixed reach
    counts when one hit takes 12% of starting life, and single-target reach is a
    finisher only against one opponent."""

    def test_evasive_body_threshold_scales_with_life(self):
        flyer = test_card("Serra Angel")  # 4-power flier
        assert is_wincon_card(flyer) is False  # 40 life: needs 6 power
        assert is_wincon_card(flyer, game=DUEL_25) is True  # 25 life: 4 power
        five = test_card("Shivan Dragon")  # 5-power flier
        assert is_wincon_card(five, game=POD_30) is True  # 30 life: 5 power

    def test_evasion_reads_keywords_and_blocking_restrictions(self):
        # Landwalk is evasion (CR 702.14c), as is a restriction on what can block
        # the creature (509.1b). Reach is not, though its reminder text says
        # "flying" — the old substring scan counted Arbor Colossus.
        assert is_wincon_card(test_card("Stormtide Leviathan")) is True  # islandwalk
        assert is_wincon_card(test_card("Pathrazer of Ulamog")) is True
        assert is_wincon_card(test_card("Arbor Colossus")) is False

    def test_an_adventurer_is_read_off_its_faces(self):
        # A two-face record carries its text on the faces, not on the record:
        # Bloomvine Regent is a 4/5 flier whose record has no oracle_text.
        regent = test_card("Bloomvine Regent // Claim Territory")
        assert not regent.get("oracle_text")
        assert is_wincon_card(regent, game=DUEL_25) is True

    def test_fixed_group_reach_scales_with_life(self):
        # 3 damage to each opponent is 7.5% of a Commander life total and 12% of a
        # Brawl one — a closer at 25, not at 40; 5 clears the 40-life bar.
        three = test_card("Sizzle")  # "deals 3 damage to each opponent"
        five = test_card("Breath of Malfegor")  # "deals 5 damage to each opponent"
        assert is_wincon_card(three) is False
        assert is_wincon_card(three, game=DUEL_25) is True
        assert is_wincon_card(five) is True

    def test_fixed_single_target_reach_closes_only_when_lethal(self):
        # A fixed bolt is removal, not a finisher, even one-on-one at 25 life —
        # otherwise every Lightning Bolt in an Arena Brawl deck would count. A
        # single hit that is the whole starting life is a closer one-on-one.
        bolt = test_card("Lightning Bolt")
        axe = test_card("Lava Axe")  # 5 damage to target player
        reservoir = test_card("Aetherflux Reservoir")  # 50 damage to any target
        assert is_wincon_card(bolt, game=DUEL_25) is False
        assert is_wincon_card(axe, game=DUEL_25) is False
        assert is_wincon_card(reservoir, game=DUEL_25) is True
        assert is_wincon_card(reservoir) is False  # single-target: not a pod closer

    def test_repeated_and_symmetric_reach(self):
        # Torment of Hailfire's 3 life repeats X times: it scales. Earthquake hits
        # every player, you too, so it is neither scope.
        assert is_wincon_card(test_card("Torment of Hailfire")) is True
        assert is_wincon_card(test_card("Earthquake"), game=DUEL_25) is False

    def test_an_x_phase_parks_still_reaches(self):
        # Insatiable Hemophage: "each opponent loses X life", X its mutate count;
        # Zenith Flare: "deals X damage to any target". Phase parks both X effects
        # (see reads.unbound_x_reach); group reach counts at a pod, single only
        # one-on-one.
        assert is_wincon_card(test_card("Insatiable Hemophage")) is True
        flare = test_card("Zenith Flare")
        assert is_wincon_card(flare) is False
        assert is_wincon_card(flare, game=DUEL_25) is True

    def test_single_target_scaling_reach_counts_only_one_on_one(self):
        # Blaze: "deals X damage to any target" (Fireball divides its X among
        # any number of targets, a different shape). Essence Harvest: "Target
        # player loses X life".
        blaze = test_card("Blaze")
        drain = test_card("Essence Harvest")
        assert is_wincon_card(blaze) is False
        assert is_wincon_card(blaze, game=DUEL_25) is True
        assert is_wincon_card(drain, game=DUEL_25) is True
        # Group scaling reach counts at any table (unchanged).
        exsanguinate = test_card("Exsanguinate")
        assert is_wincon_card(exsanguinate) is True

    def test_closer_band_scales_with_life(self):
        from mtg_utils._tuner.metrics import win_conditions

        classes = [
            _cc("Blank", {"name": "Blank", "oracle_text": "", "type_line": "Sorcery"})
        ]
        pod = win_conditions(classes, shape="aggro", combo_count=0)
        duel = win_conditions(classes, shape="aggro", combo_count=0, game=DUEL_25)
        assert pod["target"] == [4, 6]
        # 4 x 25/40 = 2.5 and 6 x 25/40 = 3.75, rounded as _scaled rounds.
        assert duel["target"] == [2, 4]
        assert duel["multiplayer"] is False
        assert duel["life"] == 25
        # The band keeps a card of width at low life: control's (2, 4) would round to
        # (2, 2) at 25, so hi is held at lo + 1.
        control = win_conditions(classes, shape="control", combo_count=0, game=DUEL_25)
        assert control["target"] == [2, 3]
        combo = win_conditions(classes, shape="combo", combo_count=0, game=DUEL_25)
        assert combo["target"] == [2, 3]

    def test_voltron_is_a_closer_only_where_commander_damage_wins(self):
        from mtg_utils._tuner.metrics import win_conditions

        equips = [
            _cc(
                f"Sword {i}",
                {
                    "name": f"Sword {i}",
                    "oracle_text": "Equip {2}",
                    "type_line": "Artifact — Equipment",
                    "keywords": ["Equip"],
                },
            )
            for i in range(4)
        ]
        commander = win_conditions(equips, shape="midrange", combo_count=0)
        assert commander["voltron"] is True
        assert commander["voltron_commander_damage"] is True
        assert commander["count"] == 1  # the 21-damage plan (CR 903.10a) is a closer
        # The synthetic closer is its pieces — what the cut-protection floor keeps.
        assert commander["voltron_cards"] == [f"Sword {i}" for i in range(4)]
        brawl = win_conditions(equips, shape="midrange", combo_count=0, game=DUEL_25)
        assert brawl["voltron_commander_damage"] is False
        assert brawl["voltron_needs_real_damage"] is True
        assert brawl["voltron_cards"] == []
        assert brawl["count"] == 0

    def test_voltron_without_commander_damage_surfaces_as_an_advisory(self):
        wins = {
            "status": "ok",
            "count": 3,
            "target": [2, 4],
            "life": 25,
            "voltron_needs_real_damage": True,
        }
        issues = _top_issues_for(
            efficiency_r={"verdict": "ok"},
            focus_r={
                "verdict": "FOCUSED",
                "filler": 0,
                "low_value": 0,
                "viable_avenues": [],
                "stranded_avenues": [],
                "emerging": [],
            },
            template_r={"short": {}, "over": {}},
            wincons_r=wins,
            protection_r={"status": "ok"},
            commander_r={"misfit": False},
        )
        [issue] = [i for i in issues if i.kind == "voltron_no_commander_damage"]
        assert issue.advisory is True
        assert issue.remedy is None  # no swap fixes a plan
        assert "full 25 life" in issue.message


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
    issues = _top_issues_for(template_r=template_r, **_ISSUES_BASE)
    by_role = {i.role: i.to_json() for i in issues if i.kind == "role_short"}
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


def test_commander_holding_a_viable_avenue_is_never_a_misfit():
    from mtg_utils._tuner.classify import CardClass
    from mtg_utils._tuner.metrics import commander_fit

    def cc(name, bucket, served):
        return CardClass(
            name=name,
            bucket=bucket,
            roles=(),
            served=tuple(served),
            dual_purpose=False,
            cmc=2.0,
            record={"name": name},
        )

    classes = [cc("Polymorph Cmdr", "commander", ["Cheat into play"])]
    rows = [
        {"label": lbl, "depth": 20, "carers": 6, "cards": [], "tier": "main"}
        for lbl in ("Cheat into play", "Go wide", "Spellslinger", "Artifacts")
    ]
    held = commander_fit(
        classes,
        {"viable_avenues": rows, "commander_avenues": ["Cheat into play"]},
    )
    assert held["fit"] == 0.25
    assert held["misfit"] is False
    # The same numbers with the commander holding none of the lanes.
    stranger = commander_fit(
        [cc("Tribal Cmdr", "commander", ["Goblin tribal"])],
        {"viable_avenues": rows, "commander_avenues": []},
    )
    assert stranger["misfit"] is True


def test_a_bare_tokens_payoff_cares_about_predefined_token_makers():
    """Deep Clue Sea: Adrix and Nev (a token doubler) and Esix care about the
    deck's twenty Clue makers — a Clue is a token (CR 111.10f) — not only about
    the creature-token makers ``token_maker`` spells."""
    from mtg_utils._analysis.lanes import TOKEN_SUBTYPE_PAYOFF_KEYS
    from mtg_utils._tuner.metrics import _cares_keys

    # One table: every token doer — creature tokens and each predefined kind —
    # is cared about by a tokens payoff and a doubler alike (Doubling Season
    # cares about Soldier makers as it does about Clue makers).
    for doer in ("token_maker", *(f"{k}_makers" for k in TOKEN_SUBTYPE_PAYOFF_KEYS)):
        assert {"tokens_matter", "token_doubling"} <= set(_cares_keys(doer)), doer
    # The kind's own payoff stays first; only creature tokens are polymorph fodder.
    assert _cares_keys("clue_makers")[0] == "clue_matters"
    assert "wants_fodder" in _cares_keys("token_maker")
    assert "wants_fodder" not in _cares_keys("treasure_makers")
    assert "tokens_matter" not in _cares_keys("lifegain_makers")


def test_an_activated_ability_is_a_payoff_target_not_a_builder():
    """Abzan Armor: eleven cards with an activated ability made "Activated-ability
    engine" the main over a forty-two-deep toughness lane. The lane's builders
    are the untap engines its spec names, never the cards that merely have an
    ability."""
    from mtg_utils._tuner.metrics import _cares_keys

    assert _cares_keys("activated_ability") == ("untap_engine",)


class TestPoisonClosers:
    """Ten poison counters lose the game whatever the life total (CR 704.5c,
    122.1f), so in a deck that poisons a poison giver is a closer: infect
    (702.90b), toxic (702.164c), poisonous (702.70a) and a direct "gets N
    poison counters". Proliferate adds a counter of each kind a player has
    (701.34a): a closer only where the deck poisons, and so is a lone poison
    giver — one infect flier is no clock (Viral Drake, 2026-11-02)."""

    @pytest.mark.parametrize(
        "name",
        [
            "Fynn, the Fangbearer",  # "that player gets two poison counters"
            "Venerated Rotpriest",  # a target trigger gives a poison counter
            "Glistener Elf",  # infect
            "Bilious Skulldweller",  # toxic
            "Marsh Viper",  # damage to a player gives two poison counters
            "Inkmoth Nexus",  # a land that becomes an infect creature
        ],
    )
    def test_a_poison_giver_is_a_closer_where_the_deck_poisons(self, name):
        assert is_wincon_card(test_card(name), poisons=True) is True
        assert is_wincon_card(test_card(name), game=DUEL_25, poisons=True) is True

    def test_a_lone_poison_giver_is_judged_as_any_card(self):
        assert is_wincon_card(test_card("Viral Drake")) is False
        assert is_wincon_card(test_card("Glistener Elf")) is False
        # a one-shot team pump closes whatever the deck: infect and +1/+1
        assert is_wincon_card(test_card("Triumph of the Hordes")) is True

    def test_proliferate_closes_only_where_the_deck_poisons(self):
        clasp = test_card("Contagion Clasp")
        assert is_wincon_card(clasp) is False
        assert is_wincon_card(clasp, poisons=True) is True

    def test_win_conditions_reads_the_deck_for_poison(self):
        from mtg_utils._tuner.metrics import win_conditions

        fynn = _cc("Fynn, the Fangbearer", test_card("Fynn, the Fangbearer"))
        clasp = _cc("Contagion Clasp", test_card("Contagion Clasp"))
        wins = win_conditions([fynn, clasp], shape="aggro", combo_count=0)
        assert wins["poisons"] is True
        assert wins["cards"] == ["Contagion Clasp", "Fynn, the Fangbearer"]
        alone = win_conditions([clasp], shape="aggro", combo_count=0)
        assert alone["poisons"] is False
        assert alone["cards"] == []


# ── Limited closers (ADR-0055's 2026-11-25 amendment, Dan's ruling) ────────────

DRAFT = FORMATS["draft"].game("digital")


class TestLimitedClosers:
    """A sealed or draft closer is a threat that's hard to block or hard to
    answer, read off the card's keywords and parse."""

    @pytest.mark.parametrize(
        ("name", "reason"),
        [
            # Protection from the chosen player (CR 702.16k): it can't be blocked,
            # targeted or damaged by that player's things.
            ("True-Name Nemesis", "resilient"),
            # A 4/4 flier.
            ("Serra Angel", "evasive"),
            # "Can't be blocked by creatures with power 2 or less" (CR 509.1b).
            ("Rust-Shield Rampager", "evasive"),
            # Persist brings it back to the battlefield.
            ("Kitchen Finks", "resilient"),
            # Trample on a big body: exactly power 4, and a 6/6.
            ("Gnarlback Rhino", "evasive"),
            ("Colossal Dreadmaw", "evasive"),
            # A conditional self-grant that is simply on when its condition holds.
            ("Waterspout Warden", "evasive"),
            # Its enters trigger's "discard your hand" is paid once; then a 5/5
            # menace while its hand is small.
            ("Carnage Interpreter", "evasive"),
            # A 2/1 menace that endures 2 as it enters (CR 701.63a).
            ("Sandskitter Outrider", "evasive"),
            # A double-faced card's power is its front face's: a 7/7 trampler.
            ("Etali, Primal Conqueror", "evasive"),
            # Noncreature engines: an upkeep token, a zero loyalty ability's 2/2,
            # a plus ability's 2 damage to each opponent.
            ("Bitterblossom", "creature_engine"),
            ("Gideon, Ally of Zendikar", "creature_engine"),
            ("Chandra, Torch of Defiance", "repeat_reach"),
            # What closes in a 40-card deck still closes.
            ("Overrun", "finisher"),
        ],
    )
    def test_threats_that_count(self, name, reason):
        assert limited_closer_reason(test_card(name), game=DRAFT) == reason
        assert is_limited_closer(test_card(name), game=DRAFT) is True

    @pytest.mark.parametrize(
        "name",
        [
            # Evasive, but too small to end a 20-life game: power under 3.
            "Wind Drake",
            "Phantom Warrior",
            # Trample on a 3-power body is no evasion.
            "Garruk's Companion",
            # "Can't be blocked by more than one creature": any one blocks it.
            "Charging Rhino",
            # Big but blockable and answerable; vanilla.
            "Craw Wurm",
            "Grizzly Bears",
            # A creature that makes tokens or pings is judged by its body.
            "Young Pyromancer",
            "Prodigal Sorcerer",
            # A noncreature source of one damage at a time.
            "Goblin Bombardment",
            # Can't close: decayed (CR 702.147a), defender (CR 702.3b).
            "Rot-Curse Rakshasa",
            "Wall of Swords",
            # Indestructible only on a turn it pays for (expend 4).
            "Bark-Knuckle Boxer",
            # Back to hand at a cost: removal still buys a turn.
            "Furious Forebear",
            # Planeswalkers: a plus ability's 0/1 Plant; a minus ability's token
            # and a minus ultimate's emblem.
            "Nissa, Voice of Zendikar",
            "The Wandering Emperor",
            "Ajani, Adversary of Tyrants",
            # An alternative win a 40-card deck doesn't reach.
            "Thassa's Oracle",
        ],
    )
    def test_threats_that_do_not(self, name):
        assert limited_closer_reason(test_card(name), game=DRAFT) is None

    @pytest.mark.parametrize(
        ("name", "at_20", "at_40"),
        [
            # The Commander-shaped finisher read: no resilience, no engines,
            # trample on any body past its life-scaled power floor (3 at 20 life,
            # 6 at the 40-life pod), an alternative win, and its enters costs
            # still hold a body back (Inverter of Truth, Carnage Interpreter).
            ("True-Name Nemesis", False, False),
            ("Kitchen Finks", False, False),
            ("Bitterblossom", False, False),
            ("Chandra, Torch of Defiance", False, False),
            ("Garruk's Companion", True, False),
            ("Serra Angel", True, False),
            ("Colossal Dreadmaw", True, True),
            ("Wind Drake", False, False),
            ("Grizzly Bears", False, False),
            ("Thassa's Oracle", True, True),
            ("Inverter of Truth", False, False),
            ("Carnage Interpreter", False, False),
            # The shared blocking-restriction read and the front face's power.
            ("Rust-Shield Rampager", True, False),
            ("Etali, Primal Conqueror", True, True),
        ],
    )
    def test_the_finisher_read(self, name, at_20, at_40):
        assert is_wincon_card(test_card(name), game=DRAFT) is at_20
        assert is_wincon_card(test_card(name)) is at_40

    def test_a_leveler_is_read_at_its_first_level(self):
        """Level up (CR 711.2a): Hexdrinker's first level, 4/4 with protection
        from instants, makes it a resilient body; its later level is not
        credited."""
        from mtg_utils._card_ir.trees import trees_for
        from mtg_utils._tuner.metrics import _grown_base

        card = test_card("Hexdrinker")
        assert _grown_base(card, trees_for(card)) == (4, frozenset({"protection"}))
        assert limited_closer_reason(card, game=DRAFT) == "resilient"

    def test_a_power_counting_your_creatures_is_read_at_a_board_of_three(self):
        """Adeline, Resplendent Cathar's power counts the creatures you control
        (a characteristic-defining ability, CR 604.3), credited at
        ``LIMITED_BOARD_CREATURES``. Her power is three, but vigilance makes her
        neither hard to block nor hard to answer, so she is no closer."""
        from mtg_utils._card_ir.trees import trees_for
        from mtg_utils._tuner.metrics import LIMITED_BOARD_CREATURES, _grown_base

        card = test_card("Adeline, Resplendent Cathar")
        assert _grown_base(card, trees_for(card)) == (
            LIMITED_BOARD_CREATURES,
            frozenset(),
        )
        assert limited_closer_reason(card, game=DRAFT) is None

    def test_one_attacks_growth_counts_and_a_conditional_one_does_not(self):
        """Charging Griffin (2/2 flying) gets +1/+1 whenever it attacks: three
        power in the air, an evasive body. Gryff Rider's training counter needs
        a stronger creature attacking beside it, and that help is not
        credited."""
        assert limited_closer_reason(test_card("Charging Griffin"), game=DRAFT) == (
            "evasive"
        )
        assert limited_closer_reason(test_card("Gryff Rider"), game=DRAFT) is None

    @pytest.mark.parametrize(
        "name",
        [
            "Brawl-Bash Ogre",  # "you may sacrifice another creature"
            "Aetherstream Leopard",  # "you may pay {E}"
            "Phelia, Exuberant Shepherd",  # a delayed end-step counter
            "Thrashing Frontliner",  # only when it attacks a battle
            "Gryff Rider",  # training: a stronger creature attacking with it
        ],
    )
    def test_attack_growth_that_needs_help_is_not_credited(self, name):
        from mtg_utils._card_ir.trees import trees_for
        from mtg_utils._tuner.metrics import _attack_growth

        assert _attack_growth(trees_for(test_card(name))) == 0

    @pytest.mark.parametrize(
        ("name", "board"),
        [
            # Creatures you control, no other property: a board of three.
            ("Sharpshooter Elf", True),
            # An opponent's permanents, any player's shadow creatures, a token's
            # ability, and a count of cards in a graveyard are not your board.
            ("Wilderness Elemental", False),
            ("Dauthi Warlord", False),
            ("Voice of Resurgence", False),
            ("Boneyard Mycodrax", False),
        ],
    )
    def test_a_counted_power_is_read_only_off_your_own_board(self, name, board):
        from mtg_utils._card_ir.trees import trees_for
        from mtg_utils._tuner.metrics import (
            LIMITED_BOARD_CREATURES,
            _grown_base,
            _printed_power,
        )

        card = test_card(name)
        base, _kw = _grown_base(card, trees_for(card))
        assert base == (LIMITED_BOARD_CREATURES if board else _printed_power(card))

    def test_a_leveler_gets_only_its_first_levels_keywords(self):
        """Kargan Dragonlord's first level is a 4/4 flier, an evasive body; its
        level-8 trample is not credited. Transcendent Master's first level is a
        6/6 lifelinker; its level-12 indestructible is not credited, so it is no
        closer."""
        assert limited_closer_reason(test_card("Kargan Dragonlord"), game=DRAFT) == (
            "evasive"
        )
        assert (
            limited_closer_reason(test_card("Transcendent Master"), game=DRAFT) is None
        )

    def test_a_one_time_enters_cost_holds_no_limited_body_back(self):
        inverter = test_card("Inverter of Truth")
        assert limited_closer_reason(inverter, game=DRAFT) == "evasive"

    def test_closer_read_follows_the_family(self):
        assert closer_read(LIMITED) is is_limited_closer
        assert closer_read(COMMANDER) is is_wincon_card
        assert closer_read(CONSTRUCTED) is is_wincon_card

    def test_the_limited_band_is_its_own_and_counts_true_name_nemesis(self):
        from mtg_utils._tuner.metrics import win_conditions

        classes = [_cc(n, test_card(n)) for n in ("True-Name Nemesis", "Grizzly Bears")]
        wins = win_conditions(
            classes,
            shape="midrange",
            combo_count=0,
            deck_size=40,
            game=DRAFT,
            cal=LIMITED,
        )
        assert wins["cards"] == ["True-Name Nemesis"]
        assert wins["count"] == 1
        # Stated at the limited game itself: never life-scaled from 40.
        assert wins["target"] == [LIMITED_CLOSER_FLOOR, LIMITED_CLOSER_TOP]
        assert wins["status"] == "ok"
        # The finisher read at the same game counts none.
        finisher = win_conditions(
            classes,
            shape="midrange",
            combo_count=0,
            deck_size=40,
            game=DRAFT,
            cal=replace(LIMITED, closers="finisher"),
        )
        assert finisher["count"] == 0

    def test_the_closer_search_takes_the_familys_read(self):
        sourcing = Sourcing(
            {"viable_avenues": []}, [], {}, game=DRAFT, closer=is_limited_closer
        )
        remedy = sourcing.remedy_for("wincon_short")
        assert remedy is not None
        assert remedy.spec["_filter"](test_card("True-Name Nemesis")) is True
        commander = Sourcing({"viable_avenues": []}, [], {}, game=DRAFT).remedy_for(
            "wincon_short"
        )
        assert commander.spec["_filter"](test_card("True-Name Nemesis")) is False
