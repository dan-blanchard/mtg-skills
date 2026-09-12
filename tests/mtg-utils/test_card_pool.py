"""Tests for CardPool — the one owner of the bulk and every index over it (ADR-0046).

The interface is the test surface: one name-index policy (cheapest priced game-layout
printing, text-bearing preferred, tokens never), ``by_id`` reaching tokens, the
per-format rarity index, the printing indexes, folded-object resolution, the Arena
alias map, per-process memoization, and the loud no-bulk failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtg_utils.bulk_loader import clear_memory_cache
from mtg_utils.card_pool import CardPool, NoBulkError, is_game_card
from mtg_utils.formats import FORMATS


def _card(name: str, **extra) -> dict:
    base = {
        "id": extra.pop("id", f"id-{name}"),
        "oracle_id": extra.pop("oracle_id", f"oid-{name}"),
        "name": name,
        "layout": "normal",
        "type_line": "Artifact",
        "oracle_text": f"{name} does a thing.",
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.00"},
    }
    base.update(extra)
    return base


def _bulk(tmp_path: Path, cards: list[dict], name: str = "bulk.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(cards), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _fresh_memo():
    CardPool.clear_memo()
    clear_memory_cache()
    yield
    CardPool.clear_memo()
    clear_memory_cache()


# --- loading -----------------------------------------------------------------------


def test_load_raises_no_bulk_error_naming_the_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    with pytest.raises(NoBulkError, match="download-mtgjson"):
        CardPool.load(None)
    with pytest.raises(NoBulkError, match="download-mtgjson"):
        CardPool.load(tmp_path / "missing.json")


def test_load_is_memoized_per_process(tmp_path):
    bulk = _bulk(tmp_path, [_card("Sol Ring")])
    assert CardPool.load(bulk) is CardPool.load(bulk)


def test_identity_tracks_the_bulk_file(tmp_path):
    bulk = _bulk(tmp_path, [_card("Sol Ring")])
    before = CardPool.load(bulk).identity
    assert before != "memory"
    assert CardPool.from_cards([]).identity == "memory"
    # A rewritten bulk (download-mtgjson refresh) changes the identity token.
    _bulk(tmp_path, [_card("Sol Ring"), _card("Arcane Signet")])
    CardPool.clear_memo()
    clear_memory_cache()
    assert CardPool.load(bulk).identity != before


# --- the ONE name-index policy -------------------------------------------------------


def test_by_name_folds_and_keeps_display_name():
    pool = CardPool.from_cards([_card("Lim-Dûl's Vault")])
    assert pool.lookup("lim-dul's vault")["name"] == "Lim-Dûl's Vault"
    assert pool.lookup("Nope") is None


def test_by_name_prefers_cheapest_priced_printing():
    pool = CardPool.from_cards(
        [
            _card("Sol Ring", id="a", prices={"usd": "9.00"}),
            _card("Sol Ring", id="b", prices={"usd": None}),
            _card("Sol Ring", id="c", prices={"usd": "1.00"}),
        ]
    )
    assert pool.by_name["Sol Ring"]["id"] == "c"


def test_by_name_prefers_a_printing_with_oracle_text_over_a_cheaper_blank():
    # The proxy path's rule folded into the one policy: a text-less placeholder
    # printing never wins the name, however cheap.
    pool = CardPool.from_cards(
        [
            _card("Chaos Orb", id="blank", oracle_text="", prices={"usd": "0.10"}),
            _card("Chaos Orb", id="text", prices={"usd": "500.00"}),
        ]
    )
    assert pool.by_name["Chaos Orb"]["id"] == "text"


def test_by_name_never_serves_tokens_or_memorabilia_but_by_id_does():
    token = _card("Soldier", id="tok", layout="token")
    memo = _card("Memo", id="memo", set_type="memorabilia")
    art = _card("Showcase", id="art", layout="art_series")
    pool = CardPool.from_cards([_card("Real Card"), token, memo, art])
    assert "Real Card" in pool.by_name
    for name in ("Soldier", "Memo", "Showcase"):
        assert name not in pool.by_name
    assert pool.by_id["tok"] is token
    assert pool.by_id["memo"] is memo
    assert not is_game_card(token)


def test_by_name_indexes_every_dfc_face():
    dfc = _card(
        "Bruna, the Fading Light // Brisela, Voice of Nightmares",
        card_faces=[
            {"name": "Bruna, the Fading Light"},
            {"name": "Brisela, Voice of Nightmares"},
        ],
    )
    pool = CardPool.from_cards([dfc])
    assert pool.lookup("Bruna, the Fading Light") is dfc
    assert pool.lookup("Brisela, Voice of Nightmares") is dfc


# --- rarity index ----------------------------------------------------------------


def test_rarity_index_takes_the_lowest_legal_rarity_and_is_memoized():
    pool = CardPool.from_cards(
        [
            _card("Lightning Bolt", id="a", rarity="rare", games=["arena", "paper"]),
            _card("Lightning Bolt", id="b", rarity="uncommon", games=["arena"]),
            _card("Lightning Bolt", id="c", rarity="common", games=["paper"]),
            _card("Banned One", rarity="common", legalities={"commander": "banned"}),
        ]
    )
    fmt = FORMATS["commander"]
    idx = pool.rarity_index(fmt, arena_only=True)
    assert idx["Lightning Bolt"]["rarity"] == "uncommon"
    assert "Banned One" not in idx
    assert pool.rarity_index(fmt, arena_only=True) is idx
    assert pool.rarity_index(fmt)["Lightning Bolt"]["rarity"] == "common"


# --- printings, folded objects, aliases ---------------------------------------------


def test_printings_keep_every_addable_printing_newest_first():
    old = _card("Sol Ring", id="old", released_at="1993-08-05")
    new = _card("Sol Ring", id="new", released_at="2024-01-01")
    token = _card("Soldier", id="tok", layout="token", oracle_id="oid-tok")
    pool = CardPool.from_cards([old, new, token])
    assert [p["id"] for p in pool.printings_by_oracle["oid-Sol Ring"]] == ["new", "old"]
    assert pool.printing_by_id["old"] is old
    assert "tok" not in pool.printing_by_id


def test_resolve_object_finds_dungeons_emblems_and_meld_results_by_front_face():
    dungeon = _card("Lost Mine of Phandelver", type_line="Dungeon")
    ring = _card("The Ring // The Ring Tempts You", type_line="Emblem // Emblem")
    brisela = _card("Brisela, Voice of Nightmares", type_line="Legendary Creature")
    bruna = _card(
        "Bruna, the Fading Light",
        all_parts=[
            {"component": "meld_result", "name": "Brisela, Voice of Nightmares"}
        ],
    )
    pool = CardPool.from_cards([dungeon, ring, brisela, bruna])
    assert pool.resolve_object("Lost Mine of Phandelver") is dungeon
    assert pool.resolve_object("The Ring") is ring
    assert pool.resolve_object("Brisela, Voice of Nightmares") is brisela
    assert pool.resolve_object("Bruna, the Fading Light") is None
    assert "Lost Mine of Phandelver" in pool.by_name  # addability is by_name's call


def test_name_aliases_map_arena_names_to_canonical():
    pool = CardPool.from_cards(
        [
            _card("Masked Meower", printed_name="Skittering Kitten", games=["arena"]),
            _card("Paper Only", printed_name="Ignored", games=["paper"]),
        ]
    )
    assert pool.name_aliases == {"skittering kitten": "masked meower"}


def test_unreleased_ids_is_empty_for_an_ordinary_pool():
    assert CardPool.from_cards([_card("Sol Ring")]).unreleased_ids == frozenset()
