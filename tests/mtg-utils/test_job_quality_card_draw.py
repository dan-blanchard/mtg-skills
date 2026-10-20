"""The card-draw read (``job_quality.card_draw``): how well a card nets you cards,
off its own trees — real cards (ADR-0056)."""

import pytest

from mtg_utils._analysis.job_quality import card_draw, job_score
from mtg_utils.testkit import test_card, test_signals


def _real(name: str) -> dict:
    test_signals(name)  # seed the concept-tree memo (CI-safe, no sidecar)
    return test_card(name)


def _score(name: str) -> float | None:
    return job_score(_real(name), "card_draw")


@pytest.mark.parametrize(
    "name",
    [
        "Faithless Looting",  # draw two, discard two: filtering, not draw
        "Frantic Search",  # the same at instant speed
        "Ledger Shredder",  # connive: draw, then discard (CR 701.50a)
    ],
)
def test_card_filtering_reads_none(name):
    """A draw that takes back as many cards as it gives nets nothing: the tuner
    never offers it as a draw upgrade."""
    assert _score(name) is None


@pytest.mark.parametrize("name", ["Lightning Bolt", "Llanowar Elves"])
def test_no_draw_reads_none(name):
    """A card the read can't see scores None, never a low number."""
    assert _score(name) is None


@pytest.mark.parametrize("name", ["Phyrexian Arena", "Rhystic Study", "Esper Sentinel"])
def test_engines_read_above_a_one_shot(name):
    """A card that keeps drawing reads above Divination's one-time two cards."""
    assert card_draw.features(_real(name))["engine"] == 1.0
    assert _score(name) > _score("Divination")


def test_opponent_fired_engine_reads_above_a_turn_engine():
    """Rhystic Study draws off each of three opponents' spells; Phyrexian Arena
    once a turn."""
    assert card_draw.features(_real("Rhystic Study"))["opp_fuel"] == 1.0
    assert _score("Rhystic Study") > _score("Phyrexian Arena")


def test_cheaper_draw_two_reads_above_divination():
    """Night's Whisper draws the same two cards as Divination for a mana less."""
    assert _score("Night's Whisper") > _score("Divination")


def test_a_symmetric_draw_nets_no_flow():
    """Howling Mine gives every player the card it gives you: no card advantage
    on the table, so its engine flows nothing (it still nets you a card)."""
    feats = card_draw.features(_real("Howling Mine"))
    assert feats["engine"] == 1.0
    assert feats["flow"] == 0.0


def test_a_cracked_rock_reads_as_a_one_shot():
    """Mind Stone's "sacrifice: draw a card" happens once: no engine."""
    feats = card_draw.features(_real("Mind Stone"))
    assert feats["sac_draw"] == 1.0
    assert feats["engine"] == 0.0


# ── Deck context: the fuel a draw engine needs from its deck ─────────────────

_BODIES = [
    "Llanowar Elves",
    "Esper Sentinel",
    "Birds of Paradise",
    "Raise the Alarm",
    "Young Pyromancer",
    "Krenko, Mob Boss",
    "Island",
]
_SPELLS = [
    "Lightning Bolt",
    "Divination",
    "Brainstorm",
    "Opt",
    "Counterspell",
    "Ponder",
    "Preordain",
    "Murder",
    "Island",
]


def _deck(names: list[str]) -> list[dict]:
    return [_real(n) for n in names]


def test_skullclamp_runs_on_x1_creatures_and_token_makers():
    """Skullclamp's engine is an equipped creature dying: a deck of X/1s and
    creature-token makers fuels all of it, a deck of instants none."""
    clamp = _real("Skullclamp")
    assert card_draw.draw_fuel(clamp) == "x1_creatures_or_tokens"
    assert card_draw.deck_fit(clamp, _deck(_BODIES)) == 1.0
    assert card_draw.deck_fit(clamp, _deck(_SPELLS)) == 0.0


def test_archmage_emeritus_runs_on_instants_and_sorceries():
    archmage = _real("Archmage Emeritus")
    assert card_draw.draw_fuel(archmage) == "instants_sorceries"
    assert card_draw.deck_fit(archmage, _deck(_SPELLS)) == 1.0
    # one instant (Raise the Alarm) among six nonland cards: half the third it wants
    assert card_draw.deck_fit(archmage, _deck(_BODIES)) == pytest.approx(0.5)


@pytest.mark.parametrize("name", ["Phyrexian Arena", "Rhystic Study", "Divination"])
def test_a_draw_no_deck_fuels_fits_every_deck(name):
    """An upkeep engine, an opponent-fired engine and a one-shot need nothing
    from the deck."""
    card = _real(name)
    assert card_draw.draw_fuel(card) is None
    assert card_draw.deck_fit(card, _deck(_SPELLS)) == 1.0


def test_the_job_score_in_a_deck_scales_by_its_fit():
    """``job_score`` with a deck: Skullclamp's score in a spells deck is zero;
    Phyrexian Arena's is unchanged."""
    clamp, arena = _real("Skullclamp"), _real("Phyrexian Arena")
    spells = _deck(_SPELLS)
    assert job_score(clamp, "card_draw", spells) == 0.0
    assert job_score(clamp, "card_draw", _deck(_BODIES)) == job_score(
        clamp, "card_draw"
    )
    assert job_score(arena, "card_draw", spells) == job_score(arena, "card_draw")


def test_a_deck_fit_lowers_a_score_by_the_share_it_cannot_fuel():
    """One formula for either sign: a score loses the unfueled share of its own
    size (a positive score 1.0 at fit 0.4 reads 0.4, a negative -1.0 reads -1.6)."""
    from mtg_utils._analysis.job_quality import JobRead

    def read(base, fit):
        return JobRead(
            "card_draw",
            lambda _c: {"x": base},
            {"x": 1.0},
            orders=False,
            fit=lambda _c, _d: fit,
        )

    card = {"name": "Test Engine", "oracle_id": ""}
    assert read(1.0, 0.4).score(card, deck=[card]) == 0.4
    assert read(-1.0, 0.4).score(card, deck=[card]) == -1.6


def test_a_cumulative_upkeep_engine_reads_below_a_lasting_one():
    """Mystic Remora's upkeep climbs every turn until it is sacrificed (CR
    702.24a): a few turns of draws, not an engine. It reads below Rhystic Study,
    the same opponent-fired draw on a permanent that stays, and below Phyrexian
    Arena's one card a turn."""
    remora = job_score(test_card("Mystic Remora"), "card_draw")
    assert remora is not None
    assert remora < job_score(test_card("Rhystic Study"), "card_draw")
    assert remora < job_score(test_card("Phyrexian Arena"), "card_draw")
