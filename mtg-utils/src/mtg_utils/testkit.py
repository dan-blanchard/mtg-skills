"""Real-card test fixtures backed by a committed Scryfall + raw-phase-record snapshot.

The signal tests must evaluate the SAME Card IR real cards parse into — not a
hand-built ``_ir(Ability(...))`` shape that silently drifts from production. This
module serves, from a single committed JSON (``tests/fixtures/card_snapshot.json``),
both halves of the production call:

  * :func:`test_card` — the minimal Scryfall record (the ``record`` arg the regex /
    kept-mirror path re-scans).
  * :func:`test_card_ir` — the REAL Card IR for *name*, built ON DEMAND from the
    snapshot's stored raw phase face records (ADR-0039 task #80 step 5/6) —
    unconditionally the crosswalk-era compat ``Card`` (``compat_card_from_records``,
    the same shape ``ir_for`` serves in production; the ADR-0035 cutover flag and
    the legacy revert path it selected are gone, task #80 step 6). A REAL production
    build, never a baked artifact: the snapshot carries phase's own parse (the
    INPUT), not a frozen projection (the OUTPUT), so a crosswalk code change is
    reflected the next test run with no snapshot regen.
  * :func:`test_signals` — the production ``extract_signals_hybrid`` over the two, so
    a test asserts what production actually emits. Pre-seeds
    ``_ir_lookup``'s trees memo from the same stored records (:func:`_seed_trees`), so
    the crosswalk merge (Seam A) runs for real in CI — no phase cache, no network.
  * :func:`test_legacy_card_ir` — the LEGACY (``project_card``) IR, unconditionally.
    For the handful of pins that assert a NAMED ``supplement._recover_X`` function's
    own structural output (a project.py-only recovery the crosswalk's parallel
    ``dropped_clauses.py`` / ``field_corrections.py`` machinery hasn't ported yet)
    rather than "whatever production emits today".

The snapshot is committed (ADR-0027 / task #25 / ADR-0035/0039): CI has no phase
cache, which is why the synthetic-IR pattern existed; the snapshot is the missing
real-IR-in-CI piece. Build or refresh it with ``build-card-snapshot`` (gated like
``download-mtgjson`` / ``build-card-ir-crosswalk`` — needs the local MTGJSON bulk +
phase's card-data.json, never run in CI). The snapshot carries the
``crosswalk_sidecar_version`` and ``phase_tag`` it was captured at; loading asserts
both match the current pins, so a mirror-schema / compat-adapter / phase bump fails
loudly until the snapshot is regenerated (the same staleness guard the production
sidecars use) — even though the crosswalk build itself is on-demand, a version drift
here means the STORED records may no longer strict-load cleanly against the CURRENT
committed mirror schema.

The card-data source is MTGJSON (ADR-0033): ``build-card-snapshot`` sources the
minimal Scryfall records from the MTGJSON-backed ``bulk_loader`` (translated to the
Scryfall record shape); the committed IR is phase's own parse either way (source-
agnostic Scryfall re-source is signal-identical).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mtg_utils._card_ir.compat import compat_card_from_records
from mtg_utils._card_ir.load import CROSSWALK_SIDECAR_VERSION
from mtg_utils._card_ir.mirror.build import load_committed_schema
from mtg_utils._deck_forge._ir_lookup import build_trees, seed_trees
from mtg_utils._phase import PHASE_TAG
from mtg_utils.card_ir import Card

if TYPE_CHECKING:
    from mtg_utils._card_ir.mirror.schema import MirrorSchema

SCHEMA_VERSION = 2
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
            "(needs the local MTGJSON bulk + phase's card-data.json)."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    got_version = payload.get("crosswalk_sidecar_version")
    got_tag = payload.get("phase_tag")
    if got_version != CROSSWALK_SIDECAR_VERSION or got_tag != PHASE_TAG:
        raise ValueError(
            f"Card snapshot at {path} was captured at crosswalk_sidecar_version "
            f"{got_version} / phase {got_tag}, but the pins are now "
            f"{CROSSWALK_SIDECAR_VERSION} / {PHASE_TAG}. Regenerate it with "
            "`build-card-snapshot` and commit the refreshed fixture."
        )
    if payload.get("cards") is None:
        raise ValueError(f"Card snapshot at {path} has no 'cards' object.")
    return payload


@lru_cache(maxsize=1)
def _schema() -> MirrorSchema:
    """The committed mirror schema (CI-usable, no corpus/network) — the SAME
    fixture ``_ir_lookup.build_trees`` reads in production."""
    return load_committed_schema()


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


def _seed_trees(name: str) -> None:
    """Pre-populate ``_ir_lookup``'s trees memo for *name* from the snapshot's
    stored phase records — so the production crosswalk merge (``trees_for``) runs
    for real in CI: no phase cache, no network dependency. Called by every IR
    accessor below (not just :func:`test_signals`) — a test that manually calls
    ``extract_signals_hybrid(test_card(name), test_card_ir(name))`` (bypassing
    :func:`test_signals`) still gets a CI-safe crosswalk merge, because fetching
    the IR always warms the SAME oracle_id's trees first."""
    entry = _entry(name)
    oid = entry["scryfall"].get("oracle_id") or ""
    if not oid:
        return
    trees = build_trees(oid, entry["phase_records"], bulk=entry["scryfall"])
    seed_trees(oid, trees)


def test_card_ir(name: str) -> Card:
    """The REAL Card IR for *name*, built on demand from the committed snapshot's
    stored raw phase face records — never a baked artifact.

    Mirrors production's own ``ir_for`` (ADR-0039 task #80 step 6: unconditionally
    crosswalk now that the cutover flag and the legacy revert path it gated are
    gone) — the crosswalk-era compat ``Card`` (``compat_card_from_records``), a
    pure function of the stored ``phase_records``, so this needs no phase cache /
    network with zero snapshot-shape duplication. An empty ``Card`` (no faces) is
    returned when every stored record drifts from the current committed mirror
    schema — the honest "nothing structured survives" answer, not a crash."""
    _seed_trees(name)
    return _compat_card_ir(name)


def _compat_card_ir(name: str) -> Card:
    entry = _entry(name)
    oid = entry["scryfall"].get("oracle_id") or ""
    card, _drift = compat_card_from_records(oid, entry["phase_records"], _schema())
    return card if card is not None else Card(oracle_id=oid, name=name, faces=())


def test_legacy_card_ir(name: str) -> Card:
    """The LEGACY (``project_card``) IR for *name*, unconditionally — built on
    demand from the same stored phase face records.

    For the handful of pins that assert a NAMED ``project.py`` /
    ``supplement.py`` recovery function's OWN structural output (a
    ``supplement._recover_X`` marker with no crosswalk equivalent yet — the
    ongoing wave-by-wave porting ``dropped_clauses.py`` / ``field_corrections.py``
    tracks), not "whatever production emits today". :func:`test_card_ir` stays
    the production-matching default (unconditionally crosswalk as of ADR-0039
    task #80 step 6); reach for this only when the test is EXPLICITLY about the
    legacy builder's own behavior — ``project_card`` itself survives (ADR-0039
    task #80 step 6 retired only the PRODUCTION wiring that called it; step 7
    decides the builder's own fate), addressable directly here."""
    _seed_trees(name)
    from mtg_utils._card_ir.project import project_card

    return project_card(_entry(name)["phase_records"])


def test_signals(name: str) -> list:
    """``extract_signals_hybrid(test_card(name), test_card_ir(name))`` — exactly what
    production emits for *name* (real Scryfall record, real Card IR, real concept
    trees — CI-safe via the snapshot's stored phase records)."""
    from mtg_utils._deck_forge.signals import extract_signals_hybrid

    _seed_trees(name)
    return extract_signals_hybrid(test_card(name), test_card_ir(name))


# These are helpers, not tests — pytest must not collect them despite the ``test_``
# prefix (chosen so a fixture reads ``test_card("Sol Ring")``). ``__test__ = False`` is
# pytest's documented opt-out and travels with the function when imported into a test
# module. Set via ``setattr`` (the attribute isn't declared on the function type).
for _helper in (test_card, test_card_ir, test_legacy_card_ir, test_signals):
    setattr(_helper, "__test__", False)  # noqa: B010 — dynamic set dodges ty's undeclared-attr check
