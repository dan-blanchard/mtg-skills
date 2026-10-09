"""The crosswalk reads behind deck-stats and the tuner's bracket and closer reads:
mass land denial, game wins, reach, self evasion and printed alternative costs.

Every card is a real one from the testkit snapshot (ADR-0056); each read runs over
the same corrected trees phase's records build in production.
"""

from __future__ import annotations

import pytest

from mtg_utils._analysis.costs import effective_mana_value
from mtg_utils._card_ir.crosswalk import (
    NARROWED_PERMANENT_SWEEPS,
    AltCost,
    cost_symbols,
    ends_the_game,
    is_evasive_body,
    mass_land_denial,
    reach_amount,
    shard_symbol,
    tag_of,
    unbound_x_reach,
)
from mtg_utils._card_ir.trees import trees_for
from mtg_utils.testkit import test_card, test_phase_records, test_signals


def _trees(name: str):
    trees = trees_for(test_card(name))
    assert trees, f"{name}: no trees"
    return trees


def _denial(name: str) -> str | None:
    kinds = {mass_land_denial(t) for t in _trees(name)} - {None}
    return next(iter(kinds), None)


# ── Mass land denial ──────────────────────────────────────────────────────────
# Wizards' Commander Brackets: "cards that regularly destroy, exile, and bounce
# other lands, keep lands tapped, or change what mana is produced by four or more
# lands per player without replacing them".


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Armageddon", "destroy"),
        ("Jokulhaups", "destroy"),  # an Or filter with a Land arm
        ("Ruination", "destroy"),  # nonbasic lands
        ("Sunder", "bounce"),
        ("Upheaval", "bounce"),  # all permanents, lands among them
        ("Omen of Fire", "bounce"),  # all Islands
        ("Apocalypse", "exile"),  # all permanents
        ("Boil", "destroy"),  # a basic land type
        ("Ajani Vengeant", "destroy"),  # -7: all lands target player controls
        ("Desolation Angel", "destroy"),  # kicked: all lands, not only yours
        ("Wildfire", "sacrifice"),  # four each
        ("Death Cloud", "sacrifice"),  # X each
        ("Keldon Firebombers", "sacrifice"),  # all but three
        ("Restore Balance", "sacrifice"),  # down to the fewest
        ("Cataclysm", "sacrifice"),  # keep one land, sacrifice the rest
        ("Winter Orb", "untap_lock"),
        ("Static Orb", "untap_lock"),  # two permanents, lands among them
        ("Back to Basics", "untap_lock"),
        ("Choke", "untap_lock"),
        ("Stasis", "untap_lock"),  # players skip their untap steps
        ("Blood Moon", "mana_change"),  # CR 305.7
        ("Magus of the Moon", "mana_change"),
        ("Contamination", "mana_change"),  # lands produce {B} instead
    ],
)
def test_mass_land_denial(name, kind):
    assert _denial(name) == kind


@pytest.mark.parametrize(
    "name",
    [
        "Yawning Fissure",  # each opponent sacrifices one land
        "Tremble",  # each player sacrifices one land
        "Ember Swallower",  # three lands each, under the four of the definition
        "Pox",  # a third of their lands, rounded up
        "From the Ashes",  # each player searches for a basic per land destroyed
        "Wave of Vitriol",
        "Planar Birth",  # returns lands to the battlefield
        "Second Sunrise",
        "Mungha Wurm",  # only your own untap step
        "Celestial Dawn",  # only your own lands
        "Smokestack",  # permanents: each player may choose nonlands
        "Strip Mine",  # one land
        "Wrath of God",
        "Cyclonic Rift",  # nonland permanents
        # Not "regularly": one untap step, one turn.
        "Exhaustion",
        "Mana Vapors",
        "Nightcreep",
        # A residue since phase v0.104.0 (attached_to_qualifier).
        "End Hostilities",
        # Phase drops the narrowing clause (vetoed; see the canary below).
        "Eye of Singularity",
        "Herald of Vengeance",
    ],
)
def test_not_mass_land_denial(name):
    assert _denial(name) is None


# ── Game wins ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "ends"),
    [
        ("Felidar Sovereign", True),  # you win (CR 104.2b)
        ("Thassa's Oracle", True),
        ("Laboratory Maniac", True),  # a replacement
        ("Door to Nothingness", True),  # target player loses (CR 104.3e)
        ("Phage the Untouchable", True),  # that player loses; its own loss is yours
        ("Pact of Negation", False),  # you lose: a drawback
        ("Platinum Angel", False),  # can't-win / can't-lose statics
    ],
)
def test_ends_the_game(name, ends):
    assert any(ends_the_game(t) for t in _trees(name)) is ends


# ── Reach ─────────────────────────────────────────────────────────────────────


def _reach(name: str) -> list[tuple[str, int | None]]:
    return [
        r
        for t in _trees(name)
        for u in t.units
        for n in u.iter_typed()
        if (r := reach_amount(u.node, n)) is not None
    ]


@pytest.mark.parametrize(
    ("name", "reach"),
    [
        ("Exsanguinate", ("group", None)),  # each opponent loses X
        ("Gray Merchant of Asphodel", ("group", None)),  # devotion
        ("Kokusho, the Evening Star", ("group", 5)),
        ("Torment of Hailfire", ("group", None)),  # 3 life, repeated X times
        ("Fanatic of Mogis", ("group", None)),  # damage to each opponent
        ("Blood Artist", ("single", 1)),  # target player
        ("Aetherflux Reservoir", ("single", 50)),  # any target
        ("Fireball", ("single", None)),
        ("Lava Axe", ("single", 5)),  # target player or planeswalker
    ],
)
def test_reach_amount(name, reach):
    assert reach in _reach(name)


@pytest.mark.parametrize(
    "name",
    [
        "Earthquake",  # each player, you included
        "Crypt Rats",
        "Abyssal Hunter",  # damage to the creature it tapped
        "Bite Down",  # creature or planeswalker
    ],
)
def test_no_reach(name):
    assert _reach(name) == []


# ── Evasive body ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "evasive"),
    [
        ("Phantom Warrior", True),  # can't be blocked
        ("Pathrazer of Ulamog", True),  # except by three or more creatures
        ("Tromokratis", True),  # unless all creatures defending player controls block
        ("Serra Angel", False),  # flying is a keyword, read off the record
    ],
)
def test_is_evasive_body(name, evasive):
    assert any(is_evasive_body(t) for t in _trees(name)) is evasive


# ── Printed alternative costs ─────────────────────────────────────────────────


def _alts(name: str) -> list[AltCost]:
    return [a for t in _trees(name) for a in t.card_alt_costs]


@pytest.mark.parametrize(
    ("name", "alt"),
    [
        ("Ancestral Vision", AltCost("suspend", "4—{U}", "special_action")),
        ("Lotus Bloom", AltCost("suspend", "3—{0}", "special_action")),
        (
            "Phyrexian Fleshgorger",
            AltCost("prototype", "{1}{B}{B} — 3/3", "alternative_characteristics"),
        ),
        ("Fury", AltCost("evoke", "Exile a red card from your hand", "alternative")),
        ("Infestation", AltCost("evoke", "{1}{B}{B}, Pay 3 life", "alternative")),
        (
            "Uro, Titan of Nature's Wrath",
            AltCost(
                "escape",
                "{G}{G}{U}{U}, Exile five other cards from your graveyard",
                "alternative",
            ),
        ),
        ("Deep Analysis", AltCost("flashback", "{1}{U}, Pay 3 life", "alternative")),
        (
            "Twinned Vision",
            AltCost("flashback", "{1}{U/R}{U/R}, Discard a card", "alternative"),
        ),
        ("Ragavan, Nimble Pilferer", AltCost("dash", "{1}{R}", "alternative")),
        ("Cyclonic Rift", AltCost("overload", "{6}{U}", "alternative")),
        ("Lurker in the Deep", AltCost("impending", "3—{2}{U}{U}", "alternative")),
        (
            "Abundant Maw",
            AltCost("emerge", "{6}{B}, Sacrifice a creature", "alternative"),
        ),
        ("Dig Up", AltCost("cleave", "{1}{B}{B}{G}", "alternative")),
        ("All-Fates Stalker", AltCost("warp", "{1}{W}", "alternative")),
        ("Channeled Dragonfire", AltCost("harmonize", "{5}{R}{R}", "alternative")),
        ("Amazing Spider-Girl", AltCost("web-slinging", "{2}{W}", "alternative")),
        ("Aloe Alchemist", AltCost("plot", "{1}{G}", "special_action")),
        # Buyback is paid on top of the mana cost (CR 702.27a, 118.8).
        ("Capsize", AltCost("buyback", "{3}", "additional")),
        # Retrace: "by discarding a land card as an additional cost" (702.81a).
        ("Raven's Crime", AltCost("retrace", "Discard a land card", "additional")),
        # Ninjutsu puts the card onto the battlefield; it is never cast (702.49a/d).
        ("Ingenious Infiltrator", AltCost("ninjutsu", "{U}{B}", "ability")),
        (
            "Yuriko, the Tiger's Shadow",
            AltCost("commander ninjutsu", "{U}{B}", "ability"),
        ),
    ],
)
def test_card_alt_costs(name, alt):
    assert alt in _alts(name)


def test_morph_is_cast_face_down_for_three_and_turned_up_for_its_cost():
    # 702.37a: cast face down "by paying {3} rather than paying its mana cost";
    # turning it face up is a special action (116.2b).
    assert _alts("Exalted Angel") == [
        AltCost("morph", "{3} (face down)", "alternative"),
        AltCost("morph (face up)", "{2}{W}{W}", "special_action"),
    ]


def test_no_alt_costs_on_a_plain_card():
    assert _alts("Lightning Bolt") == []


@pytest.mark.parametrize(
    ("shard", "symbol"),
    [
        ("Blue", "{U}"),
        ("BlueRed", "{U/R}"),  # hybrid
        ("TwoRed", "{2/R}"),  # monocolored hybrid
        ("PhyrexianBlack", "{B/P}"),
        ("PhyrexianBlackRed", "{B/R/P}"),  # hybrid Phyrexian
        ("ColorlessRed", "{C/R}"),
        ("Colorless", "{C}"),
        ("Snow", "{S}"),
        ("X", "{X}"),
    ],
)
def test_shard_symbol(shard, symbol):
    # CR 107.4's mana symbols, from phase's ManaCostShard names.
    assert shard_symbol(shard) == symbol


@pytest.mark.parametrize(
    ("name", "alt"),
    [
        ("Bonfire of the Damned", AltCost("miracle", "{X}{R}", "alternative")),
        ("Street Spasm", AltCost("overload", "{X}{X}{R}{R}", "alternative")),
    ],
)
def test_x_costs_print_x_first(name, alt):
    assert alt in _alts(name)


def test_cost_symbols_of_a_non_cost_is_empty():
    assert cost_symbols(None) == ""


# ── Keywords phase drops ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "alt"),
    [
        (
            "Zombie Cutthroat",
            AltCost("morph (face up)", "Pay 5 life", "special_action"),
        ),
        (
            "Tenacious Underdog",
            AltCost("blitz", "{2}{B}{B}, Pay 2 life", "alternative"),
        ),
        ("Timeline Culler", AltCost("warp", "{B}, Pay 2 life", "alternative")),
        (
            "Shadowgrange Archfiend",
            AltCost("madness", "{2}{B}, Pay 8 life", "alternative"),
        ),
        (
            "Escape Velocity",
            AltCost(
                "escape",
                "{1}{R}, Exile two other cards from your graveyard",
                "alternative",
            ),
        ),
        # "Suspend X—{X}{3}{R}" (CR 702.62a's N is X here).
        ("Detritivore", AltCost("suspend", "X—{X}{3}{R}", "special_action")),
    ],
)
def test_dropped_keyword_is_recovered_off_its_line(name, alt):
    assert alt in _alts(name)


def test_recovered_warp_reaches_the_curve():
    # Timeline Culler's "Warp—{B}, Pay 2 life" is paid rather than its mana cost
    # (702.185a); a life payment is always payable, so the deck can plan on {B}.
    culler = test_card("Timeline Culler")
    assert effective_mana_value(culler) == 1


@pytest.mark.retirement_canary
@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Zombie Cutthroat", "Morph"),
        ("Timeline Culler", "Warp"),
        ("Shadowgrange Archfiend", "Madness"),
        ("Escape Velocity", "Escape"),
    ],
)
def test_dropped_keyword_costs_canary(name, key):
    """Retirement canary for ``crosswalk.core._dropped_keyword_costs`` and the
    ``keyword_dropped_paylife`` ledger bridge that reads its rows: phase v0.94.0
    leaves these keywords (costs with a non-mana part) off the card."""
    keys = {
        next(iter(kw)) if isinstance(kw, dict) else kw
        for rec in test_phase_records(name)
        for kw in rec.get("keywords") or ()
    }
    assert key not in keys, (
        f"crosswalk.core._dropped_keyword_costs: RETIRE-READY — phase now carries "
        f"{name}'s {key}. Delete _dropped_keyword_costs, its call in "
        "build_concept_tree, this canary — and re-check the "
        "keyword_dropped_paylife ledger bridge, which reads the recovered rows."
    )


def test_misread_keywords_are_corrected():
    # Warbringer's "Dash costs you pay cost {2} less" reduces dash costs (its
    # ruling); it is not a second dash.
    assert _alts("Warbringer") == [AltCost("dash", "{2}{R}", "alternative")]
    # Memory Crystal's "Buyback costs cost {2} less" changes buyback costs (its
    # rulings); it has no buyback of its own.
    assert _alts("Memory Crystal") == []


@pytest.mark.retirement_canary
def test_misread_keyword_canary():
    """Retirement canary for ``crosswalk.core._misread_keyword``: phase v0.94.0
    reads "Suspend X—{X}{3}{R}" as count 0 and Warbringer's dash reducer as a
    second Dash."""

    def keywords(name):
        return [
            kw
            for rec in test_phase_records(name)
            for kw in rec.get("keywords") or ()
            if isinstance(kw, dict)
        ]

    suspend = [kw["Suspend"] for kw in keywords("Detritivore") if "Suspend" in kw]
    dashes = [kw for kw in keywords("Warbringer") if "Dash" in kw]
    assert suspend
    assert suspend[0]["count"] == 0, (
        "crosswalk.core._misread_keyword: RETIRE-READY — phase now reads suspend X."
    )
    assert len(dashes) == 2, (
        "crosswalk.core._misread_keyword: RETIRE-READY — Warbringer has one Dash."
    )
    assert any("Buyback" in kw for kw in keywords("Memory Crystal")), (
        "crosswalk.core._misread_keyword: RETIRE-READY — Memory Crystal has no "
        "Buyback keyword."
    )


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Eye of Singularity", "Herald of Vengeance"])
def test_narrowed_permanent_sweeps_canary(name):
    """Retirement canary for ``reads.NARROWED_PERMANENT_SWEEPS``: phase (v0.94.0,
    still at v0.104.0) parses each of these narrowed sweeps as destroying every
    permanent."""
    bare = [
        n
        for t in _trees(name)
        for n in t.iter_typed()
        if tag_of(n) == "DestroyAll"
        and tag_of(getattr(n, "target", None)) == "Typed"
        and set(n.target.type_filters) == {"Permanent"}
    ]
    assert bare, (
        f"reads.NARROWED_PERMANENT_SWEEPS: RETIRE-READY for {name} — phase keeps "
        "the narrowing clause now; drop its phrase (and this pin)."
    )
    assert any(p in test_card(name)["oracle_text"] for p in NARROWED_PERMANENT_SWEEPS)


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Exhaustion", "Mana Vapors"])
def test_one_shot_untap_statics_canary(name):
    """Retirement canary for ``reads._lasting_static_defs``' instant/sorcery rule:
    phase v0.94.0 parses "don't untap during their next untap step" as a top-level
    static, with no duration."""
    statics = [rec.get("static_abilities") for rec in test_phase_records(name)]
    assert any(statics), (
        f"reads._lasting_static_defs: RETIRE-READY — phase reads {name} as a "
        "resolving effect with a duration now."
    )


# ── Unbound X reach ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "scope"),
    [("Insatiable Hemophage", "group"), ("Zenith Flare", "single")],
)
def test_unbound_x_reach(name, scope):
    assert any(unbound_x_reach(t) == scope for t in _trees(name))


@pytest.mark.retirement_canary
@pytest.mark.parametrize("name", ["Insatiable Hemophage", "Zenith Flare"])
def test_unbound_x_reach_canary(name):
    """Retirement canary for ``reads.unbound_x_reach``: phase v0.94.0 parks the
    X effect as a where_x_binding residue, so no reach node is left."""
    assert not _reach(name), (
        f"reads.unbound_x_reach: RETIRE-READY — phase now reads {name}'s X effect."
    )


# ── The mass_land_denial key ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Armageddon", "destroy"),
        ("Wildfire", "sacrifice"),
        ("Blood Moon", "mana_change"),
        # Ledger bridges over phase's parse failures (ADR-0048).
        ("Burning of Xinye", "destroy"),  # four lands per player
        ("Global Ruin", "sacrifice"),  # keep one of each basic type
    ],
)
def test_mass_land_denial_key_carries_its_shape(name, kind):
    idents = {(s.key, s.scope, s.subject) for s in test_signals(name)}
    assert ("mass_land_denial", "each", kind) in idents
