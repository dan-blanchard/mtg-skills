"""Tests for the theme_presets module.

Three layers of coverage:

1. Unit tests for the Preset dataclass and registry API.
2. Golden fixture tests: for every KEYWORD preset in PRESETS, iterate its
   should_match / should_not_match tuples and assert matching behavior. The
   card record is the committed real-card snapshot's (``mtg_utils.testkit``:
   the bulk's own keywords and oracle text, never hand-typed;
   `build-card-snapshot` reads the registry's fixture names itself).
3. Structural-view golden fixture tests (task #83): for every preset with
   a non-empty ``signal_keys``/``concept`` (see
   ``TestStructuralPresetsAgainstSnapshot``), the SAME should_match /
   should_not_match tuples are proven against real Scryfall records + real
   crosswalk trees from the same snapshot.
"""

from __future__ import annotations

import os
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from mtg_utils import theme_presets
from mtg_utils.theme_presets import (
    PRESETS,
    Preset,
    get_preset,
    list_presets,
    matches,
)

# ─── Unit tests ────────────────────────────────────────────────────────────


class TestPreset:
    def test_is_frozen(self):
        p = get_preset("flying")
        with pytest.raises(FrozenInstanceError):
            p.name = "other"  # type: ignore[misc]

    def test_matches_by_keyword(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        assert p.matches({"keywords": ["Flying"]}) is True
        assert p.matches({"keywords": ["Vigilance"]}) is False
        assert p.matches({"keywords": []}) is False

    def test_keyword_match_is_case_insensitive(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        assert p.matches({"keywords": ["flying"]}) is True
        assert p.matches({"keywords": ["FLYING"]}) is True

    def test_matches_by_pattern(self):
        p = Preset(
            name="t",
            description="",
            patterns=(re.compile(r"deals? \d+ damage", re.IGNORECASE),),
        )
        assert p.matches({"oracle_text": "Deals 3 damage"}) is True
        assert p.matches({"oracle_text": "Counter target spell."}) is False

    def test_combines_keyword_and_pattern_with_or(self):
        p = Preset(
            name="t",
            description="",
            keywords=("Flying",),
            patterns=(re.compile(r"matches", re.IGNORECASE),),
        )
        assert p.matches({"keywords": ["Flying"], "oracle_text": ""})
        assert p.matches({"keywords": [], "oracle_text": "this matches"})
        assert not p.matches({"keywords": [], "oracle_text": "no"})

    def test_no_keywords_no_patterns_never_matches(self):
        p = Preset(name="t", description="")
        assert p.matches({"keywords": ["Flying"], "oracle_text": "anything"}) is False

    def test_missing_keywords_array_is_safe(self):
        p = Preset(name="t", description="", keywords=("Flying",))
        # No keywords key at all — should treat as empty.
        assert p.matches({}) is False


class TestRegistry:
    def test_has_expected_keyword_presets(self):
        for expected in (
            "flying",
            "vigilance",
            "scry",
            "surveil",
            "flashback",
            "cascade",
            "cycling",
            "kicker",
            "evoke",
            "ninjutsu",
            "exalted",
            "prowess",
            "investigate",
            "landfall",
            "dredge",
            "miracle",
        ):
            assert expected in PRESETS, f"missing keyword preset: {expected}"

    def test_has_expected_functional_presets(self):
        for expected in (
            "top-manipulation",
            "self-mill",
            "counterspell",
            "removal",
            "board-wipe",
            "bounce",
            "discard",
            "tutors",
            "tokens",
            "sacrifice-outlet",
            "burn",
            "reanimate",
            "graveyard-return",
            "cantrip",
            "card-draw",
        ):
            assert expected in PRESETS, f"missing functional preset: {expected}"

    def test_registry_is_immutable(self):
        with pytest.raises(TypeError):
            PRESETS["new"] = Preset(name="new", description="")  # type: ignore[index]

    def test_all_names_unique(self):
        names = [p.name for p in PRESETS.values()]
        assert len(names) == len(set(names))

    def test_all_presets_have_nonempty_description(self):
        for name, p in PRESETS.items():
            assert p.description.strip(), f"preset {name!r} has empty description"

    def test_list_presets_covers_every_registry_entry(self):
        """Guards against accidentally omitting a preset from a group tuple."""
        listed = list_presets()
        assert set(listed.keys()) == set(PRESETS.keys())
        assert len(listed) == len(PRESETS)


class TestApi:
    def test_get_preset_returns_same_object(self):
        p1 = get_preset("flying")
        p2 = get_preset("flying")
        assert p1 is p2

    def test_get_preset_unknown_raises_keyerror(self):
        with pytest.raises(KeyError, match="unknown preset"):
            get_preset("doesnt-exist")

    def test_matches_convenience(self):
        assert matches("flying", {"keywords": ["Flying"]}) is True
        assert matches("flying", {"keywords": []}) is False

    def test_list_presets_returns_sorted_name_to_description(self):
        presets = list_presets()
        names = list(presets.keys())
        assert names == sorted(names)
        # Spot-check a few entries
        assert "flying" in presets
        assert "self-mill" in presets
        for name, desc in presets.items():
            assert isinstance(desc, str), name
            assert desc.strip(), name


# ─── Golden fixture tests ──────────────────────────────────────────────────
#
# Every preset's should_match and should_not_match tuples must hold against
# the committed real-card snapshot (keywords + oracle text as the bulk carries
# them). This catches keyword drift if an Oracle update changes a card.
#
# Structural-view presets (task #83 — non-empty ``signal_keys``/``concept``)
# are EXCLUDED here: their view arm also needs the snapshot's stored phase
# records, so ``TestStructuralPresetsAgainstSnapshot`` below proves them
# against real Scryfall records + real crosswalk trees.

_STRUCTURAL_PRESET_NAMES = frozenset(
    name for name, preset in PRESETS.items() if preset.signal_keys or preset.concept
)


def _get_fixture(card_name: str) -> dict:
    """The record a keyword preset's fixture is proven against: the committed
    real-card snapshot (``mtg_utils.testkit`` — the bulk's own keywords and
    oracle text, never hand-typed; ``build-card-snapshot`` reads every preset's
    should_match / should_not_match itself, so a new fixture name needs only a
    regen)."""
    from mtg_utils import testkit

    try:
        return testkit.test_card(card_name)
    except KeyError as exc:
        msg = (
            f"no snapshot record for {card_name!r}: run `build-card-snapshot` "
            f"(it reads every preset's should_match / should_not_match)."
        )
        raise pytest.fail.Exception(msg) from exc


@pytest.mark.parametrize(
    ("preset_name", "card_name"),
    [
        (name, card)
        for name, preset in PRESETS.items()
        if name not in _STRUCTURAL_PRESET_NAMES
        for card in preset.should_match
    ],
)
def test_preset_should_match(preset_name: str, card_name: str):
    preset = PRESETS[preset_name]
    card = _get_fixture(card_name)
    assert preset.matches(card), (
        f"preset {preset_name!r} should match {card_name!r} but did not.\n"
        f"Card keywords: {card.get('keywords')}\n"
        f"Oracle text: {card.get('oracle_text')!r}"
    )


@pytest.mark.parametrize(
    ("preset_name", "card_name"),
    [
        (name, card)
        for name, preset in PRESETS.items()
        if name not in _STRUCTURAL_PRESET_NAMES
        for card in preset.should_not_match
    ],
)
def test_preset_should_not_match(preset_name: str, card_name: str):
    preset = PRESETS[preset_name]
    card = _get_fixture(card_name)
    assert not preset.matches(card), (
        f"preset {preset_name!r} should NOT match {card_name!r} but did.\n"
        f"Card keywords: {card.get('keywords')}\n"
        f"Oracle text: {card.get('oracle_text')!r}"
    )


# ─── Structural-view golden fixture tests (task #83) ───────────────────────
#
# A structural-view preset's should_match/should_not_match fixtures are
# proven against REAL production signals. This routes through mtg_utils.testkit's committed
# snapshot instead — the same real-Scryfall-record + real-crosswalk-tree
# pattern tests/deck-forge/test_migrated_keys.py uses, CI-safe (no phase
# cache / network; the snapshot carries phase's OWN parse for each card).
# ``testkit.test_card_ir`` seeds ``_ir_lookup``'s trees memo for the name as
# a side effect, so the subsequent ``preset.matches(testkit.test_card(name))``
# resolves its signal_keys arm from the SAME seeded trees, not a live phase
# fetch. A future conversion batch adds should_match/should_not_match names
# to the relevant preset above, then a snapshot-name entry + `build-card-
# snapshot` run (see this file's own docstring / testkit's).

_STRUCTURAL_SHOULD_MATCH = [
    (name, card)
    for name in sorted(_STRUCTURAL_PRESET_NAMES)
    for card in PRESETS[name].should_match
]
_STRUCTURAL_SHOULD_NOT_MATCH = [
    (name, card)
    for name in sorted(_STRUCTURAL_PRESET_NAMES)
    for card in PRESETS[name].should_not_match
]


class TestStructuralPresetsAgainstSnapshot:
    """should_match/should_not_match for signal_keys/concept presets, proven
    against the committed real-card snapshot (mtg_utils.testkit)."""

    @pytest.mark.parametrize(("preset_name", "card_name"), _STRUCTURAL_SHOULD_MATCH)
    def test_should_match(self, preset_name: str, card_name: str):
        from mtg_utils import testkit

        testkit.test_card_ir(card_name)  # seeds the crosswalk trees memo
        preset = PRESETS[preset_name]
        card = testkit.test_card(card_name)
        assert preset.matches(card), (
            f"structural preset {preset_name!r} should match {card_name!r} "
            f"but did not.\nsignal keys seen: "
            f"{sorted(theme_presets._signal_keys_for(card))}"
        )

    @pytest.mark.parametrize(("preset_name", "card_name"), _STRUCTURAL_SHOULD_NOT_MATCH)
    def test_should_not_match(self, preset_name: str, card_name: str):
        from mtg_utils import testkit

        testkit.test_card_ir(card_name)  # seeds the crosswalk trees memo
        preset = PRESETS[preset_name]
        card = testkit.test_card(card_name)
        assert not preset.matches(card), (
            f"structural preset {preset_name!r} should NOT match "
            f"{card_name!r} but did.\nsignal keys seen: "
            f"{sorted(theme_presets._signal_keys_for(card))}"
        )


# ─── Integration tests against real Scryfall bulk data ────────────────────
#
# Opt-in: these only run when ``MTG_UTILS_BULK_DATA`` points to a Scryfall
# default-cards.json. They protect against two kinds of drift:
#
# 1. SNAPSHOT drift — the committed snapshot's record for a card no longer
#    matches the live bulk (an Oracle update since the last regen).
# 2. PRESET drift — the preset's keyword list no longer matches the real
#    card even though the snapshot does.
#
# Both are caught by running the preset against real data. Skipped by
# default to keep CI fast and offline.


@pytest.fixture(scope="module")
def real_bulk_index() -> dict[str, dict]:
    """Load Scryfall bulk data into a name→card dict, or skip."""
    path_str = os.environ.get("MTG_UTILS_BULK_DATA")
    if not path_str:
        pytest.skip(
            "MTG_UTILS_BULK_DATA not set; integration tests skipped. "
            "Set it to a Scryfall default-cards.json path to enable."
        )

    path = Path(path_str).expanduser()
    if not path.exists():
        pytest.skip(f"bulk data file not found: {path}")

    from mtg_utils.bulk_loader import load_bulk_cards

    cards = load_bulk_cards(path)
    # Keep the first matching printing for each oracle name; skip tokens and
    # emblem layouts.
    index: dict[str, dict] = {}
    for c in cards:
        if c.get("layout") in ("token", "double_faced_token", "art_series", "emblem"):
            continue
        name = c.get("name")
        if name and name not in index:
            index[name] = c
    return index


class TestPresetsAgainstRealData:
    """Verify every should_match / should_not_match claim against real data."""

    @pytest.mark.parametrize(
        ("preset_name", "card_name"),
        [(n, c) for n, p in PRESETS.items() for c in p.should_match],
    )
    def test_should_match_against_real(self, preset_name, card_name, real_bulk_index):
        real = real_bulk_index.get(card_name)
        if real is None:
            pytest.fail(f"card {card_name!r} not in real Scryfall bulk data")
        preset = PRESETS[preset_name]
        assert preset.matches(real), (
            f"preset {preset_name!r} does not match real Scryfall data for "
            f"{card_name!r}.\n"
            f"  Real keywords: {real.get('keywords')}\n"
            f"  Real oracle:   {real.get('oracle_text')!r}"
        )

    @pytest.mark.parametrize(
        ("preset_name", "card_name"),
        [(n, c) for n, p in PRESETS.items() for c in p.should_not_match],
    )
    def test_should_not_match_against_real(
        self, preset_name, card_name, real_bulk_index
    ):
        real = real_bulk_index.get(card_name)
        if real is None:
            pytest.fail(f"card {card_name!r} not in real Scryfall bulk data")
        preset = PRESETS[preset_name]
        assert not preset.matches(real), (
            f"preset {preset_name!r} unexpectedly matches real Scryfall data "
            f"for {card_name!r}.\n"
            f"  Real keywords: {real.get('keywords')}\n"
            f"  Real oracle:   {real.get('oracle_text')!r}"
        )


class TestSeedSignalKeyIndex:
    """Sidecar-seeded ``_SIGNAL_KEY_INDEX`` membership must equal a live
    ``_signal_keys_for`` compute (task #90) — the persisted signals-index
    sidecar is a CACHE of the same crosswalk extraction, never a divergent
    second system."""

    def _reset(self):
        theme_presets._SIGNAL_KEY_INDEX.clear()
        theme_presets._SEEDED_BULK_IDENTITIES.clear()

    def test_seeded_value_matches_a_synthetic_extractor(self, tmp_path, monkeypatch):
        from mtg_utils._analysis import signals_index
        from mtg_utils._analysis.signals import Signal

        self._reset()
        try:
            bulk = tmp_path / "AllPrintings.json"
            bulk.write_text("{}", encoding="utf-8")

            def fake_extract(rec, *_args, **_kwargs):
                return [Signal("ramp", "you", "", "", rec.get("name", ""), "high")]

            monkeypatch.setattr(
                "mtg_utils._analysis.signals.extract_signals", fake_extract
            )
            records = [{"oracle_id": "oid-seed", "name": "Fake Card"}]
            signals_index.load_signals_index(bulk, records=records)

            seeded = theme_presets.seed_signal_key_index(bulk)
            assert seeded is True
            assert theme_presets._SIGNAL_KEY_INDEX["oid-seed"] == frozenset({"ramp"})

            # A subsequent live call must NOT recompute — it's already seeded.
            def boom(_rec, *_args, **_kwargs):
                raise AssertionError("must not recompute — already seeded")

            monkeypatch.setattr("mtg_utils._analysis.signals.extract_signals", boom)
            assert theme_presets._signal_keys_for(
                {"oracle_id": "oid-seed"}
            ) == frozenset({"ramp"})
        finally:
            self._reset()

    def test_noop_without_a_bulk_path(self):
        self._reset()
        try:
            assert theme_presets.seed_signal_key_index(None) is False
            assert theme_presets._SIGNAL_KEY_INDEX == {}
        finally:
            self._reset()

    def test_seed_matches_live_for_a_real_snapshot_card(self, tmp_path):
        from mtg_utils import testkit
        from mtg_utils._analysis import signals_index

        self._reset()
        try:
            name = min(testkit._snapshot()["cards"])
            live_keys = frozenset(sig.key for sig in testkit.test_signals(name))
            rec = testkit.test_card(name)

            bulk = tmp_path / "AllPrintings.json"
            bulk.write_text("{}", encoding="utf-8")
            signals_index.load_signals_index(bulk, records=[rec])

            assert theme_presets.seed_signal_key_index(bulk) is True
            assert theme_presets._SIGNAL_KEY_INDEX[rec["oracle_id"]] == live_keys
        finally:
            self._reset()
