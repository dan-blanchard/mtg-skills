"""ADR-0040 §2/§5 (task #97): the curated ability-quality table.

Granter value = granted-ability quality relative to cost, never body or
playrate. Grades are CR-grounded: outlast is tap-gated sorcery-speed growth
(CR 702.107a — Dan's Q2: "not a very good one, because it requires
tapping"); exalted is a real attacks-alone combat boost (CR 702.83a — First
Sliver's Chosen is NOT a correct cut); defender prohibits attacking (CR
702.3); mass infect converts damage to poison, lethal at ten (CR 702.90b /
104.3d) — a closer. Closer flags per ADR-0040 §5: double strike /
team-unblockable yes; vigilance / first strike no; haste no on its own.
"""

from mtg_utils._deck_forge.crosswalk_signals import GrantPayload
from mtg_utils._tuner.ability_quality import grade_of, grant_grade


def _pay(keyword, raw="", kind="keyword"):
    return GrantPayload(
        keyword=keyword,
        scope="you",
        subject=("creature", "sliver"),
        raw=raw,
        kind=kind,
    )


def test_table_grades_and_closer_flags():
    assert grade_of("double strike") == ("premium", True)
    assert grade_of("infect") == ("premium", True)
    assert grade_of("flying") == ("premium", False)
    assert grade_of("first strike") == ("solid", False)
    assert grade_of("vigilance") == ("solid", False)
    assert grade_of("haste") == ("solid", False)
    assert grade_of("exalted") == ("solid", False)
    assert grade_of("outlast") == ("weak", False)
    assert grade_of("defender") == ("weak", False)


def test_unknown_keyword_defaults_solid_never_condemns():
    # The table is curated, not exhaustive — an ungraded keyword must never
    # push a Granter into the cut queue on table absence alone.
    assert grade_of("some future keyword") == ("solid", False)


def test_ability_grants_default_solid():
    # A granted activated ability (Scuttling Sliver) has no table row; it is
    # utility the table can't grade — solid by default, misleads corrected
    # by predicates as they are observed (the grow-predicates direction).
    assert grant_grade([_pay("", kind="ability")]) == "solid"


def test_card_grade_is_best_payload():
    pays = [_pay("outlast"), _pay("double strike")]
    assert grant_grade(pays) == "premium"


def test_hellbent_predicate_demotes_under_draw_engine():
    # ADR-0040 §2's first observed mislead: Bladeback Sliver's hellbent-gated
    # grant under a draw-engine commander (Sliver Weftwinder draws a card per
    # Sliver ETB — the hand never empties). Real oracle sentence as raw.
    raw = (
        "Hellbent — As long as you have no cards in hand, Sliver creatures "
        'you control have "{T}: This creature deals 1 damage to target '
        'player or planeswalker."'
    )
    hellbent = _pay("", raw=raw, kind="ability")
    assert grant_grade([hellbent], draw_engine_commander=True) == "weak"
    # Without the draw engine the gate is reachable — base grade stands.
    assert grant_grade([hellbent]) == "solid"


def test_no_payloads_is_not_a_granter():
    assert grant_grade([]) is None
