"""Tests for mark_owned — populate owned_cards from a parsed collection."""

import json

from click.testing import CliRunner

from commander_utils.mark_owned import main, mark_owned


class TestMarkOwned:
    def test_basic_intersection(self):
        """``owned_cards`` is written as ``[{name, quantity}]`` dicts —
        same shape as ``cards``/``commanders`` — with the quantity
        taken from the collection side of the intersection."""
        deck = {
            "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
            "cards": [
                {"name": "Sol Ring", "quantity": 1},
                {"name": "Command Tower", "quantity": 1},
                {"name": "Mana Crypt", "quantity": 1},
            ],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Sol Ring", "quantity": 2},
                {"name": "Command Tower", "quantity": 4},
                {"name": "Lightning Bolt", "quantity": 3},
            ],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Command Tower", "quantity": 4},
            {"name": "Sol Ring", "quantity": 2},
        ]

    def test_commander_counted_as_owned(self):
        """A commander present in the collection should show up in owned_cards."""
        deck = {
            "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Atraxa, Praetors' Voice", "quantity": 1},
                {"name": "Sol Ring", "quantity": 2},
            ],
        }
        result = mark_owned(deck, collection)
        names = {entry["name"] for entry in result["owned_cards"]}
        assert names == {"Atraxa, Praetors' Voice", "Sol Ring"}

    def test_diacritic_folding(self):
        """ASCII-only deck name should match diacritic-bearing collection entry.

        Deck-side spelling is preserved in the written ``owned_cards``
        entry; collection-side quantity is recorded.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Lim-Dul's Vault", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Lim-D\u00fbl's Vault", "quantity": 3}],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Lim-Dul's Vault", "quantity": 3},
        ]

    def test_owned_cards_schema_is_dicts(self):
        """Result matches the canonical ``[{name, quantity}]`` schema
        that price-check consumes and that ``cards``/``commanders`` use.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        result = mark_owned(deck, collection)
        assert all(
            isinstance(entry, dict)
            and isinstance(entry.get("name"), str)
            and isinstance(entry.get("quantity"), int)
            for entry in result["owned_cards"]
        )

    def test_collection_sums_split_printing_quantities(self):
        """A Moxfield collection splits the same card across its distinct
        printings (different set codes / collector numbers / languages),
        so the same card name appears as many separate rows. ``mark-owned``
        must SUM those rows on the collection side — taking the max of
        any single printing would make a deck wanting 7 basics look like
        it's short by N copies the user actually owns.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Island", "quantity": 7}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Island", "quantity": 3},  # e.g. RAV set
                {"name": "Island", "quantity": 2},  # e.g. ZEN set
                {"name": "Island", "quantity": 4},  # e.g. UNF set
            ],
        }
        result = mark_owned(deck, collection)
        # Sum = 9, deck needs 7, so Island is fully owned at quantity 9.
        assert result["owned_cards"] == [{"name": "Island", "quantity": 9}]

    def test_deck_commander_listed_in_both_sections_uses_max(self):
        """``parse-deck`` can emit a legendary creature in both
        ``commanders`` and ``cards`` if the source file quirkily listed
        it twice. Those rows describe the same physical copy — deck-side
        reconciliation must use ``max``, not ``sum``, or the quantity
        recorded in owned_cards would wrongly describe two copies.
        """
        deck = {
            "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
            "cards": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
        }
        result = mark_owned(deck, collection)
        # Owned qty is 1 (from the collection side), not 2.
        assert result["owned_cards"] == [
            {"name": "Atraxa, Praetors' Voice", "quantity": 1},
        ]

    def test_zero_quantity_collection_row_is_not_owned(self):
        """A Moxfield wishlist/binder row exported at ``quantity=0`` is
        NOT marked as owned: "zero copies" is not owning the card. The
        previous string-schema implementation pinned the opposite
        behavior (quantity was ignored entirely); first-class quantity
        in the dict schema lets us do the right thing.
        """
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 0}],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == []

    def test_does_not_mutate_input(self):
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
            "owned_cards": [],
        }
        original = json.loads(json.dumps(deck))
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        mark_owned(deck, collection)
        assert deck == original


class TestDFCAliasing:
    """DFC / split / adventure / modal cards match across the combined
    ``"A // B"`` form and the front-face alone. This matters because
    Scryfall's canonical name (and therefore any importer that resolves
    via bulk data, like mtga-import) uses the combined form while Arena
    exports and many Moxfield exports use front-face only — without
    alias fallback, every DFC the user owns would silently fail to
    mark as owned."""

    def test_deck_front_face_matches_collection_full_form(self):
        """Deck lists the front face only; collection (MTGA import)
        has Scryfall's canonical ``"A // B"``. This is the primary
        use case the alias lookup was added for."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Fable of the Mirror-Breaker", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {
                    "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
                    "quantity": 2,
                },
            ],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Fable of the Mirror-Breaker", "quantity": 2},
        ]

    def test_deck_full_form_matches_collection_front_face(self):
        """Mirror case — a deck that uses the full Scryfall name
        matches a collection (e.g., some Moxfield CSV exports) that
        stored only the front face. The asymmetric fallback in
        ``_match_collection_key`` handles this direction too."""
        deck = {
            "commanders": [],
            "cards": [
                {
                    "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
                    "quantity": 1,
                },
            ],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Fable of the Mirror-Breaker", "quantity": 3},
            ],
        }
        result = mark_owned(deck, collection)
        # Deck-side spelling preserved, collection-side quantity recorded.
        assert result["owned_cards"] == [
            {
                "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki",
                "quantity": 3,
            },
        ]

    def test_both_full_form_matches(self):
        """Baseline sanity — when both sides use the full form, the
        primary-key match fires and the alias code path is irrelevant."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Consecrate // Consume", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Consecrate // Consume", "quantity": 4}],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Consecrate // Consume", "quantity": 4},
        ]

    def test_standalone_wins_over_dfc_alias_within_collection(self):
        """When the same side of the intersection contains BOTH a
        standalone card named ``"Duress"`` AND a hypothetical DFC
        ``"Duress // Second Duress"``, the standalone must claim the
        ``"duress"`` normalized key during pass 1 so the DFC's pass-2
        alias attempt is suppressed. Without that protection, a deck
        asking for standalone Duress could false-match the DFC via the
        alias. This mirrors ``scryfall_lookup._load_bulk_index``'s
        two-pass semantics."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Duress", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Duress", "quantity": 2},
                # Hypothetical DFC with the same front-face name.
                # Arena has no such collision empirically, but the
                # within-index protection still matters for any source
                # (Moxfield CSV, hand-authored JSON) that could supply
                # both forms to the same side.
                {"name": "Duress // Second Duress", "quantity": 1},
            ],
        }
        result = mark_owned(deck, collection)
        # The standalone Duress in the collection must be the one that
        # matches the standalone in the deck — not the DFC via its
        # front-face alias, which would record the wrong quantity.
        assert result["owned_cards"] == [
            {"name": "Duress", "quantity": 2},
        ]

    def test_split_layout_full_name_no_double_count(self):
        """A split card like Consecrate // Consume with both sides
        identical in full form must not double-count via the alias
        (primary key match fires first; alias is a secondary lookup
        that isn't consulted when the primary hit)."""
        deck = {
            "commanders": [],
            "cards": [
                {"name": "Consecrate // Consume", "quantity": 1},
            ],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Consecrate // Consume", "quantity": 2},
            ],
        }
        result = mark_owned(deck, collection)
        # Exactly one entry — no double-emission from the alias.
        assert len(result["owned_cards"]) == 1
        assert result["owned_cards"][0]["quantity"] == 2

    def test_diacritic_folding_plus_dfc(self):
        """Diacritic folding and DFC aliasing compose correctly: a deck
        listing the ASCII-folded front face matches a collection that
        stored the diacritic-bearing full form."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Lim-Dul's Vault", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                # Hypothetical DFC using diacritic-bearing spelling.
                {"name": "Lim-D\u00fbl's Vault // Second Vault", "quantity": 3},
            ],
        }
        result = mark_owned(deck, collection)
        assert result["owned_cards"] == [
            {"name": "Lim-Dul's Vault", "quantity": 3},
        ]


class TestCLI:
    def test_writes_output_file(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        coll_path = tmp_path / "collection.json"
        out_path = tmp_path / "out.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )
        coll_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(deck_path), str(coll_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        written = json.loads(out_path.read_text())
        assert written["owned_cards"] == [{"name": "Sol Ring", "quantity": 1}]
        # Pin the human-readable summary format so a refactor of
        # _collect_entries can't silently regress the stdout contract.
        assert "1 of 1 unique deck cards owned" in result.output

    def test_refuses_same_file_without_output(self, tmp_path):
        """Passing the same file as both DECK_PATH and COLLECTION_PATH with
        no ``--output`` would corrupt the user's file via an intersection-
        of-itself in-place overwrite. The CLI must refuse and exit non-zero,
        leaving the file untouched.
        """
        same_path = tmp_path / "collection.json"
        original = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        same_path.write_text(json.dumps(original))

        runner = CliRunner()
        result = runner.invoke(main, [str(same_path), str(same_path)])
        assert result.exit_code != 0
        assert "same file" in result.output or "same file" in (result.stderr or "")
        # File contents must be untouched.
        assert json.loads(same_path.read_text()) == original

    def test_refuses_same_file_via_symlink_without_output(self, tmp_path):
        """The same-file guard must compare *resolved* paths so a symlink
        pointing at the collection can't slip through."""
        real_path = tmp_path / "collection.json"
        link_path = tmp_path / "deck.json"
        real_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )
        link_path.symlink_to(real_path)

        runner = CliRunner()
        result = runner.invoke(main, [str(link_path), str(real_path)])
        assert result.exit_code != 0

    def test_same_file_allowed_with_explicit_output(self, tmp_path):
        """The same-file case is only dangerous because the default is
        in-place overwrite. With an explicit ``--output``, a user can
        legitimately intersect a collection with itself (e.g., to
        populate owned_cards on a collection-as-deck view).
        """
        same_path = tmp_path / "collection.json"
        out_path = tmp_path / "out.json"
        same_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(same_path), str(same_path), "--output", str(out_path)],
        )
        assert result.exit_code == 0, result.output
        written = json.loads(out_path.read_text())
        assert written["owned_cards"] == [{"name": "Sol Ring", "quantity": 1}]

    def test_in_place_overwrite(self, tmp_path):
        deck_path = tmp_path / "deck.json"
        coll_path = tmp_path / "collection.json"
        deck_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )
        coll_path.write_text(
            json.dumps(
                {
                    "commanders": [],
                    "cards": [{"name": "Sol Ring", "quantity": 1}],
                },
            ),
        )

        runner = CliRunner()
        result = runner.invoke(main, [str(deck_path), str(coll_path)])
        assert result.exit_code == 0, result.output
        written = json.loads(deck_path.read_text())
        assert written["owned_cards"] == [{"name": "Sol Ring", "quantity": 1}]


class TestNameAliasMatching:
    """Test that printed_name / flavor_name aliases resolve across sources."""

    def test_printed_name_alias_matches(self):
        """A collection with an Arena name (printed_name) should match
        a deck using the canonical Scryfall name via the alias map."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Masked Meower", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Skittering Kitten", "quantity": 2}],
        }
        # Alias map: printed_name -> canonical_name
        aliases = {"skittering kitten": "masked meower"}
        result = mark_owned(deck, collection, name_aliases=aliases)
        assert len(result["owned_cards"]) == 1
        assert result["owned_cards"][0]["name"] == "Masked Meower"
        assert result["owned_cards"][0]["quantity"] == 2

    def test_flavor_name_alias_matches(self):
        """A collection with a flavor_name (Godzilla variant) should match."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Void Beckoner", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [
                {"name": "Spacegodzilla, Death Corona", "quantity": 1},
            ],
        }
        aliases = {"spacegodzilla, death corona": "void beckoner"}
        result = mark_owned(deck, collection, name_aliases=aliases)
        assert len(result["owned_cards"]) == 1

    def test_no_aliases_still_works(self):
        """Without aliases, matching falls back to exact + DFC aliasing."""
        deck = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 1}],
        }
        collection = {
            "commanders": [],
            "cards": [{"name": "Sol Ring", "quantity": 4}],
        }
        result = mark_owned(deck, collection, name_aliases=None)
        assert len(result["owned_cards"]) == 1
