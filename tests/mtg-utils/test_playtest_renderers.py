"""Tests for the shared envelope-header / warnings helpers in
`_playtest_common`. The helpers are extracted from the five mode-specific
renderers so a single edit can reshape every report's header (e.g., when
the schema-v1 envelope adds a field).
"""

from __future__ import annotations

from mtg_utils._playtest_common import render_envelope_header, render_warnings


def _env(**overrides) -> dict:
    """Minimal envelope with all the fields the helpers read."""
    return {
        "schema_version": 1,
        "mode": "test",
        "engine": "phase",
        "engine_version": "phase v0.1.19",
        "seed": 42,
        "format": "standard",
        "card_coverage": None,
        "results": {},
        "warnings": [],
        "duration_s": 1.23,
        "generated_at": 1700000000,
        **overrides,
    }


class TestRenderEnvelopeHeader:
    def test_default_shape_matches_legacy_format(self):
        # The pre-refactor format was 4 lines: title, blank, fields, blank.
        # Behavior preservation: the same 4-line shape with the same field
        # ordering and `**Key:** value` separator.
        out = render_envelope_header(_env(), title="Goldfish report")
        assert out == [
            "# Goldfish report",
            "",
            (
                "**Engine:** phase v0.1.19  "
                "**Seed:** 42  "
                "**Format:** standard  "
                "**Duration:** 1.23s"
            ),
            "",
        ]

    def test_format_falls_back_to_unspecified(self):
        out = render_envelope_header(_env(format=None), title="X report")
        assert "**Format:** unspecified" in out[2]

    def test_show_engine_false_omits_engine_field(self):
        # Custom-format renderer puts engine_version in the title and
        # therefore omits the inline `**Engine:**` field.
        out = render_envelope_header(
            _env(),
            title="Custom-format playtest report — phase v0.1.19",
            show_engine=False,
        )
        assert out[0] == "# Custom-format playtest report — phase v0.1.19"
        # The fields line starts with **Seed:**, no **Engine:**.
        assert out[2].startswith("**Seed:**")
        assert "**Engine:**" not in out[2]

    def test_extra_fields_inserted_between_format_and_duration(self):
        # Standard left-to-right reading order: Engine → Seed → Format →
        # extras → Duration. Test a single extra field (Games) sits in
        # the right slot.
        out = render_envelope_header(
            _env(),
            title="X",
            extra_fields=[("Games", "10")],
        )
        fields = out[2]
        # Format must come before Games, Games before Duration.
        assert fields.index("**Format:**") < fields.index("**Games:**")
        assert fields.index("**Games:**") < fields.index("**Duration:**")


class TestRenderWarnings:
    def test_returns_empty_when_no_warnings(self):
        # Renderer can `lines += render_warnings(env)` without an `if`.
        assert render_warnings(_env(warnings=[])) == []
        assert render_warnings(_env(warnings=None)) == []

    def test_returns_h2_warnings_block(self):
        # H2 (## Warnings), matches gauntlet/match/custom_format.
        # Goldfish was H3 pre-refactor — that was a layout bug fixed by
        # consolidation.
        out = render_warnings(_env(warnings=["timeout on TCG", "MP captcha"]))
        assert out == [
            "",
            "## Warnings",
            "- timeout on TCG",
            "- MP captcha",
        ]

    def test_returns_lines_extendable_into_renderer(self):
        # Caller pattern: lines += render_warnings(env). Confirm the
        # return is a plain list (not a generator), so `+=` produces the
        # expected result and the caller can mutate after.
        result = render_warnings(_env(warnings=["x"]))
        assert isinstance(result, list)
        result.append("extra")  # must be mutable, no exception
        assert result[-1] == "extra"
