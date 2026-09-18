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
    assert pool.by_name.get("lim-dul's vault")["name"] == "Lim-Dûl's Vault"
    assert pool.by_name.get("Nope") is None


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
    assert pool.by_name.get("Bruna, the Fading Light") is dfc
    assert pool.by_name.get("Brisela, Voice of Nightmares") is dfc


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


class TestRarityIndex:
    def test_finds_lowest_rarity(self, tmp_path):
        cards = [
            {
                "name": "Dual Card",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
            },
            {
                "name": "Dual Card",
                "rarity": "uncommon",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert index["dual card"]["rarity"] == "uncommon"
        assert index["dual card"]["exempt_from_4cap"] is False

    def test_filters_by_legality(self, tmp_path):
        cards = [
            {
                "name": "Arena Card",
                "rarity": "common",
                "legalities": {"brawl": "legal", "commander": "not_legal"},
            },
            {
                "name": "Arena Card",
                "rarity": "rare",
                "legalities": {"brawl": "legal", "commander": "not_legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        # Legal in brawl — should find common
        index = CardPool.load(bulk_path).rarity_index(FORMATS["historic_brawl"])
        assert index["arena card"]["rarity"] == "common"
        # Not legal in commander — should be absent
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert "arena card" not in index

    def test_treats_special_as_rare(self, tmp_path):
        cards = [
            {
                "name": "Special Card",
                "rarity": "special",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert index["special card"]["rarity"] == "rare"

    def test_indexes_front_face_of_split_cards(self, tmp_path):
        cards = [
            {
                "name": "Fire // Ice",
                "rarity": "uncommon",
                "legalities": {"commander": "legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert index["fire // ice"]["rarity"] == "uncommon"
        assert index["fire"]["rarity"] == "uncommon"

    def test_exempt_from_4cap_for_any_number_cards(self, tmp_path):
        """Cards with 'A deck can have any number of cards named X' oracle
        text are flagged ``exempt_from_4cap=True`` so price-check can
        suppress the Arena 4-cap substitution for them."""
        cards = [
            {
                "name": "Hare Apparent",
                "rarity": "common",
                "legalities": {"commander": "legal"},
                "oracle_text": (
                    "When this creature enters, create a number of 1/1 white Rabbit creature tokens equal to the number of other creatures you control named Hare Apparent.\nA deck can have any number of cards named Hare Apparent."
                ),
            },
            {
                "name": "Regular Rare",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
                "oracle_text": "Draw a card.",
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert index["hare apparent"]["exempt_from_4cap"] is True
        assert index["regular rare"]["exempt_from_4cap"] is False

    def test_exempt_from_4cap_for_up_to_n_cards(self, tmp_path):
        """Cards with 'A deck can have up to N cards named X' oracle text
        are also flagged exempt — a deck can legitimately want 7 Seven
        Dwarves, so owning 4 is not infinite supply."""
        cards = [
            {
                "name": "Seven Dwarves",
                "rarity": "rare",
                "legalities": {"commander": "legal"},
                "oracle_text": (
                    "This creature gets +1/+1 for each other creature named Seven Dwarves you control.\nA deck can have up to seven cards named Seven Dwarves."
                ),
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        index = CardPool.load(bulk_path).rarity_index(FORMATS["commander"])
        assert index["seven dwarves"]["exempt_from_4cap"] is True

    def test_skips_draft_set_reprints_for_arena(self, tmp_path):
        """J21/JMP/AJMP reprints have draft-format rarities that don't match
        Arena wildcard cost.  A J21 common reprint should be excluded so the
        real printing's uncommon rarity wins. Round-trips an MTGJSON fixture so
        ``reprint`` is the adapter's own emission (from ``isReprint``) — a hand-built
        Scryfall-shaped record hid that MTGJSON never carried the field."""

        def printing(set_code, rarity, availability):
            return {
                "name": "Lightning Bolt",
                "uuid": f"u-{set_code}",
                "identifiers": {
                    "scryfallOracleId": "oid-bolt",
                    "scryfallId": f"s-{set_code}",
                },
                "type": "Instant",
                "types": ["Instant"],
                "manaValue": 1.0,
                "colorIdentity": ["R"],
                "layout": "normal",
                "availability": availability,
                "legalities": {"brawl": "Legal"},
                "setCode": set_code,
                "rarity": rarity,
                "isReprint": True,
            }

        data = {
            "data": {
                "J21": {
                    "code": "J21",
                    "name": "Jumpstart: Historic Horizons",
                    "type": "draft_innovation",
                    "releaseDate": "2021-08-26",
                    "cards": [printing("J21", "common", ["arena"])],
                },
                "STA": {
                    "code": "STA",
                    "name": "Strixhaven Mystical Archive",
                    "type": "masterpiece",
                    "releaseDate": "2021-04-23",
                    "cards": [printing("STA", "uncommon", ["arena", "mtgo", "paper"])],
                },
            }
        }
        bulk_path = tmp_path / "AllPrintings.json"
        bulk_path.write_text(json.dumps(data))
        index = CardPool.load(bulk_path).rarity_index(
            FORMATS["historic_brawl"], arena_only=True
        )
        assert index["lightning bolt"]["rarity"] == "uncommon"


class TestRarityIndexFormatBanOverrides:
    """Competitive Brawl reads the ``brawl`` legality key but legalizes every
    card that key marks ``banned`` (Force of Will, Mana Drain, ...) while
    enforcing its own ten-card list by name. The rarity index must honor the
    same overrides ``check_format_legality`` does, or ``price-check`` reports
    owned, legal staples as "illegal or not on Arena"."""

    def _bulk(self, tmp_path):
        cards = [
            {
                "name": "Force of Will",
                "rarity": "mythic",
                "games": ["arena"],
                "legalities": {"brawl": "banned"},
            },
            {
                "name": "Oko, Thief of Crowns",
                "rarity": "mythic",
                "games": ["arena"],
                "legalities": {"brawl": "banned"},
            },
            {
                "name": "Counterspell",
                "rarity": "uncommon",
                "games": ["arena"],
                "legalities": {"brawl": "legal"},
            },
            {
                "name": "Black Lotus",
                "rarity": "mythic",
                "games": ["paper"],
                "legalities": {"brawl": "not_legal"},
            },
        ]
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(cards))
        return bulk_path

    def test_default_still_excludes_key_banned_cards(self, tmp_path):
        index = CardPool.load(self._bulk(tmp_path)).rarity_index(
            FORMATS["historic_brawl"], arena_only=True
        )
        assert "force of will" not in index
        assert "counterspell" in index

    def test_competitive_brawl_admits_key_banned_cards(self, tmp_path):
        index = CardPool.load(self._bulk(tmp_path)).rarity_index(
            FORMATS["competitive_brawl"], arena_only=True
        )
        assert index["force of will"]["rarity"] == "mythic"
        assert index["counterspell"]["rarity"] == "uncommon"
        # not_legal still means "not in the pool at all".
        assert "black lotus" not in index

    def test_competitive_brawl_own_ban_list_is_excluded_by_name(self, tmp_path):
        # Oko is on Competitive Brawl's own ten-card list.
        index = CardPool.load(self._bulk(tmp_path)).rarity_index(
            FORMATS["competitive_brawl"], arena_only=True
        )
        assert "force of will" in index
        assert "oko, thief of crowns" not in index


def test_set_records_is_one_per_oracle_in_collector_order():
    first = _card("Alpha", set="hob", collector_number="12", id="a12")
    also = _card("Alpha", set="hob", collector_number="300", id="a300")  # a showcase
    other = _card("Beta", set="hob", collector_number="3", id="b3")
    elsewhere = _card("Gamma", set="m21", collector_number="1", id="g1")
    token = _card("Elf", set="thob", layout="token", oracle_id="oid-tok", id="t1")
    pool = CardPool.from_cards([also, elsewhere, first, other, token])
    assert [c["id"] for c in pool.set_records("HOB")] == ["b3", "a12"]
    assert pool.set_records("hob") is pool.set_records("HOB")  # memoized per code
    assert pool.set_records("nope") == []
