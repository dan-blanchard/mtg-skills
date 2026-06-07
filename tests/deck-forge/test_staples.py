"""The general-staples avenue: a curated, hardcoded list of cards that are broadly good
in *most* commander decks (Sol Ring, Arcane Signet, Command Tower, Bojuka Bog, …),
offered as an always-present avenue filtered by the deck's color identity AND format
legality.

The list is curated by FUNCTION, not EDHREC popularity (the project never ranks by
popularity), and every name was verified to resolve against the real Scryfall bulk with
the expected color identity during authoring. Tests here use synthetic records (no real
network / bulk — same constraint as the rest of the suite).
"""

from fastapi.testclient import TestClient

from mtg_utils._deck_forge import engine, staples
from mtg_utils._deck_forge.app import build_app
from mtg_utils._deck_forge.state import DeckSession, ForgeState

SOL_RING = {
    "name": "Sol Ring",
    "type_line": "Artifact",
    "cmc": 1.0,
    "color_identity": [],
    "oracle_text": "{T}: Add {C}{C}.",
    "prices": {"usd": "2.00"},
    "legalities": {
        "commander": "legal",
        "standardbrawl": "not_legal",
        "brawl": "banned",
    },
}
CULTIVATE = {
    "name": "Cultivate",
    "type_line": "Sorcery",
    "cmc": 3.0,
    "color_identity": ["G"],
    "oracle_text": "Search your library for up to two basic land cards.",
    "prices": {"usd": "0.25"},
    "legalities": {
        "commander": "legal",
        "standardbrawl": "not_legal",
        "brawl": "legal",
    },
}
COUNTERSPELL = {
    "name": "Counterspell",
    "type_line": "Instant",
    "cmc": 2.0,
    "color_identity": ["U"],
    "oracle_text": "Counter target spell.",
    "prices": {"usd": "1.00"},
    "legalities": {
        "commander": "legal",
        "standardbrawl": "not_legal",
        "brawl": "legal",
    },
}
INDEX = {c["name"]: c for c in (SOL_RING, CULTIVATE, COUNTERSPELL)}


class TestStaplesData:
    def test_staple_names_includes_named_examples(self):
        names = staples.staple_names()
        for n in ("Sol Ring", "Arcane Signet", "Command Tower", "Bojuka Bog"):
            assert n in names, n

    def test_every_staple_has_a_category(self):
        for name in staples.staple_names():
            assert staples.STAPLES[name] in staples.CATEGORY_ORDER, name


class TestColorIdentityFilter:
    def test_colorless_staple_fits_any_deck(self):
        # Sol Ring (colorless) appears in a mono-white deck.
        out = staples.staples_for("W", INDEX, legality_key="commander")
        assert SOL_RING in out

    def test_colored_staple_only_in_matching_identity(self):
        # Cultivate (G) is offered to a green deck, not to a mono-blue deck.
        green = staples.staples_for("G", INDEX, legality_key="commander")
        blue = staples.staples_for("U", INDEX, legality_key="commander")
        assert CULTIVATE in green
        assert CULTIVATE not in blue
        assert COUNTERSPELL in blue


class TestFormatLegalityFilter:
    def test_sol_ring_excluded_in_brawl(self):
        # Sol Ring is the #1 commander staple but BANNED in Brawl (standardbrawl).
        commander = staples.staples_for("WUBRG", INDEX, legality_key="commander")
        brawl = staples.staples_for("WUBRG", INDEX, legality_key="standardbrawl")
        assert SOL_RING in commander
        assert SOL_RING not in brawl

    def test_legal_staple_kept_for_format(self):
        # Cultivate is legal in Historic Brawl (legality key "brawl").
        out = staples.staples_for("G", INDEX, legality_key="brawl")
        assert CULTIVATE in out


# ── Engine integration: the always-present "Staples / good stuff" avenue ──────
GRUUL_COMMANDER = {
    "name": "Test Gruul Commander",
    "type_line": "Legendary Creature — Beast",
    "cmc": 4.0,
    "color_identity": ["R", "G"],
    "oracle_text": "",
    "legalities": {"commander": "legal"},
}
MONO_W_COMMANDER = {
    "name": "Test White Commander",
    "type_line": "Legendary Creature — Human",
    "cmc": 3.0,
    "color_identity": ["W"],
    "oracle_text": "",
    "legalities": {"commander": "legal"},
}
ENGINE_INDEX = {
    c["name"]: c
    for c in (GRUUL_COMMANDER, MONO_W_COMMANDER, SOL_RING, CULTIVATE, COUNTERSPELL)
}


def _engine_state(commander, fmt="commander"):
    session = DeckSession(fmt)
    session.add(commander, 1, zone="commanders")
    return ForgeState(by_name=ENGINE_INDEX, search_fn=lambda **_: [], session=session)


class TestStaplesAvenue:
    def test_staples_avenue_always_present(self):
        st = _engine_state("Test Gruul Commander")
        avs = engine.avenues(st, engine.hydrate(st).records)
        assert any(a["label"] == "Staples / good stuff" for a in avs)

    def test_staple_pool_scoped_to_color_identity(self):
        gruul = _engine_state("Test Gruul Commander")  # CI = RG
        white = _engine_state("Test White Commander")  # CI = W
        gruul_names = {r["name"] for r in engine.staple_pool(gruul)}
        white_names = {r["name"] for r in engine.staple_pool(white)}
        # Colorless Sol Ring fits both; green Cultivate only the Gruul deck; blue
        # Counterspell neither.
        assert "Sol Ring" in gruul_names
        assert "Sol Ring" in white_names
        assert "Cultivate" in gruul_names
        assert "Cultivate" not in white_names
        assert "Counterspell" not in gruul_names

    def test_staples_avenue_carries_name_serve(self):
        st = _engine_state("Test Gruul Commander")
        avenue = next(
            a
            for a in engine.avenues(st, engine.hydrate(st).records)
            if a["label"] == "Staples / good stuff"
        )
        # The name serve lets ranking credit staples as on-theme for this avenue.
        assert "Sol Ring" in avenue["serve"]["names"]


class TestStaplesExploreEndpoint:
    """POST /api/explore with the staples search resolves the curated list by name
    (NOT via search_fn), scoped to the deck's color identity + format."""

    def _client(self, commander, fmt="commander"):
        session = DeckSession(fmt)
        session.add(commander, 1, zone="commanders")
        state = ForgeState(
            by_name=ENGINE_INDEX,
            # A poisoned search_fn: if the staples path wrongly fell through to it, the
            # test would surface these instead of the real staples.
            search_fn=lambda **_: [{"name": "WRONG PATH", "type_line": "Land"}],
            session=session,
            bulk_available=True,
        )
        return TestClient(build_app(state))

    def test_explore_staples_returns_color_identity_filtered_pool(self):
        client = self._client("Test Gruul Commander")  # CI = RG
        resp = client.post(
            "/api/explore",
            json={"label": "Staples / good stuff", "search": {"staples": True}},
        )
        names = {c["name"] for c in resp.json()["package"]["candidates"]}
        assert "Sol Ring" in names  # colorless
        assert "Cultivate" in names  # green, in identity
        assert "Counterspell" not in names  # blue, out of identity
        assert "WRONG PATH" not in names  # never hits search_fn

    def test_explore_staples_are_credited_on_theme(self):
        client = self._client("Test Gruul Commander")
        resp = client.post(
            "/api/explore",
            json={"label": "Staples / good stuff", "search": {"staples": True}},
        )
        sol = next(
            c for c in resp.json()["package"]["candidates"] if c["name"] == "Sol Ring"
        )
        # Credited by the avenue's name serve, not read as a zero-fit irrelevant hit.
        assert sol["score"]["synergy_fit"] >= 1
