"""Tests for gauntlet color/curve inference + theme-based score_card.

Covers the auto-inference path that turns a stated_archetype's theme
matchers into a build spec (colors + curve_target) using the cube's
actual card pool, plus the theme+shape additive scoring layer.
"""

from __future__ import annotations

from mtg_utils._gauntlet_build import (
    infer_archetype_colors,
    infer_curve_target,
    score_card,
)


def _card(
    name: str,
    *,
    cmc: int = 2,
    colors: list[str] | None = None,
    types: str = "Creature",
    text: str = "",
    power: int | None = None,
) -> dict:
    return {
        "name": name,
        "cmc": cmc,
        "color_identity": colors or [],
        "type_line": types,
        "oracle_text": text,
        "power": power,
        "keywords": [],
    }


def _matches_text(needle: str):
    """Build a simple text-matching predicate for tests."""
    return lambda card: needle.lower() in (card.get("oracle_text") or "").lower()


class TestInferArchetypeColors:
    def test_returns_empty_when_no_matchers(self):
        cube = [_card("X", colors=["R"], text="haste")]
        assert infer_archetype_colors(cube, []) == []

    def test_returns_empty_when_no_matches(self):
        cube = [_card("X", colors=["R"], text="haste")]
        assert infer_archetype_colors(cube, [_matches_text("flying")]) == []

    def test_picks_dominant_color_alone(self):
        # 5 black sacrifice cards, 1 red one — black dominates.
        cube = [_card(f"B{i}", colors=["B"], text="sacrifice") for i in range(5)]
        cube.append(_card("R", colors=["R"], text="sacrifice"))
        assert infer_archetype_colors(cube, [_matches_text("sacrifice")]) == ["B"]

    def test_picks_two_colors_when_comparable(self):
        # 5 BW each, 1 R; black + white are comparable, both above 60% threshold.
        cube = [_card(f"B{i}", colors=["B"], text="sacrifice") for i in range(5)]
        cube += [_card(f"W{i}", colors=["W"], text="sacrifice") for i in range(4)]
        cube.append(_card("R", colors=["R"], text="sacrifice"))
        result = infer_archetype_colors(cube, [_matches_text("sacrifice")])
        assert set(result) == {"W", "B"}

    def test_returns_wubrg_canonical_order(self):
        # Equal counts in U, R, G — canonical order is W U B R G.
        cube = (
            [_card(f"U{i}", colors=["U"], text="x") for i in range(3)]
            + [_card(f"R{i}", colors=["R"], text="x") for i in range(3)]
            + [_card(f"G{i}", colors=["G"], text="x") for i in range(3)]
        )
        result = infer_archetype_colors(cube, [_matches_text("x")])
        assert result == ["U", "R", "G"]

    def test_threshold_excludes_low_match_colors(self):
        # 10 black, 1 white — 60% threshold cuts white off.
        cube = [_card(f"B{i}", colors=["B"], text="sacrifice") for i in range(10)]
        cube.append(_card("W", colors=["W"], text="sacrifice"))
        result = infer_archetype_colors(cube, [_matches_text("sacrifice")])
        assert result == ["B"]


class TestInferCurveTarget:
    def test_falls_back_to_midrange_on_no_matches(self):
        cube = [_card(f"X{i}", cmc=2, colors=["R"], text="haste") for i in range(5)]
        # No matchers fire on these cards.
        target = infer_curve_target(cube, [_matches_text("flying")], {"R"})
        assert target == {2: 5, 3: 7, 4: 6, 5: 4, 6: 1}

    def test_normalizes_to_nonland_target(self):
        # Bell-curve distribution: 10 at CMC 3, 5 each at 2 and 4.
        cube = (
            [_card(f"A{i}", cmc=2, colors=["R"], text="match") for i in range(5)]
            + [_card(f"B{i}", cmc=3, colors=["R"], text="match") for i in range(10)]
            + [_card(f"C{i}", cmc=4, colors=["R"], text="match") for i in range(5)]
        )
        target = infer_curve_target(
            cube,
            [_matches_text("match")],
            {"R"},
            nonland_target=23,
        )
        assert sum(target.values()) == 23
        # CMC 3 should dominate (50% of matches → ~12 of 23).
        assert target[3] == max(target.values())

    def test_excludes_off_color_cards(self):
        # Match cards exist in both R (on-color) and U (off-color).
        cube = [_card(f"R{i}", cmc=2, colors=["R"], text="match") for i in range(3)] + [
            _card(f"U{i}", cmc=5, colors=["U"], text="match") for i in range(3)
        ]
        target = infer_curve_target(
            cube,
            [_matches_text("match")],
            {"R"},
            nonland_target=23,
        )
        # Only the 3 R cards count → all weight at CMC 2.
        assert target.get(2, 0) > 0
        assert target.get(5, 0) == 0


class TestScoreCardThemeBased:
    def test_lands_score_zero(self):
        land = {
            "name": "Mountain",
            "cmc": 0,
            "color_identity": ["R"],
            "type_line": "Basic Land — Mountain",
            "oracle_text": "({T}: Add {R}.)",
        }
        s = score_card(land, colors={"R"}, matchers=[_matches_text("anything")])
        assert s == 0.0

    def test_off_color_returns_negative(self):
        card = _card("U", colors=["U"], text="haste")
        s = score_card(card, colors={"R"}, matchers=[_matches_text("haste")])
        assert s == -1.0

    def test_each_matching_theme_adds_three(self):
        # Card matches both matchers — 2 x 3.0 = 6.0.
        card = _card(
            "X",
            colors=["R"],
            text="haste; sacrifice this creature",
            cmc=2,
            power=2,
            types="Creature",
        )
        s = score_card(
            card,
            colors={"R"},
            matchers=[_matches_text("haste"), _matches_text("sacrifice")],
        )
        # 2 themes x 3.0 = 6.0; no shape priors since shape=None.
        assert s == 6.0

    def test_shape_adds_canonical_priors_on_top(self):
        # Aggro shape: 2-power 2-CMC creature gets +5.0 + +1.5 + theme bonus.
        card = _card(
            "X",
            colors=["R"],
            text="haste",
            cmc=2,
            power=2,
            types="Creature",
        )
        # Theme alone:
        theme_only = score_card(
            card,
            colors={"R"},
            matchers=[_matches_text("haste")],
        )
        # Theme + aggro shape:
        with_shape = score_card(
            card,
            colors={"R"},
            matchers=[_matches_text("haste")],
            shape="aggro",
        )
        assert with_shape > theme_only
        # Shape should add +5.0 (2-power 2-CMC creature) +1.5 (2-CMC creature).
        assert with_shape - theme_only == 6.5

    def test_unknown_shape_contributes_nothing(self):
        # No silent fallback — unknown shape is treated as None.
        card = _card("X", colors=["R"], cmc=3, power=2, types="Creature")
        s_unknown = score_card(card, colors={"R"}, shape="tokens")
        s_none = score_card(card, colors={"R"}, shape=None)
        assert s_unknown == s_none

    def test_archetype_kwarg_back_compat(self):
        # Legacy callers passed `archetype="aggro"`; should still work as
        # `shape="aggro"`.
        card = _card("X", colors=["R"], cmc=2, power=2, types="Creature")
        new_style = score_card(card, colors={"R"}, shape="aggro")
        old_style = score_card(card, colors={"R"}, archetype="aggro")
        assert new_style == old_style
