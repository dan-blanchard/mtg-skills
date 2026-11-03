"""The ramp read (``job_quality.ramp``): how well a nonland card accelerates your
mana, off its own trees — real cards (ADR-0056)."""

from mtg_utils._analysis.job_quality import job_score, ramp
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float:
    score = job_score(_real(name), "ramp")
    assert score is not None, name
    return score


def test_a_two_mana_rock_reads_above_a_four_mana_one():
    """Mind Stone and Hedron Archive both tap for colorless and sacrifice to draw;
    Mind Stone's one mana a turn for two pays back faster than Archive's two for
    four."""
    assert ramp.features(_real("Mind Stone"))["early"] == 1.0
    assert ramp.features(_real("Hedron Archive"))["early"] == 0.0
    assert _score("Mind Stone") > _score("Hedron Archive")


def test_an_untapped_forest_for_two_reads_above_cultivate():
    """Nature's Lore and Three Visits put a Forest onto the battlefield untapped
    for two mana; Cultivate's land enters tapped for three, its second land going
    to the hand."""
    cultivate = ramp.features(_real("Cultivate"))
    assert cultivate["land_tapped"] == 1.0
    assert cultivate["land_hand"] == 1.0
    for name in ("Nature's Lore", "Three Visits"):
        features = ramp.features(_real(name))
        assert features["land"] == 1.0
        assert features["land_tapped"] == 0.0
        assert _score(name) > _score("Cultivate")


def test_a_summoning_sick_dork_reads_below_an_equal_rock():
    """Ornithopter of Paradise and Arcane Signet each cost two and tap for one
    mana of a color you need; the creature's {T} ability waits a turn (CR 302.6)
    and dies to a sweeper."""
    assert ramp.features(_real("Ornithopter of Paradise"))["dork"] == 1.0
    assert ramp.features(_real("Arcane Signet"))["dork"] == 0.0
    assert _score("Ornithopter of Paradise") < _score("Arcane Signet")


def test_a_rock_of_borrowed_colors_reads_below_a_signet():
    """Fellwar Stone's colors are whatever an opponent's lands make; a Signet
    of the deck's own colors fixes on your terms. Equal rocks tie, so a Signet
    is no upgrade over another Signet either."""
    assert ramp.features(_real("Fellwar Stone"))["fixes"] == 0.5
    assert ramp.features(_real("Golgari Signet"))["fixes"] == 1.0
    assert _score("Golgari Signet") > _score("Fellwar Stone")
    assert _score("Golgari Signet") == _score("Arcane Signet")


def test_sol_ring_reads_above_every_two_mana_rock():
    """Two colorless a turn for one mana: the read's best payback."""
    assert _score("Sol Ring") > _score("Arcane Signet") > _score("Hedron Archive")


def test_a_non_ramp_card_and_a_land_are_not_read():
    """Lightning Bolt makes no mana; Command Tower is a land — the mana base,
    never ramp (``roles.is_ramp``)."""
    assert job_score(_real("Lightning Bolt"), "ramp") is None
    assert job_score(_real("Command Tower"), "ramp") is None


def test_a_land_put_the_synthesis_stage_adds_reads_as_conditional():
    """The read walks the signal trees, so Bonny Pall's "put a land card from your
    hand or graveyard onto the battlefield" (a clause phase leaves to the
    synthesis stage) reaches it: an extra land, at the conditional rate, since a
    synthesized clause carries no kind or trigger to say how often it repeats."""
    feats = ramp.features(_real("Bonny Pall, Clearcutter"))
    assert feats is not None
    assert feats["extra_land"] == 1.0
    assert feats["per_turn"] == 0.25


def test_the_synthesis_unit_is_no_ability_of_the_card():
    """Deathrite Shaman's two non-mana abilities are its other abilities; the
    synthesis unit its signal trees carry is not a third."""
    feats = ramp.features(_real("Deathrite Shaman"))
    assert feats is not None
    assert feats["other_units"] == 2.0


def test_a_paid_activation_for_a_spawn_makes_no_mana():
    """Idol of False Gods pays "{1}{C}, {T}" for an Eldrazi Spawn that
    sacrifices for one {C}: no mana a turn (Lorehold Spirit, 2026-11-02).
    Awakening Zone's upkeep Spawn is free and stays a turn's mana."""
    from mtg_utils._analysis.job_quality import ramp

    assert ramp.features(test_card("Idol of False Gods"))["per_turn"] == 0.0
    assert ramp.features(test_card("Awakening Zone"))["per_turn"] == 1.0


def test_a_mana_grant_to_creature_tokens_runs_on_token_makers():
    """Insidious Roots gives "Creature tokens you control" a mana ability:
    a deck making no creature tokens fuels none of it (Dance of the
    Elements, 2026-11-02); a rock is fit anywhere."""
    from mtg_utils._analysis.job_quality import ramp

    rocks = [test_card("Mind Stone")] * 20
    assert ramp.deck_fit(test_card("Insidious Roots"), rocks) == 0.0
    assert ramp.deck_fit(test_card("Sol Ring"), rocks) == 1.0


def test_a_bonus_on_tapping_forests_runs_on_the_decks_forests():
    """Nissa, Who Shakes the World adds {G} "whenever you tap a Forest for
    mana": a deck of Islands feeds none of it (Dance of the Elements,
    2026-11-02)."""
    from mtg_utils._analysis.job_quality import ramp

    nissa = test_card("Nissa, Who Shakes the World")
    assert ramp.deck_fit(nissa, [test_card("Forest")] * 20) == 1.0
    assert ramp.deck_fit(nissa, [test_card("Island")] * 20) == 0.0


def test_lands_on_a_later_sacrifice_are_not_early_ramp():
    """Ordeal of Nylea's "When you sacrifice this Aura, search your library
    for up to two basic land cards" comes after three attacks: not early,
    and below Careful Cultivation's "{T}: Add {G}{G}" (Virtue and Valor,
    2026-11-02); Rampant Growth's land comes on cast."""
    assert ramp.features(_real("Ordeal of Nylea"))["early"] == 0.0
    assert ramp.features(_real("Rampant Growth"))["early"] == 1.0
    assert _score("Ordeal of Nylea") < _score("Careful Cultivation")


def test_a_land_sacrificed_by_the_effect_counts_as_one_paid():
    """Harrow sacrifices a land as its cost, Cycle of Renewal as its effect:
    both net one land, and Cycle's enter tapped (World Shaper, 2026-11-02)."""
    assert ramp.features(_real("Cycle of Renewal"))["per_turn"] == 1.0
    assert _score("Cycle of Renewal") < _score("Harrow")
