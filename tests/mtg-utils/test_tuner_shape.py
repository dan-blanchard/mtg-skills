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


def _cc(name, *, creature, cmc=2.0):
    type_line = "Creature — Test" if creature else "Instant"
    return CardClass(
        name=name,
        bucket="engine",
        roles=(),
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
