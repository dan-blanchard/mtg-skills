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


# ── task #np_roles — the deferred Role identities + the single-creator tail ──
# Entry dicts mirror phase v0.23.0's known-tokens.toml verbatim (the same
# texts the committed fallback carries). Each integration test runs the
# real production pipeline over the pinned fixture creator and asserts the
# wired lane opens; the Monster test pins the ADJUDICATED-OUT decision
# (real durable trample Auras — Rancor, Unflinching Courage — fire no
# keyword-grant key, so the Role token must not either).

_CURSED_ENTRY = {
    "display_name": "Cursed",
    "rules_text": (
        "Enchant creature\nEnchanted creature has base power and toughness 1/1."
    ),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura", "Role"),
    "supertypes": (),
}
_ROYAL_ENTRY = {
    "display_name": "Royal",
    "rules_text": (
        "Enchant creature\nEnchanted creature gets +1/+1 and has ward {1}. "
        "(Whenever this creature becomes the target of a spell or ability "
        "an opponent controls, counter it unless that player pays {1}.)"
    ),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura", "Role"),
    "supertypes": (),
}
_SORCERER_ENTRY = {
    "display_name": "Sorcerer",
    "rules_text": (
        "Enchant creature\nEnchanted creature gets +1/+1 and has "
        '"Whenever this creature attacks, scry 1."'
    ),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura", "Role"),
    "supertypes": (),
}
_MONSTER_ENTRY = {
    "display_name": "Monster",
    "rules_text": ("Enchant creature\nEnchanted creature gets +1/+1 and has trample."),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura", "Role"),
    "supertypes": (),
}
_SHARD_ENTRY = {
    "display_name": "Shard",
    "rules_text": "{2}, Sacrifice this enchantment: Scry 1, then draw a card.",
    "core_types": ("Enchantment",),
    "subtypes": ("Shard",),
    "supertypes": (),
}
_WIZARD_ENTRY = {
    "display_name": "Wizard",
    "rules_text": (
        "{1}, Sacrifice this creature: Counter target noncreature spell "
        "unless its controller pays {1}."
    ),
    "core_types": ("Creature",),
    "subtypes": ("Wizard",),
    "supertypes": (),
}
_CONTRACT_ENTRY = {
    "display_name": "Contract",
    "rules_text": (
        "Enchant creature\nWhenever enchanted creature attacks, it gets "
        "+2/+0 until end of turn if it's attacking one of your opponents. "
        "Otherwise, its controller loses 2 life."
    ),
    "core_types": ("Enchantment",),
    "subtypes": ("Aura",),
    "supertypes": (),
}
_SPELLGORGER_ENTRY = {
    "display_name": "Spellgorger Weird",
    "rules_text": (
        "Whenever you cast a noncreature spell, put a +1/+1 counter on "
        "this creature.\n(This token's mana cost is {2}{R}.)"
    ),
    "core_types": ("Creature",),
    "subtypes": ("Weird",),
    "supertypes": (),
}


def test_cursed_courtier_cursed_role_fires_single_target_neutralize(monkeypatch):
    """Cursed (CR 111.10j) opens the new single_target_neutralize lane via
    the synth_single_target_neutralize marker."""
    rec = _fixture_records()["Cursed Courtier"]
    keys = {s.key for s in _signals_for(rec, _CURSED_ENTRY, monkeypatch)}
    assert "single_target_neutralize" in keys


def test_charmed_clothier_royal_role_fires_protection_grant(monkeypatch):
    """Royal (CR 111.10m) — ward {1} is the suit-up protective grant
    (CR 702.21a), the same key a real ward Aura fires."""
    rec = _fixture_records()["Charmed Clothier"]
    keys = {s.key for s in _signals_for(rec, _ROYAL_ENTRY, monkeypatch)}
    assert "protection_grant" in keys


def test_spellbook_vendor_sorcerer_role_fires_topdeck_selection(monkeypatch):
    """Sorcerer (CR 111.10n) — the granted attack-scry is own-library
    curation (CR 701.22a), read via the synth_topdeck_selection marker."""
    rec = _fixture_records()["Spellbook Vendor"]
    keys = {s.key for s in _signals_for(rec, _SORCERER_ENTRY, monkeypatch)}
    assert "topdeck_selection" in keys


def test_monstrous_rage_monster_role_stays_out_of_keyword_grant_keys(monkeypatch):
    """Monster (CR 111.10k) is ADJUDICATED OUT, not deferred: the display
    name is absent from _KNOWN_TOKEN_WIRED_DISPLAY_NAMES, so even with the
    toml entry present no tree is appended — a Role token must not fire a
    key the real Rancor-class trample Auras don't."""
    rec = _fixture_records()["Monstrous Rage"]
    keys = {s.key for s in _signals_for(rec, _MONSTER_ENTRY, monkeypatch)}
    assert "protection_grant" not in keys
    assert "keyword_grant_target" not in keys


def test_niko_aris_shard_fires_topdeck_selection(monkeypatch):
    """The Shard's fixed 'Scry 1, then draw a card' is a scry DOER —
    topdeck_selection (CR 701.22a). The draw half is a per-token one-shot
    cantrip, which this system deliberately never tags with a draw-doer
    key (Opt fires none)."""
    rec = _fixture_records()["Niko Aris"]
    keys = {s.key for s in _signals_for(rec, _SHARD_ENTRY, monkeypatch)}
    assert "topdeck_selection" in keys


def test_mages_attendant_wizard_fires_counter_control(monkeypatch):
    """The Wizard token's sac-to-Counter (CR 701.6a) emits the REAL
    counter_spell concept — _counter_control reads it with no lane edit."""
    rec = _fixture_records()["Mage's Attendant"]
    keys = {s.key for s in _signals_for(rec, _WIZARD_ENTRY, monkeypatch)}
    assert "counter_control" in keys


def test_scriv_contract_fires_lifeloss_makers_opponents(monkeypatch):
    """The Contract Aura's 'Otherwise, its controller loses 2 life' rides
    the existing synth_lifeloss_makers_opponents marker read (the Wicked
    precedent) — Scriv attaches it to a creature an opponent controls."""
    rec = _fixture_records()["Scriv, the Obligator"]
    idents = {(s.key, s.scope) for s in _signals_for(rec, _CONTRACT_ENTRY, monkeypatch)}
    assert ("lifeloss_makers", "opponents") in idents


def test_ral_implicit_maze_spellgorger_fires_spellcast_matters(monkeypatch):
    """Spellgorger Weird's 'Whenever you cast a noncreature spell...' rides
    the PRE-EXISTING _arm_spellcast_matters bucket-B arm — allowlist-only
    wiring, zero new arm code."""
    rec = _fixture_records()["Ral and the Implicit Maze"]
    keys = {s.key for s in _signals_for(rec, _SPELLGORGER_ENTRY, monkeypatch)}
    assert "spellcast_matters" in keys
