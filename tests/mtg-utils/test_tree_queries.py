"""The gap-predicate vocabulary on ConceptTree (ADR-0047) — six presence reads every
gap-gated arm composes instead of re-walking the tree in its own idiom. Pinned on
real cards from the committed snapshot, through the tree owner."""

from __future__ import annotations

from mtg_utils import testkit
from mtg_utils._card_ir.trees import trees_for


def _tree(name: str):
    testkit._seed_trees(name)
    trees = trees_for(testkit.test_card(name))
    assert trees, name
    return trees[0]


def test_iter_typed_is_the_whole_card_deep_walk():
    tree = _tree("Viscera Seer")
    nodes = list(tree.iter_typed())
    assert nodes
    # every unit's own node is reachable, so nothing is walked twice or skipped
    assert all(any(n is unit.node for n in nodes) for unit in tree.units)


def test_has_typed_reads_any_tag_anywhere():
    seer = _tree("Viscera Seer")  # "Sacrifice a creature: Scry 1."
    assert seer.has_typed("Sacrifice")
    assert seer.has_typed("Nope", "Sacrifice")  # any of the tags
    assert not seer.has_typed("Meld")
    ring = _tree("Sol Ring")
    assert ring.has_typed("Mana")
    assert not ring.has_typed("Sacrifice")


def test_has_concept_narrows_by_role_scope_and_subject():
    seer = _tree("Viscera Seer")
    assert seer.has_concept("sacrifice")
    assert seer.has_concept("sacrifice", role="cost")
    assert not seer.has_concept("sacrifice", role="effect")
    assert not seer.has_concept("sacrifice", scope="opponents")
    assert not seer.has_concept("no-such-concept")


def test_has_trigger_and_has_static_mode_read_unit_metadata():
    seer = _tree("Viscera Seer")
    assert not seer.has_trigger("becomes_target")
    assert not seer.has_static_mode("LegendRuleDoesntApply")
    bears = _tree("Grizzly Bears")
    assert not bears.has_trigger("dies")
    assert not any(u.origin == "trigger" for u in bears.units)


def test_residues_are_phase_unimplemented_descriptions():
    ring = _tree("Sol Ring")
    assert list(ring.residues()) == []
    assert not ring.has_residue()
    assert not ring.has_residue("static_structure")
    # a residue read keyed on a phase ``name`` never matches a fully parsed card
    assert not any(
        t.has_residue("effect_structure")
        for t in trees_for(testkit.test_card("Grizzly Bears"))
    )


def test_is_text_only_marks_a_tree_with_no_phase_unit():
    assert not _tree("Sol Ring").is_text_only
    from mtg_utils._card_ir.crosswalk import ConceptTree

    empty = ConceptTree(name="Face", oracle_id="oid", units=(), oracle="Draw a card.")
    assert empty.is_text_only
    assert not empty.has_typed("Draw")
    assert list(empty.residues()) == []
