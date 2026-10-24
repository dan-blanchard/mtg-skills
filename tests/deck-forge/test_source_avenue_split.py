"""ADR-0026: a fused payoff/source spec splits into a payoff avenue (oracle) plus a
Source avenue (the pieces, fetched by card_type) — the static-membership analogue of
the tribal bodies/payoffs/enablers split."""

from mtg_utils._analysis.signal_specs import Serve, pages_by_serve, source_split
from mtg_utils._card_ir import compat_lookup as _ir_lookup
from mtg_utils._deck_forge import engine
from mtg_utils._deck_forge.state import DeckSession, ForgeState
from mtg_utils.testkit import _seed_trees, test_card, test_card_ir

# ADR-0027 (voltron migration — the LAST key): voltron_matters is served only from the
# Card IR now, so the engine must resolve Sram's IR (the structural Aura/Equipment cast
# trigger _detect_voltron_payoff_ir reads) for the voltron avenue to surface. Real
# Scryfall record + real projected IR from the committed snapshot (#25).
SRAM = test_card("Sram, Senior Edificer")
_SRAM_IR = test_card_ir("Sram, Senior Edificer")
_SRAM_OID = SRAM["oracle_id"]
INDEX = {SRAM["name"]: SRAM}


def _state():
    session = DeckSession("commander")
    session.add(SRAM["name"], 1, zone="commanders")
    return ForgeState(by_name=INDEX, search_fn=lambda **_: [], session=session)


def _by_label(avs):
    return {a["label"]: a for a in avs}


def test_voltron_fans_into_payoff_and_source_avenues(monkeypatch):
    # ADR-0039 task #80 step 6: extract_signals is now crosswalk-only —
    # pre-seed the trees memo from the committed snapshot's stored phase
    # records (the concept-tree resolver) alongside the the compat-Card resolver Card IR index.
    _seed_trees("Sram, Senior Edificer")
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: {_SRAM_OID: _SRAM_IR})
    avs = _by_label(engine.avenues(_state(), [SRAM]))
    # The payoff avenue (the _matters lane) stays, now an ident serve: no type fetch
    # and no oracle pattern, so it pages by its serve.
    payoff = avs["Voltron / equipment & auras"]
    assert "card_type" not in payoff["search"]
    assert pages_by_serve(payoff["search"])
    # A distinct Source avenue surfaces the pieces, fetched by an OR of card types.
    source = avs["Auras & Equipment"]
    assert source["search"]["card_type"] == ("aura", "equipment")
    # The source serve credits the types; the payoff serve no longer does.
    assert set(source["serve"]["types"]) == {"aura", "equipment"}
    assert not payoff.get("serve", {}).get("types")


def test_source_split_skips_specs_without_a_payoff_oracle():
    # A pure type-membership serve (no oracle) is already a single source-ish lane;
    # it must not be split (nothing to put in a payoff avenue).
    class _FakeSpec:
        serve = Serve(types=frozenset({"artifact"}))  # no oracle
        search = {"card_type": "Artifact"}
        label = "x"
        avenue = "x"
        extras = ()

    assert source_split(_FakeSpec()) is None


def test_card_type_or_is_backward_compatible_with_string():
    # The card_search change: a tuple OR-matches; a bare string is unchanged.
    from mtg_utils.card_search import _matches_filters

    aura = {"type_line": "Enchantment — Aura", "legalities": {"commander": "legal"}}
    equip = {"type_line": "Artifact — Equipment", "legalities": {"commander": "legal"}}
    base = {
        "allowed_colors": None,
        "oracle_re": None,
        "name_substr": None,
        "cmc_min": None,
        "cmc_max": None,
        "price_min": None,
        "price_max": None,
    }
    assert _matches_filters(aura, type_lower=("aura", "equipment"), **base)
    assert _matches_filters(equip, type_lower=("aura", "equipment"), **base)
    assert _matches_filters(aura, type_lower="aura", **base)
    assert not _matches_filters(aura, type_lower="equipment", **base)


def test_artifacts_payoff_avenue_pages_creature_payoffs_by_its_serve(monkeypatch):
    """ADR-0026 for an ident serve: the Artifacts spec splits into its payoff
    avenue, which Find pages by the avenue's serve (the lanes' idents) — so Sai,
    a creature payoff no Artifact card-type fetch finds, surfaces there — and a
    Source avenue fetching the artifacts by card type (Sol Ring). Neither page
    ANDs a pattern with a card type."""
    from mtg_utils.card_search import pool_search_fn
    from mtg_utils.formats import FORMATS
    from mtg_utils.testkit import test_signals

    names = (
        "Urza, Lord High Artificer",
        "Sai, Master Thopterist",
        "Sol Ring",
        "Snapcaster Mage",
    )
    for name in names:
        test_signals(name)  # seed each real card's trees memo
    irs = {test_card(n)["oracle_id"]: test_card_ir(n) for n in names}
    monkeypatch.setattr(_ir_lookup, "_crosswalk_index", lambda: irs)
    urza = test_card(names[0])
    pool = [test_card(n) for n in names[1:]]
    session = DeckSession("commander")
    session.add(urza["name"], 1, zone="commanders")
    state = ForgeState(
        by_name={urza["name"]: urza},
        search_fn=pool_search_fn(pool, FORMATS["commander"]),
        session=session,
        bulk_available=True,
    )
    avs = {a["id"]: a for a in engine.avenues(state, [urza])}
    payoff = avs["engine:artifacts_matter:you"]
    assert payoff["label"] == "Artifacts"
    assert "card_type" not in payoff["search"]

    def found(avenue_id):
        state.focused_avenue_ids = {avenue_id}
        page = engine.find_candidates(state, engine.FindParams(limit=50))
        return {row["card"]["name"] for row in page.rows}

    # The serve's ``artifacts_matter|you|*`` also counts what the lane emits for
    # an artifact itself (Sol Ring); a card that is neither stays out.
    payoffs = found("engine:artifacts_matter:you")
    assert "Sai, Master Thopterist" in payoffs
    assert "Snapcaster Mage" not in payoffs
    assert found("engine:artifacts_matter:you:src") == {"Sol Ring"}


def test_find_and_tune_page_a_theme_the_same_way():
    """Find (``engine.lane_page``) and the tuner (``swaps._run_search``) page a
    theme through the one ``signal_specs.theme_page``: a theme with no search of
    its own, or only a mana-value band, pages its serve; a card-type search
    overrides it with its own fetch; a pattern with no serve to page by (an
    agent's avenue, a serve that admits nothing) pages by the pattern."""
    from mtg_utils._tuner.swaps import _run_search

    serve = Serve(keywords=frozenset({"defender"}))
    cases = (
        ({}, serve, True),
        ({"cmc_max": 2}, serve, True),
        ({"card_type": "Sliver"}, serve, False),
        ({"oracle": "toughness"}, None, False),
        ({"oracle": "toughness"}, Serve(), False),
    )
    for search, srv, by_serve in cases:
        calls: list[dict] = []
        _run_search(
            lambda **kw: calls.append(kw) or [],  # noqa: B023 — called at once
            {**search, "_serve": srv},
            identity="WG",
            fmt="commander",
            paper_only=True,
            cmc_cap=None,
            limit=10,
        )
        avenue = engine.avenue_with_serve({"search": search}, srv)
        page, find_serve = engine.lane_page(avenue)
        tune = calls[0]
        assert (tune["serve"] is not None) is by_serve, search
        assert (find_serve is not None) is by_serve, search
        assert (tune["oracle"], tune["card_type"]) == (
            page.get("oracle"),
            page.get("card_type"),
        ), search


def test_every_theme_pages_alike_in_find_and_tune():
    """Over every spec ADR-0026 does not split (a split spec's Find avenues are
    its payoffs and its pieces; the tuner pages it whole), the Find avenue the
    engine builds pages exactly the tuner's page: an oracle-only serve the theme
    pages by (Permanents entering) and a mana-cost serve (X-spell sinks) ride on
    the avenue too, not only a structured one."""
    from mtg_utils._analysis.signal_specs import SPECS, theme_page

    for key, spec in SPECS.items():
        if source_split(spec) is not None:
            continue
        tune_page, tune_serve = theme_page(spec.search, spec.serve)
        avenue = engine.avenue_with_serve({"search": dict(spec.search)}, spec.serve)
        find_page, find_serve = engine.lane_page(avenue)
        assert find_page == tune_page, key
        assert (find_serve and find_serve.as_dict()) == (
            tune_serve and tune_serve.as_dict()
        ), key
