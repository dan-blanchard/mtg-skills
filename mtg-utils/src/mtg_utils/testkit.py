"""Real-card test fixtures backed by a committed Scryfall + Card-IR snapshot.

The signal tests must evaluate the SAME Card IR that real cards parse into — not a
hand-built ``_ir(Ability(...))`` shape that silently drifts from the real
``project_card`` output. This module serves, from a single committed JSON
(``tests/fixtures/card_snapshot.json``), both halves of the production call:

  * :func:`test_card` — the minimal Scryfall record (the ``record`` arg the regex /
    kept-mirror path re-scans).
  * :func:`test_card_ir` — the REAL projected IR (a verbatim slice of the production
    sidecar, deserialized via :meth:`Card.from_dict` — the exact path
    ``load_card_ir`` uses), so a test runs real-card IR in CI with **no** sidecar
    rebuild, no phase, no network.
  * :func:`test_signals` — the production ``extract_signals_hybrid(record, ir)`` over
    the two, so a test asserts what production actually emits.

The snapshot is committed (ADR-0027 / task #25): CI has no sidecar, which is why the
synthetic-IR pattern existed; the snapshot is the missing real-IR-in-CI piece. Build
or refresh it with ``build-card-snapshot`` (gated like ``download-bulk`` — needs the
local bulk + a built sidecar, never run in CI). The snapshot carries the
``sidecar_version`` it was projected at; loading asserts it matches the current
:data:`SIDECAR_VERSION`, so a projection bump fails loudly until the snapshot is
regenerated (the same staleness guard the production sidecar uses).

The card-data source is MTGJSON (ADR-0033): ``build-card-snapshot`` sources the
minimal records from the MTGJSON-backed ``bulk_loader`` (translated to the Scryfall
record shape), and the committed snapshot is MTGJSON-sourced. The committed IR slices
are source-agnostic (the IR is the *output*); a re-source is signal-identical.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mtg_utils._card_ir.load import SIDECAR_VERSION
from mtg_utils.card_ir import Card

SCHEMA_VERSION = 1
_ENV_OVERRIDE = "MTG_SKILLS_CARD_SNAPSHOT"
_SNAPSHOT_RELPATH = ("tests", "fixtures", "card_snapshot.json")


def snapshot_path() -> Path:
    """Locate ``tests/fixtures/card_snapshot.json``.

    ``$MTG_SKILLS_CARD_SNAPSHOT`` wins when set. Otherwise walk up from this module's
    real path (``.resolve()`` follows the skill ``src`` symlinks to the canonical
    ``mtg-utils/src/mtg_utils``) to the first ancestor that holds the fixture — so it
    resolves identically from every skill's venv and from the worktree checkout.
    """
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor.joinpath(*_SNAPSHOT_RELPATH)
        if candidate.exists():
            return candidate
    # Fall through to the conventional repo layout (mtg-utils/src/mtg_utils → 3 up)
    # so the error message names a concrete path rather than raising mid-walk.
    return here.parents[3].joinpath(*_SNAPSHOT_RELPATH)


@lru_cache(maxsize=1)
def _snapshot() -> dict[str, Any]:
    path = snapshot_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Card snapshot not found at {path}. Build it with `build-card-snapshot` "
            "(needs the local Scryfall bulk + a built Card IR sidecar)."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    got = payload.get("sidecar_version")
    if got != SIDECAR_VERSION:
        raise ValueError(
            f"Card snapshot at {path} was projected at sidecar_version {got}, but the "
            f"projection is now version {SIDECAR_VERSION}. Regenerate it with "
            "`build-card-snapshot` and commit the refreshed fixture."
        )
    if payload.get("cards") is None:
        raise ValueError(f"Card snapshot at {path} has no 'cards' object.")
    return payload


def _entry(name: str) -> dict[str, Any]:
    cards = _snapshot()["cards"]
    entry = cards.get(name)
    if entry is None:
        raise KeyError(
            f"{name!r} is not in the card snapshot. Add it via `build-card-snapshot` "
            "(it scans the tests for test_card/test_card_ir/test_signals literals)."
        )
    return entry


def test_card(name: str) -> dict[str, Any]:
    """The minimal Scryfall record for *name* (a copy — safe for callers to mutate)."""
    return dict(_entry(name)["scryfall"])


def test_card_ir(name: str) -> Card:
    """The REAL projected Card IR for *name* (deserialized from the committed slice)."""
    return Card.from_dict(_entry(name)["ir"])


def test_signals(name: str) -> list:
    """``extract_signals_hybrid(test_card(name), test_card_ir(name))`` — exactly what
    production emits for *name* (real Scryfall record over real projected IR)."""
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    return extract_signals_hybrid(test_card(name), test_card_ir(name))


# These are helpers, not tests — pytest must not collect them despite the ``test_``
# prefix (chosen so a fixture reads ``test_card("Sol Ring")``). ``__test__ = False`` is
# pytest's documented opt-out and travels with the function when imported into a test
# module. Set via ``setattr`` (the attribute isn't declared on the function type).
for _helper in (test_card, test_card_ir, test_signals):
    setattr(_helper, "__test__", False)  # noqa: B010 — dynamic set dodges ty's undeclared-attr check
