"""Ident->ability provenance seam (Rate v2 S0, task #9).

Pair rows match flat "key|scope|subject" idents with no join back to the
ability that emitted them — both Rate v2 gate-(b) reviews verified this
as the blocker for limiter discounts and per-ability tiebreak keys. The
seam attributes idents per unit by re-running the crosswalk extraction
over SINGLE-UNIT tree views (dataclasses.replace(tree, units=(u,))),
with INTERSECTION semantics: an ident is attributed to unit u iff the
single-unit view emits it AND the full extraction (the truth) contains
it. Idents no single-unit view emits (cross-unit lanes, record-derived
cost idents, membership-floor grants) stay UNATTRIBUTED — consumers must
treat unattributed as no-evidence (no discount, no per-ability key).

Every case runs real committed-snapshot IR (ADR-0027/0039).
"""

from __future__ import annotations

import pytest

from mtg_utils._deck_forge.ident_provenance import unit_idents_for
from mtg_utils.testkit import test_card, test_card_ir


def _attribution(name: str) -> dict:
    test_card_ir(name)
    return unit_idents_for(test_card(name))


def test_multi_ability_card_attributes_to_distinct_units():
    # Myr Galvanizer: the untap engine lives on the {1},{T} ability, the
    # anthem on the static — distinct units, distinct attributions.
    attr = _attribution("Myr Galvanizer")
    untap_units = [k for k, ids in attr.items() if "untap_engine|you|Myr" in ids]
    anthem_units = [k for k, ids in attr.items() if "anthem_static|you|Myr" in ids]
    assert untap_units
    assert anthem_units
    assert set(untap_units).isdisjoint(anthem_units)


def test_attribution_is_subset_of_full_idents():
    # Intersection semantics: no single-unit view may attribute an ident
    # the full extraction does not contain.
    from mtg_utils.theme_presets import _signal_idents_for

    for name in ("Myr Galvanizer", "Siege-Gang Lieutenant", "Krenko, Mob Boss"):
        test_card_ir(name)
        full = set(_signal_idents_for(test_card(name)))
        attr = unit_idents_for(test_card(name))
        for ids in attr.values():
            assert ids <= full, (name, ids - full)


def test_record_derived_ident_stays_unattributed():
    # xcost_spell is read off the mana cost, not any unit — it must not
    # appear in any unit's attribution.
    test_card_ir("Stroke of Genius")
    attr = unit_idents_for(test_card("Stroke of Genius"))
    assert all("xcost_spell|you|" not in ids for ids in attr.values())


def test_single_unit_card_attributes_everything_it_can():
    # Thousand-Year Elixir's untap engine attributes to its ability unit.
    attr = _attribution("Thousand-Year Elixir")
    assert any("untap_engine|you|" in ids for ids in attr.values())


@pytest.mark.parametrize(
    "name",
    [
        ("Myr Galvanizer"),
        ("Siege-Gang Lieutenant"),
        ("Thousand-Year Elixir"),
        ("Stroke of Genius"),
    ],
)
def test_provenance_pin_is_snapshot_resident(name):
    test_card_ir(name)
    assert test_card(name)["name"] == name


def test_keys_are_tree_and_unit_ordinals():
    attr = _attribution("Myr Galvanizer")
    for key in attr:
        ti, ui = key
        assert isinstance(ti, int)
        assert isinstance(ui, int)
