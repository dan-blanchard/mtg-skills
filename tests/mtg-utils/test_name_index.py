"""The shared name-indexing core (_name_index): one consistent keying + folding + DFC
handling that the per-builder index functions consume (candidate 03)."""

from mtg_utils._name_index import (
    NameIndex,
    _Tier,
    alias_keys,
    build_name_index,
    keep_cheaper,
)


def _keys(card):
    return {(k, t.name) for k, t in alias_keys(card)}


class TestAliasKeys:
    def test_canonical_key_is_folded(self):
        card = {"name": "Lim-Dûl's Vault"}
        assert (("lim-dul's vault", "CANONICAL")) in _keys(card)

    def test_ascii_and_diacritic_fold_to_same_key(self):
        # The whole point: an ASCII-typed name and the real diacritic name collapse.
        ascii_key = alias_keys({"name": "Lim-Dul's Vault"})[0][0]
        real_key = alias_keys({"name": "Lim-Dûl's Vault"})[0][0]
        assert ascii_key == real_key == "lim-dul's vault"

    def test_all_faces_indexed_via_card_faces(self):
        card = {
            "name": "Brazen Borrower // Petty Theft",
            "card_faces": [{"name": "Brazen Borrower"}, {"name": "Petty Theft"}],
        }
        keys = _keys(card)
        assert ("brazen borrower // petty theft", "CANONICAL") in keys
        assert ("brazen borrower", "FACE") in keys
        assert ("petty theft", "FACE") in keys  # the BACK face is indexed too

    def test_faces_fall_back_to_split_without_card_faces(self):
        card = {"name": "Bind // Liberate"}  # no card_faces
        keys = _keys(card)
        assert ("bind", "FACE") in keys
        assert ("liberate", "FACE") in keys

    def test_meld_back_face_indexed(self):
        card = {
            "name": "Bruna, the Fading Light // Brisela, Voice of Nightmares",
            "card_faces": [
                {"name": "Bruna, the Fading Light"},
                {"name": "Brisela, Voice of Nightmares"},
            ],
        }
        keys = _keys(card)
        assert ("brisela, voice of nightmares", "FACE") in keys

    def test_single_faced_card_has_no_face_keys(self):
        keys = alias_keys({"name": "Sol Ring"})
        assert keys == [("sol ring", _Tier.CANONICAL)]

    def test_arena_aliases_indexed_for_english(self):
        card = {
            "name": "Masked Meower",
            "printed_name": "Skittering Kitten",
            "lang": "en",
        }
        keys = _keys(card)
        assert ("masked meower", "CANONICAL") in keys
        assert ("skittering kitten", "ALIAS") in keys

    def test_non_english_aliases_dropped(self):
        card = {"name": "Opt", "printed_name": "選択", "lang": "ja"}
        keys = _keys(card)
        assert all(t != "ALIAS" for _, t in keys)

    def test_flavor_name_alias(self):
        card = {
            "name": "Hangarback Walker",
            "flavor_name": "Mechagodzilla",
            "lang": "en",
        }
        assert ("mechagodzilla", "ALIAS") in _keys(card)


class TestNameIndex:
    def test_get_folds_the_query(self):
        rec = {"name": "Lim-Dûl's Vault"}
        idx = NameIndex({"lim-dul's vault": rec})
        assert idx.get("Lim-Dul's Vault") is rec  # ASCII query
        assert idx.get("LIM-DÛL'S VAULT") is rec  # diacritic + case
        assert idx.get("nope") is None

    def test_contains_and_getitem_fold(self):
        idx = NameIndex({"sol ring": {"name": "Sol Ring"}})
        assert "SOL RING" in idx
        assert idx["Sol Ring"]["name"] == "Sol Ring"
        assert "Nonexistent" not in idx

    def test_values_keep_real_display_name(self):
        idx = NameIndex({"jotun grunt": {"name": "Jötun Grunt"}})
        # the stored record keeps its diacritics for display; only the KEY is folded
        assert next(iter(idx.values()))["name"] == "Jötun Grunt"
        assert list(idx) == ["jotun grunt"]  # iteration yields folded keys


class TestBuildNameIndex:
    def test_standalone_wins_over_a_face_regardless_of_order(self):
        split = {
            "name": "Bind // Liberate",
            "card_faces": [{"name": "Bind"}, {"name": "Liberate"}],
        }
        standalone = {"name": "Bind"}
        # split first, standalone second
        idx = build_name_index([split, standalone])
        assert idx.get("Bind")["name"] == "Bind"
        # standalone first, split second — same result
        idx2 = build_name_index([standalone, split])
        assert idx2.get("Bind")["name"] == "Bind"

    def test_reduce_picks_cheapest_among_same_tier(self):
        cheap = {"name": "Sol Ring", "prices": {"usd": "1.00"}}
        pricey = {"name": "Sol Ring", "prices": {"usd": "9.00"}}
        idx = build_name_index([pricey, cheap], reduce=keep_cheaper)
        assert idx.get("Sol Ring")["prices"]["usd"] == "1.00"

    def test_reduce_applies_to_face_keys_too(self):
        # Two printings of a split card -> the FACE key points at the cheaper printing.
        cheap = {
            "name": "Fire // Ice",
            "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
            "prices": {"usd": "0.25"},
        }
        pricey = {
            "name": "Fire // Ice",
            "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
            "prices": {"usd": "5.00"},
        }
        idx = build_name_index([pricey, cheap], reduce=keep_cheaper)
        assert idx.get("Fire")["prices"]["usd"] == "0.25"

    def test_first_seen_when_no_reducer(self):
        first = {"name": "Sol Ring", "set": "a"}
        second = {"name": "Sol Ring", "set": "b"}
        idx = build_name_index([first, second])  # reduce=None
        assert idx.get("Sol Ring")["set"] == "a"

    def test_prefilter_excludes(self):
        idx = build_name_index(
            [
                {"name": "Sol Ring", "layout": "normal"},
                {"name": "A Token", "layout": "token"},
            ],
            prefilter=lambda c: c.get("layout") != "token",
        )
        assert "Sol Ring" in idx
        assert "A Token" not in idx

    def test_value_projection(self):
        idx = build_name_index(
            [{"name": "Sol Ring", "rarity": "uncommon"}],
            value=lambda c: c.get("rarity"),
        )
        assert idx.get("Sol Ring") == "uncommon"

    def test_skips_none_entries(self):
        idx = build_name_index([None, {"name": "Sol Ring"}, None])
        assert idx.get("Sol Ring")["name"] == "Sol Ring"


class TestKeepCheaper:
    def test_priced_beats_priceless_either_direction(self):
        priced = {"name": "X", "prices": {"usd": "2.00"}}
        priceless = {"name": "X", "prices": {}}
        assert keep_cheaper(priceless, priced) is priced  # new priced wins
        assert keep_cheaper(priced, priceless) is priced  # existing priced kept

    def test_cheaper_wins_among_priced(self):
        cheap = {"name": "X", "prices": {"usd": "1.00"}}
        dear = {"name": "X", "prices": {"usd": "3.00"}}
        assert keep_cheaper(dear, cheap) is cheap
        assert keep_cheaper(cheap, dear) is cheap

    def test_first_kept_among_priceless(self):
        a = {"name": "X", "prices": {}}
        b = {"name": "X", "prices": {}}
        assert keep_cheaper(a, b) is a
