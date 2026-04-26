"""Tests for the pick-decision heuristic."""

from __future__ import annotations

from mtg_utils._custom_format._common import (
    CardMetadata,
    LibraryEffect,
    PickDecision,
    choose_pick,
)


def _meta(name, *, cmc=2, ci=("R",), is_land=False, archetypes=()):
    return CardMetadata(
        name=name,
        cmc=cmc,
        color_identity=frozenset(ci),
        produced_mana=("R",) if is_land else (),
        is_land=is_land,
        library_effect=LibraryEffect.NONE,
        archetype_matches=frozenset(archetypes),
    )


class TestChoosePick:
    def test_uncommitted_picks_highest_cmc_playable(self):
        marketplace = [
            _meta("Bolt", cmc=1),
            _meta("Mid", cmc=3),
            _meta("Big", cmc=5),
        ]
        pick = choose_pick(
            marketplace,
            committed=None,
            available_mana=3,
            available_colors={"R"},
        )
        assert isinstance(pick, PickDecision)
        assert pick.kind == "marketplace"
        assert marketplace[pick.card_index].name == "Mid"

    def test_uncommitted_falls_back_to_blind_when_nothing_castable(self):
        marketplace = [_meta("Big", cmc=5), _meta("Bigger", cmc=6)]
        pick = choose_pick(
            marketplace,
            committed=None,
            available_mana=2,
            available_colors={"R"},
        )
        assert pick.kind == "blind"

    def test_uncommitted_blind_when_marketplace_empty(self):
        pick = choose_pick(
            [],
            committed=None,
            available_mana=3,
            available_colors={"R"},
        )
        assert pick.kind == "blind"

    def test_committed_prefers_archetype_match(self):
        marketplace = [
            _meta("Beater", cmc=2, archetypes=()),
            _meta("Reanimator", cmc=3, archetypes=("reanimate",)),
        ]
        pick = choose_pick(
            marketplace,
            committed="reanimate",
            available_mana=3,
            available_colors={"R"},
        )
        assert pick.kind == "marketplace"
        assert marketplace[pick.card_index].name == "Reanimator"

    def test_committed_soft_fallback_when_no_match(self):
        marketplace = [
            _meta("Beater", cmc=2, archetypes=()),
            _meta("Bolt", cmc=1, archetypes=()),
        ]
        pick = choose_pick(
            marketplace,
            committed="reanimate",
            available_mana=3,
            available_colors={"R"},
        )
        # No reanimate match; fall back to greedy: highest playable CMC.
        assert pick.kind == "marketplace"
        assert marketplace[pick.card_index].name == "Beater"

    def test_committed_picks_archetype_even_when_off_curve(self):
        # A 5-CMC reanimate enabler when player has 2 mana — the commitment
        # is sticky enough to pick it for later use.
        marketplace = [
            _meta("Smol", cmc=2, archetypes=()),
            _meta("BigReanimator", cmc=5, archetypes=("reanimate",)),
        ]
        pick = choose_pick(
            marketplace,
            committed="reanimate",
            available_mana=2,
            available_colors={"R"},
        )
        assert pick.kind == "marketplace"
        assert marketplace[pick.card_index].name == "BigReanimator"

    def test_skips_off_color_when_uncommitted(self):
        marketplace = [
            _meta("RedSpell", cmc=2, ci=("R",)),
            _meta("BlueSpell", cmc=3, ci=("U",)),
        ]
        pick = choose_pick(
            marketplace,
            committed=None,
            available_mana=3,
            available_colors={"R"},
        )
        # Player only has R mana — pick the red one.
        assert pick.kind == "marketplace"
        assert marketplace[pick.card_index].name == "RedSpell"
