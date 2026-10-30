"""The tune's mana-base swaps (``_tuner.mana_base``): which lands are swapped,
for what, within what purse. Real cards via the testkit (ADR-0056)."""

from mtg_utils._tuner.mana_base import (
    enters_tapped_unconditionally,
    land_candidates,
    land_plan,
    mana_only,
    pick_add,
    produced,
)
from mtg_utils.testkit import test_card


def test_a_guildgate_enters_tapped_and_only_makes_mana():
    gate = test_card("Azorius Guildgate")
    assert enters_tapped_unconditionally(gate)
    assert mana_only(gate)
    assert produced(gate) == {"W", "U"}


def test_a_thriving_land_is_tapped_mana_only():
    # "As it enters, choose a color" is an as-enters replacement, still mana only.
    heath = test_card("Thriving Heath")
    assert enters_tapped_unconditionally(heath)
    assert mana_only(heath)


def test_a_bounce_land_and_a_temple_are_not_mana_only():
    # Azorius Chancery's return trigger and Temple of Enlightenment's scry are
    # reasons a deck keeps them beyond their mana.
    assert enters_tapped_unconditionally(test_card("Azorius Chancery"))
    assert not mana_only(test_card("Azorius Chancery"))
    assert not mana_only(test_card("Temple of Enlightenment"))


def test_a_conditional_or_optional_tap_is_not_unconditional():
    # Glacial Fortress: "unless you control a Plains or an Island"; Hallowed
    # Fountain: "you may pay 2 life. If you don't, it enters tapped."
    assert not enters_tapped_unconditionally(test_card("Glacial Fortress"))
    assert not enters_tapped_unconditionally(test_card("Hallowed Fountain"))
    assert not enters_tapped_unconditionally(test_card("Command Tower"))


def _audit(production: dict[str, int], land_count: int, pips: dict[str, float]) -> dict:
    return {
        "pip_demand_pct": pips,
        "land_color_production": production,
        "land_count": land_count,
    }


def test_the_plan_cuts_tapped_mana_only_lands_and_keeps_plan_lands():
    gate, heath, plains = (
        test_card("Azorius Guildgate"),
        test_card("Thriving Heath"),
        test_card("Plains"),
    )
    audit = _audit({"W": 20, "U": 12}, 36, {"W": 0.6, "U": 0.4})
    plan = land_plan(
        [gate, heath, plains], audit, keep=lambda r: r["name"] == "Thriving Heath"
    )
    names = [r["name"] for r, _must in plan.cuts]
    assert "Azorius Guildgate" in names
    assert "Thriving Heath" not in names  # on the plan: kept
    # Blue is at demand (12 of 36 at 0.4 → 14.4 wanted): the Guildgate's
    # replacement must keep making blue.
    must = {r["name"]: m for r, m in plan.cuts}["Azorius Guildgate"]
    assert "U" in must


def test_surplus_basics_follow_the_tapped_lands():
    plains = test_card("Plains")
    audit = _audit({"W": 30, "U": 6}, 36, {"W": 0.5, "U": 0.5})
    plan = land_plan([plains, plains, plains], audit, keep=lambda _r: False)
    assert [r["name"] for r, _m in plan.cuts][:1] == ["Plains"]


def test_candidates_are_untapped_cover_the_needed_colours_and_respect_the_cap():
    pool = [
        test_card("Azorius Guildgate"),  # tapped: never a candidate
        test_card("Hallowed Fountain"),
        test_card("Glacial Fortress"),
        test_card("Command Tower"),
        test_card("Plains"),  # a basic: never a candidate
    ]
    cands = land_candidates(pool, needed={"W", "U"}, exclude=set())
    names = [c["name"] for c in cands]
    assert "Azorius Guildgate" not in names
    assert "Plains" not in names
    assert set(names) == {"Hallowed Fountain", "Glacial Fortress", "Command Tower"}
    # A cheap purse: the pick must make blue and cost under the cap.
    pick = pick_add(
        cands,
        must=frozenset({"U"}),
        used=set(),
        price_cap=1.0,
        affordable=lambda c: 0.5 if c["name"] == "Glacial Fortress" else 50.0,
    )
    assert pick is not None
    assert pick[0]["name"] == "Glacial Fortress"
