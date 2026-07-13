"""Tests for stated_archetypes resolver."""

from __future__ import annotations

import pytest

from mtg_utils._archetype_resolver import (
    ArchetypeGroup,
    CustomRegexArchetype,
    ResolvedArchetypes,
    resolve_stated_archetypes,
)


def _cube(stated_archetypes):
    return {"designer_intent": {"stated_archetypes": stated_archetypes}}


class TestEmptyAndShape:
    def test_empty_stated_archetypes(self):
        out = resolve_stated_archetypes(_cube([]))
        assert out == ResolvedArchetypes(
            preset_names=(),
            groups=(),
            custom=(),
        )

    def test_missing_designer_intent_returns_empty(self):
        out = resolve_stated_archetypes({})
        assert out.preset_names == ()
        assert out.groups == ()
        assert out.custom == ()


class TestPresetReferenceShape:
    def test_single_preset_reference(self):
        cube = _cube([{"name": "removal"}])
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)
        assert out.groups == ()
        assert out.custom == ()

    def test_multiple_preset_references_dedupe_preserved(self):
        cube = _cube(
            [
                {"name": "top-manipulation"},
                {"name": "removal"},
                {"name": "counterspell"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("top-manipulation", "removal", "counterspell")

    def test_unknown_preset_raises(self):
        cube = _cube([{"name": "no-such-preset"}])
        with pytest.raises(ValueError, match="no-such-preset"):
            resolve_stated_archetypes(cube)


class TestGroupShape:
    def test_single_group_resolves(self):
        cube = _cube(
            [
                {
                    "name": "graveyard",
                    "members": ["reanimate", "self-mill", "graveyard-cast"],
                },
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.groups == (
            ArchetypeGroup("graveyard", ("reanimate", "self-mill", "graveyard-cast")),
        )
        # preset_names is the flattened union of members.
        assert set(out.preset_names) == {"reanimate", "self-mill", "graveyard-cast"}

    def test_group_plus_preset_reference_combine(self):
        cube = _cube(
            [
                {"name": "removal"},
                {"name": "graveyard", "members": ["reanimate", "self-mill"]},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert "removal" in out.preset_names
        assert "reanimate" in out.preset_names
        assert "self-mill" in out.preset_names
        assert len(out.groups) == 1
        assert out.groups[0].name == "graveyard"

    def test_group_dedupes_preset_names_with_other_entries(self):
        cube = _cube(
            [
                {"name": "reanimate"},
                {"name": "graveyard", "members": ["reanimate", "self-mill"]},
            ]
        )
        out = resolve_stated_archetypes(cube)
        # 'reanimate' should appear once even though it's both a top-level
        # entry and a member of the group.
        assert out.preset_names.count("reanimate") == 1

    def test_group_with_unknown_member_raises(self):
        cube = _cube(
            [
                {"name": "graveyard", "members": ["reanimate", "no-such", "self-mill"]},
            ]
        )
        with pytest.raises(ValueError, match="no-such") as excinfo:
            resolve_stated_archetypes(cube)
        assert "graveyard" in str(excinfo.value)

    def test_group_with_empty_members_raises(self):
        cube = _cube([{"name": "empty-group", "members": []}])
        with pytest.raises(ValueError, match="empty-group") as excinfo:
            resolve_stated_archetypes(cube)
        assert "members" in str(excinfo.value).lower()


class TestRegexShape:
    def test_legacy_regex_resolves_to_custom_bucket(self):
        cube = _cube(
            [
                {"name": "kindred-cats", "regex": "(?i)cats? you control"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ()
        assert out.groups == ()
        assert out.custom == (
            CustomRegexArchetype("kindred-cats", "(?i)cats? you control"),
        )

    def test_invalid_regex_raises(self):
        cube = _cube(
            [
                {"name": "broken", "regex": "(?i)[unclosed"},
            ]
        )
        with pytest.raises(ValueError, match="broken") as excinfo:
            resolve_stated_archetypes(cube)
        assert "regex" in str(excinfo.value).lower()

    def test_regex_when_name_is_also_a_preset_keeps_regex_behavior(self):
        # If the author wrote {name: 'removal', regex: '...custom...'}
        # they explicitly want the custom matcher, not the preset.
        cube = _cube(
            [
                {"name": "removal", "regex": "(?i)destroy target nonland"},
            ]
        )
        out = resolve_stated_archetypes(cube)
        # Goes to custom, not preset_names.
        assert out.preset_names == ()
        assert out.custom == (
            CustomRegexArchetype("removal", "(?i)destroy target nonland"),
        )


class TestNameValidation:
    def test_duplicate_name_raises(self):
        cube = _cube(
            [
                {"name": "removal"},
                {"name": "removal"},
            ]
        )
        with pytest.raises(ValueError, match="duplicate") as excinfo:
            resolve_stated_archetypes(cube)
        assert "removal" in str(excinfo.value)

    def test_missing_name_raises(self):
        cube = _cube([{"members": ["reanimate"]}])
        with pytest.raises(ValueError, match="name") as excinfo:
            resolve_stated_archetypes(cube)
        assert "name" in str(excinfo.value).lower()

    def test_non_dict_entry_raises(self):
        cube = _cube(["just-a-string"])
        with pytest.raises(ValueError, match=r"object|dict") as excinfo:
            resolve_stated_archetypes(cube)
        msg = str(excinfo.value).lower()
        assert "object" in msg or "dict" in msg

    def test_multiple_violations_all_reported(self):
        cube = _cube(
            [
                {"name": "no-such-preset"},
                {"name": "broken", "regex": "(?i)[unclosed"},
                {"members": ["reanimate"]},  # missing name
            ]
        )
        with pytest.raises(ValueError, match=r"no-such-preset|broken|name") as excinfo:
            resolve_stated_archetypes(cube)
        msg = str(excinfo.value)
        # Multi-line message with one entry per violation.
        assert "no-such-preset" in msg
        assert "broken" in msg
        assert "name" in msg.lower()


class TestLegacyTopLevelLocation:
    def test_top_level_stated_archetypes_resolves_with_warning(self):
        # No `designer_intent` key; entries at top level instead.
        cube = {"stated_archetypes": [{"name": "removal"}]}
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)
        assert any(
            "deprecat" in str(w.message).lower()
            and "stated_archetypes" in str(w.message)
            for w in caught
        )

    def test_designer_intent_takes_precedence_over_top_level(self):
        # If both are present, designer_intent wins; top-level is ignored.
        cube = {
            "designer_intent": {"stated_archetypes": [{"name": "removal"}]},
            "stated_archetypes": [{"name": "counterspell"}],
        }
        out = resolve_stated_archetypes(cube)
        assert out.preset_names == ("removal",)


class TestMergeMemberPresets:
    def test_merged_preset_or_matches_any_member(self):
        # Task #83: both ``graveyard-return`` and ``self-mill`` moved to
        # structural (``concept``) views — neither has a surviving
        # ``patterns`` arm — so both halves of this sanity check need a
        # real oracle_id to resolve against, via the committed testkit
        # snapshot.
        from mtg_utils import testkit
        from mtg_utils._archetype_resolver import merge_member_presets
        from mtg_utils.theme_presets import PRESETS

        merged = merge_member_presets(
            "graveyard",
            ("graveyard-return", "self-mill"),
        )

        # The merged preset's `matches` returns True if EITHER constituent
        # preset's matchers fire on a card.
        # graveyard-return match: a real grave-to-hand recursion spell,
        # resolved via the committed testkit snapshot (graveyard-return's
        # concept arm needs a real oracle_id).
        testkit.test_card_ir("Regrowth")
        graveyard_return_card = testkit.test_card("Regrowth")
        # Self-mill match: a real self-mill card, resolved via the
        # committed testkit snapshot (self-mill's concept arm needs a
        # real oracle_id).
        testkit.test_card_ir("Stitcher's Supplier")
        self_mill_card = testkit.test_card("Stitcher's Supplier")
        # Neither — should NOT match the union.
        bystander = {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
        }

        # Sanity-check the constituents match individually.
        assert PRESETS["graveyard-return"].matches(graveyard_return_card)
        assert PRESETS["self-mill"].matches(self_mill_card)
        assert not PRESETS["graveyard-return"].matches(bystander)
        assert not PRESETS["self-mill"].matches(bystander)

        # Merged preset matches both kinds, doesn't match the bystander.
        assert merged.matches(graveyard_return_card)
        assert merged.matches(self_mill_card)
        assert not merged.matches(bystander)

    def test_merged_preset_name_matches_group_name(self):
        from mtg_utils._archetype_resolver import merge_member_presets

        merged = merge_member_presets("graveyard", ("graveyard-return", "self-mill"))
        assert merged.name == "graveyard"

    def test_unknown_member_raises(self):
        from mtg_utils._archetype_resolver import merge_member_presets

        with pytest.raises(KeyError):
            merge_member_presets("bad-group", ("does-not-exist",))

    def test_merged_preset_unions_a_structural_view_with_a_regex_member(self):
        """Task #83: merge_member_presets ORs a converted (signal_keys) member
        with an unconverted (regex) member — a mixed group during the
        transition still merges to a coherent single Preset."""
        from mtg_utils import testkit
        from mtg_utils._archetype_resolver import merge_member_presets

        merged = merge_member_presets(
            "value-engines", ("landfall", "plus-one-counters")
        )
        assert merged.signal_keys == ("landfall",)
        # plus-one-counters' regex arm survives the merge (task #85 converted
        # extra-turns; plus-one-counters is task #85's OTHER deferred lane,
        # so it's still the unconverted regex example here).
        assert merged.patterns

        # landfall member matches ONLY via the structural signal_keys arm.
        testkit.test_card_ir("Courser of Kruphix")
        landfall_card = testkit.test_card("Courser of Kruphix")
        assert merged.matches(landfall_card)

        # plus-one-counters member matches ONLY via the regex arm (no
        # oracle_id needed — plus-one-counters is still an unconverted
        # regex preset).
        counters_card = {
            "name": "Scavenging Ooze",
            "type_line": "Creature",
            "oracle_text": (
                "{G}, Exile a creature card from a graveyard: Put a +1/+1 "
                "counter on Scavenging Ooze and you gain 1 life."
            ),
        }
        assert merged.matches(counters_card)

        # Neither arm fires on a bystander.
        bystander = {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        }
        assert not merged.matches(bystander)
