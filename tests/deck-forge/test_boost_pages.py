"""The pages the creature-boost signals are offered on (ADR-0065; Dan's rulings,
2026-11-25): who is offered what, both directions. Real cards via
``mtg_utils.testkit`` (ADR-0056)."""

from __future__ import annotations

import pytest

from mtg_utils._analysis.signal_specs import SPECS, avenue_spec_for, spec_for
from mtg_utils._analysis.signals import Signal
from mtg_utils._deck_forge import engine
from mtg_utils.testkit import test_card, test_signals


def _sig(key: str, scope: str = "you", subject: str = "") -> Signal:
    return Signal(key=key, scope=scope, subject=subject, text="", source="")


def _card(name: str) -> dict:
    test_signals(name)  # seeds the trees the serve's ident arm reads
    return test_card(name)


def _extra(spec, label):
    return next(e for e in spec.extras if e.label == label)


def test_the_self_boost_page_is_grows_itself():
    spec = spec_for(_sig("self_boost"))
    assert spec is not None
    assert spec.label == "Grows itself"
    assert spec.serve.matches(_card("Shivan Dragon"))
    assert spec.serve.matches(_card("Glaze Fiend"))
    assert not spec.serve.matches(_card("Giant Growth"))
    assert ("self_pump", "you") not in SPECS


@pytest.mark.parametrize(
    "card",
    [
        "Fling",  # power-as-damage
        "Prey Upon",  # a fight
        "Unleash Fury",  # a power doubler
        "Rancor",  # trample
        "Garruk's Uprising",  # a power payoff
    ],
)
def test_a_self_booster_is_offered_its_cash_ins(card):
    """Fights and bites, power-as-damage, power doubling, power payoffs,
    trample and evasion: one sub-avenue, so the page stays one theme."""
    spec = spec_for(_sig("self_boost"))
    assert _extra(spec, "Cash in its size").serve.matches(_card(card))


@pytest.mark.parametrize(
    "key",
    [
        "fight_makers",
        "damage_equal_power",
        "power_tap_engine",
        "power_double",
        "power_matters",
        "team_evasion_grant",
        "keyword_grant_target",
        "aura_equip_kw_grant",
    ],
)
def test_the_cash_in_pages_are_offered_self_boosters(key):
    spec = spec_for(_sig(key))
    assert _extra(spec, "Creatures that grow themselves").serve.matches(
        _card("Shivan Dragon")
    )


@pytest.mark.parametrize(
    "key",
    [
        ("power_matters", "you"),
        ("combat_damage_matters", "opponents"),
        ("combat_damage_to_opp", "opponents"),
        ("fight_makers", "you"),
        ("damage_equal_power", "you"),
        ("power_double", "you"),
    ],
)
def test_the_size_pages_are_offered_whatever_boosts_your_other_creatures(key):
    extra = _extra(SPECS[key], "Boosts your other creatures")
    for name in ("Giant Growth", "Glorious Anthem", "Bonesplitter", "Dragonscale Boon"):
        assert extra.serve.matches(_card(name)), name
    assert not extra.serve.matches(_card("Glaze Fiend"))


def test_no_page_still_offers_the_old_combat_tricks_extra():
    labels = {e.label for spec in SPECS.values() for e in spec.extras}
    assert "Combat tricks / pump" not in labels


def test_big_mana_and_untaps_go_to_the_activated_self_booster_only():
    spec = spec_for(_sig("self_boost", subject="activated"))
    mana = _extra(spec, "Mana and untaps for firebreathing")
    assert mana.offered_for("activated")
    assert not mana.offered_for("")
    assert not mana.offered_for("counters")
    # Both directions: the big-mana and untap pages offer the firebreathers.
    for key in ("big_mana", "untap_engine"):
        extra = _extra(spec_for(_sig(key)), "Firebreathers (mana sinks)")
        assert extra.serve.matches(_card("Shivan Dragon"))
        assert not extra.serve.matches(_card("Glaze Fiend"))


def test_the_engine_opens_a_gated_extra_under_a_later_subject():
    """A deck whose triggered self-pump opened "Grows itself" first still gets
    the firebreather's partners from its activated one."""
    seen: set[str] = set()
    spec = spec_for(_sig("self_boost"))
    first = engine._subject_extras(
        spec, _sig("self_boost"), "engine:self_boost:you", seen, gated=False
    )
    assert "Mana and untaps for firebreathing" not in {a["label"] for a in first}
    later = engine._subject_extras(
        spec,
        _sig("self_boost", subject="activated"),
        "engine:self_boost:you:activated",
        seen,
    )
    assert [a["label"] for a in later] == ["Mana and untaps for firebreathing"]


def _targeting_extras(subject: str) -> list:
    sig = _sig("targeting_matters", "any", subject)
    spec = avenue_spec_for(sig)
    assert spec is not None
    return [e for e in spec.extras if e.offered_for(subject)]


def test_a_heroic_payoff_is_offered_spells_but_not_abilities():
    """Heroic's "Whenever you cast a spell that targets ~" fires on a spell:
    Giant Growth's pump, not Bonesplitter's equip."""
    assert ("targeting_matters", "any", "spell") in {
        (s.key, s.scope, s.subject) for s in test_signals("Akroan Crusader")
    }
    extras = {e.label: e for e in _targeting_extras("spell")}
    assert set(extras) == {
        "Single-target pump spells",
        "Single-target protection spells",
    }
    pumps = extras["Single-target pump spells"]
    assert pumps.serve.matches(_card("Giant Growth"))
    assert not pumps.serve.matches(_card("Bonesplitter"))
    # Its keyword grants are spells' too: Gods Willing, not Mother of Runes's
    # "{T}: Target creature you control gains protection".
    grants = extras["Single-target protection spells"]
    assert grants.serve.matches(_card("Gods Willing"))
    assert not grants.serve.matches(_card("Mother of Runes"))
    # Dirge of Dread's targeted grant is its cycling trigger's (CR 115.1a's
    # example), not the sorcery's; an Aura spell targets as it is cast (CR
    # 303.4a), so Flight's grant is a spell's (the coordinator's call).
    assert not grants.serve.matches(_card("Dirge of Dread"))
    assert grants.serve.matches(_card("Flight"))


def test_a_spell_or_ability_payoff_is_offered_both():
    """ "Whenever ~ becomes the target of a spell or ability" (Cephalid
    Illusionist)."""
    (extra,) = _targeting_extras("")
    assert extra.serve.matches(_card("Giant Growth"))
    assert extra.serve.matches(_card("Bonesplitter"))


def test_an_ability_payoff_is_offered_abilities_but_not_spells():
    (extra,) = _targeting_extras("ability")
    assert extra.serve.matches(_card("Bonesplitter"))
    assert not extra.serve.matches(_card("Giant Growth"))
    # Keyword grants by an ability only: Mother of Runes and Dirge of Dread's
    # cycling trigger, never Gods Willing's spell (the coordinator's call).
    assert extra.serve.matches(_card("Mother of Runes"))
    assert extra.serve.matches(_card("Dirge of Dread"))
    assert not extra.serve.matches(_card("Gods Willing"))


def test_a_team_trample_grant_is_offered_self_boosters_back():
    """``team_boost_or_grant|you|trample`` is a cash-in's trample (the forward
    direction is "Cash in its size"); only its trample subject is offered them."""
    spec = spec_for(_sig("team_boost_or_grant", subject="trample"))
    extra = _extra(spec, "Creatures that grow themselves")
    assert extra.offered_for("trample")
    assert not extra.offered_for("")
    assert extra.serve.matches(_card("Shivan Dragon"))
    cash_in = _extra(spec_for(_sig("self_boost")), "Cash in its size")
    assert cash_in.serve.matches(_card("Overrun"))
