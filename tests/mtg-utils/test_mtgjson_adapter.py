"""Unit tests for the pure MTGJSON → Scryfall-record adapter functions.

Synthetic inputs modeled on real v5.3.0 shapes (Arlinn, Sunfall, Human token) so the
suite runs in CI with no MTGJSON data on disk.
"""

from __future__ import annotations

from mtg_utils._mtgjson import adapter
from mtg_utils._mtgjson.load import (
    ALLPRICES_NAME,
    ALLPRINTINGS_NAME,
    MTGJSON_FILES,
    _group_faces,
    flatten,
    source_files,
)
from mtg_utils.card_classify import get_mana_cost, get_oracle_text


# ── normalize_legalities ──────────────────────────────────────────────────────
def test_normalize_legalities_lowercases_values():
    out = adapter.normalize_legalities({"commander": "Legal", "vintage": "Restricted"})
    assert out["commander"] == "legal"
    assert out["vintage"] == "restricted"


def test_normalize_legalities_fills_omitted_formats_as_not_legal():
    # MTGJSON omits not-legal formats; Scryfall carries every format as "not_legal".
    out = adapter.normalize_legalities({"commander": "Legal"})
    assert out["standard"] == "not_legal"
    assert out["modern"] == "not_legal"


def test_normalize_legalities_banned_lowercased():
    out = adapter.normalize_legalities({"modern": "Banned"})
    assert out["modern"] == "banned"


def test_normalize_legalities_none_is_all_not_legal():
    out = adapter.normalize_legalities(None)
    assert out["commander"] == "not_legal"
    assert set(out.values()) == {"not_legal"}


# ── image_uris ────────────────────────────────────────────────────────────────
def test_image_uris_front_scheme():
    out = adapter.image_uris("32e29c7d-ed4b-4eff-b3c2-d99e5b63ef8d")
    assert out["normal"] == (
        "https://cards.scryfall.io/normal/front/3/2/"
        "32e29c7d-ed4b-4eff-b3c2-d99e5b63ef8d.jpg"
    )
    assert out["small"].startswith("https://cards.scryfall.io/small/front/3/2/")
    assert out["art_crop"].startswith("https://cards.scryfall.io/art_crop/front/3/2/")


def test_image_uris_back_face():
    out = adapter.image_uris("038c2d23-50d0-4590-87f9-f4099832da06", face="back")
    assert out["normal"] == (
        "https://cards.scryfall.io/normal/back/0/3/"
        "038c2d23-50d0-4590-87f9-f4099832da06.jpg"
    )


def test_image_uris_missing_id_is_none():
    assert adapter.image_uris(None) is None


# ── prices ────────────────────────────────────────────────────────────────────
def _price_entry():
    return {
        "paper": {
            "tcgplayer": {
                "retail": {
                    "normal": {"2026-06-27": 3.37},
                    "foil": {"2026-06-27": 4.56},
                },
                "currency": "USD",
            },
            "cardmarket": {
                "retail": {"normal": {"2026-06-27": 3.38}},
                "currency": "EUR",
            },
        },
        "mtgo": {"cardhoarder": {"retail": {"normal": {"2026-06-27": 0.02}}}},
    }


def test_prices_usd_from_tcgplayer():
    out = adapter.prices("u1", {"u1": _price_entry()})
    assert out["usd"] == "3.37"
    assert out["usd_foil"] == "4.56"


def test_prices_eur_from_cardmarket_and_tix_from_cardhoarder():
    out = adapter.prices("u1", {"u1": _price_entry()})
    assert out["eur"] == "3.38"
    assert out["tix"] == "0.02"


def test_prices_missing_uuid_is_empty():
    assert adapter.prices("absent", {}) == {}


# ── token_part / meld_parts ───────────────────────────────────────────────────
def test_token_part_component():
    token = {
        "name": "Human",
        "type": "Token Creature — Human",
        "identifiers": {
            "scryfallId": "b7667345-e11b-4cad-ac4c-84eb1c5656c5",
            "scryfallOracleId": "30272edf-097c-4918-84d2-9fa6c42dbe0a",
        },
    }
    p = adapter.token_part(token)
    assert p["component"] == "token"
    assert p["id"] == "b7667345-e11b-4cad-ac4c-84eb1c5656c5"
    assert p["name"] == "Human"
    assert p["oracle_id"] == "30272edf-097c-4918-84d2-9fa6c42dbe0a"


def test_token_part_uses_combined_name_for_df_token():
    # A double-faced token's all_part name is the combined "A // B" (matches Scryfall),
    # not the per-face name — so it's distinguishable in a token list.
    df = {
        "name": "Incubator // Phyrexian",
        "faceName": "Incubator",
        "type": "Token Artifact — Incubator",
        "identifiers": {"scryfallId": "c5", "scryfallOracleId": "dd"},
    }
    assert adapter.token_part(df)["name"] == "Incubator // Phyrexian"


def test_meld_parts_empty_for_non_meld():
    assert adapter.meld_parts({"layout": "normal"}, {}) == []
    assert adapter.meld_parts({"layout": "meld"}, None) == []


# ── translate_card: single-face ───────────────────────────────────────────────
def _sunfall():
    return {
        "name": "Sunfall",
        "text": "Exile all creatures...",
        "type": "Sorcery",
        "types": ["Sorcery"],
        "subtypes": [],
        "supertypes": [],
        "manaValue": 5.0,
        "manaCost": "{3}{W}{W}",
        "colors": ["W"],
        "colorIdentity": ["W"],
        "keywords": [],
        "rarity": "rare",
        "setCode": "MOM",
        "number": "38",
        "availability": ["arena", "mtgo", "paper"],
        "layout": "normal",
        "legalities": {"commander": "Legal", "modern": "Legal"},
        "identifiers": {
            "scryfallId": "b961b23d-a16f-4126-9293-2906dc2aba79",
            "scryfallOracleId": "fb3f5097-0da0-458c-8508-60823567e2da",
        },
    }


def test_translate_single_face_core_fields():
    rec = adapter.translate_card([_sunfall()])
    assert rec["name"] == "Sunfall"
    assert rec["oracle_id"] == "fb3f5097-0da0-458c-8508-60823567e2da"
    assert rec["id"] == "b961b23d-a16f-4126-9293-2906dc2aba79"
    assert rec["oracle_text"] == "Exile all creatures..."
    assert rec["type_line"] == "Sorcery"
    assert rec["cmc"] == 5.0
    assert rec["mana_cost"] == "{3}{W}{W}"
    assert rec["color_identity"] == ["W"]
    assert rec["rarity"] == "rare"
    assert rec["set"] == "mom"  # lowercased
    assert rec["collector_number"] == "38"
    assert rec["legalities"]["commander"] == "legal"
    assert rec["legalities"]["standard"] == "not_legal"  # filled
    assert set(rec["games"]) == {"paper", "arena", "mtgo"}
    # New pre-split arrays exposed for the _subtypes precision gate.
    assert rec["types"] == ["Sorcery"]


def test_translate_single_face_has_image_uris():
    rec = adapter.translate_card([_sunfall()])
    assert rec["image_uris"]["normal"].startswith(
        "https://cards.scryfall.io/normal/front/b/9/"
    )


def test_translate_meld_piece_uses_face_name():
    # A meld piece is a single, un-collapsed entry whose `name` is the combined meld
    # name; Scryfall names the piece singularly (its faceName). Without this, the
    # meld_pair signal subject drifts (Bruna parity diff).
    piece = {
        "name": "Bruna, the Fading Light // Brisela, Voice of Nightmares",
        "faceName": "Bruna, the Fading Light",
        "layout": "meld",
        "type": "Legendary Creature — Angel Horror",
        "types": ["Creature"],
        "otherFaceIds": ["result-uuid"],
        "uuid": "bruna-uuid",
        "identifiers": {"scryfallId": "aa11", "scryfallOracleId": "o"},
    }
    rec = adapter.translate_card([piece])
    assert rec["name"] == "Bruna, the Fading Light"


def test_translate_game_changer_bool():
    c = _sunfall()
    assert adapter.translate_card([c]).get("game_changer") is False
    c["isGameChanger"] = True
    assert adapter.translate_card([c])["game_changer"] is True


# ── translate_card: DFC collapse ──────────────────────────────────────────────
def _arlinn_faces():
    front = {
        "name": "Arlinn, the Pack's Hope // Arlinn, the Moon's Fury",
        "faceName": "Arlinn, the Pack's Hope",
        "side": "a",
        "text": "Daybound...",
        "type": "Legendary Planeswalker — Arlinn",
        "types": ["Planeswalker"],
        "subtypes": ["Arlinn"],
        "supertypes": ["Legendary"],
        "manaValue": 4.0,
        "faceManaValue": 4.0,
        "manaCost": "{2}{R}{G}",
        "loyalty": "4",
        "colors": ["G", "R"],
        "colorIdentity": ["G", "R"],
        "keywords": ["Daybound", "Nightbound"],
        "producedMana": ["G", "R"],
        "rarity": "mythic",
        "setCode": "MID",
        "number": "245",
        "availability": ["arena", "mtgo", "paper"],
        "layout": "transform",
        "otherFaceIds": ["uuid-b"],
        "uuid": "uuid-a",
        "legalities": {"commander": "Legal"},
        "identifiers": {
            "scryfallId": "50d4b0df-a1d8-494f-a019-70ce34161320",
            "scryfallOracleId": "f227ce07-7e96-4a36-ab7c-9be6e777d649",
        },
    }
    back = {
        "name": "Arlinn, the Pack's Hope // Arlinn, the Moon's Fury",
        "faceName": "Arlinn, the Moon's Fury",
        "side": "b",
        "text": "Nightbound...",
        "type": "Legendary Planeswalker — Arlinn",
        "types": ["Planeswalker"],
        "subtypes": ["Arlinn"],
        "supertypes": ["Legendary"],
        "manaValue": 4.0,
        "faceManaValue": 0.0,
        "manaCost": None,
        "loyalty": "4",
        "colors": ["G", "R"],
        "colorIdentity": ["G", "R"],
        "keywords": ["Daybound", "Nightbound"],
        "producedMana": ["G", "R"],
        "rarity": "mythic",
        "setCode": "MID",
        "number": "245",
        "availability": ["arena", "mtgo", "paper"],
        "layout": "transform",
        "otherFaceIds": ["uuid-a"],
        "uuid": "uuid-b",
        "legalities": {"commander": "Legal"},
        "identifiers": {
            "scryfallId": "50d4b0df-a1d8-494f-a019-70ce34161320",
            "scryfallOracleId": "f227ce07-7e96-4a36-ab7c-9be6e777d649",
        },
    }
    return [front, back]


def test_translate_dfc_builds_card_faces_joined_type_line():
    rec = adapter.translate_card(_arlinn_faces())
    assert rec["name"] == "Arlinn, the Pack's Hope // Arlinn, the Moon's Fury"
    assert rec["cmc"] == 4.0
    # Scryfall joins every face's type with " // " at the top level.
    assert rec["type_line"] == (
        "Legendary Planeswalker — Arlinn // Legendary Planeswalker — Arlinn"
    )
    faces = rec["card_faces"]
    assert [f["name"] for f in faces] == [
        "Arlinn, the Pack's Hope",
        "Arlinn, the Moon's Fury",
    ]
    assert faces[0]["oracle_text"] == "Daybound..."
    assert faces[1]["oracle_text"] == "Nightbound..."
    # Front carries its cost; back's is empty — matching Scryfall's per-face shape.
    assert faces[0]["mana_cost"] == "{2}{R}{G}"
    assert faces[1]["mana_cost"] == ""


def test_translate_dfc_top_text_and_cost_fold_via_accessors():
    # Like Scryfall, a multi-face card leaves top-level oracle_text/mana_cost empty;
    # get_oracle_text / get_mana_cost fold both faces so signals see the whole card.
    rec = adapter.translate_card(_arlinn_faces())
    assert rec.get("oracle_text", "") == ""
    folded = get_oracle_text(rec)
    assert "Daybound" in folded
    assert "Nightbound" in folded
    assert get_mana_cost(rec) == "{2}{R}{G}"


def test_translate_dfc_images_under_faces_not_top():
    rec = adapter.translate_card(_arlinn_faces())
    assert rec.get("image_uris") is None
    faces = rec["card_faces"]
    assert "/front/" in faces[0]["image_uris"]["normal"]
    assert "/back/" in faces[1]["image_uris"]["normal"]


def test_translate_dfc_produced_mana_union():
    rec = adapter.translate_card(_arlinn_faces())
    assert set(rec["produced_mana"]) == {"G", "R"}


# ── _group_faces / flatten ────────────────────────────────────────────────────
def _entry(
    uuid,
    name,
    *,
    other=None,
    side=None,
    typ="Creature",
    setcode="X",
    oid=None,
    sid=None,
):
    return {
        "uuid": uuid,
        "name": name,
        "type": typ,
        "setCode": setcode,
        "side": side,
        "otherFaceIds": other or [],
        "identifiers": {"scryfallOracleId": oid or uuid, "scryfallId": sid or uuid},
    }


def test_group_faces_merges_dfc_faces():
    cards = [
        _entry("a", "A // B", other=["b"], side="a"),
        _entry("b", "A // B", other=["a"], side="b"),
    ]
    groups = _group_faces(cards)
    assert len(groups) == 1
    assert {e["uuid"] for e in groups[0]} == {"a", "b"}


def test_group_faces_keeps_distinct_printings_separate():
    # Two printings of one DFC → two groups, not one merged blob.
    cards = [
        _entry("a1", "A // B", other=["b1"], side="a"),
        _entry("b1", "A // B", other=["a1"], side="b"),
        _entry("a2", "A // B", other=["b2"], side="a"),
        _entry("b2", "A // B", other=["a2"], side="b"),
    ]
    groups = _group_faces(cards)
    assert len(groups) == 2
    assert all(len(g) == 2 for g in groups)


def test_group_faces_meld_pieces_stay_separate():
    # Meld links never form a shared frozenset → 3 singleton groups (Scryfall keeps
    # meld pieces as separate records, not card_faces).
    cards = [
        _entry("piece1", "Piece One", other=["result"]),
        _entry("piece2", "Piece Two", other=["result"]),
        _entry("result", "Result", other=["piece1", "piece2"]),
    ]
    groups = _group_faces(cards)
    assert len(groups) == 3
    assert all(len(g) == 1 for g in groups)


def test_group_faces_normal_card_is_singleton():
    groups = _group_faces([_entry("x", "Bear")])
    assert len(groups) == 1
    assert len(groups[0]) == 1


def test_flatten_emits_cards_and_tokens():
    data = {
        "SET": {
            "cards": [_entry("c1", "Bear", oid="oid-bear", sid="sid-bear")],
            "tokens": [
                {
                    "uuid": "t1",
                    "name": "Treasure",
                    "type": "Token Artifact — Treasure",
                    "layout": "token",
                    "identifiers": {
                        "scryfallId": "sid-tre",
                        "scryfallOracleId": "oid-tre",
                    },
                }
            ],
        }
    }
    out = flatten(data)
    by_id = {r["id"]: r for r in out}
    assert "sid-bear" in by_id
    assert "sid-tre" in by_id
    assert by_id["sid-tre"]["type_line"] == "Token Artifact — Treasure"


# ── layout-aware top-level multi-face fields (verified vs live Scryfall) ─────────
def _two_face(layout, *, fcost="{1}{U}", bcost="{2}{B}", fpow=None, ftou=None):
    def face(nm, side, typ, cost, p, t):
        return {
            "name": "Front // Back",
            "faceName": nm,
            "side": side,
            "type": typ,
            "manaCost": cost,
            "manaValue": 3.0,
            "layout": layout,
            "power": p,
            "toughness": t,
            "colors": ["U"] if side == "a" else ["B"],
            "otherFaceIds": ["b" if side == "a" else "a"],
            "uuid": side,
            "identifiers": {"scryfallId": "aa11", "scryfallOracleId": "o"},
        }

    return [
        face("Front", "a", "Creature — Bear", fcost, fpow, ftou),
        face("Back", "b", "Sorcery", bcost, None, None),
    ]


def test_flip_keeps_top_pt_and_front_cost():
    rec = adapter.translate_card(_two_face("flip", fpow="2", ftou="2"))
    assert rec["power"] == "2"
    assert rec["toughness"] == "2"
    assert rec["mana_cost"] == "{1}{U}"  # front only


def test_adventure_keeps_top_pt_and_joined_cost():
    rec = adapter.translate_card(_two_face("adventure", fpow="3", ftou="4"))
    assert rec["power"] == "3"
    assert rec["mana_cost"] == "{1}{U} // {2}{B}"  # joined


def test_split_joined_cost_no_pt():
    rec = adapter.translate_card(_two_face("split"))
    assert rec["mana_cost"] == "{1}{U} // {2}{B}"
    assert "power" not in rec


def test_transform_omits_top_pt_cost_and_colors():
    rec = adapter.translate_card(_two_face("transform", fpow="2", ftou="2"))
    assert "power" not in rec
    assert "mana_cost" not in rec
    assert "colors" not in rec


def test_produced_mana_omitted_when_empty():
    c = _sunfall()  # no producedMana
    assert "produced_mana" not in adapter.translate_card([c])


def test_meld_piece_emits_meld_result_all_part():
    piece = {
        "name": "Bruna // Brisela",
        "faceName": "Bruna",
        "layout": "meld",
        "type": "Creature — Angel",
        "otherFaceIds": ["result"],
        "uuid": "bruna",
        "identifiers": {"scryfallId": "bb22", "scryfallOracleId": "ob"},
    }
    result = {
        "name": "Brisela, Voice of Nightmares",
        "faceName": "Brisela",
        "layout": "meld",
        "type": "Creature — Eldrazi Angel",
        "otherFaceIds": ["bruna", "gisela"],
        "uuid": "result",
        "identifiers": {"scryfallId": "cc33", "scryfallOracleId": "obr"},
    }
    rec = adapter.translate_card([piece], card_by_uuid={"result": result})
    meld = [p for p in rec["all_parts"] if p["component"] == "meld_result"]
    assert len(meld) == 1
    assert meld[0]["name"] == "Brisela"


# ── oracle-level legality aggregation ───────────────────────────────────────────
def test_aggregate_legalities_most_permissive_across_printings():
    # Karn-shape: most printings Legal, an oversized one omits commander → legal.
    out = adapter.aggregate_legalities(
        [{"commander": "Legal", "vintage": "Legal"}, {"vintage": "Legal"}, None]
    )
    assert out["commander"] == "legal"
    assert out["vintage"] == "legal"
    assert out["standard"] == "not_legal"


def test_aggregate_legalities_banned_when_no_legal_printing():
    out = adapter.aggregate_legalities([{"legacy": "Banned"}, {"legacy": "Banned"}])
    assert out["legacy"] == "banned"


def test_translate_uses_oracle_legalities_index():
    c = _sunfall()  # its own legalities say modern Legal
    idx = {
        "fb3f5097-0da0-458c-8508-60823567e2da": dict.fromkeys(
            adapter._LEGALITY_FORMATS, "not_legal"
        )
        | {"commander": "legal"}
    }
    rec = adapter.translate_card([c], legalities_index=idx)
    assert rec["legalities"]["commander"] == "legal"
    assert rec["legalities"]["modern"] == "not_legal"  # index overrides own


def test_gate_arena_formats_forces_not_legal_off_arena():
    leg = dict.fromkeys(adapter._LEGALITY_FORMATS, "legal")
    out = adapter.gate_arena_formats(leg, arena_available=False)
    assert out["historic"] == "not_legal"
    assert out["brawl"] == "not_legal"
    assert out["timeless"] == "not_legal"
    assert out["commander"] == "legal"  # paper format untouched


def test_gate_arena_formats_noop_when_arena_available():
    leg = dict.fromkeys(adapter._LEGALITY_FORMATS, "legal")
    assert adapter.gate_arena_formats(leg, arena_available=True) == leg


def test_translate_cmc_defaults_zero_when_manavalue_absent():
    tok = {
        "name": "Treasure",
        "type": "Token Artifact — Treasure",
        "identifiers": {"scryfallId": "t1", "scryfallOracleId": "to"},
    }
    assert adapter.translate_card([tok])["cmc"] == 0.0


def test_translate_threads_set_metadata():
    rec = adapter.translate_card(
        [_sunfall()],
        set_meta={
            "set_type": "expansion",
            "set_name": "MOM",
            "released_at": "2023-04-21",
        },
    )
    assert rec["set_type"] == "expansion"
    assert rec["set_name"] == "MOM"
    assert rec["released_at"] == "2023-04-21"


# ── flatten: oracle-level token graph + DF-token collapse ───────────────────────
def _maker(uuid, oid, *, tokens=None, setcode="X"):
    return {
        "uuid": uuid,
        "name": "Goblin Boss",
        "type": "Creature — Goblin",
        "manaValue": 2.0,
        "setCode": setcode,
        "identifiers": {"scryfallId": uuid, "scryfallOracleId": oid},
        "relatedCards": {"tokens": tokens or []},
    }


def _tok(uuid, sid, oid, name, *, side=None):
    return {
        "uuid": uuid,
        "name": name,
        "faceName": name.split(" // ")[0] if " // " in name else None,
        "type": f"Token Creature — {name}",
        "side": side,
        "layout": "token",
        "identifiers": {"scryfallId": sid, "scryfallOracleId": oid},
    }


def test_flatten_token_survives_token_less_printing():
    # Maker printed twice: a normal printing references its token, a promo printing omits
    # relatedCards.tokens. Oracle-level aggregation must give BOTH maker records the token.
    data = {
        "MAIN": {
            "type": "expansion",
            "name": "Main",
            "releaseDate": "2020-01-01",
            "cards": [_maker("m1", "MOID", tokens=["t1"], setcode="MAIN")],
            "tokens": [_tok("t1", "sidGob", "TOID", "Goblin")],
        },
        "PROMO": {
            "type": "promo",
            "name": "Promo",
            "releaseDate": "2021-01-01",
            "cards": [_maker("m2", "MOID", tokens=[], setcode="PROMO")],
            "tokens": [],
        },
    }
    out = flatten(data)
    makers = [r for r in out if r["name"] == "Goblin Boss"]
    assert len(makers) == 2
    for r in makers:
        toks = [p for p in (r.get("all_parts") or []) if p["component"] == "token"]
        assert [p["name"] for p in toks] == ["Goblin"], r["set"]


def test_flatten_df_token_collapses_by_scryfall_id():
    # Two faces sharing one scryfallId collapse to ONE record (no by-id collision).
    data = {
        "EOC": {
            "type": "commander",
            "name": "EOC",
            "releaseDate": "2024-01-01",
            "cards": [],
            "tokens": [
                _tok("ta", "c5", "dd", "Incubator // Phyrexian", side="a"),
                _tok("tb", "c5", "dd", "Incubator // Phyrexian", side="b"),
            ],
        }
    }
    out = flatten(data)
    by_id = {r["id"]: r for r in out}
    assert "c5" in by_id  # single record, no collision
    rec = by_id["c5"]
    assert rec["name"] == "Incubator // Phyrexian"
    assert len(rec["card_faces"]) == 2


# ── source descriptor (one home for "which files an MTGJSON source is") ─────────
def test_source_files_lists_printings_then_prices(tmp_path):
    printings = tmp_path / ALLPRINTINGS_NAME
    # The loader and the freshness check resolve the SAME set off the printings path.
    assert source_files(printings) == [printings, tmp_path / ALLPRICES_NAME]
    # ...and download fetches exactly those names — one home, so they can't drift.
    assert MTGJSON_FILES == (ALLPRINTINGS_NAME, ALLPRICES_NAME)
