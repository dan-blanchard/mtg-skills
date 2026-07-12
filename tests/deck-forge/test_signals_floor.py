"""The membership / cares-about FLOOR — behavior pins on the crosswalk path.

Moved out of ``test_crosswalk_cutover.py`` (ADR-0039 task #80 step 7) and named
for what it tests now: the broad "commander cares about X" floor (a vanilla
Enchantment → enchantments_matter, an Artifact → artifacts_matter, an
Equipment / big body → voltron_matters, an own-subtype / token-profile tribe →
type_matters) that ``apply_membership_floor`` opens under
``include_membership=True`` (the commander-only gate), and the step-3-rewired
structural detectors it reads off the concept tree (big_mana / kill_engine /
token-maker subjects / land_destruction).

Step 7 retired the old file's LEGACY-baseline comparisons along with the
``project_card`` builder they compared against: the full-floor
``extract_signals_ir(include=True) - extract_signals_ir(include=False)`` GATE
(its whole definition was "the legacy reader's floor delta" — with the legacy
projection gone the comparison has no subject) and the per-pin
``_is_big_mana_ir`` / ``_is_kill_engine_ir`` legacy-projection cross-checks
(each pin's tree-reader assertion — the load-bearing half — is preserved
verbatim below, with its original adjudication docstring). The DFC
floor-to-merge pins at the bottom run the REAL production ``test_signals``.

CI-safe: single-face cases come from the committed
``crosswalk_fixture_cards.json`` phase records + the committed mirror schema;
the DFC multi-face pins use the committed ``mtg_utils.testkit`` card snapshot
(which stores TWO phase records sharing one oracle_id, keyed by name, for
exactly this purpose) — no bulk / sidecar / phase / network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache

import pytest

from mtg_utils._card_ir.crosswalk import build_concept_tree
from mtg_utils._card_ir.mirror import strict_load_card
from mtg_utils._card_ir.mirror.build import fixtures_dir, load_committed_schema
from mtg_utils._card_ir.tree_synthesis import has_structural_kill_engine
from mtg_utils._deck_forge import _ir_lookup as il
from mtg_utils._deck_forge._subtypes import CREATURE_SUBTYPES
from mtg_utils._deck_forge.crosswalk_signals import (
    _floor_token_maker_subjects,
    _is_big_mana_tree,
)
from mtg_utils._deck_forge.signals import extract_signals_hybrid
from mtg_utils.testkit import test_signals

FIXTURE = "crosswalk_fixture_cards.json"


def _returns(value: object) -> Callable[..., object]:
    """A monkeypatch stand-in that ignores its args and returns ``value``."""

    def _fn(*_args: object, **_kwargs: object) -> object:
        return value

    return _fn


@lru_cache(maxsize=1)
def _fixture_records() -> list[dict]:
    path = fixtures_dir() / FIXTURE
    if not path.exists():
        pytest.skip(f"{FIXTURE} not present")
    return list(json.loads(path.read_text())["cards"].values())


@lru_cache(maxsize=1)
def _schema():
    return load_committed_schema()


@pytest.fixture(autouse=True)
def _clean_caches():
    """Every test starts with the memoized indexes / trees memo cleared."""
    il.clear_caches()
    yield
    il.clear_caches()


@lru_cache(maxsize=1)
def _faces_by_oid() -> dict[str, list[dict]]:
    """Fixture phase face-records grouped by oracle_id."""
    out: dict[str, list[dict]] = {}
    for rec in _fixture_records():
        oid = rec.get("scryfall_oracle_id")
        if oid:
            out.setdefault(oid, []).append(rec)
    return out


def _floor_case(oid: str, faces: list[dict]):
    """Build (bulk_record, concept_tree) for a fixture card, or None when the
    phase record drifts. The bulk record's ``type_line`` is reconstructed from
    the tree's typed supertype/type/subtype fields so the membership floor
    reads the REAL card types (the fixture carries no Scryfall type_line).
    (ADR-0039 step 7: the tuple's third element — the legacy ``project_card``
    IR — died with the builder.)"""
    nm = faces[0].get("name") or ""
    try:
        root = strict_load_card(faces[0], _schema(), name=nm)
        tree = build_concept_tree(root, name=nm, oracle_id=oid)
    except Exception:  # noqa: BLE001 — skip drift/odd cards
        return None
    parts = list(tree.card_supertypes) + list(tree.card_types)
    type_line = " ".join(parts)
    if tree.card_subtypes:
        type_line += " — " + " ".join(tree.card_subtypes)
    bulk = {
        "oracle_id": oid,
        "name": nm,
        "oracle_text": faces[0].get("oracle_text") or "",
        "type_line": type_line,
        "keywords": [],
        "cmc": tree.cmc,
    }
    return bulk, tree


def _hybrid_idents(monkeypatch, bulk, tree, *, include: bool):
    """Every signal ident from ``extract_signals_hybrid`` (the crosswalk-only
    path), wiring the crosswalk seam to the fixture tree."""
    monkeypatch.setattr(il, "trees_for", _returns((tree,)))
    sigs = extract_signals_hybrid(bulk, include_membership=include)
    return {(s.key, s.scope, s.subject) for s in sigs}


def _floor_case_for(name: str):
    """A single named fixture card's floor case (see :func:`_floor_case`), or
    ``None`` if the card isn't present / drifts."""
    for oid, faces in _faces_by_oid().items():
        if faces and faces[0].get("name") == name:
            return _floor_case(oid, faces)
    return None


# ── ADR-0039 task #80 step 3 — the membership floor's rewired detectors ──────
# Direct unit pins for the structural facts ``_apply_membership_floor`` used to
# read off the OLD projected ``Card`` and now reads off the concept tree
# instead, one detector at a time. Each pin was originally verified against the
# LEGACY reader over the SAME real card (positive: the legacy reader also
# fired; negative: neither reader fired) — the mechanism moved, membership did
# not. Step 7 deleted the legacy projection, so the tree-reader assertion is
# the surviving pin; each docstring keeps the original adjudication record.


def test_land_destruction_promoted_floor(monkeypatch):
    """ADR-0039 W8 (land_destruction PROMOTED off the KEPT twelve): the
    shared ``_apply_membership_floor`` (imported by BOTH ``extract_signals_
    ir`` and ``crosswalk_signals.apply_membership_floor``, one source, zero
    drift) fires land_destruction for a CREATURE commander whose own oracle
    matches "destroy target land(s)" (Goblin Settler — "When this creature
    enters, destroy target land", CR 305.6) under ``include_membership=True``
    on the crosswalk hybrid path, and fires on neither path with
    ``include_membership=False`` (the 99-card candidate-mode gate)."""
    built = _floor_case_for("Goblin Settler")
    if built is None:
        pytest.skip("Goblin Settler fixture record drifts")
    bulk, tree = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("land_destruction", "you", "") in on_cmd
    on_99 = _hybrid_idents(monkeypatch, bulk, tree, include=False)
    assert "land_destruction" not in {k for k, _s, _su in on_99}


def test_big_mana_promoted_floor(monkeypatch):
    """ADR-0039 W8 (big_mana PROMOTED off the KEPT twelve): Sol Ring's
    ``{T}: Add {C}{C}`` fires the shared ``_apply_membership_floor``'s
    big_mana arm via ``_is_big_mana_tree`` (reading the magnitude off the
    concept tree's ``ramp`` effect-concept, ADR-0039 task #80 step 3) under
    ``include_membership=True`` on the crosswalk hybrid path."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    bulk, tree = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("big_mana", "you", "") in on_cmd


def test_is_big_mana_tree_direct_ramp_effect():
    """Positive, direct ramp effect: Sol Ring's ``{T}: Add {C}{C}`` is a
    ``ramp`` effect concept whose typed ``produced`` is
    ``Colorless(count=Fixed(2))`` — factor > 1 (CR 106.4). Originally also
    matched the legacy ``_is_big_mana_ir`` reader on the SAME card's legacy
    projection (that comparison arm died with project_card, step 7)."""
    built = _floor_case_for("Sol Ring")
    if built is None:
        pytest.skip("Sol Ring fixture record drifts")
    _bulk, tree = built
    assert _is_big_mana_tree(tree) is True


def test_is_big_mana_tree_granted_mana_ability():
    """Positive, GRANTED mana ability: Discreet Retreat's Aura grants
    enchanted land "{T}: Add two mana of any one color" — the magnitude
    lives on the granted ``GrantAbility`` definition's own effect
    (:func:`_granted_mana_defs`), not a direct ``ramp`` effect concept on
    Discreet Retreat's own ability (``tree.effect_concepts("ramp")`` is
    empty for this card — verified this session). Originally also matched
    the legacy ``_is_big_mana_ir`` reader on the SAME card's legacy
    projection (CR 106.4; that comparison arm died with project_card,
    step 7)."""
    built = _floor_case_for("Discreet Retreat")
    if built is None:
        pytest.skip("Discreet Retreat fixture record drifts")
    _bulk, tree = built
    assert not tree.effect_concepts("ramp")
    assert _is_big_mana_tree(tree) is True


def test_is_big_mana_tree_returnasaura_granted_mana_gain():
    """GENUINE recall gain (corpus-adjudicated, ADR-0039 task #80 step 3):
    Harold and Bob, First Numens's ``ReturnAsAura`` effect grants "Enchanted
    Forest has '{T}: Add three mana of any one color...'" — factor 3, CR
    106.4. ``_is_big_mana_tree`` reads it via
    :func:`_iter_returnasaura_mana_defs`; the OLD IR did NOT structure a
    ``ReturnAsAura``-granted ability into a ramp-category ``Effect`` at all,
    so the legacy ``_is_big_mana_ir`` reader's ``ir.all_abilities()`` walk
    found nothing to check — a real gap the old projection had, not
    something this rewire introduced (the legacy-False assertion died with
    project_card, step 7)."""
    built = _floor_case_for("Harold and Bob, First Numens")
    if built is None:
        pytest.skip("Harold and Bob, First Numens fixture record drifts")
    _bulk, tree = built
    assert _is_big_mana_tree(tree) is True


def test_is_big_mana_tree_single_mana_dork_negative():
    """Negative: Llanowar Elves' ``{T}: Add {G}`` is exactly ONE mana —
    factor == 1, not big mana (CR 106.4). Originally also matched the legacy
    ``_is_big_mana_ir`` reader on the SAME card's legacy projection (that
    comparison arm died with project_card, step 7)."""
    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree = built
    assert _is_big_mana_tree(tree) is False


def test_floor_kill_engine_reads_tree_directly():
    """The floor's kill_engine arm now reads ``has_structural_kill_engine``
    off the tree (CR 701.8a: "To destroy a permanent, move it from the
    battlefield to its owner's graveyard") instead of the legacy
    ``_is_kill_engine_ir`` reader off the OLD ``Card`` — verified equivalent
    on a genuine repeatable-destroy engine (Visara the Dreadful's "{2}{B}{B},
    {T}: Destroy target creature.") and a creature with no such ability
    (Llanowar Elves), matching the legacy reader on the SAME cards both
    ways at the time of the step-3 rewire (the legacy comparison arm died
    with project_card, step 7)."""
    built = _floor_case_for("Visara the Dreadful")
    if built is None:
        pytest.skip("Visara the Dreadful fixture record drifts")
    _bulk, tree = built
    assert has_structural_kill_engine(tree) is True

    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree = built
    assert has_structural_kill_engine(tree) is False


def test_floor_token_maker_subjects_directed_raw_mirror():
    """Positive, raw-mirror recovery: "Each player OTHER THAN target player
    creates a 5/5 red Dragon creature token" (Death by Dragons) and "its
    controller creates a 3/3 white Angel creature token" (Soul of
    Emancipation) both leave phase's ``Token`` node ``Unimplemented`` (no
    typed ``types`` field) — the floor cares only that the card's own
    ability NAMES a creature-token subtype (CR 111.2/205.3), not who
    receives it (unlike the ``token_maker`` KEY lane's own directed-gift
    exclusion), so :func:`_floor_token_maker_subjects` recovers both via the
    per-concept raw mirror."""
    built = _floor_case_for("Death by Dragons")
    if built is None:
        pytest.skip("Death by Dragons fixture record drifts")
    _bulk, tree = built
    assert "Dragon" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)

    built = _floor_case_for("Soul of Emancipation")
    if built is None:
        pytest.skip("Soul of Emancipation fixture record drifts")
    _bulk, tree = built
    assert "Angel" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)


def test_floor_token_maker_subjects_structural_no_mirror_needed():
    """Positive, purely structural: Krenko, Mob Boss's own "create X 1/1 red
    Goblin creature tokens" resolves via phase's typed ``Token.types`` field
    directly — no raw-mirror fallback needed."""
    built = _floor_case_for("Krenko, Mob Boss")
    if built is None:
        pytest.skip("Krenko, Mob Boss fixture record drifts")
    _bulk, tree = built
    assert "Goblin" in _floor_token_maker_subjects(tree, CREATURE_SUBTYPES)


def test_floor_token_maker_subjects_no_maker_negative():
    """Negative: Llanowar Elves makes no tokens at all — the empty set,
    matching the legacy reader's ``ir.all_abilities()`` walk on the same
    card (at the step-3 rewire; the legacy walk died with project_card,
    step 7)."""
    built = _floor_case_for("Llanowar Elves")
    if built is None:
        pytest.skip("Llanowar Elves fixture record drifts")
    _bulk, tree = built
    assert _floor_token_maker_subjects(tree, CREATURE_SUBTYPES) == set()


def test_type_matters_go_wide_arm_vi_dropped_in_commander_mode(monkeypatch):
    """The dropped ``_type_matters_go_wide`` arm (vi) reproduced a KNOWN
    old-IR hallucination (a synthetic board_count ability fabricated for
    Elvish Berserker's Rampage "for each creature blocking it") — already
    adjudicated a SHED for candidate mode
    (``test_type_matters_go_wide_rampage_shed_not_ported``,
    tests/mtg-utils/test_crosswalk.py). This pins the SAME adjudication in
    ``include_membership=True`` COMMANDER mode too: the crosswalk path never
    reproduces the class-tribe Berserker lane the legacy reader's
    hallucination fires. Elvish Berserker's own RACE tribe (Elf) fires
    regardless (CR 205.3/702.23)."""
    built = _floor_case_for("Elvish Berserker")
    if built is None:
        pytest.skip("Elvish Berserker fixture record drifts")
    bulk, tree = built
    on_cmd = _hybrid_idents(monkeypatch, bulk, tree, include=True)
    assert ("type_matters", "you", "Elf") in on_cmd
    assert ("type_matters", "you", "Berserker") not in on_cmd


# ── ADR-0039 task #80 step 6 — the DFC floor-to-merge move ───────────────────
# The membership floor used to run PER FACE inside ``extract_crosswalk_signals``,
# so a two-face card whose qualifying ability lives on a DIFFERENT face than its
# creature type lost the floor's class-tribe / kill_engine cross-opens (step 3's
# documented, accepted gap — see ``crosswalk_signals._floor_token_maker_subjects``'s
# docstring at the time). Moving the floor to run ONCE per card, over every face's
# tree together (``crosswalk_signals.apply_membership_floor``, called from
# ``signals.extract_signals_hybrid``), closes it. These pins use the committed
# ``mtg_utils.testkit`` card snapshot (not ``crosswalk_fixture_cards.json`` — the
# DFC pins need TWO phase records sharing one oracle_id, keyed by name, which the
# testkit snapshot already stores for exactly this purpose) and run the REAL
# production ``test_signals`` — no fixture indirection.


def test_dfc_floor_flaxen_intruder_gains_class_tribe():
    """Flaxen Intruder // Welcome Home: the token-maker ability (making Bear
    tokens) lives on the Adventure face ("Welcome Home"), not the Creature
    face ("Flaxen Intruder" — Human Berserker). Berserker is a CLASS_TRIBES
    entry (CR 205.3), so it only opens behind the go_wide gate — which the
    merge-level union now sees fire from the sibling face's token-maker
    ability. Berserker was the exact card the ``_floor_token_maker_subjects``
    per-face-gap docstring named."""
    sigs = test_signals("Flaxen Intruder // Welcome Home")
    idents = {(s.key, s.subject) for s in sigs}
    assert ("type_matters", "Berserker") in idents


def test_dfc_floor_kianne_imbraham_gains_class_tribe():
    """Kianne, Dean of Substance // Imbraham, Dean of Theory: both faces are
    Creatures (Elf Druid // Bird Wizard), each with its own race tribe
    firing unconditionally; Wizard (Imbraham's class) only opens behind the
    go_wide gate the merge-level union now proves via the sibling face."""
    sigs = test_signals("Kianne, Dean of Substance // Imbraham, Dean of Theory")
    idents = {(s.key, s.subject) for s in sigs}
    assert ("type_matters", "Wizard") in idents
    # Both race tribes still fire unconditionally regardless (CR 205.3).
    assert ("type_matters", "Elf") in idents
    assert ("type_matters", "Bird") in idents


def test_dfc_floor_sheoldred_gains_kill_engine():
    """Sheoldred // The True Scriptures: the repeatable destroy ability (a
    Saga chapter trigger, "destroy up to one target creature or
    planeswalker") lives on the Enchantment — Saga face ("The True
    Scriptures"), never the Creature face ("Sheoldred", which has no
    destroy ability of its own). ``has_structural_kill_engine`` gates on
    ``tree.is_type("Creature")`` per-face, so a bare per-face union can't
    close this — the merge-level ``apply_membership_floor`` separates "is
    ANY face a Creature" from "does ANY face carry the repeatable destroy
    unit" (:func:`_has_repeatable_kill_unit`) and combines them at the
    whole-card level instead (CR 701.8a)."""
    sigs = test_signals("Sheoldred // The True Scriptures")
    assert any(s.key == "kill_engine" for s in sigs)
