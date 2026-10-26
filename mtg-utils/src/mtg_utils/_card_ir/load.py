"""Runtime loader for the crosswalk Card IR cache sidecar.

The sidecar is a JSON ``{version, phase_tag, cards: {oracle_id: Card.to_dict()}}``
written by ``_card_ir.build.build_crosswalk_sidecar``. Consumers join their
Scryfall record to the IR by ``oracle_id`` and read structured abilities instead
of re-grepping oracle text.

An in-memory cache (keyed by path + mtime) makes repeated lookups in one process
free — a tune issues many searches, each of which wants the IR, so without this
we'd re-parse the sidecar every call (mirrors ``bulk_loader``'s rationale).

A process reads about two thousand of the sidecar's ~35k cards, so it never
decodes the whole 42 MB (0.12 s): a span index beside it (``<sidecar>.spans.pkl``,
:func:`_span_index`) holds where each card's JSON starts and ends, keyed by the
sidecar's mtime and size, and a card is decoded from its span of a memory map
when first read (the index and two thousand cards: 0.02 s; backlog (l),
2026-10-26). Building the index costs one decode of the whole file, once per
sidecar.

ADR-0039 step 7: the LEGACY sidecar arm (``SIDECAR_VERSION`` v1-v76, its
changelog, ``sidecar_path`` / ``load_card_ir`` / ``card_for``) died with the
``project.py`` builder; the crosswalk sidecar is the only on-disk Card IR now.
"""

from __future__ import annotations

import json
import mmap
import os
import re
from collections.abc import Iterator, Mapping
from pathlib import Path

from mtg_utils._http import cache_root
from mtg_utils._sidecar import load_pickle_sidecar
from mtg_utils.card_ir import Card


def card_ir_dir() -> Path:
    """The Card IR cache root: ``<cache root>/card-ir`` (``_http.cache_root``)."""
    return cache_root() / "card-ir"


# ADR-0035 Stage-3a: the crosswalk-backed sidecar carries the SAME on-disk shape
# (oracle_id → Card dict) the legacy sidecar carried — it is produced by
# ``compat_card(build_concept_tree(...))`` — and kept its own DISTINCT path +
# version tag from the cutover era, so a stale legacy ``card-ir.json`` on disk
# can never be mistaken for it. ``ir_for`` reads it unconditionally (step 6).
CROSSWALK_SIDECAR_VERSION = 1


def crosswalk_sidecar_path() -> Path:
    return card_ir_dir() / "card-ir-crosswalk.json"


class LazyCardMap(Mapping[str, Card]):
    """``oracle_id`` → :class:`Card`, deserialized on first access.

    The sidecar carries ~35k cards but a tune/build touches ~100 of them, so
    eager ``Card.from_dict`` over the whole payload dominated CLI startup.
    Materialized Cards are cached, so repeated lookups stay free."""

    __slots__ = ("_cards", "_raw")

    def __init__(self, raw: Mapping[str, dict]) -> None:
        self._raw = raw
        self._cards: dict[str, Card] = {}

    def __getitem__(self, oracle_id: str) -> Card:
        card = self._cards.get(oracle_id)
        if card is None:
            card = Card.from_dict(self._raw[oracle_id])
            self._cards[oracle_id] = card
        return card

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    def __contains__(self, oracle_id: object) -> bool:
        return oracle_id in self._raw


class _SpanCards(Mapping[str, dict]):
    """``oracle_id`` → the card's sidecar dict, decoded from its span of the
    memory-mapped sidecar when asked (:func:`_span_index`)."""

    __slots__ = ("_map", "_spans")

    def __init__(self, path: Path, spans: dict[str, tuple[int, int]]) -> None:
        with path.open("rb") as f:
            self._map = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        self._spans = spans

    def __getitem__(self, oracle_id: str) -> dict:
        start, end = self._spans[oracle_id]
        return json.loads(self._map[start:end])

    def __iter__(self) -> Iterator[str]:
        return iter(self._spans)

    def __len__(self) -> int:
        return len(self._spans)

    def __contains__(self, oracle_id: object) -> bool:
        return oracle_id in self._spans


#: Bumped for a change in what the span index holds.
_SPANS_VERSION = 1
_WS = re.compile(r"[ \t\n\r]*")


def _span_index(path: Path, identity: tuple[int, int]) -> dict:
    """The sidecar's ``version`` and each card's span: the offsets its JSON value
    starts and ends at. They are byte offsets because the sidecar is ASCII
    (``json.dump`` escapes the rest); a file that isn't is not read here
    (``spans`` ``None``: the loader decodes it whole). ``identity`` is the
    file's (mtime_ns, size), what the index is valid for. Raises ``ValueError``
    on a file that isn't a JSON object."""
    raw = path.read_bytes()
    if not raw.isascii():
        return {"identity": identity, "version": None, "spans": None}
    text = raw.decode("ascii")
    del raw
    decode = json.JSONDecoder().raw_decode

    def skip(pos: int) -> int:
        match = _WS.match(text, pos)
        return match.end() if match else pos

    def expect(pos: int, char: str) -> int:
        if text[pos : pos + 1] != char:
            msg = f"{path}: not a JSON object (expected {char!r} at offset {pos})"
            raise ValueError(msg)
        return skip(pos + 1)

    version = None
    spans: dict[str, tuple[int, int]] = {}
    pos = expect(skip(0), "{")
    while text[pos : pos + 1] != "}":
        key, pos = decode(text, pos)
        pos = expect(skip(pos), ":")
        if key == "cards":
            pos = expect(pos, "{")
            while text[pos : pos + 1] != "}":
                oid, pos = decode(text, pos)
                start = expect(skip(pos), ":")
                _card, end = decode(text, start)
                spans[oid] = (start, end)
                pos = skip(end)
                if text[pos : pos + 1] == ",":
                    pos = skip(pos + 1)
            pos = expect(pos, "}")
        else:
            value, pos = decode(text, pos)
            if key == "version":
                version = value
            pos = skip(pos)
        if text[pos : pos + 1] == ",":
            pos = skip(pos + 1)
    return {"identity": identity, "version": version, "spans": spans}


def load_crosswalk_card_ir(path: str | Path | None = None) -> Mapping[str, Card]:
    """Load the crosswalk-backed sidecar into an ``oracle_id`` → :class:`Card` map
    (lazy — see :class:`LazyCardMap`; a card's JSON is decoded from its span when
    first read, :func:`_span_index`).

    Raises ``FileNotFoundError`` when the crosswalk sidecar is absent (build it with
    ``build-card-ir-crosswalk``) and ``ValueError`` on an on-disk version mismatch.
    ``_MEM_CACHE`` is keyed by the file's (mtime_ns, size), as the span index
    is, so a rebuilt sidecar is re-read."""
    p = Path(path) if path else crosswalk_sidecar_path()
    if not p.exists():
        raise FileNotFoundError(
            f"Crosswalk Card IR sidecar not found at {p}. Build it with "
            "`build-card-ir-crosswalk` (ADR-0035 Stage-3a)."
        )
    stat = p.stat()
    identity = (stat.st_mtime_ns, stat.st_size)
    key = str(p)
    hit = _MEM_CACHE.get(key)
    if hit is not None and hit[0] == identity:
        return hit[1]

    # ``MTG_SKILLS_CARD_IR_SPANS=none`` keeps the index in memory (every test but
    # the index's own: ``tests/conftest.py``, which never writes the user's cache).
    index = (
        _span_index(p, identity)
        if os.environ.get("MTG_SKILLS_CARD_IR_SPANS") == "none"
        else load_pickle_sidecar(
            p,
            p.with_name(p.name + ".spans.pkl"),
            version_tag=_SPANS_VERSION,
            value_key="index",
            build_fn=lambda: _span_index(p, identity),
            validate=lambda v: isinstance(v, dict) and v.get("identity") == identity,
        )
    )
    spans = index["spans"]
    raw: Mapping[str, dict]
    if spans is None:  # not ASCII: decoded whole
        payload = json.loads(p.read_text())
        version, raw = payload.get("version"), payload.get("cards") or {}
    else:
        version, raw = index["version"], _SpanCards(p, spans)
    if version != CROSSWALK_SIDECAR_VERSION:
        raise ValueError(
            f"Crosswalk Card IR sidecar at {p} is version "
            f"{version}, expected {CROSSWALK_SIDECAR_VERSION}. "
            "Rebuild with `build-card-ir-crosswalk`."
        )
    cards = LazyCardMap(raw)
    _MEM_CACHE[key] = (identity, cards)
    return cards


# oracle_id → Card, keyed by path, with the file's (mtime_ns, size). Shared by
# reference; treat read-only.
_MEM_CACHE: dict[str, tuple[tuple[int, int], Mapping[str, Card]]] = {}


def clear_memory_cache() -> None:
    """Drop the in-memory cache (test hygiene)."""
    _MEM_CACHE.clear()
