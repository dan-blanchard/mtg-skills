"""Slug normalization + art-catalog lookup chain."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtg_utils import proxy_print
from mtg_utils.proxy_print import (
    _split_type_line,
    _try_read_attributed,
    lookup_art,
    slug,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Eldrazi Spawn", "eldrazi-spawn"),
        ("Urza's", "urzas"),
        ("Phyrexian Mite", "phyrexian-mite"),
        ("  Treasure  ", "treasure"),
        ("Power-Plant", "power-plant"),
        ("Eldrazi  Spawn", "eldrazi-spawn"),  # collapsed dashes
    ],
)
def test_slug(name: str, expected: str) -> None:
    assert slug(name) == expected


@pytest.mark.parametrize(
    ("type_line", "types", "subs"),
    [
        ("Sorcery", ["sorcery"], []),
        ("Instant", ["instant"], []),
        ("Legendary Creature — Vampire Knight", ["legendary", "creature"], ["vampire", "knight"]),
        ("Token Artifact — Treasure", ["token", "artifact"], ["treasure"]),
        ("Basic Land — Forest", ["basic", "land"], ["forest"]),
        ("", [], []),
    ],
)
def test_split_type_line(type_line: str, types: list[str], subs: list[str]) -> None:
    actual_types, actual_subs = _split_type_line(type_line)
    assert actual_types == types
    assert actual_subs == subs


def test_lookup_subtype_hit() -> None:
    """Vampire Knight should hit vampire.txt first (subtype tier)."""
    art, tier, key, _credit = lookup_art("Token Creature — Vampire Knight")
    assert tier == "subtype"
    # Either vampire or knight, depending on catalog state, but it shouldn't be generic.
    assert key in ("vampire", "knight")
    assert art  # non-empty


def test_lookup_card_type_fallback() -> None:
    """A type line whose only subtype is missing falls back to the card-type tier."""
    art, tier, key, _credit = lookup_art("Token Creature — Definitelynotrealsubtype")
    assert tier == "card-type"
    assert key == "creature"
    assert art


def test_lookup_generic_fallback() -> None:
    """An empty type line falls all the way through to _generic."""
    art, tier, key, _credit = lookup_art("")
    assert tier == "generic"
    assert key == "_generic"
    assert art


def test_lookup_skips_meta_words() -> None:
    """'Token' / 'Legendary' / 'Basic' / 'Snow' must never become lookup keys."""
    # type_line is "Legendary Creature" with no subtypes — should fall through
    # to creature.txt (card-type tier), NOT legendary.txt.
    art, tier, key, _credit = lookup_art("Legendary Creature")
    assert tier == "card-type"
    assert key == "creature"


def test_lookup_sorcery_card_type() -> None:
    art, tier, key, _credit = lookup_art("Sorcery")
    assert tier == "card-type"
    assert key == "sorcery"


def test_attributed_lookup_parses_header(tmp_path, monkeypatch) -> None:
    """A file in the attributed dir splits header from body and pulls
    the artist's name out of ``# Title (by Name (sig))``."""
    monkeypatch.setattr(proxy_print, "ATTRIBUTED_ART_DIR", tmp_path)
    (tmp_path / "kitten.txt").write_text(
        "# Kitten (by Some Artist (sig))\n"
        "# Source: https://example.com/cats\n"
        "# Used with attribution per https://example.com/faq\n"
        "\n"
        "  /\\_/\\\n"
        " ( o.o )\n"
        "  > ^ <\n"
    )
    result = _try_read_attributed("kitten")
    assert result is not None
    art, artist = result
    assert artist == "Some Artist"
    # Header lines are stripped; art body preserved.
    assert "Kitten (by" not in art
    assert "Source:" not in art
    assert "/\\_/\\" in art
    assert "> ^ <" in art


def test_attributed_lookup_misses_when_dir_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(proxy_print, "ATTRIBUTED_ART_DIR", tmp_path)
    assert _try_read_attributed("nope") is None


def test_lookup_art_prefers_attributed(tmp_path, monkeypatch) -> None:
    """When attributed art exists for a subtype, lookup_art returns it
    and propagates the credit string."""
    monkeypatch.setattr(proxy_print, "ATTRIBUTED_ART_DIR", tmp_path)
    (tmp_path / "vampire.txt").write_text(
        "# Vampire (by The Artist)\n"
        "# Source: https://example.com/x\n"
        "# Used with attribution per https://example.com/faq\n"
        "\n"
        "VAMPIRE\n"
    )
    art, tier, key, credit = lookup_art("Creature — Vampire")
    assert tier == "subtype"
    assert key == "vampire"
    assert credit == "The Artist"
    assert "VAMPIRE" in art
