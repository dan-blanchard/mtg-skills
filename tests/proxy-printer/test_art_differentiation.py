"""Two-pass art differentiation: when distinct card names collide on the
same type-keyed art file, the build pipeline re-tries each card via
name-keyed lookup. Same-name cards intentionally stay on the shared
art (helps players scan across the table)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtg_utils import proxy_print
from mtg_utils.proxy_print import _resolve_art_with_differentiation


def _card(name: str, type_line: str) -> dict:
    """Minimal card dict for art-resolution testing."""
    return {"name": name, "type_line": type_line}


def test_same_name_multiple_copies_share_one_art(monkeypatch) -> None:
    """24 basic Plains all use the same art (intentional — helps table-scanning)."""
    monkeypatch.setattr(
        proxy_print,
        "lookup_art",
        lambda _tl: ("PLAINS-ART", "subtype", "plains", "Artist A"),
    )
    items = [(_card("Plains", "Basic Land — Plains"), None) for _ in range(24)]
    resolutions = _resolve_art_with_differentiation(items)
    # All 24 land on the same (tier, key).
    assert {(r[1], r[2]) for r in resolutions} == {("subtype", "plains")}


def test_different_names_with_name_keyed_files_get_differentiated(
    tmp_path,
    monkeypatch,
) -> None:
    """Karplusan Forest + Sacred Foundry would both hit mountain.txt; with
    name-keyed files present they each get their own."""
    # Stub the type-keyed lookup to always return mountain.txt.
    monkeypatch.setattr(
        proxy_print,
        "lookup_art",
        lambda _tl: ("MOUNTAIN-ART", "subtype", "mountain", "Type Artist"),
    )
    # Stage name-keyed attributed files for both.
    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    (tmp_path / "karplusan-forest.txt").write_text(
        "# Karplusan Forest (by KF Artist)\n# Source: x\n# x\n\nKARPLUSAN\n"
    )
    (tmp_path / "sacred-foundry.txt").write_text(
        "# Sacred Foundry (by SF Artist)\n# Source: x\n# x\n\nSACRED\n"
    )

    items = [
        (_card("Karplusan Forest", "Land — Mountain Forest"), None),
        (_card("Sacred Foundry", "Land — Mountain Plains"), None),
    ]
    resolutions = _resolve_art_with_differentiation(items)

    assert resolutions[0][1] == "name"
    assert resolutions[0][2] == "karplusan-forest"
    assert "KARPLUSAN" in resolutions[0][0]
    assert resolutions[0][3] == "KF Artist"

    assert resolutions[1][1] == "name"
    assert resolutions[1][2] == "sacred-foundry"
    assert resolutions[1][3] == "SF Artist"


def test_different_names_without_name_keyed_files_keep_shared_art(
    tmp_path,
    monkeypatch,
) -> None:
    """When name-keyed files don't exist, distinct-name cards still share —
    the differentiation pass tries, finds nothing, and leaves type-keyed
    art in place."""
    monkeypatch.setattr(
        proxy_print,
        "lookup_art",
        lambda _tl: ("MOUNTAIN-ART", "subtype", "mountain", "Type Artist"),
    )
    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    # No name-keyed files in tmp_path.
    items = [
        (_card("Karplusan Forest", "Land — Mountain Forest"), None),
        (_card("Sacred Foundry", "Land — Mountain Plains"), None),
    ]
    resolutions = _resolve_art_with_differentiation(items)
    # Both still use mountain.txt.
    assert all(r[2] == "mountain" for r in resolutions)


def test_mixed_same_and_different_names(tmp_path, monkeypatch) -> None:
    """A pool of 4 Plains + 1 Karplusan Forest + 1 Sacred Foundry: the two
    distinct-name lands try name-keyed; the 4 Plains all keep their shared
    plains.txt regardless of whether plains.txt has name-keyed alternatives."""

    def fake_lookup(type_line):
        if (
            "Plains" in type_line
            and "Forest" not in type_line
            and "Mountain" not in type_line
        ):
            return ("PLAINS", "subtype", "plains", "")
        return ("MOUNTAIN", "subtype", "mountain", "")

    monkeypatch.setattr(proxy_print, "lookup_art", fake_lookup)
    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    (tmp_path / "karplusan-forest.txt").write_text(
        "# Karplusan Forest (by KF)\n# x\n# x\n\nKARPLUSAN\n"
    )
    # Sacred Foundry has no name-keyed file — should stay on mountain.txt.

    items = (
        [(_card("Plains", "Basic Land — Plains"), None)] * 4
        + [(_card("Karplusan Forest", "Land — Mountain Forest"), None)]
        + [(_card("Sacred Foundry", "Land — Mountain Plains"), None)]
    )
    resolutions = _resolve_art_with_differentiation(items)

    # 4 Plains: identical resolution (intentional — same-name group).
    assert {(r[1], r[2]) for r in resolutions[:4]} == {("subtype", "plains")}
    # Karplusan Forest swaps to its name-keyed file.
    assert resolutions[4][2] == "karplusan-forest"
    # Sacred Foundry stays on mountain (no name-keyed file).
    assert resolutions[5][2] == "mountain"


def test_name_slug_colliding_with_subtype_doesnt_fake_a_swap(
    tmp_path,
    monkeypatch,
) -> None:
    """Regression: ``"Eldrazi"`` (card name) slugs to the same key as the
    ``eldrazi`` subtype. Without the body-content group + same-art guard,
    the diff pass would "swap" Eldrazi from (subtype, eldrazi) to
    (name, eldrazi), pointing at the *same file*. The cards still render
    identical art, but the warn pass would no longer flag them because
    their (tier, key) tuples now differ. Verify: (1) the swap is a no-op
    because the name lookup returns the same body; (2) both cards keep
    their original (subtype, eldrazi) tuple so the warn pass groups them
    together."""
    monkeypatch.setattr(
        proxy_print,
        "lookup_art",
        lambda _tl: ("ELDRAZI-ART", "subtype", "eldrazi", "Type Artist"),
    )
    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    # The eldrazi.txt that BOTH the subtype lookup AND the name lookup
    # for "Eldrazi" would return — same content, same file.
    (tmp_path / "eldrazi.txt").write_text("# Eldrazi (by X)\n# x\n# x\n\nELDRAZI-ART\n")
    # No name-keyed file for "Eldrazi Spawn" — it stays on subtype.
    items = [
        (_card("Eldrazi", "Token Creature — Eldrazi"), None),
        (_card("Eldrazi Spawn", "Token Creature — Eldrazi Spawn"), None),
    ]
    resolutions = _resolve_art_with_differentiation(items)
    # Both keep the (subtype, eldrazi) tuple — no fake swap.
    assert resolutions[0][1] == "subtype"
    assert resolutions[0][2] == "eldrazi"
    assert resolutions[1][1] == "subtype"
    assert resolutions[1][2] == "eldrazi"
    # And both still share the same art (this is the catalog gap the
    # warning is supposed to surface — user should hand-curate).
    assert resolutions[0][0] == resolutions[1][0]


def test_warn_unresolved_duplicates_catches_slug_collision(capsys) -> None:
    """The warn pass groups by art body. Even if the diff pass had
    swapped one card to (name, eldrazi) and left the other on
    (subtype, eldrazi), the warning must still fire because both
    files have identical content."""
    items = [
        (_card("Eldrazi", "Token Creature — Eldrazi"), None),
        (_card("Eldrazi Spawn", "Token Creature — Eldrazi Spawn"), None),
    ]
    # Both resolutions point at the SAME art body but DIFFERENT (tier, key).
    resolutions = [
        ("ELDRAZI-ART", "name", "eldrazi", "X"),
        ("ELDRAZI-ART", "subtype", "eldrazi", ""),
    ]
    proxy_print._warn_unresolved_duplicates(items, resolutions)
    err = capsys.readouterr().err
    assert "Eldrazi" in err
    assert "Eldrazi Spawn" in err
    assert "eldrazi.txt" in err


def test_warn_excludes_canonical_basic_land(capsys) -> None:
    """A basic ``"Swamp"`` card whose name slugs to ``swamp`` is the
    canonical occupant of ``swamp.txt`` — it's supposed to look like
    that. The warning should list only **non-canonical** neighbors
    (Blood Crypt, Smoldering Marsh) that just happen to share the
    swamp subtype, not the basic land itself."""
    items = [
        (_card("Swamp", "Basic Land — Swamp"), None),
        (_card("Blood Crypt", "Land — Swamp Mountain"), None),
        (_card("Smoldering Marsh", "Land — Swamp Mountain"), None),
    ]
    resolutions = [
        ("SWAMP-ART", "subtype", "swamp", ""),
        ("SWAMP-ART", "subtype", "swamp", ""),
        ("SWAMP-ART", "subtype", "swamp", ""),
    ]
    proxy_print._warn_unresolved_duplicates(items, resolutions)
    err = capsys.readouterr().err
    # Non-canonical neighbors listed.
    assert "Blood Crypt" in err
    assert "Smoldering Marsh" in err
    # The basic land itself is NOT flagged — it's canonical.
    assert "(Swamp," not in err
    assert ", Swamp," not in err
    assert ", Swamp)" not in err
    # Count reflects non-canonical members only.
    assert "2 cards share swamp.txt" in err


def test_warn_silent_when_only_canonical_name(capsys) -> None:
    """24 basic Plains in a 60-card deck collapse to one distinct name
    (``"Plains"``), which is canonical. Nothing to warn about."""
    items = [(_card("Plains", "Basic Land — Plains"), None) for _ in range(24)]
    resolutions = [("PLAINS-ART", "subtype", "plains", "")] * 24
    proxy_print._warn_unresolved_duplicates(items, resolutions)
    err = capsys.readouterr().err
    assert err == ""


def test_dfc_name_strips_back_face_for_name_keyed_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    """A DFC card whose front face has a name-keyed file should match it
    (the back-face suffix shouldn't poison the lookup)."""
    monkeypatch.setattr(
        proxy_print,
        "lookup_art",
        lambda _tl: ("CREATURE", "card-type", "creature", ""),
    )
    monkeypatch.setattr(proxy_print, "attributed_art_dir", lambda: tmp_path)
    (tmp_path / "delver-of-secrets.txt").write_text(
        "# Delver of Secrets (by DOS)\n# x\n# x\n\nDELVER\n"
    )
    items = [
        (
            _card(
                "Delver of Secrets // Insectile Aberration",
                "Creature — Human Wizard",
            ),
            None,
        ),
        (_card("Some Other Creature", "Creature — Beast"), None),
    ]
    resolutions = _resolve_art_with_differentiation(items)
    # Delver hits the name-keyed file (after // stripped).
    assert resolutions[0][2] == "delver-of-secrets"
