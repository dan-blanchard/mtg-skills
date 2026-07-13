"""task #92 — the KNOWN-TOKENS SUBSTRATE.

phase's Token effect node for a PREDEFINED token (Saproling, Mutagen, the WOE
Role cycle, ...) carries only the token's printed body; when its ability is
an activated cost or a granted trigger phase's static-ability parser doesn't
decompose, the Token node is a bare shell with no ``static_abilities``/
``keywords`` at all. ``_ir_lookup._known_token_trees`` closes that gap for an
ADJUDICATED allowlist of token identities (``Mutagen``, ``Young Hero``) by
joining the source card's ``metadata.related_token_ids`` to phase's own
``known-tokens.toml`` data and appending one extra zero-unit text-only
``ConceptTree`` per matched token — the SAME per-oid tuple :func:`trees_for`
already returns, so every existing lane reading "does ANY tree do X" picks
this up for free.

Unit tests below monkeypatch ``_known_tokens_index`` directly (a small literal
dict) — no real toml, no network, fully deterministic. The two integration
tests at the bottom run the REAL committed mirror schema against the two
representative real cards pinned in ``crosswalk_fixture_cards.json``
(Michelangelo, Weirdness to 11 / Cut In) and assert the production
``extract_crosswalk_signals`` path actually fires ``plus_one_makers`` off the
synthesized token tree — plus a THIRD pinned card, Ozox, the Clattering King,
whose Jumblebones token is fully ad-hoc (no known-tokens.toml join at all,
``metadata`` carries no ``related_token_ids``) and already fires the
``graveyard-return`` preset concept via ordinary structural descent, with
zero code from this task — a regression pin for that finding.
"""

from __future__ import annotations

import json
from functools import lru_cache

import pytest

from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._card_ir.overlay_corrections import apply_overlay_corrections
from mtg_utils._card_ir.tree_synthesis import apply_tree_synthesis
from mtg_utils._deck_forge import _ir_lookup as il
from mtg_utils._deck_forge.crosswalk_signals import (
    extract_crosswalk_signals,
    graveyard_return_direction,
)

FIXTURE = "crosswalk_fixture_cards.json"

_MUTAGEN_ID = "mutagen-test-id"
_MUTAGEN_ENTRY = {
    "display_name": "Mutagen",
    "rules_text": (
        "{1}, {T}, Sacrifice this token: Put a +1/+1 counter on target "
        "creature. Activate only as a sorcery."
    ),
    "core_types": ("Artifact",),
    "subtypes": ("Mutagen",),
    "supertypes": (),
}
_YOUNG_HERO_ID = "young-hero-test-id"
_YOUNG_HERO_ENTRY = {
    "display_name": "Young Hero",
    "rules_text": (
        'Enchant creature\nEnchanted creature has "Whenever this creature '
        "attacks, if its toughness is 3 or less, put a +1/+1 counter on "
        'it."'
    ),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura", "Role"),
    "supertypes": (),
}
_TREASURE_ID = "treasure-test-id"
_TREASURE_ENTRY = {
    "display_name": "Treasure",
    "rules_text": "{T}, Sacrifice this token: Add one mana of any color.",
    "core_types": ("Artifact",),
    "subtypes": ("Treasure",),
    "supertypes": (),
}


@pytest.fixture(autouse=True)
def _clean_caches():
    il.clear_caches()
    yield
    il.clear_caches()


def _index(*entries: tuple[str, dict]) -> dict:
    return dict(entries)


def _token_node(name: str, *, statics=None, keywords=None) -> dict:
    node = {"type": "Token", "name": name}
    if statics is not None:
        node["static_abilities"] = statics
    if keywords is not None:
        node["keywords"] = keywords
    return node


def _rec(name: str, related_ids: list[str], token_node: dict) -> dict:
    return {
        "name": name,
        "metadata": {"related_token_ids": related_ids},
        "triggers": [{"execute": {"effect": token_node}}],
    }


# ── unit tests: the join + gate logic, no real toml/network ────────────────


def test_wires_mutagen_by_exact_name(monkeypatch):
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_MUTAGEN_ID, _MUTAGEN_ENTRY))
    )
    rec = _rec("X", [_MUTAGEN_ID], _token_node("Mutagen"))
    trees = il._known_token_trees(rec, oracle_id="oid1")
    assert len(trees) == 1
    tree = trees[0]
    assert tree.name == "Mutagen"
    assert tree.oracle_id == "oid1"
    assert tree.units == ()
    assert "+1/+1 counter" in tree.oracle
    assert tree.card_types == ("Artifact",)
    assert tree.card_subtypes == ("Mutagen",)


def test_wires_young_hero_stripping_role_suffix(monkeypatch):
    """phase's Token node carries the FULL subtype suffix ("Young Hero
    Role"); the toml's ``display_name`` is just "Young Hero" — the join
    must strip the trailing " Role" to match."""
    monkeypatch.setattr(
        il,
        "_known_tokens_index",
        lambda: _index((_YOUNG_HERO_ID, _YOUNG_HERO_ENTRY)),
    )
    rec = _rec("Cut In", [_YOUNG_HERO_ID], _token_node("Young Hero Role"))
    trees = il._known_token_trees(rec, oracle_id="oid2")
    assert len(trees) == 1
    assert trees[0].name == "Young Hero"
    assert "put a" in trees[0].oracle
    assert "+1/+1 counter" in trees[0].oracle


def test_non_wired_display_name_is_skipped(monkeypatch):
    """A real known-tokens.toml match (Treasure) that is NOT on the
    adjudicated allowlist contributes nothing — the corpus-discipline gate
    (task #92's own sweep found ~30 identities; only Mutagen/Young Hero are
    wired this task)."""
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_TREASURE_ID, _TREASURE_ENTRY))
    )
    rec = _rec("Alchemist's Talent", [_TREASURE_ID], _token_node("Treasure"))
    assert il._known_token_trees(rec, oracle_id="oid3") == []


def test_gap_gate_skips_when_phase_already_parsed_static_abilities(monkeypatch):
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_MUTAGEN_ID, _MUTAGEN_ENTRY))
    )
    rec = _rec(
        "X",
        [_MUTAGEN_ID],
        _token_node("Mutagen", statics=[{"mode": "CantBlock"}]),
    )
    assert il._known_token_trees(rec, oracle_id="oid4") == []


def test_gap_gate_skips_when_phase_already_parsed_keywords(monkeypatch):
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_MUTAGEN_ID, _MUTAGEN_ENTRY))
    )
    rec = _rec("X", [_MUTAGEN_ID], _token_node("Mutagen", keywords=["Flying"]))
    assert il._known_token_trees(rec, oracle_id="oid5") == []


def test_empty_without_related_token_ids(monkeypatch):
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_MUTAGEN_ID, _MUTAGEN_ENTRY))
    )
    rec = {"name": "X", "triggers": [{"execute": {"effect": _token_node("Mutagen")}}]}
    assert il._known_token_trees(rec, oracle_id="oid6") == []


def test_empty_when_known_tokens_index_unavailable(monkeypatch):
    monkeypatch.setattr(il, "_known_tokens_index", lambda: None)
    rec = _rec("X", [_MUTAGEN_ID], _token_node("Mutagen"))
    assert il._known_token_trees(rec, oracle_id="oid7") == []


def test_dedupes_repeated_matches_within_one_rec(monkeypatch):
    """Mutagen Man creates MULTIPLE Mutagen tokens off one Token node
    (``count`` handles the ``X`` copies) — but a hypothetical rec with two
    SEPARATE Token nodes for the same predefined token must still yield
    only one tree, not two."""
    monkeypatch.setattr(
        il, "_known_tokens_index", lambda: _index((_MUTAGEN_ID, _MUTAGEN_ENTRY))
    )
    rec = {
        "name": "X",
        "metadata": {"related_token_ids": [_MUTAGEN_ID]},
        "triggers": [
            {"execute": {"effect": _token_node("Mutagen")}},
            {"execute": {"effect": _token_node("Mutagen")}},
        ],
    }
    trees = il._known_token_trees(rec, oracle_id="oid8")
    assert len(trees) == 1


# ── integration: real fixture cards through the whole pipeline ─────────────


@lru_cache(maxsize=1)
def _fixture_records() -> dict[str, dict]:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return json.loads(path.read_text())["cards"]


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


def _signals_for(rec: dict, entry: dict, monkeypatch: pytest.MonkeyPatch) -> list:
    """Build the real per-oid tree tuple for ``rec``, with the known-tokens
    index faked to map EVERY id in ``rec``'s OWN ``related_token_ids``
    (whatever real toml ids the fixture card carries) to ``entry`` — the
    actual display-name JOIN (Token node name -> ``display_name``) still
    runs for real, unmocked. Assigning the same entry to every related id is
    harmless even for a card with several (Cut In's real two WOE Role ids):
    the join discriminates on the Token node's own printed name, and the
    per-tree dedupe collapses any repeats."""
    oid = rec.get("scryfall_oracle_id") or rec["name"]
    related_ids = (rec.get("metadata") or {}).get("related_token_ids") or []
    known_index = dict.fromkeys(related_ids, entry)
    monkeypatch.setattr(il, "_known_tokens_index", lambda: known_index)
    trees = il.build_trees(oid, [rec])
    sigs = []
    for tree in trees:
        corrected = apply_tree_synthesis(apply_overlay_corrections(tree))
        sigs.extend(extract_crosswalk_signals(corrected, keywords=frozenset()))
    return sigs


def test_michelangelo_mutagen_cycle_fires_plus_one_makers(monkeypatch):
    rec = _fixture_records()["Michelangelo, Weirdness to 11"]
    keys = {s.key for s in _signals_for(rec, _MUTAGEN_ENTRY, monkeypatch)}
    assert "plus_one_makers" in keys


def test_cut_in_young_hero_cycle_fires_plus_one_makers(monkeypatch):
    rec = _fixture_records()["Cut In"]
    keys = {s.key for s in _signals_for(rec, _YOUNG_HERO_ENTRY, monkeypatch)}
    assert "plus_one_makers" in keys


def test_ozox_jumblebones_graveyard_return_needs_no_known_tokens_work():
    """Ozox's Jumblebones token is fully AD-HOC (its whole granted trigger,
    including the "return ... to your hand" clause, is spelled out inline
    on Ozox's own Token effect node) — ``metadata`` carries no
    ``related_token_ids`` at all, so this substrate contributes nothing
    here, and none is needed: the existing generic ``iter_typed_nodes``
    descent already reaches the nested GrantTrigger's ChangeZone. Pinned as
    a regression: a future change to that generic walk must not silently
    stop reaching a Token's own static_abilities."""
    rec = _fixture_records()["Ozox, the Clattering King"]
    assert (rec.get("metadata") or {}).get("related_token_ids") in (None, [])
    tree = build_concept_tree(
        strict_load_card(rec, _schema(), name=rec["name"]),
        name=rec["name"],
        oracle_id=rec.get("scryfall_oracle_id") or "",
    )
    assert graveyard_return_direction(tree) is True
