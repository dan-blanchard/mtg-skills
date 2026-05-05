"""End-to-end integration test with all adapters mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from click.testing import CliRunner


def test_dry_run_full_flow(tmp_path, monkeypatch):
    deck = {
        "format": "commander",
        "commanders": [{"name": "Atraxa, Praetors' Voice", "quantity": 1}],
        "cards": [
            {"name": "Sol Ring", "quantity": 1},
            {"name": "Mana Drain", "quantity": 1},
            {"name": "Plains", "quantity": 7},
        ],
        "sideboard": [],
    }
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(deck))

    bulk = tmp_path / "bulk.json"
    bulk.write_text(
        json.dumps(
            [
                {"name": "Atraxa, Praetors' Voice", "prices": {"usd": "5.00"}},
                {"name": "Sol Ring", "prices": {"usd": "1.10"}},
                {"name": "Mana Drain", "prices": {"usd": "100.00"}},
            ]
        )
    )

    atraxa_listing = {
        "store": "tgp",
        "card_name": "Atraxa, Praetors' Voice",
        "set_code": "C16",
        "condition": "NM",
        "foil": False,
        "price": 5.50,
        "qty_available": 1,
        "listing_id": "id1",
        "url": "x",
    }

    def tgp_search(_page, card_name, *, qty, prefs):  # noqa: ARG001
        # Only Atraxa is in stock at TGP for this fixture.
        return [atraxa_listing] if card_name == "Atraxa, Praetors' Voice" else []

    tgp = MagicMock()
    tgp.kind = "lgs"
    tgp.name = "tgp"
    tgp.display_name = "TGP"
    tgp.search.side_effect = tgp_search

    ae = MagicMock()
    ae.kind = "lgs"
    ae.name = "atomic_empire"
    ae.display_name = "AE"
    ae.search.return_value = []

    tcg = MagicMock()
    tcg.kind = "marketplace"
    tcg.name = "tcgplayer"
    tcg.display_name = "TCG"
    tcg.bulk_submit_and_optimize.return_value = {
        "store": "tcgplayer",
        "total": 105.0,
        "items_subtotal": 100.0,
        "shipping": 5.0,
        "lines": [],
        "unfound": [],
        "cart_url": "u",
    }

    mp = MagicMock()
    mp.kind = "marketplace"
    mp.name = "manapool"
    mp.display_name = "MP"
    mp.bulk_submit_and_optimize.return_value = {
        "store": "manapool",
        "total": 102.0,
        "items_subtotal": 99.0,
        "shipping": 3.0,
        "lines": [],
        "unfound": [],
        "cart_url": "v",
    }

    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_ADAPTERS",
        {"tgp": tgp, "atomic_empire": ae},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_ADAPTERS",
        {"tcgplayer": tcg, "manapool": mp},
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.LGS_STORES",
        ["tgp", "atomic_empire"],
    )
    monkeypatch.setattr(
        "mtg_utils.lgs_search.MARKETPLACE_STORES",
        ["tcgplayer", "manapool"],
    )

    from mtg_utils.lgs_search import main

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--input",
            str(deck_path),
            "--bulk-data",
            str(bulk),
            "--output-dir",
            str(tmp_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    sidecar = json.loads((tmp_path / "lgs-cart-allocation.json").read_text())
    assert sidecar["version"] == 1
    assert sidecar["basic_lands_needed"] == {"Plains": 7}
    assert any(a["store"] == "tgp" for a in sidecar["allocation"])
    # Mana Drain ($100 scryfall) — LGS empty, spills to Marketplace.
    assert any(
        a["store"] == "marketplace" and a["card_name"] == "Mana Drain"
        for a in sidecar["allocation"]
    )
    # --dry-run promises not to touch any cart, so the Marketplace optimizer
    # (which submits to TCG Mass Entry / MP add-deck) must NOT run.
    assert sidecar["online_optimizer_results"] is None
    tcg.bulk_submit_and_optimize.assert_not_called()
    mp.bulk_submit_and_optimize.assert_not_called()
