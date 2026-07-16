"""Grant-covered roles (ADR-0040 §1): structural per-body draw-grant read."""

from mtg_utils import testkit
from mtg_utils._tuner.grant_coverage import covered_roles


def test_weftwinder_grant_covers_card_draw():
    # Sliver Weftwinder: "Sliver creatures you control have 'When this
    # creature enters, conjure a random card from the Slivers Spellbook
    # into the top five cards of your library at random, then draw a
    # card.'" — a per-Sliver-body repeatable draw grant (CR 603.6a fires
    # once per Sliver that enters), the ADR-0040 motivating benchmark.
    testkit.test_card_ir("Sliver Weftwinder")  # seeds the crosswalk trees memo
    weftwinder = testkit.test_card("Sliver Weftwinder")
    assert covered_roles([weftwinder]) == {"card_draw": "Sliver Weftwinder"}


def test_own_cast_trigger_draw_is_not_a_grant():
    # Beast Whisperer draws off its OWN cast trigger ("Whenever you cast a
    # creature spell, draw a card.") — real card advantage, but not a
    # GRANT to a creature board; every other Spine role already counts it
    # as card_draw via role_of. Must not double-count as grant coverage.
    testkit.test_card_ir("Beast Whisperer")
    beast_whisperer = testkit.test_card("Beast Whisperer")
    assert covered_roles([beast_whisperer]) == {}


def test_keyword_grant_with_no_draw_is_not_covered():
    # Goblin Warchief grants a genuine creature-board ability ("Goblins you
    # control have haste") — a real Granter (ADR-0040 §2's separate value
    # axis) — but the grant is a bare AddKeyword, not a GrantTrigger, and
    # carries no Draw. The creature-board gate alone must not false-fire.
    testkit.test_card_ir("Goblin Warchief")
    warchief = testkit.test_card("Goblin Warchief")
    assert covered_roles([warchief]) == {}


def test_no_oracle_id_degrades_to_uncovered():
    # A synthetic fixture with no oracle_id resolves no concept trees
    # (trees_for's own documented degrade) — never a crash.
    assert covered_roles([{"name": "Nonesuch"}]) == {}


def test_first_covering_commander_wins_partner_pair():
    testkit.test_card_ir("Sliver Weftwinder")
    testkit.test_card_ir("Goblin Warchief")
    weftwinder = testkit.test_card("Sliver Weftwinder")
    warchief = testkit.test_card("Goblin Warchief")
    assert covered_roles([warchief, weftwinder]) == {"card_draw": "Sliver Weftwinder"}
