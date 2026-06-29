"""Deterministic Shape inference (``_tuner.shape.infer_shape``).

The combo axis is the subtle one: Commander Spellbook reports 2-card combos in almost
every real deck (a go-wide Goblin deck carries dozens). For a creature-LED deck those
combos are a SECONDARY win condition — the deck still wins by attacking — so combo
*presence* must NOT by itself flip the shape to "combo" (which would size the role
template for a combo-PRIMARY deck). Shape captures the primary plan; the combo is still
counted on the win-conditions axis and policed by the bracket gate elsewhere.
"""

from mtg_utils._tuner.classify import CardClass
from mtg_utils._tuner.shape import infer_shape


def _cc(name, *, creature, cmc=2.0, roles=()):
    type_line = "Creature — Test" if creature else "Instant"
    return CardClass(
        name=name,
        bucket="engine",
        roles=tuple(roles),
        served=(),
        dual_purpose=False,
        cmc=cmc,
        record={"name": name, "type_line": type_line},
    )


def test_secondary_combo_does_not_flip_creature_dense_deck_to_combo():
    # Reproduces real Edgar Markov: 60% creatures, avg MV ~2.7, a moderate (not
    # maxed) low-drop count. The pre-fix flat +4.0 combo bonus beat the ~2.8 aggro
    # score and mislabeled this aggressive tribal deck "combo". Creatures are the
    # primary plan here; the combo is a secondary win condition and must not flip
    # the shape (the deck wants aggro scaffolding, not combo-deck protection).
    creatures = [
        _cc(f"C{i}", creature=True, cmc=(2.0 if i < 3 else 3.5)) for i in range(6)
    ]
    others = [
        _cc(f"S{i}", creature=False, cmc=(2.0 if i < 1 else 3.5)) for i in range(4)
    ]
    classes = creatures + others  # 6/10 creatures, 4 low-drops (lowf 0.4)
    r = infer_shape(classes, avg_cmc=2.7, combo_present=True)
    assert r.shape != "combo"
    assert r.shape == "aggro"


def test_spell_dense_deck_with_combo_is_combo():
    # 1/12 nonland are creatures — a spell-dense build whose combo IS the plan.
    classes = [_cc("C0", creature=True, cmc=2.0)] + [
        _cc(f"S{i}", creature=False, cmc=2.0) for i in range(11)
    ]
    r = infer_shape(classes, avg_cmc=2.4, combo_present=True)
    assert r.shape == "combo"


def test_moderate_creature_combo_deck_still_reads_combo():
    # ~36% creatures (a dork-heavy cEDH combo deck like Kinnan) stays combo —
    # the gate only excludes clearly creature-LED decks, not every creature.
    classes = [_cc(f"C{i}", creature=True, cmc=2.0) for i in range(9)] + [
        _cc(f"S{i}", creature=False, cmc=2.0) for i in range(16)
    ]  # 9/25 = 36%
    r = infer_shape(classes, avg_cmc=2.4, combo_present=True)
    assert r.shape == "combo"


def test_high_curve_creature_deck_is_not_control():
    # Goreclaw / Gishath: ~56% creatures, high avg MV (ramp/stompy), a little
    # interaction + draw. The avg-MV-driven control term overwhelmed the weak creature
    # penalty and mislabeled these creature decks "control" → board_wipe band (5,7) →
    # the tuner tried to ADD sweepers (Hurricane) into a creature deck. A creature-dense
    # deck is not control just for being expensive.
    creatures = [_cc(f"C{i}", creature=True, cmc=4.0) for i in range(11)]
    spells = [
        _cc("Removal1", creature=False, cmc=3.0, roles=["interaction"]),
        _cc("Removal2", creature=False, cmc=3.0, roles=["interaction"]),
        _cc("Removal3", creature=False, cmc=3.0, roles=["interaction"]),
        _cc("Draw1", creature=False, cmc=3.0, roles=["card_draw"]),
        _cc("Draw2", creature=False, cmc=3.0, roles=["card_draw"]),
        _cc("Draw3", creature=False, cmc=3.0, roles=["card_draw"]),
    ]
    classes = creatures + spells  # 11/17 = 65% creatures, avg MV ~3.9
    r = infer_shape(classes, avg_cmc=3.9, combo_present=False)
    assert r.shape != "control"


def test_wrath_heavy_lowcurve_deck_is_not_aggro():
    # Heliod lifegain: ~47% creatures, low avg MV, but 4 board wipes + pillowfort. The
    # low curve made aggro win, narrowing board_wipe to (1,2) → the tuner CUT Wrath of
    # God / Fumigate. A deck running several sweepers is not aggro.
    creatures = [_cc(f"C{i}", creature=True, cmc=2.0) for i in range(7)]
    wipes = [
        _cc(f"Wrath{i}", creature=False, cmc=4.0, roles=["board_wipe", "interaction"])
        for i in range(4)
    ]
    others = [_cc(f"S{i}", creature=False, cmc=2.0) for i in range(4)]
    classes = creatures + wipes + others  # 7/15 creatures, avg MV ~2.7, 4 wipes
    r = infer_shape(classes, avg_cmc=2.7, combo_present=False)
    assert r.shape != "aggro"


def test_genuine_control_still_reads_control():
    # Low creature count, interaction-dense, higher curve → still control (the fix must
    # not flip a real control deck to midrange).
    creatures = [_cc(f"C{i}", creature=True, cmc=3.0) for i in range(3)]
    interaction = [
        _cc(f"I{i}", creature=False, cmc=3.0, roles=["interaction"]) for i in range(9)
    ]
    draw = [
        _cc(f"D{i}", creature=False, cmc=3.0, roles=["card_draw"]) for i in range(6)
    ]
    classes = creatures + interaction + draw  # 3/18 = 17% creatures
    r = infer_shape(classes, avg_cmc=3.4, combo_present=False)
    assert r.shape == "control"


def test_genuine_low_curve_aggro_still_reads_aggro():
    # A low-curve creature deck with no sweepers stays aggro (the curve + wipe penalties
    # must not over-suppress real aggro).
    creatures = [_cc(f"C{i}", creature=True, cmc=1.5) for i in range(9)]
    others = [_cc(f"S{i}", creature=False, cmc=1.5) for i in range(3)]
    classes = creatures + others  # 9/12 = 75% creatures, avg MV 1.5, 0 wipes
    r = infer_shape(classes, avg_cmc=1.6, combo_present=False)
    assert r.shape == "aggro"
