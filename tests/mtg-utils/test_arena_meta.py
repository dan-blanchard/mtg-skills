"""arena-meta (ADR-0059): Untapped's deckstrings, the meta model's reads, the
client's period choice / naming / cache, and the CLI over a saved raw bundle."""

import base64
import json

import pytest
from click.testing import CliRunner

from mtg_utils import arena_meta
from mtg_utils._arena_meta import meta as m
from mtg_utils._arena_meta import untapped
from mtg_utils._arena_meta.deckstring import DeckstringError, decode
from mtg_utils.formats import FORMATS

# --- Deckstrings ---------------------------------------------------------------------

# Real V4 deckstrings from Untapped's decks endpoint (2026-10-05): a Competitive Brawl
# list (period 763), a Bo1 Standard list and an 87-card Bo3 one (period 753).
GOLOS_BRAWL = (
    "AAQB0L8VAQFfiAUEAaADtQGOAcAGrwGMBisUfKcFtzTRBj5iR0ieAsoEG4QVgQ2bIe4B9AW2BqgMHjOtC9k"
    "Nvg3CAsAEihHyBvQL_gPqBdEK_wKOAS0dYHLTDYAO0iDYDZMQhIMOurEE0wGDAaPkA8gB7i7aPsQBBOdChw"
    "YC47YCwgHaTJYCkm2UsAPEBwndP87iAanYCN5YJ-sxyiCcBTfZAcSNA9-CBPlMjrMCkgT7AcfnB5cF0nTL"
    "fMTRAQKHBdlWAAAAAA"
)
STANDARD_BO1 = (
    "AAQAAQ2v0ixh1y2IxgT8kAf23QeSAol5JtY73b4BBIpBB_NU9u8T6voFtJgTgcoE16cGvOIIAu38Au3zPgL-"
    "zDHN-gYBE40FAA"
)
STANDARD_BO3 = (
    "AAQAAQ2DAYkE1gS-zwLZA7jRHgPwqAuJL6vHC6DqCoBEvB8IjgP6AaAHkt8BjcI_0rsCxxLIIAKZzDj63ggN"
    "3ugCE9uwK4-5B64EpfkCtdoIsgIm-AGIugKhA94uAAIGlxC8AdEcoP0B4PMv9awGAAAAAAA"
)


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _section(cards: dict[int, int]) -> bytes:
    """Untapped's grouping: 1-, 2-, 3- and 4-ofs, then explicit quantities."""
    out = b""
    for fixed in (1, 2, 3, 4, None):
        group = sorted(
            (t, q) for t, q in cards.items() if (q == fixed if fixed else q > 4)
        )
        out += _varint(len(group))
        prev = 0
        for title, qty in group:
            if fixed is None:
                out += _varint(qty)
            out += _varint(title - prev)
            prev = title
    return out


def encode(commanders=(), main=None, sideboard=None) -> str:
    """A V4 deckstring, as Untapped's encoder (``nb``) writes one."""
    out = b"\x00" + _varint(4) + _varint(len(commanders))
    prev = 0
    for title in sorted(commanders):
        out += _varint(title - prev) + _varint(1)
        prev = title
    if main:
        out += _varint(1) + _section(main)
    if sideboard:
        out += _varint(2) + _section(sideboard)
    out += _varint(0)
    return base64.urlsafe_b64encode(out).decode().rstrip("=")


def test_a_brawl_deckstring_holds_its_commander_and_99():
    deck = decode(GOLOS_BRAWL)
    assert deck.commanders == (352208,)  # Golos, Tireless Pilgrim's titleId
    assert deck.companions == ()
    assert sum(q for _, q in deck.main) == 99
    assert deck.sideboard == ()


def test_a_60_card_deckstring_groups_copies():
    deck = decode(STANDARD_BO1)
    assert deck.commanders == ()
    assert sum(q for _, q in deck.main) == 60
    # 1- to 4-ofs, plus the basics in the explicit-quantity group.
    assert {q for _, q in deck.main} == {1, 2, 3, 4, 19}


def test_a_bo3_deckstring_has_a_sideboard():
    deck = decode(STANDARD_BO3)
    assert sum(q for _, q in deck.main) == 87  # 13x1 + 8x2 + 2x3 + 13x4
    assert sum(q for _, q in deck.sideboard) > 0


def test_encode_decode_round_trip_with_explicit_quantities():
    ds = encode(commanders=[50], main={7: 1, 9: 4, 12: 17}, sideboard={3: 2})
    deck = decode(ds)
    assert deck.commanders == (50,)
    assert dict(deck.main) == {7: 1, 9: 4, 12: 17}
    assert dict(deck.sideboard) == {3: 2}


@pytest.mark.parametrize("bad", ["", "AQ", "AAM", "!!!"])
def test_bad_deckstrings_raise(bad):
    with pytest.raises(DeckstringError):
        decode(bad)


# --- The model -------------------------------------------------------------------------

# Synthetic titleIds/names (machinery only — no card data is read).
NAMES = {
    1: "Commander Alpha",
    2: "Commander Beta",
    10: "Island",
    11: "Spell One",
    12: "Spell Two",
    13: "Spell Three",
    14: "Spell Four",
    15: "Spell Five",
}


def _arch(gid, tags, stats, color=2):
    return {
        "primary_tag_group_id": gid,
        "primary_tags": tags,
        "color_byte": color,
        "stats": {
            r: {"total_matches": n, "winrate": wr, "avg_seconds": 400}
            for r, (n, wr) in stats.items()
        },
    }


def _deck(ptg, ds, rs):
    return {"ptg": ptg, "ds": ds, "cb": 2, "rs": rs}


TAGS = [
    {"id": 100, "name": "Mono-Blue", "metadata": {"type": 7, "color": 2}},
    {"id": 101, "name": "Commander Alpha", "metadata": {"type": 8}},
    {"id": 102, "name": "Commander Beta", "metadata": {"type": 8}},
]


def _brawl_raw():
    return {
        "event": "Brawl_Ladder",
        "period": {"id": 763, "description": "Set Release", "start": "2026-09-29"},
        "fetched_at": "2026-10-05T12:00:00+00:00",
        "tags": TAGS,
        # Beta wins more but on fewer games, so its Wilson bound is lower; Alpha is
        # the bigger field.
        "archetypes": [
            _arch(1, [101, 100], {"platinum": (900, 55.0), "mythic": (100, 60.0)}),
            _arch(2, [100, 102], {"platinum": (260, 57.0), "gold": (50, 40.0)}),
            _arch(3, [100], {"platinum": (5, 20.0)}),
        ],
        "decks": [
            _deck(
                1,
                encode([1], {10: 30, 11: 1, 12: 1, 13: 1}),
                {"p": [600, 330, 400], "m": [100, 60, 380]},
            ),
            _deck(1, encode([1], {10: 30, 11: 1, 12: 1, 14: 1}), {"p": [300, 165, 1]}),
            _deck(2, encode([2], {10: 30, 15: 1}), {"p": [260, 148, 1]}),
        ],
        "names": {str(k): v for k, v in NAMES.items()},
        "lands": ["Island"],
    }


def _parsed(commanders, cards=()):
    """A parsed deck's zones, names only."""
    return {
        "commanders": [{"name": n, "quantity": 1} for n in commanders],
        "cards": [{"name": n, "quantity": 1} for n in cards],
    }


@pytest.fixture
def snap():
    return untapped.snapshot_from_raw(_brawl_raw())


def test_parse_ranks():
    assert m.parse_ranks("platinum+") == ("platinum", "diamond", "mythic")
    assert m.parse_ranks("gold, platinum") == ("gold", "platinum")
    assert m.parse_ranks("all") == m.LADDER_RANKS
    with pytest.raises(ValueError, match="unknown"):
        m.parse_ranks("wood+")


def test_wilson_lower_bound_shrinks_with_fewer_games():
    assert m.wilson_lower(55, 100) < m.wilson_lower(550, 1000) < 0.55
    assert m.wilson_lower(0, 0) == 0.0


def test_archetype_names_lead_with_the_colour_tag(snap):
    assert snap.archetypes[1].name == "Mono-Blue / Commander Alpha"
    assert snap.archetypes[2].name == "Mono-Blue / Commander Beta"
    assert snap.archetypes[1].colors == "U"
    assert snap.ranked


def test_ranking_orders_by_the_wilson_lower_bound(snap):
    rows = m.ranking(snap, ("platinum", "diamond", "mythic"), min_matches=250)
    # Alpha: 555 of 1000 (bound ~52.4%); Beta: 148 of 260 (bound ~50.9%).
    assert [r["id"] for r in rows] == [1, 2]
    assert rows[0]["matches"] == 1000
    assert rows[0]["mythic"]["matches"] == 100
    assert 3 not in {r["id"] for r in m.ranking(snap, min_matches=250)}


def test_field_shares_sum_the_asked_ranks(snap):
    rows = m.field_shares(snap, ("platinum",), min_share=0.01)
    shares = {r["id"]: r["share"] for r in rows}
    assert shares[1] == pytest.approx(900 / 1165, abs=1e-4)
    assert 3 not in shares  # 5 of 1165 games is under 1%


def test_card_shares_weight_lists_by_matches(snap):
    shares = m.card_shares(snap, 1)
    # Both lists run Spell One; only the 700-match list runs Spell Three.
    assert shares["Spell One"]["share"] == 1.0
    assert shares["Spell Three"]["share"] == pytest.approx(700 / 1000, abs=1e-4)
    assert shares["Island"]["avg_copies"] == 30
    core = m.core(snap, 1, min_share=0.5)
    assert {c["name"] for c in core} == {
        "Island",
        "Spell One",
        "Spell Two",
        "Spell Three",
    }
    assert next(c for c in core if c["name"] == "Island")["land"] is True


def test_a_brawl_deck_matches_by_commander(snap):
    match = m.match_deck(snap, _parsed(["Commander Beta"]))
    assert match.archetype.id == 2
    assert match.by == "commander"
    assert m.match_deck(snap, _parsed(["Nobody"])) is None


def test_a_60_card_deck_matches_by_nonland_overlap(snap):
    match = m.match_deck(
        snap, _parsed([], ["Island", "Spell One", "Spell Two", "Spell Four"])
    )
    assert match.archetype.id == 1
    assert match.by == "overlap"
    assert m.match_deck(snap, _parsed([], ["Island", "Spell Five", "X", "Y"])) is None


def test_resolve_prefers_a_named_archetype(snap):
    named = m.resolve(snap, deck=_parsed(["Commander Alpha"]), archetype="beta")
    assert named.archetype.id == 2
    assert named.by == "named"
    assert m.resolve(snap, archetype="nothing like it") is None
    assert m.resolve(snap) is None


def test_find_archetype_by_part_of_its_name(snap):
    assert m.find_archetype(snap, "commander beta").id == 2
    assert m.find_archetype(snap, "nothing like it") is None


def test_deck_context_reads_shares_and_core(snap):
    ctx = m.deck_context(snap, _parsed(["Commander Alpha"], ["Spell One"]))
    assert ctx.archetype["name"] == "Mono-Blue / Commander Alpha"
    assert ctx.share("spell one") == 1.0  # folded like every name read
    assert ctx.share("Not In Any List") == 0.0
    assert any(c["name"] == "Spell Two" for c in ctx.core)


def test_buildable_puts_what_fits_first(snap):
    cost = {1: {"rare": 3}, 2: {"rare": 1}}

    def fn(deck):
        return cost[deck.archetype]

    rows = m.buildable(snap, fn, wildcards={"rare": 2})
    assert rows[0]["archetype"] == "Mono-Blue / Commander Beta"
    assert rows[0]["fits"] is True
    assert all(not r["fits"] for r in rows[1:])


def test_an_unranked_queue_reads_its_one_bucket():
    raw = _brawl_raw()
    raw["archetypes"] = [_arch(1, [101], {"all": (300, 50.0)})]
    raw["decks"] = [_deck(1, encode([1], {11: 1}), {"a": [300, 150, 1]})]
    snap = untapped.snapshot_from_raw(raw)
    assert not snap.ranked
    assert m.ranking(snap, ("platinum",), min_matches=250)[0]["matches"] == 300
    assert m.card_shares(snap, 1, ("mythic",))["Spell One"]["share"] == 1.0


def test_snapshot_json_round_trip(snap):
    again = m.Snapshot.from_json(json.loads(json.dumps(snap.to_json())))
    assert again == snap


# --- The client's pure parts -------------------------------------------------------------

PERIODS = [
    {
        "id": 751,
        "predecessor_id": 744,
        "event_name": "Brawl_Ladder",
        "start_ts": "2026-09-22",
    },
    {
        "id": 763,
        "predecessor_id": 751,
        "event_name": "Brawl_Ladder",
        "start_ts": "2026-09-29",
    },
    {
        "id": 753,
        "predecessor_id": 734,
        "event_name": "Ladder",
        "start_ts": "2026-09-29",
    },
]


def test_pick_period_reads_the_newest_and_its_predecessor():
    assert untapped.pick_period(PERIODS, "Brawl_Ladder")["id"] == 763
    assert untapped.pick_period(PERIODS, "Brawl_Ladder", previous=True)["id"] == 751
    assert untapped.pick_period(PERIODS, "Ladder", previous=True)["id"] == 734
    assert untapped.pick_period(PERIODS, "Ladder", period_id=999)["id"] == 999
    with pytest.raises(untapped.MetaError):
        untapped.pick_period(PERIODS, "Alchemy_Ladder")


def test_ranked_events_are_the_ladders():
    assert untapped.is_ranked_event("Brawl_Ladder")
    assert untapped.is_ranked_event("Traditional_Explorer_Ladder")
    assert not untapped.is_ranked_event("Play_Brawl_Historic")


def test_resolve_titles_prefers_the_card_pool_name():
    cards = [
        {"grpid": 5, "titleId": 1, "isToken": False},
        {"grpid": 6, "titleId": 2},
        {"grpid": 7, "titleId": 3},
    ]
    loc = [
        {"id": 1, "text": "Arena Name"},
        {"id": 2, "text": "Island"},
        {"id": 3, "text": "A /// B"},
    ]
    by_arena_id = {5: [{"name": "Canonical Name", "type_line": "Land"}]}
    names, lands = untapped.resolve_titles({1, 2, 3}, cards, loc, by_arena_id)
    assert names == {1: "Canonical Name", 2: "Island", 3: "A // B"}
    assert lands == {"Canonical Name", "Island"}


def test_the_cache_round_trips_and_only_a_digital_build_reads_it(tmp_path, monkeypatch):
    from mtg_utils.hydrated_deck import HydratedDeck

    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    snap = untapped.snapshot_from_raw(_brawl_raw())
    path = untapped.meta_dir() / "Brawl_Ladder.current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(snap.to_json()))
    assert untapped.cached_snapshot("Brawl_Ladder") == snap

    deck = {
        "format": "competitive_brawl",
        "commanders": [{"name": "Commander Alpha", "quantity": 1}],
        "cards": [{"name": "Spell One", "quantity": 1}],
    }
    hd = HydratedDeck.from_parsed(deck, by_name={})
    ctx, note = untapped.cached_deck_context(hd, "digital")
    assert ctx.archetype["id"] == 1
    assert "Commander Alpha" in note
    assert untapped.cached_deck_context(hd, "paper") == (None, None)


def test_no_cache_says_how_to_fill_it(tmp_path, monkeypatch):
    from mtg_utils.hydrated_deck import HydratedDeck

    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    hd = HydratedDeck.from_parsed({"format": "historic", "cards": []}, by_name={})
    ctx, note = untapped.cached_deck_context(hd, "digital")
    assert ctx is None
    assert "arena-meta --format historic" in note


def test_the_queue_rule_prefers_bo3_for_a_sideboard():
    standard = FORMATS["standard"]
    assert standard.arena_queues(sideboard=True) == (
        ("Traditional_Ladder", True),
        ("Ladder", False),
    )
    assert standard.arena_queues(sideboard=False)[0] == ("Ladder", False)
    # A Brawl queue has no Bo3; a format with no queue has none.
    assert FORMATS["competitive_brawl"].arena_queues(sideboard=True) == (
        ("Brawl_Ladder", False),
    )
    assert FORMATS["commander"].arena_queues(sideboard=False) == ()


def test_a_cold_cache_falls_back_to_the_other_queue(tmp_path, monkeypatch):
    from mtg_utils.hydrated_deck import HydratedDeck

    monkeypatch.setenv("MTG_SKILLS_CACHE_DIR", str(tmp_path))
    snap = untapped.snapshot_from_raw({**_brawl_raw(), "event": "Ladder"})
    path = untapped.meta_dir() / "Ladder.current.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(snap.to_json()))
    deck = {"format": "standard", "cards": [], "sideboard": [{"name": "X"}]}
    hd = HydratedDeck.from_parsed(deck, by_name={})
    event, bo3, cached = untapped.deck_queue(hd)
    assert (event, bo3) == ("Ladder", False)  # Bo3 uncached → Bo1
    assert cached == snap


def test_every_arena_meta_format_names_an_event():
    queues = {n: f.arena_event_for() for n, f in FORMATS.items() if f.arena_event}
    assert queues["competitive_brawl"] == "Brawl_Ladder"
    assert queues["pioneer"] == "Explorer_Ladder"
    assert FORMATS["standard"].arena_event_for(bo3=True) == "Traditional_Ladder"
    assert FORMATS["competitive_brawl"].arena_event_for(bo3=True) is None
    assert FORMATS["commander"].arena_event_for() is None


# --- The CLI ----------------------------------------------------------------------------


def test_cli_reports_from_a_saved_bundle(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(_brawl_raw()))
    result = CliRunner().invoke(
        arena_meta.main,
        [
            "--format",
            "competitive_brawl",
            "--from-json",
            str(raw),
            "--min-matches",
            "250",
            "--archetype",
            "alpha",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert [r["id"] for r in report["ranking"]] == [1, 2]
    assert report["core"]["archetype"] == "Mono-Blue / Commander Alpha"
    assert report["buildable"] is None


def test_cli_matches_a_deck_and_renders_text(tmp_path):
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(_brawl_raw()))
    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps(
            {
                "format": "competitive_brawl",
                "commanders": [{"name": "Commander Beta", "quantity": 1}],
                "cards": [],
            }
        )
    )
    result = CliRunner().invoke(
        arena_meta.main, ["--deck", str(deck), "--from-json", str(raw)]
    )
    assert result.exit_code == 0, result.output
    assert "Deck matches Mono-Blue / Commander Beta (commander)" in result.output
    assert "## Core of Mono-Blue / Commander Beta" in result.output


def test_cli_refuses_a_format_without_a_queue():
    result = CliRunner().invoke(
        arena_meta.main, ["--format", "standard", "--bo3", "--help"]
    )
    assert result.exit_code == 0
    result = CliRunner().invoke(arena_meta.main, [])
    assert result.exit_code != 0
    assert "--format" in result.output


def test_a_bo3_list_counts_main_and_sideboard_copies_together():
    from mtg_utils._arena_meta.report import wildcard_cost_fn

    deck = m.MetaDeck(1, (), (("Spell One", 2),), (("Spell One", 2),), {})
    rarity = {"Spell One": {"rarity": "rare"}}
    owned = {"spell one": 2}
    assert wildcard_cost_fn(owned, rarity, sideboard=True)(deck) == {
        "mythic": 0,
        "rare": 2,
        "uncommon": 0,
        "common": 0,
    }
    assert wildcard_cost_fn(owned, rarity)(deck)["rare"] == 0


def test_core_cards_say_whether_the_deck_runs_them(snap):
    from mtg_utils._arena_meta.report import build_report

    match = m.resolve(snap, archetype="alpha")
    report = build_report(snap, match=match, held=["spell one"])
    held = {c["name"]: c["in_deck"] for c in report["core"]["cards"]}
    assert held["Spell One"] is True
    assert held["Spell Two"] is False


def test_a_land_no_list_runs_doesnt_count_against_the_overlap(snap):
    lands = ["Odd Land", "Other Land", "Third Land", "Fourth Land"]
    deck = _parsed([], ["Spell One", "Spell Two", *lands])
    assert m.match_deck(snap, deck) is None  # 2 of 6 "nonland" cards: under 40%
    match = m.match_deck(snap, deck, lands=lands)
    assert match.archetype.id == 1
