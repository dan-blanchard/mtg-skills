"""Unit tests for :func:`mtg_utils.proxy_print.compute_layout`.

The layout phase is pure(ish): it takes a card dict and a
``measure_width`` callable, and returns a :class:`ProxyLayout` carrying
every rect, font size, and rendered string the emit phase will draw.
By passing a fake ``measure_width`` we get fast, deterministic tests of
the geometry math + font fitting + footer precedence — no reportlab,
no PDF emission, no string-width oracle.
"""

from __future__ import annotations

import pytest

from mtg_utils.proxy_print import (
    BANNER_GAP,
    BANNER_H,
    CARD_H,
    CARD_W,
    PAD,
    PAGE_SIZES,
    PT_BOX_H,
    PT_BOX_W,
    ProxyLayout,
    compute_layout,
)

# ---------------------------------------------------------------------------
# Fake measure_width.
# ---------------------------------------------------------------------------

# Every character is 0.6 * size points wide — close to reportlab's Courier
# behaviour and stable enough for testing geometry decisions. The font
# parameter is ignored: we don't model font-specific kerning.
def fixed_width(text: str, _font: str, size: float) -> float:
    return len(text) * size * 0.6


# ---------------------------------------------------------------------------
# Card factories.
# ---------------------------------------------------------------------------

LETTER_W, LETTER_H = PAGE_SIZES["letter"]


def make_card(**overrides) -> dict:
    """Minimal card with sensible defaults; override specific fields per test."""
    base = {
        "name": "Llanowar Elves",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
        "mana_cost": "{G}",
        "power": "1",
        "toughness": "1",
        "colors": ["G"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Card-cell positioning (slot → x,y).
# ---------------------------------------------------------------------------


def test_slot_zero_top_left_corner() -> None:
    layout = compute_layout(
        make_card(), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    # Slot 0 is the top-left of the 3x3 grid; x and y are positive.
    assert layout.x > 0
    assert layout.y > 0


def test_two_slots_share_a_row() -> None:
    """Slots 0 and 1 must share a y; slot 2 the same; slot 3 jumps down."""
    layouts = [
        compute_layout(
            make_card(), slot=i,
            page_w=LETTER_W, page_h=LETTER_H,
            is_token=False, measure_width=fixed_width,
        )
        for i in (0, 1, 2, 3)
    ]
    assert layouts[0].y == layouts[1].y == layouts[2].y
    assert layouts[3].y < layouts[0].y
    assert layouts[0].x < layouts[1].x < layouts[2].x


# ---------------------------------------------------------------------------
# Name banner.
# ---------------------------------------------------------------------------


def test_card_name_left_aligned_with_mana_cost() -> None:
    """A non-token card has the name left-aligned and the mana cost on the right."""
    layout = compute_layout(
        make_card(name="Counterspell", mana_cost="{U}{U}"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.name_centered is False
    assert layout.mana_cost_text == "{U}{U}"


def test_token_name_centred_no_mana_cost() -> None:
    layout = compute_layout(
        make_card(name="Soldier", mana_cost="{W}"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=True, measure_width=fixed_width,
    )
    assert layout.name_centered is True
    assert layout.mana_cost_text == ""  # tokens drop the cost


def test_name_font_shrinks_to_fit() -> None:
    """A very long name must produce a font size below 9.5."""
    long = "Sliver Hivelord, Magus of the Disjunction"
    layout = compute_layout(
        make_card(name=long, mana_cost=""), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.name_text_size < 9.5
    # Minimum floor is 6.0.
    assert layout.name_text_size >= 6.0


def test_name_font_full_size_when_short() -> None:
    """A short name keeps the default 9.5 size."""
    layout = compute_layout(
        make_card(name="Bolt", mana_cost=""), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.name_text_size == 9.5


# ---------------------------------------------------------------------------
# P/T box.
# ---------------------------------------------------------------------------


def test_creature_pt_text() -> None:
    layout = compute_layout(
        make_card(power="3", toughness="4"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.pt_text == "3 / 4"


def test_planeswalker_loyalty_text() -> None:
    layout = compute_layout(
        make_card(
            name="Ajani",
            type_line="Legendary Planeswalker — Ajani",
            power=None, toughness=None, loyalty="4",
        ),
        slot=0, page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.pt_text == "L: 4"


def test_no_pt_for_non_creature_non_planeswalker() -> None:
    layout = compute_layout(
        make_card(
            name="Counterspell",
            type_line="Instant",
            power=None, toughness=None, loyalty=None,
            oracle_text="Counter target spell.",
        ),
        slot=0, page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.pt_text == ""


# ---------------------------------------------------------------------------
# Footer-slot precedence: token source wins over artist credit.
# ---------------------------------------------------------------------------


def test_token_sources_no_longer_appear_in_footer(monkeypatch) -> None:
    """Tokens no longer render 'from: X' — only artist credit takes the footer."""
    from mtg_utils import proxy_print
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("art", "subtype", "soldier", ""),
    )
    layout = compute_layout(
        make_card(name="Soldier"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=True, measure_width=fixed_width,
    )
    assert "from:" not in layout.footer_text
    assert layout.footer_text == ""


def test_non_token_card_no_credit_empty_footer(monkeypatch) -> None:
    """A regular card with no attributed art credit has an empty footer."""
    from mtg_utils import proxy_print
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("art", "subtype", "elf", ""),
    )
    layout = compute_layout(
        make_card(), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.footer_text == ""


def test_non_token_with_artist_credit_renders_art_by(monkeypatch) -> None:
    from mtg_utils import proxy_print
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("art", "subtype", "elf", "Joan Stark"),
    )
    layout = compute_layout(
        make_card(), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.footer_text == "art by Joan Stark"


def test_token_with_artist_credit_renders_art_by(monkeypatch) -> None:
    """Even with token sources passed, the footer prefers the artist credit."""
    from mtg_utils import proxy_print
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("art", "subtype", "soldier", "Joan Stark"),
    )
    layout = compute_layout(
        make_card(name="Soldier", type_line="Token Creature — Soldier"),
        slot=0, page_w=LETTER_W, page_h=LETTER_H,
        is_token=True, measure_width=fixed_width,
    )
    assert layout.footer_text == "art by Joan Stark"


def test_long_artist_credit_gets_ellipsized(monkeypatch) -> None:
    from mtg_utils import proxy_print
    very_long = "Some Extremely Long Multi-Word Artist Name " * 4
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("art", "subtype", "x", very_long),
    )
    layout = compute_layout(
        make_card(), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.footer_text.endswith("…")


# ---------------------------------------------------------------------------
# Body math: oracle / art / type-banner share the inner space.
# ---------------------------------------------------------------------------


def test_type_banner_fixed_at_third_for_non_tokens() -> None:
    """Non-token cards have type_banner_y at exactly y + CARD_H/3, regardless of
    how much oracle text or art the card has.
    """
    from mtg_utils.proxy_print import CARD_H
    layouts = [
        compute_layout(
            make_card(oracle_text=oracle), slot=0,
            page_w=LETTER_W, page_h=LETTER_H,
            is_token=False, measure_width=fixed_width,
        )
        for oracle in (
            "{T}: Add {G}.",                                  # tiny
            "Flying, vigilance, haste, trample. " * 4,        # huge
            "",                                                # none
        )
    ]
    expected = layouts[0].y + CARD_H / 3
    for layout in layouts:
        assert layout.type_banner_y == expected, (
            f"banner moved across cards: {layout.type_banner_y} vs {expected}"
        )


def test_token_banner_remains_dynamic() -> None:
    """Tokens keep the legacy dynamic layout — banner Y depends on content."""
    short = compute_layout(
        make_card(oracle_text=""), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=True, measure_width=fixed_width,
    )
    long = compute_layout(
        make_card(oracle_text="Trample. " * 30), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=True, measure_width=fixed_width,
    )
    # On a token with lots of oracle, the banner shifts up to make room.
    assert long.type_banner_y > short.type_banner_y


def test_no_oracle_zero_oracle_lines() -> None:
    layout = compute_layout(
        make_card(oracle_text=""), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.oracle_lines == []
    assert layout.oracle_size == 0.0


# ---------------------------------------------------------------------------
# DFC name / type-line handling.
# ---------------------------------------------------------------------------


def test_dfc_name_strips_back_face() -> None:
    layout = compute_layout(
        make_card(name="Delver of Secrets // Insectile Aberration"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.name_text == "Delver of Secrets"


def test_dfc_type_line_strips_back_face() -> None:
    layout = compute_layout(
        make_card(
            name="Delver of Secrets",
            type_line="Creature — Human Wizard // Creature — Human Insect",
        ),
        slot=0, page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.type_text == "Creature — Human Wizard"


# ---------------------------------------------------------------------------
# Layout is a value (no mutation, no canvas).
# ---------------------------------------------------------------------------


def test_layout_is_frozen() -> None:
    layout = compute_layout(
        make_card(), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    with pytest.raises(AttributeError):
        layout.name_text = "Mutated"  # type: ignore[misc]


def test_layout_returns_lookup_art_tier_and_key(monkeypatch) -> None:
    from mtg_utils import proxy_print
    monkeypatch.setattr(
        proxy_print, "lookup_art",
        lambda _type_line: ("ascii-art", "subtype", "wolf", ""),
    )
    layout = compute_layout(
        make_card(type_line="Creature — Wolf"), slot=0,
        page_w=LETTER_W, page_h=LETTER_H,
        is_token=False, measure_width=fixed_width,
    )
    assert layout.art_tier == "subtype"
    assert layout.art_key == "wolf"
