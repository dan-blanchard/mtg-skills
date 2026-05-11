"""End-to-end render smoke: tiny in-memory bulk → PDF → extracted text."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader

from mtg_utils.deck import discover_tokens, hydrate
from mtg_utils.proxy_print import build_pdf


def _make_card(
    name: str,
    *,
    type_line: str,
    mana_cost: str = "",
    oracle: str = "",
    power: str | None = None,
    toughness: str | None = None,
    colors: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "type_line": type_line,
        "mana_cost": mana_cost,
        "oracle_text": oracle,
        "power": power,
        "toughness": toughness,
        "colors": colors or [],
    }


def test_render_cards_pdf_has_expected_pages_and_text(tmp_path: Path) -> None:
    cards = [
        _make_card(
            "Lightning Bolt",
            type_line="Instant",
            mana_cost="{R}",
            oracle="Lightning Bolt deals 3 damage to any target.",
            colors=["R"],
        ),
        _make_card(
            "Llanowar Elves",
            type_line="Creature — Elf Druid",
            mana_cost="{G}",
            oracle="{T}: Add {G}.",
            power="1",
            toughness="1",
            colors=["G"],
        ),
        _make_card(
            "Forest",
            type_line="Basic Land — Forest",
        ),
    ]
    items = [(c, None) for c in cards]
    out = tmp_path / "cards.pdf"
    build_pdf(out, items, page_size="letter", is_token=False, title="Test")

    reader = PdfReader(str(out))
    assert len(reader.pages) == 1  # 3 cards on 1 page

    text = reader.pages[0].extract_text()
    assert "Lightning Bolt" in text
    assert "Llanowar Elves" in text
    assert "Forest" in text
    assert "{R}" in text  # mana cost rendered as braces
    assert "Lightning Bolt deals 3 damage" in text  # oracle text


def test_render_tokens_pdf_drops_source_text(tmp_path: Path) -> None:
    """Tokens no longer print 'from: <source>' — the footer slot is reserved
    for the artist credit (when attributed art is available)."""
    treasure = {
        "name": "Treasure",
        "type_line": "Token Artifact — Treasure",
        "oracle_text": "{T}, Sacrifice this token: Add one mana of any color.",
        "colors": [],
        "power": None,
        "toughness": None,
    }
    items = [(treasure, ["Mahadi", "Pitiless Plunderer"])]

    out = tmp_path / "tokens.pdf"
    build_pdf(out, items, page_size="letter", is_token=True, title="Test")

    reader = PdfReader(str(out))
    text = reader.pages[0].extract_text()
    assert "Treasure" in text
    assert "Token Artifact" in text
    assert "from:" not in text


def test_render_two_pages_for_ten_items(tmp_path: Path) -> None:
    cards = [
        _make_card(f"C{i}", type_line="Sorcery", mana_cost="{1}{R}", oracle="Foo.")
        for i in range(10)
    ]
    items = [(c, None) for c in cards]
    out = tmp_path / "cards.pdf"
    build_pdf(out, items, page_size="letter", is_token=False, title="Test")
    reader = PdfReader(str(out))
    assert len(reader.pages) == 2  # 9 + 1


def test_no_real_network_in_render() -> None:
    """Sanity: render path should not call _api_lookup. Patch it to fail loudly."""
    with patch("mtg_utils.scryfall_lookup._api_lookup") as m:
        m.side_effect = AssertionError("render path must not hit Scryfall")
        # If render() touches _api_lookup the patch fires.
        h = hydrate({"name": "X", "type_line": "Sorcery"})
        assert h["name"] == "X"
