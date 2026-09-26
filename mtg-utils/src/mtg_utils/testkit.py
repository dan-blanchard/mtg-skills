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
  * :func:`test_signals` — the production ``extract_signals`` over the two, so
    a test asserts what production actually emits. Pre-seeds
    ``_ir_lookup``'s trees memo from the same stored records (:func:`_seed_trees`), so
    the structural merge runs for real in CI — no phase cache, no network.
  * :func:`test_phase_records` — the stored raw phase face records themselves, for a
    test of the layer BELOW the trees (strict-load, the concept overlay, the
    correction / recovery stages, the sidecar builder). The one store of real phase
    records: the crosswalk suites' own ``crosswalk_fixture_cards.json`` merged in
    here (ADR-0056).

(``test_legacy_card_ir`` — the LEGACY ``project_card`` IR — died with the
builder in ADR-0039 task #80 step 7.)

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

import copy
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mtg_utils._card_ir.compat import compat_card_from_records
from mtg_utils._card_ir.load import CROSSWALK_SIDECAR_VERSION
from mtg_utils._card_ir.mirror.build import load_committed_schema
from mtg_utils._card_ir.trees import build_trees, seed_trees
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


@lru_cache(maxsize=1)
def _by_printed_name() -> dict[str, str]:
    """A stored card's full printed name → its snapshot key, for the few keys a
    test wrote as a face or an unaccented name (``"Commit"`` for ``Commit //
    Memory``, ``"Cirdan the Shipwright"``) — so a corpus sweep that iterates
    :func:`snapshot_records` can look each record up by its own ``name``."""
    return {
        entry["scryfall"].get("name") or key: key
        for key, entry in _snapshot()["cards"].items()
    }


def _entry(name: str) -> dict[str, Any]:
    cards = _snapshot()["cards"]
    entry = cards.get(name)
    if entry is None and name in _by_printed_name():
        entry = cards[_by_printed_name()[name]]
    if entry is None:
        raise KeyError(
            f"{name!r} is not in the card snapshot. Add it via `build-card-snapshot` "
            "(it scans the tests for testkit-helper literals)."
        )
    return entry


def test_card(name: str) -> dict[str, Any]:
    """The minimal Scryfall record for *name* (a copy — safe for callers to mutate)."""
    return dict(_entry(name)["scryfall"])


#: A printing's style facts with nothing special about it (per-printing: the snapshot
#: stores gameplay facts only). ``test_printing`` overlays these, then the caller's.
_PLAIN_PRINTING = {
    "full_art": False,
    "border_color": "black",
    "frame_effects": [],
    "promo": False,
    "promo_types": [],
}


def test_printing(
    name: str, set_code: str, collector_number: str, **style: object
) -> dict[str, Any]:
    """*name*'s real record as one printing: ``set`` / ``collector_number`` / ``id``
    and a plain style, overlaid with *style* (``full_art=True``, ``promo_types=[…]``,
    …) — per-printing facts the snapshot omits (ADR-0056)."""
    return {
        **test_card(name),
        **_PLAIN_PRINTING,
        "id": f"{set_code}-{collector_number}",
        "set": set_code,
        "collector_number": collector_number,
        **style,
    }


def printing_row(
    set_code: str, collector_number: str, *, quantity: int = 0, foil_quantity: int = 0
) -> dict[str, Any]:
    """One collection ``printings`` row (``ownership.entry_printing_rows``'s stored
    shape): copies of a printing a collection holds."""
    return {
        "set": set_code,
        "collector_number": collector_number,
        "quantity": quantity,
        "foil_quantity": foil_quantity,
    }


def snapshot_records() -> list[dict[str, Any]]:
    """Every snapshot card's minimal Scryfall record, with the crosswalk
    trees memo pre-seeded for each — a CI-usable ~900-card POOL for
    whole-pool computations (the Rate index percentiles, ADR-0042). Copies,
    like :func:`test_card`."""
    out: list[dict[str, Any]] = []
    for name in _snapshot()["cards"]:
        _seed_trees(name)
        out.append(dict(_entry(name)["scryfall"]))
    return out


def _seed_trees(name: str) -> None:
    """Pre-populate ``_ir_lookup``'s trees memo for *name* from the snapshot's
    stored phase records — so the production crosswalk merge (``trees_for``) runs
    for real in CI: no phase cache, no network dependency. Called by every IR
    accessor below (not just :func:`test_signals`) — a test that manually calls
    ``extract_signals(test_card(name), test_card_ir(name))`` (bypassing
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


def test_phase_records(name: str) -> list[dict[str, Any]]:
    """The raw phase face records the snapshot stores for *name* — phase's own
    ``card-data.json`` parse, one record per face phase emits (a DFC / split card
    has two, an Aftermath back half none; a folded object such as a dungeon has
    none at all), in stored order. Deep copies, safe to mutate.

    For a test of the layer below the concept trees — ``strict_load_card``,
    ``build_concept_tree``, the correction / recovery stages, the sidecar and
    ``trees_for`` resolvers — that needs the INPUT production reads, not the trees
    or signals built from it. *name* is a snapshot key (the name a test asks for;
    a back-face name resolves to its card, so ``"Howlpack Alpha"`` returns both
    Mayor of Avabruck faces) or a stored card's full printed name. Picking the
    face is the caller's job: match on each record's ``name``."""
    return copy.deepcopy(_entry(name)["phase_records"])


def test_signals(name: str) -> list:
    """``extract_signals(test_card(name), test_card_ir(name))`` — exactly what
    production emits for *name* (real Scryfall record, real Card IR, real concept
    trees — CI-safe via the snapshot's stored phase records)."""
    from mtg_utils._analysis.signals import extract_signals

    _seed_trees(name)
    return extract_signals(test_card(name))


# These are helpers, not tests — pytest must not collect them despite the ``test_``
# prefix (chosen so a fixture reads ``test_card("Sol Ring")``). ``__test__ = False`` is
# pytest's documented opt-out and travels with the function when imported into a test
# module. Set via ``setattr`` (the attribute isn't declared on the function type).
for _helper in (
    test_card,
    test_card_ir,
    test_signals,
    test_phase_records,
    test_printing,
):
    setattr(_helper, "__test__", False)  # noqa: B010 — dynamic set dodges ty's undeclared-attr check
