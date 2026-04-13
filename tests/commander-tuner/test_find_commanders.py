"""Tests for find_commanders module."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from mtg_utils.find_commanders import (
    _build_owned_index,
    _has_background_clause,
    _is_partner,
    _load_bulk_index,
    _normalize_name,
    _partner_with_target,
    find_commanders,
    main,
)


def _card(
    name,
    *,
    type_line="Legendary Creature — Human",
    color_identity=None,
    mana_cost="{1}{G}",
    cmc=2.0,
    oracle_text="",
    legalities=None,
    edhrec_rank=None,
    game_changer=False,
    layout="normal",
    set_type="expansion",
    card_faces=None,
):
    # NOTE on legalities keys: Scryfall's format-name -> legality-key mapping
    # is counterintuitive. Our FORMAT_CONFIGS map:
    #   "commander"      -> legality key "commander"
    #   "brawl"          -> legality key "standardbrawl"  (Standard Brawl)
    #   "historic_brawl" -> legality key "brawl"          (Historic / Arena Brawl)
    # So a fixture with `{"brawl": "legal", "standardbrawl": "not_legal"}` is
    # legal in *historic_brawl* and illegal in *brawl*. Mind the inversion when
    # writing new fixtures.
    card = {
        "name": name,
        "type_line": type_line,
        "color_identity": color_identity if color_identity is not None else ["G"],
        "mana_cost": mana_cost,
        "cmc": cmc,
        "oracle_text": oracle_text,
        "legalities": legalities
        or {"commander": "legal", "brawl": "legal", "standardbrawl": "not_legal"},
        "edhrec_rank": edhrec_rank,
        "game_changer": game_changer,
        "layout": layout,
        "set_type": set_type,
    }
    if card_faces is not None:
        card["card_faces"] = card_faces
    return card


@pytest.fixture
def bulk_index():
    cards = [
        _card(
            "Korvold, Fae-Cursed King",
            color_identity=["B", "G", "R"],
            cmc=5.0,
            edhrec_rank=2387,
        ),
        _card(
            "Atraxa, Praetors' Voice",
            color_identity=["B", "G", "U", "W"],
            cmc=4.0,
            edhrec_rank=200,
        ),
        _card(
            "Faceless One",
            type_line="Legendary Creature — Shapeshifter Adventurer",
            color_identity=[],
            cmc=2.0,
            oracle_text="Choose a Background\nWhen Faceless One dies, draw a card.",
        ),
        _card(
            "Hardy Outlander",
            type_line="Legendary Enchantment — Background",
            color_identity=["G"],
            cmc=1.0,
            oracle_text="Commander creatures you own have ward {2}.",
        ),
        _card(
            "Teferi, Temporal Pilgrim",
            type_line="Legendary Planeswalker — Teferi",
            color_identity=["U", "W"],
            cmc=5.0,
            oracle_text="+1: Draw a card.",
            legalities={
                "commander": "not_legal",
                "brawl": "legal",
                "standardbrawl": "not_legal",
            },
        ),
        _card(
            "Lightning Bolt",
            type_line="Instant",
            color_identity=["R"],
            cmc=1.0,
            oracle_text="Lightning Bolt deals 3 damage to any target.",
        ),
        _card(
            "Sol Ring",
            type_line="Artifact",
            color_identity=[],
            cmc=1.0,
            oracle_text="{T}: Add {C}{C}.",
        ),
        _card(
            "Thrasios, Triton Hero",
            color_identity=["G", "U"],
            cmc=2.0,
            oracle_text="{4}: Scry 1, then reveal the top card of your library.\nPartner",
            edhrec_rank=850,
        ),
        _card(
            "Pir, Imaginative Rascal",
            color_identity=["G", "U"],
            cmc=2.0,
            oracle_text="If one or more counters would be placed on a permanent you control, that many plus one of those counters are placed on it instead.\nPartner with Toothy, Imaginary Friend",
        ),
    ]
    return {c["name"].lower(): c for c in cards}


@pytest.fixture
def parsed_collection():
    return {
        "commanders": [],
        "cards": [
            {"name": "Korvold, Fae-Cursed King", "quantity": 1},
            {"name": "Atraxa, Praetors' Voice", "quantity": 1},
            {"name": "Faceless One", "quantity": 1},
            {"name": "Hardy Outlander", "quantity": 1},
            {"name": "Teferi, Temporal Pilgrim", "quantity": 1},
            {"name": "Lightning Bolt", "quantity": 4},
            {"name": "Sol Ring", "quantity": 2},
            {"name": "Thrasios, Triton Hero", "quantity": 1},
            {"name": "Pir, Imaginative Rascal", "quantity": 1},
            # A wishlist row the user is tracking but does not own:
            {"name": "Wishlist Card", "quantity": 0},
        ],
    }


class TestFormatEligibility:
    def test_commander_format_excludes_planeswalker_without_clause(
        self, bulk_index, parsed_collection
    ):
        names = {
            c["name"]
            for c in find_commanders(parsed_collection, bulk_index, format="commander")
        }
        # Legendary creatures and Background pass; planeswalker without
        # "can be your commander" does NOT pass in commander format.
        assert "Korvold, Fae-Cursed King" in names
        assert "Atraxa, Praetors' Voice" in names
        assert "Faceless One" in names
        assert "Hardy Outlander" in names
        assert "Teferi, Temporal Pilgrim" not in names
        # Non-legendary cards never pass:
        assert "Lightning Bolt" not in names
        assert "Sol Ring" not in names

    def test_brawl_format_includes_legendary_planeswalker(
        self, bulk_index, parsed_collection
    ):
        names = {
            c["name"]
            for c in find_commanders(
                parsed_collection, bulk_index, format="historic_brawl"
            )
        }
        assert "Teferi, Temporal Pilgrim" in names

    def test_standardbrawl_filters_by_legality_key(self, bulk_index, parsed_collection):
        # All test cards have standardbrawl=not_legal, so the brawl format
        # should return zero candidates.
        result = find_commanders(parsed_collection, bulk_index, format="brawl")
        assert result == []


class TestColorIdentityFilter:
    def test_subset_match_returns_subset_only(self, bulk_index, parsed_collection):
        names = {
            c["name"]
            for c in find_commanders(
                parsed_collection,
                bulk_index,
                format="commander",
                color_identity="BG",
            )
        }
        # Korvold is BGR — superset of BG, should be excluded.
        assert "Korvold, Fae-Cursed King" not in names
        # Hardy Outlander is mono-G — subset of BG, included.
        assert "Hardy Outlander" in names
        # Faceless One is colorless — subset of any, included.
        assert "Faceless One" in names
        # Atraxa is BGUW — superset, excluded.
        assert "Atraxa, Praetors' Voice" not in names

    def test_no_filter_returns_all_eligible(self, bulk_index, parsed_collection):
        names = {
            c["name"]
            for c in find_commanders(parsed_collection, bulk_index, format="commander")
        }
        assert "Korvold, Fae-Cursed King" in names
        assert "Atraxa, Praetors' Voice" in names


class TestMinQuantity:
    def test_default_excludes_zero_quantity(self, bulk_index, parsed_collection):
        owned = _build_owned_index(parsed_collection, min_quantity=1)
        assert "wishlist card" not in owned
        assert "korvold, fae-cursed king" in owned

    def test_min_quantity_zero_includes_wishlist(self, bulk_index, parsed_collection):
        owned = _build_owned_index(parsed_collection, min_quantity=0)
        assert "wishlist card" in owned

    def test_min_quantity_two_filters_singletons(self, bulk_index, parsed_collection):
        owned = _build_owned_index(parsed_collection, min_quantity=2)
        # qty=1 cards excluded; qty=2 (Sol Ring) and qty=4 (Bolt) kept
        assert "korvold, fae-cursed king" not in owned
        assert "sol ring" in owned
        assert "lightning bolt" in owned

    def test_min_quantity_passed_through_find_commanders(
        self, bulk_index, parsed_collection
    ):
        # All commander-eligible cards in the fixture have qty=1, so
        # min_quantity=2 should yield zero candidates.
        result = find_commanders(
            parsed_collection, bulk_index, format="commander", min_quantity=2
        )
        assert result == []

    def test_string_quantity_is_coerced(self, bulk_index):
        parsed = {
            "commanders": [],
            "cards": [
                {"name": "Korvold, Fae-Cursed King", "quantity": "1"},
                {"name": "Atraxa, Praetors' Voice", "quantity": "not a number"},
            ],
        }
        owned = _build_owned_index(parsed, min_quantity=1)
        # "1" coerces cleanly; the malformed value falls back to 1 (kept).
        assert owned["korvold, fae-cursed king"] == 1
        assert owned["atraxa, praetors' voice"] == 1

    def test_missing_quantity_defaults_to_one(self, bulk_index):
        parsed = {"commanders": [], "cards": [{"name": "Korvold, Fae-Cursed King"}]}
        owned = _build_owned_index(parsed, min_quantity=1)
        assert owned["korvold, fae-cursed king"] == 1

    def test_owned_quantity_appears_in_output(self, bulk_index, parsed_collection):
        result = find_commanders(parsed_collection, bulk_index, format="commander")
        korvold = next(c for c in result if c["name"] == "Korvold, Fae-Cursed King")
        assert korvold["owned_quantity"] == 1


class TestPartnerDetection:
    def test_partner_keyword(self):
        assert _is_partner("{4}: Scry 1.\nPartner")

    def test_partner_with_named(self):
        assert _is_partner("Some text.\nPartner with Toothy, Imaginary Friend")

    def test_friends_forever(self):
        assert _is_partner("Friends forever\nDraw a card.")

    def test_choose_a_background_is_not_partner_keyword(self):
        # Choose a Background is reported via has_background_clause, not is_partner
        assert not _is_partner("Choose a Background\nDraw a card.")

    def test_partner_with_target_extraction(self):
        target = _partner_with_target(
            "Some text.\nPartner with Toothy, Imaginary Friend\nMore text."
        )
        assert target == "Toothy, Imaginary Friend"

    def test_partner_with_no_target_for_plain_partner(self):
        assert _partner_with_target("{4}: Scry 1.\nPartner") is None

    def test_partner_with_anchored_to_line_start(self):
        # Hypothetical flavor/rules text mentioning "partner with" mid-line
        # must NOT trigger the named-partner regex.
        assert (
            _partner_with_target(
                "When this creature enters, choose a creature to partner with another player.",
            )
            is None
        )

    def test_partner_with_strips_reminder_text(self):
        target = _partner_with_target(
            "Partner with Toothy, Imaginary Friend (When this creature enters the battlefield, target player may put Toothy into their hand from their library.)",
        )
        assert target == "Toothy, Imaginary Friend"

    def test_has_background_clause(self):
        assert _has_background_clause("Choose a Background\nWhen this dies, draw.")
        assert not _has_background_clause("Flying, vigilance.")

    def test_partner_flags_in_output(self, bulk_index, parsed_collection):
        result = find_commanders(parsed_collection, bulk_index, format="commander")
        thrasios = next(c for c in result if c["name"] == "Thrasios, Triton Hero")
        assert thrasios["is_partner"] is True
        assert thrasios["partner_with"] is None
        assert thrasios["has_background_clause"] is False

        pir = next(c for c in result if c["name"] == "Pir, Imaginative Rascal")
        assert pir["is_partner"] is True
        assert pir["partner_with"] == "Toothy, Imaginary Friend"

        faceless = next(c for c in result if c["name"] == "Faceless One")
        assert faceless["has_background_clause"] is True
        assert faceless["is_partner"] is False


class TestOutputShape:
    def test_required_fields_present(self, bulk_index, parsed_collection):
        result = find_commanders(parsed_collection, bulk_index, format="commander")
        korvold = next(c for c in result if c["name"] == "Korvold, Fae-Cursed King")
        expected_keys = {
            "name",
            "color_identity",
            "type_line",
            "mana_cost",
            "cmc",
            "oracle_text",
            "edhrec_rank",
            "game_changer",
            "is_partner",
            "partner_with",
            "has_background_clause",
            "owned_quantity",
        }
        assert expected_keys.issubset(korvold.keys())
        assert korvold["edhrec_rank"] == 2387
        assert korvold["color_identity"] == ["B", "G", "R"]


class TestCli:
    def test_smoke_end_to_end(self, tmp_path: Path, bulk_index, parsed_collection):
        from conftest import json_from_cli_output

        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(list(bulk_index.values())))

        parsed_path = tmp_path / "parsed.json"
        parsed_path.write_text(json.dumps(parsed_collection))

        output_override = tmp_path / "commanders.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(parsed_path),
                "--bulk-data",
                str(bulk_path),
                "--format",
                "commander",
                "--color-identity",
                "BGR",
                "--output",
                str(output_override),
            ],
        )
        assert result.exit_code == 0, result.output

        # Loose substring checks on the text table
        assert "Korvold, Fae-Cursed King" in result.output
        assert "Atraxa, Praetors' Voice" not in result.output  # BGUW not subset of BGR
        assert "Lightning Bolt" not in result.output
        assert "find-commanders:" in result.output
        assert "Full JSON:" in result.output

        # Strict correctness check via the JSON file
        candidates = json_from_cli_output(result)
        names = {c["name"] for c in candidates}
        assert "Korvold, Fae-Cursed King" in names
        assert "Atraxa, Praetors' Voice" not in names
        assert "Lightning Bolt" not in names

        # Verify output path override honored
        assert output_override.exists()

    def test_default_output_path_is_deterministic(
        self, tmp_path: Path, bulk_index, parsed_collection
    ):
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(list(bulk_index.values())))
        parsed_path = tmp_path / "parsed.json"
        parsed_path.write_text(json.dumps(parsed_collection))

        runner = CliRunner()
        args = [
            str(parsed_path),
            "--bulk-data",
            str(bulk_path),
            "--format",
            "commander",
        ]
        r1 = runner.invoke(main, args)
        r2 = runner.invoke(main, args)
        assert r1.exit_code == 0
        assert r2.exit_code == 0

        def _path_from_output(output):
            for line in output.splitlines():
                if line.startswith("Full JSON:"):
                    return line.split(":", 1)[1].strip()
            return None

        assert _path_from_output(r1.output) == _path_from_output(r2.output)

    def test_text_table_renders_flags(
        self, tmp_path: Path, bulk_index, parsed_collection
    ):
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(list(bulk_index.values())))
        parsed_path = tmp_path / "parsed.json"
        parsed_path.write_text(json.dumps(parsed_collection))
        output_override = tmp_path / "out.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(parsed_path),
                "--bulk-data",
                str(bulk_path),
                "--format",
                "commander",
                "--output",
                str(output_override),
            ],
        )
        assert result.exit_code == 0, result.output
        # PARTNER flag for Thrasios; BACKGROUND for Faceless One
        assert "PARTNER" in result.output
        assert "BACKGROUND" in result.output

    def test_cross_section_takes_max_not_sum(self):
        # parse-deck can emit a card in BOTH commanders and cards if the user
        # listed their commander in the mainboard. Both rows describe the same
        # physical pile — sum would double-count.
        parsed = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        }
        owned = _build_owned_index(parsed, min_quantity=1)
        assert owned["korvold, fae-cursed king"] == 1

    def test_cross_section_takes_max_when_quantities_differ(self):
        parsed = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [{"name": "Korvold, Fae-Cursed King", "quantity": 3}],
        }
        owned = _build_owned_index(parsed, min_quantity=1)
        assert owned["korvold, fae-cursed king"] == 3

    def test_empty_candidate_list_still_emits_full_json_footer(
        self, tmp_path: Path, bulk_index
    ):
        """When no candidates match, stdout still has 'Full JSON: <path>'
        and the file at that path contains an empty array. Agents rely on
        the footer's presence as a structural invariant."""
        from conftest import json_from_cli_output

        # A collection with zero commander-eligible cards
        parsed = {
            "commanders": [],
            "cards": [
                {"name": "Lightning Bolt", "quantity": 4},
                {"name": "Sol Ring", "quantity": 1},
            ],
        }
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(json.dumps(list(bulk_index.values())))
        parsed_path = tmp_path / "parsed.json"
        parsed_path.write_text(json.dumps(parsed))
        output_override = tmp_path / "empty.json"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                str(parsed_path),
                "--bulk-data",
                str(bulk_path),
                "--format",
                "commander",
                "--output",
                str(output_override),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "find-commanders: 0 candidates" in result.output
        assert "Full JSON:" in result.output

        data = json_from_cli_output(result)
        assert data == []
        assert output_override.exists()


class TestNameNormalization:
    def test_diacritics_are_folded(self):
        # An ASCII-only collection export must match the diacritic-bearing
        # canonical Scryfall name.
        assert _normalize_name("Lim-Dûl's Vault") == _normalize_name("Lim-Dul's Vault")

    def test_lowercase(self):
        assert _normalize_name("Sol Ring") == "sol ring"

    def test_mdfc_face_is_indexed(self, tmp_path: Path):
        # A flip/meld card whose name has no " // " separator: the front-face
        # name in card_faces[] must still be looked up successfully.
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps(
                [
                    _card(
                        "Bruna, the Fading Light // Brisela, Voice of Nightmares",
                        card_faces=[
                            {"name": "Bruna, the Fading Light"},
                            {"name": "Brisela, Voice of Nightmares"},
                        ],
                    ),
                ]
            )
        )
        index = _load_bulk_index(bulk_path)
        # Both faces and the full name should resolve to the same card object.
        assert index[_normalize_name("Bruna, the Fading Light")] is not None
        assert index[_normalize_name("Brisela, Voice of Nightmares")] is not None
        assert (
            index[_normalize_name("Bruna, the Fading Light")]
            is index[_normalize_name("Brisela, Voice of Nightmares")]
        )

    def test_mdfc_lookup_via_face_name_in_collection(self, tmp_path: Path):
        # End-to-end: user's collection lists only the front face of a meld
        # card. find-commanders must still recognize it as a candidate.
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps(
                [
                    _card(
                        "Bruna, the Fading Light // Brisela, Voice of Nightmares",
                        type_line="Legendary Creature — Angel",
                        color_identity=["W"],
                        cmc=7.0,
                        card_faces=[
                            {"name": "Bruna, the Fading Light"},
                            {"name": "Brisela, Voice of Nightmares"},
                        ],
                    ),
                ]
            )
        )
        bulk_index = _load_bulk_index(bulk_path)
        parsed = {
            "commanders": [],
            "cards": [{"name": "Bruna, the Fading Light", "quantity": 1}],
        }
        result = find_commanders(parsed, bulk_index, format="commander")
        assert len(result) == 1
        assert "Bruna" in result[0]["name"]

    def test_diacritic_collection_lookup_end_to_end(self, tmp_path: Path):
        # User has an ASCII-only "Lim-Dul's Vault" in their collection;
        # bulk data has the canonical "Lim-Dûl's Vault". They must match.
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps(
                [
                    _card(
                        "Lim-Dûl's Vault",
                        type_line="Legendary Creature — Human",
                        color_identity=["B", "U"],
                        cmc=2.0,
                    ),
                ]
            )
        )
        bulk_index = _load_bulk_index(bulk_path)
        parsed = {
            "commanders": [],
            "cards": [{"name": "Lim-Dul's Vault", "quantity": 1}],
        }
        result = find_commanders(parsed, bulk_index, format="commander")
        assert len(result) == 1


class TestMdfcOracleText:
    def test_mdfc_partner_with_detection(self):
        # Hypothetical MDFC where the partner-with text lives on a face,
        # not the top-level oracle_text. get_oracle_text() concatenates faces,
        # so _is_partner / _partner_with_target should still detect it.
        from mtg_utils.card_classify import get_oracle_text

        card = {
            "name": "Hypothetical MDFC // Partner Side",
            "oracle_text": "",
            "card_faces": [
                {
                    "name": "Hypothetical MDFC",
                    "oracle_text": "Flying.\nPartner with Partner Side",
                },
                {"name": "Partner Side", "oracle_text": "Vigilance."},
            ],
        }
        oracle = get_oracle_text(card)
        assert _is_partner(oracle)
        assert _partner_with_target(oracle) == "Partner Side"

    def test_load_bulk_index_skips_tokens(self, tmp_path: Path):
        bulk_path = tmp_path / "bulk.json"
        bulk_path.write_text(
            json.dumps(
                [
                    _card("Real Card"),
                    _card("Token Card", layout="token"),
                    _card("Memorabilia Card", set_type="memorabilia"),
                ]
            )
        )
        index = _load_bulk_index(bulk_path)
        assert "real card" in index
        assert "token card" not in index
        assert "memorabilia card" not in index
