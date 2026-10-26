"""The trees store (``_card_ir.tree_store``): a process persists the corrected trees
it builds, per oracle_id, and the next one reads them without building them —
real cards' phase records (ADR-0056), served through a stand-in records index."""

import json
import os
import pickle
import sqlite3

import pytest

from mtg_utils import _phase
from mtg_utils._analysis.signals import extract_signals
from mtg_utils._card_ir import tree_store, trees
from mtg_utils._card_ir.crosswalk.core import GRANTED_RECOVERY_ATTR
from mtg_utils._card_ir.crosswalk.reads import MEMO_ATTR_PREFIX
from mtg_utils.testkit import test_card, test_phase_records, test_signals


@pytest.fixture
def store(monkeypatch, tmp_path):
    """The store on, beside a stand-in card-data whose records index holds Sol
    Ring's and Failure // Comply's real phase records. ``new_process()`` writes
    what the process built and forgets the trees' memos, as a process exit does:
    fresh ones of the test's own, so the suite's seeded trees outlive it."""
    cards = {name: test_card(name) for name in ("Sol Ring", "Failure // Comply")}
    blobs = {
        card["oracle_id"]: json.dumps(test_phase_records(name)).encode()
        for name, card in cards.items()
    }
    card_data = tmp_path / "card-data.json"
    card_data.write_text("[]")
    known_tokens = tmp_path / "known-tokens.toml"
    known_tokens.write_text("")
    path = tmp_path / "card-data.json.trees.sqlite"  # beside the card-data
    monkeypatch.delenv("MTG_SKILLS_TREE_STORE")
    monkeypatch.setattr(_phase, "_card_data_path", lambda: card_data)
    monkeypatch.setattr(_phase, "ensure_known_tokens", lambda: known_tokens)
    index = trees.PhaseRecordIndex(blobs)
    monkeypatch.setattr(trees, "_phase_record_index", lambda: index)

    memos = ("_TREES_MEMO", "_RECORDS_MEMO", "_BULK_FACES_MEMO", "_FACE_NAMES")

    def new_process() -> None:
        current = trees._tree_store()
        if current is not None:
            current.flush()
        trees._tree_store.cache_clear()
        for memo in memos:
            monkeypatch.setattr(trees, memo, {})

    new_process()
    yield cards, path, new_process
    trees._tree_store.cache_clear()


def _no_build(*_a, **_k):
    raise AssertionError("read from the store, never built")


def test_a_stored_tree_reads_as_the_built_one(store, monkeypatch):
    """Sol Ring's trees, written by one process, are the next one's without a
    build, a records index or the mirror schema."""
    cards, _path, new_process = store
    built = trees.trees_for(cards["Sol Ring"])
    assert built
    new_process()

    monkeypatch.setattr(trees, "build_trees", _no_build)
    monkeypatch.setattr(trees, "_phase_record_index", _no_build)
    served = trees.trees_for(cards["Sol Ring"])
    assert served == built
    assert served is not built
    assert trees.has_phase_records(cards["Sol Ring"]["oracle_id"])


def test_a_card_phase_has_no_record_for_is_stored_empty(store, monkeypatch):
    """A card newer than the phase pin has no trees; the next process knows it
    without loading the records index."""
    _cards, _path, new_process = store
    stranger = {"oracle_id": "no-such-oracle-id", "name": "Stranger"}
    assert trees.trees_for(stranger) == ()
    new_process()

    monkeypatch.setattr(trees, "_phase_record_index", _no_build)
    assert trees.trees_for(stranger) == ()
    assert not trees.has_phase_records("no-such-oracle-id")


def test_an_aftermath_card_builds_its_bulk_faces(store, monkeypatch):
    """Comply has no phase record, so Failure // Comply read with its bulk faces
    holds a text-only Comply tree that its plain read lacks. The store holds the
    plain read only: the next process's bulk read builds (its own memo,
    ``trees._BULK_TREES_MEMO``), as it would with no store."""
    cards, _path, new_process = store
    failure = cards["Failure // Comply"]
    plain = trees.trees_for(failure)
    new_process()

    with_faces = trees.trees_for(failure, bulk=failure)
    assert "Comply" in {t.name for t in with_faces}
    assert "Comply" not in {t.name for t in plain}
    assert trees.reads_bulk_faces(failure)
    new_process()

    monkeypatch.setattr(trees, "build_trees", _no_build)
    assert trees.trees_for(failure) == plain


def test_another_card_data_reads_nothing(store):
    """The card-data file is part of the key: a rewritten one builds again."""
    cards, _path, new_process = store
    trees.trees_for(cards["Sol Ring"])
    new_process()

    card_data = _phase._card_data_path()
    stat = card_data.stat()
    os.utime(card_data, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert trees._tree_store().get(cards["Sol Ring"]["oracle_id"]) is None


def test_only_the_newest_keys_are_kept(store, monkeypatch):
    """Rows of a key older than the newest KEEP_KEYS are dropped at a write."""
    cards, path, new_process = store
    monkeypatch.setattr(tree_store, "KEEP_KEYS", 1)
    trees.trees_for(cards["Sol Ring"])
    new_process()
    card_data = _phase._card_data_path()
    card_data.write_text("[ ]")  # another key
    trees.trees_for(cards["Sol Ring"])
    new_process()

    with sqlite3.connect(path) as con:
        keys = con.execute("SELECT DISTINCT key FROM trees").fetchall()
    assert len(keys) == 1


def test_the_store_key_reads_the_card_ir_alone():
    """The key hashes the trees' import closure: it must not reach the signal
    path (``deck`` once took it there, ``type_line`` is its own module), or every
    lane edit would throw the whole store away."""
    from mtg_utils._import_closure import source_files

    names = {p.as_posix() for p in source_files("mtg_utils._card_ir.trees")}
    assert names
    assert not [n for n in names if "/_analysis/" in n or n.endswith("/deck.py")]


def test_an_unreadable_store_degrades_to_building(store):
    cards, path, _new_process = store
    path.write_bytes(b"not a database")
    assert trees.trees_for(cards["Sol Ring"])


def _attrs(obj: object, prefix: str, seen: set[int]) -> set[str]:
    """The ``prefix`` attribute names on the objects reachable from ``obj``."""
    if id(obj) in seen or isinstance(obj, (str, int, float, bytes, type(None))):
        return set()
    seen.add(id(obj))
    if isinstance(obj, (list, tuple, set, frozenset)):
        return set().union(*(_attrs(o, prefix, seen) for o in obj))
    if isinstance(obj, dict):
        return set().union(*(_attrs(o, prefix, seen) for o in obj.values()))
    own = getattr(obj, "__dict__", None)
    if not isinstance(own, dict):
        return set()
    return {k for k in own if k.startswith(prefix)}.union(
        *(_attrs(v, prefix, seen) for v in own.values())
    )


@pytest.mark.parametrize("name", ["Osseous Sticktwister", "Shackles of Treachery"])
def test_a_stored_tree_leaves_the_reads_memos_behind(name, monkeypatch):
    """A read's memo on a node is dropped from the stored copy (Osseous
    Sticktwister's owner index is keyed by the ids of the nodes it indexes, which
    a loaded copy doesn't share), while the recovery stage's granted bodies
    (Shackles of Treachery's, data outside the memo prefix) are kept: the loaded
    copy reads the same signals."""
    card = test_card(name)
    test_signals(name)
    built = trees.trees_for(card)
    live = sorted(map(repr, extract_signals(card)))
    loaded = pickle.loads(tree_store._dumps(built))
    assert _attrs(built, MEMO_ATTR_PREFIX, set())
    assert not _attrs(loaded, MEMO_ATTR_PREFIX, set())
    granted = _attrs(built, GRANTED_RECOVERY_ATTR, set())
    assert granted == _attrs(loaded, GRANTED_RECOVERY_ATTR, set())
    assert granted or name != "Shackles of Treachery"

    monkeypatch.setitem(trees._TREES_MEMO, card["oracle_id"], loaded)
    assert sorted(map(repr, extract_signals(card))) == live
