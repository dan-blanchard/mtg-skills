"""proposal-check: one call runs every mechanical gate a proposal must pass."""

import json

from click.testing import CliRunner

from mtg_utils.hydrated_deck import HydratedDeck
from mtg_utils.proposal_check import FAIL, PASS, WARN, main, proposal_check

# A game-winning line through Blood Artist, as Commander Spellbook would report it.
_ARISTOCRATS = {
    "cards": ["Viscera Seer", "Blood Artist"],
    "result": ["Infinite death triggers"],
}


def _deck(tmp_path):
    deck = {
        "format": "commander",
        "commanders": [{"name": "Korvold, Fae-Cursed King", "quantity": 1}],
        "cards": [
            {"name": "Viscera Seer", "quantity": 1},
            {"name": "Blood Artist", "quantity": 1},
            {"name": "Sol Ring", "quantity": 1},
        ],
    }
    path = tmp_path / "deck.json"
    path.write_text(json.dumps(deck))
    return path


def _combos(hd):
    names = {e["name"] for e in hd.deck["cards"]}
    found = [_ARISTOCRATS] if set(_ARISTOCRATS["cards"]) <= names else []
    return {"combos": found, "near_misses": []}


def _check(tmp_path, bulk, cuts, adds, **kw):
    hd = HydratedDeck.acquire(_deck(tmp_path), bulk_path=bulk)
    return proposal_check(hd, cuts, adds, bulk_path=bulk, combos_fn=_combos, **kw)


def test_losing_a_game_winning_combo_fails_the_gate(tmp_path, sample_bulk_data):
    new_hd, report = _check(
        tmp_path, sample_bulk_data, ["Blood Artist"], ["Sakura-Tribe Elder"]
    )
    combos = report["gates"]["combos"]
    assert combos["status"] == FAIL
    assert [c["cards"] for c in combos["lost"]] == [_ARISTOCRATS["cards"]]
    assert not report["pass"]
    assert "Sakura-Tribe Elder" in {e["name"] for e in new_hd.deck["cards"]}


def test_an_allowed_combo_loss_is_a_warning(tmp_path, sample_bulk_data):
    _, report = _check(
        tmp_path,
        sample_bulk_data,
        ["Blood Artist"],
        ["Sakura-Tribe Elder"],
        allow_combo_loss=True,
    )
    assert report["gates"]["combos"]["status"] == WARN


def test_a_cut_not_in_the_deck_fails(tmp_path, sample_bulk_data):
    _, report = _check(tmp_path, sample_bulk_data, ["Cultivate"], [])
    assert report["gates"]["cuts"]["status"] == FAIL
    assert report["gates"]["cuts"]["unmatched"] == ["Cultivate"]


def test_size_is_exact_for_the_commander_family(tmp_path, sample_bulk_data):
    _, report = _check(tmp_path, sample_bulk_data, ["Sol Ring"], ["Cultivate"])
    size = report["gates"]["size"]
    assert size["status"] == FAIL
    assert size["total"] == 4


def test_the_paper_budget_gates_the_adds(tmp_path, sample_bulk_data):
    def budget_status(budget):
        _, report = _check(
            tmp_path, sample_bulk_data, ["Sol Ring"], ["Cultivate"], budget=budget
        )
        return report["gates"]["budget"]["status"]

    assert budget_status(100.0) == PASS
    assert budget_status(0.0) == FAIL


def test_cut_check_runs_on_the_cuts_for_every_commander(tmp_path, sample_bulk_data):
    _, report = _check(tmp_path, sample_bulk_data, ["Sol Ring"], ["Cultivate"])
    by_commander = report["cut_check"]
    assert list(by_commander) == ["Korvold, Fae-Cursed King"]
    assert [e["name"] for e in by_commander["Korvold, Fae-Cursed King"]] == ["Sol Ring"]
    assert report["gates"]["multipliers"]["status"] == PASS


def test_cli_writes_the_deck_and_report_and_fails_on_a_failed_gate(
    tmp_path, sample_bulk_data, monkeypatch
):
    monkeypatch.setattr("mtg_utils.proposal_check.combo_search", _combos)
    deck = _deck(tmp_path)
    cuts = tmp_path / "cuts.json"
    cuts.write_text(json.dumps(["Sol Ring"]))
    adds = tmp_path / "adds.json"
    adds.write_text(json.dumps(["Cultivate"]))
    out = tmp_path / "out"
    result = CliRunner().invoke(
        main,
        [
            str(deck),
            "--bulk-data",
            str(sample_bulk_data),
            "--cuts",
            str(cuts),
            "--adds",
            str(adds),
            "--output-dir",
            str(out),
        ],
    )
    assert result.exit_code == 1  # a 4-card Commander deck fails the size gate
    assert "FAIL  size" in result.output
    assert json.loads((out / "proposal-check.json").read_text())["pass"] is False
    assert "Cultivate" in (out / "new-deck.json").read_text()


def test_an_add_the_collection_holds_costs_nothing(tmp_path, sample_bulk_data):
    """The deck's owned_cards only covers its own cards, so an owned add would be
    priced; the collection marks it free."""
    collection = {"cards": [{"name": "Cultivate", "quantity": 1}]}

    def spend(**kw):
        _, report = _check(
            tmp_path, sample_bulk_data, ["Sol Ring"], ["Cultivate"], **kw
        )
        return report["gates"]["budget"]["total_cost"]

    assert spend(budget=100.0) > 0
    assert spend(budget=100.0, collection=collection) == 0


def test_a_budget_flag_for_the_other_medium_warns(tmp_path, sample_bulk_data):
    """--wildcards on a paper build isn't silently passed as 'no budget'."""
    _, report = _check(
        tmp_path,
        sample_bulk_data,
        ["Sol Ring"],
        ["Cultivate"],
        wildcards={"rare": 1},
        medium="paper",
    )
    assert report["gates"]["budget"]["status"] == WARN


def test_an_unreachable_combo_search_degrades_the_gate(tmp_path, sample_bulk_data):
    def down(_hd):
        raise RuntimeError("commander spellbook unreachable")

    hd = HydratedDeck.acquire(_deck(tmp_path), bulk_path=sample_bulk_data)
    _, report = proposal_check(
        hd, ["Sol Ring"], ["Cultivate"], bulk_path=sample_bulk_data, combos_fn=down
    )
    assert report["gates"]["combos"]["status"] == WARN
