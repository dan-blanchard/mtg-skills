"""The per-card tree reads' write-back sidecar (``card_reads``): a process
attached to a bulk persists each read's value per card, and the next one serves it
without building the card's trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis import card_reads, roles, signals
from mtg_utils._analysis.lanes import card_advantage
from mtg_utils._analysis.write_back import MISSING
from mtg_utils._card_ir import trees
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _reads(signet: dict, opal: dict, crawler: dict) -> tuple:
    return (
        roles._mana_effects(signet),
        roles._conditionally_gated(opal),
        card_reads.has_trees(signet),
        card_advantage.card_self_return_routes(crawler),
        signals._membership_free_signals(crawler),
    )


def test_the_card_read_sidecar_serves_what_a_process_wrote_back(monkeypatch, tmp_path):
    """Arcane Signet's mana, Mox Opal's metalcraft gate, Gravecrawler's return from
    the graveyard and its signals are written back at the first process's flush
    and served to the next as the live reads' values, with no tree read; another
    bulk (its identity is the key) serves nothing."""
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    signet, opal = _real("Arcane Signet"), _real("Mox Opal")
    crawler = _real("Gravecrawler")

    card_reads.CARD_READS.detach()
    assert card_reads.attach_card_read_sidecar(bulk)
    live = _reads(signet, opal, crawler)
    assert all(live)
    card_reads.CARD_READS.flush()
    assert (tmp_path / "AllPrintings.json.card-reads.pkl").is_file()

    card_reads.CARD_READS.detach()
    assert card_reads.attach_card_read_sidecar(bulk)

    def no_trees(*_a, **_k):
        raise AssertionError("served from the sidecar, never read off the trees")

    for module in (roles, card_reads, trees):
        monkeypatch.setattr(module, "trees_for", no_trees)
    monkeypatch.setattr(signals, "extract_signals", no_trees)
    assert _reads(signet, opal, crawler) == live

    bulk.write_text("[ ]")  # another bulk: another key
    assert card_reads.attach_card_read_sidecar(bulk)
    assert card_reads.CARD_READS.served("has_trees", signet["oracle_id"]) is MISSING


def test_a_card_with_no_phase_records_is_never_persisted(tmp_path):
    """A process without the card's phase records reads it empty: that answer is
    memoized for the process, never written back for one that has them."""
    bulk = tmp_path / "AllPrintings.json"
    bulk.write_text("[]")
    card_reads.CARD_READS.detach()
    assert card_reads.attach_card_read_sidecar(bulk)
    stranger = {"name": "Card Nobody Printed", "oracle_id": "no-such-oracle-id"}
    assert card_reads.has_trees(stranger) is False
    card_reads.CARD_READS.flush()
    card_reads.CARD_READS.detach()
    assert card_reads.attach_card_read_sidecar(bulk)
    assert card_reads.CARD_READS.served("has_trees", "no-such-oracle-id") is MISSING


def test_a_read_is_read_again_when_its_trees_are_replaced(monkeypatch):
    """A value is kept with the trees it was read from: replacing them (the
    testkit seeding real trees over a phase-less process's empty ones) re-reads."""
    calls = []

    @card_reads.card_read("test_tree_count")
    def tree_count(card: dict) -> int:
        calls.append(card["name"])
        return len(trees.trees_for(card))

    opal = _real("Mox Opal")
    oid = opal["oracle_id"]
    real = trees.memoized_trees(oid)
    assert real
    assert tree_count(opal) == len(real)
    assert tree_count(opal) == len(real)
    assert calls == ["Mox Opal"]
    monkeypatch.setitem(trees._TREES_MEMO, oid, ())
    assert tree_count(opal) == 0
    assert calls == ["Mox Opal", "Mox Opal"]


@pytest.mark.parametrize("name", ["Arcane Signet", "Mox Opal", "Gravecrawler"])
def test_a_card_read_is_the_live_read(name):
    """The memoized read answers what the undecorated read computes."""
    card = _real(name)
    assert roles._mana_effects(card) == roles._mana_effects.__wrapped__(card)
    assert card_reads.has_trees(card) == card_reads.has_trees.__wrapped__(card)


def test_a_card_whose_trees_depend_on_the_read_order_is_read_live():
    """Claim // Fame's Fame half has no phase record: its trees with the bulk
    faces hold a text-only tree the plain ones don't, and the trees memo keeps
    whichever is built first. A per-card read of it is never memoized or
    persisted, so each caller reads what it read before; a one-face card is."""
    calls = []

    @card_reads.card_read("test_live_reads")
    def name_of(card: dict) -> str:
        calls.append(card["name"])
        return card["name"]

    claim, opal = _real("Claim // Fame"), _real("Mox Opal")
    assert trees.reads_bulk_faces(claim)
    assert not trees.reads_bulk_faces(opal)
    for _ in range(2):
        name_of(claim)
        name_of(opal)
    assert calls == ["Claim // Fame", "Mox Opal", "Claim // Fame"]
